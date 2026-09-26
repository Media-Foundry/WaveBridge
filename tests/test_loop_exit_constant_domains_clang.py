"""Real-Clang source-constant domains for guarded loop iteration bounds."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import shutil
import tempfile
import unittest

from wavebridge.frontend.clang_ast import _walk, collect
from wavebridge.verification.loop_exit_guards import check_iteration_bounds


CLANG = shutil.which("clang++")

SOURCE = r"""
constexpr int loop_bound = 8;

void constant_chain(int* output) {
  const int chain0 = 2;
  const int chain1 = chain0 + 1;
  for (int i = 0; i < loop_bound; i += 1) {
    if (i >= chain1) break;
    output[i] = i;
  }
}
void mutable_lookalike(int* output) {
  int constant_limit = 3;
  for (int i = 0; i < loop_bound; i += 1) {
    if (i >= constant_limit) break;
    output[i] = i;
  }
}
void dynamic_const(int runtime, int* output) {
  const int limit = runtime;
  for (int i = 0; i < loop_bound; i += 1) {
    if (i >= limit) break;
    output[i] = i;
  }
}
void mixed_constant_and_external(int offset, int* output) {
  const int stop0 = 2;
  const int stop = stop0 + 1;
  for (int i = 0; i < loop_bound; i += 1) {
    if (i + offset >= stop) break;
    output[i] = i;
  }
}
"""


@unittest.skipUnless(CLANG, "requires real clang++")
class LoopExitConstantDomainsClangTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="wb-loop-constant-domains-")
        cls.source = Path(cls.temporary.name) / "loop_exit_constant_domains.cpp"
        cls.source.write_text(SOURCE)
        report = collect(cls.source, CLANG, ["-std=c++17"], "constant_chain",
                         full_translation_unit=True)
        if report["status"] != "collected":
            raise AssertionError(report.get("execution"))
        cls.root = report["ast_roots"][0]
        cls.payload = {"ast": cls.root}
        cls.functions = [node for node in _walk(cls.root)
                         if node.get("kind") == "FunctionDecl" and node.get("name")]

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def inputs(self, name, root=None):
        tree = self.root if root is None else root
        functions = [node for node in _walk(tree)
                     if node.get("kind") == "FunctionDecl" and node.get("name") == name and
                     any(isinstance(child, dict) and child.get("kind") == "CompoundStmt"
                         for child in node.get("inner", []))]
        self.assertEqual(len(functions), 1, name)
        loops = [node for node in _walk(functions[0]) if node.get("kind") == "ForStmt"]
        self.assertEqual(len(loops), 1, name)
        declarations = {}
        for node in _walk(functions[0]):
            if node.get("kind") in {"VarDecl", "ParmVarDecl"} and node.get("name"):
                declarations.setdefault(node["name"], []).append(node)
        return loops[0], declarations

    def declaration(self, name, declaration_name, root=None):
        _, declarations = self.inputs(name, root)
        matches = declarations[declaration_name]
        self.assertEqual(len(matches), 1, (name, declaration_name, matches))
        return matches[0]

    def check(self, name, intervals, *, root=None, use_source_constants=True, **kwargs):
        tree = self.root if root is None else root
        loop, _ = self.inputs(name, tree)
        return check_iteration_bounds(
            {"ast": tree}, loop["id"], 32, {}, intervals,
            use_source_constants=use_source_constants, **kwargs)

    def test_constant_chain_is_freshly_derived_without_external_override(self):
        result = self.check("constant_chain", {})
        self.assertEqual(result["status"], "checked", result)
        self.assertEqual(result["schema_version"],
                         "guarded-loop-iteration-bounds-source-constants/v1")
        chain0 = self.declaration("constant_chain", "chain0")["id"]
        chain1 = self.declaration("constant_chain", "chain1")["id"]
        self.assertEqual(result["derived_constant_intervals"][chain1], [3, 3])
        self.assertEqual(result["source_constant_checks"][chain1]["status"], "evaluated")
        self.assertTrue(any(source["declaration_id"] == chain0
                            for source in result["source_constant_checks"][chain1]["sources"]))
        self.assertEqual(result["effective_declaration_intervals"], {chain1: [3, 3]})
        self.assertEqual(result["work_count_bounds"], [3, 3])
        self.assertFalse(result["full_iteration_domain_established"])
        self.assertFalse(result["source_program_checked"])
        self.assertFalse(result["deployable"])

    def test_default_mode_still_requires_constant_as_external_interval(self):
        chain1 = self.declaration("constant_chain", "chain1")["id"]
        missing = self.check("constant_chain", {}, use_source_constants=False)
        self.assertEqual(missing["status"], "unknown", missing)
        supplied = self.check(
            "constant_chain", {chain1: [3, 3]}, use_source_constants=False)
        self.assertEqual(supplied["status"], "checked", supplied)
        self.assertEqual(supplied["schema_version"], "guarded-loop-iteration-bounds/v1")

    def test_mutable_and_dynamic_const_reads_require_explicit_ranges(self):
        for function, declaration in (("mutable_lookalike", "constant_limit"),
                                      ("dynamic_const", "limit")):
            with self.subTest(function=function):
                identifier = self.declaration(function, declaration)["id"]
                missing = self.check(function, {})
                self.assertEqual(missing["status"], "unknown", missing)
                supplied = self.check(function, {identifier: [3, 3]})
                self.assertEqual(supplied["status"], "checked", supplied)
                self.assertNotIn(identifier, supplied["derived_constant_intervals"])

        stop = self.declaration("mixed_constant_and_external", "stop")["id"]
        offset = self.declaration("mixed_constant_and_external", "offset")["id"]
        mixed = self.check("mixed_constant_and_external", {offset: [0, 1]})
        self.assertEqual(mixed["status"], "checked", mixed)
        self.assertEqual(mixed["derived_constant_intervals"][stop], [3, 3])
        self.assertEqual(set(mixed["effective_declaration_intervals"]), {stop, offset})

    def test_constant_override_extra_keys_and_nonboolean_mode_fail_closed(self):
        chain1 = self.declaration("constant_chain", "chain1")["id"]
        for intervals in ({chain1: [3, 3]}, {"unused": [0, 0]}, {chain1: [4, 4]}):
            with self.subTest(intervals=intervals):
                result = self.check("constant_chain", intervals)
                self.assertEqual(result["status"], "unknown", result)
        for mode in (1, None, "true"):
            with self.subTest(use_source_constants=mode):
                result = self.check("constant_chain", {}, use_source_constants=mode)
                self.assertEqual(result["status"], "unknown", result)

    def test_duplicate_constant_or_dependency_identity_cannot_be_overridden(self):
        for duplicated_name in ("chain0", "chain1"):
            with self.subTest(duplicated_name=duplicated_name):
                mutated = deepcopy(self.root)
                declaration = self.declaration("constant_chain", duplicated_name, mutated)
                mutated["inner"].append(deepcopy(declaration))
                result = self.check("constant_chain", {}, root=mutated)
                self.assertEqual(result["status"], "unknown", result)

                # Supplying an interval for the ambiguous target/dependency must
                # not bypass the failed fresh constant proof.
                target = self.declaration("constant_chain", "chain1", mutated)
                result = self.check(
                    "constant_chain", {target["id"]: [3, 3]}, root=mutated)
                self.assertEqual(result["status"], "unknown", result)


if __name__ == "__main__":
    unittest.main()
