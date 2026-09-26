"""Real-Clang coverage for explicitly enabled static work-branch selection."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import shutil
import tempfile
import unittest

from wavebridge.frontend.clang_ast import _walk, collect
from wavebridge.verification.loop_exit_guards import check_work_preservation


CLANG = shutil.which("clang++")

SOURCE = r"""
constexpr int column_bound = 8;
int unknown_int();

template <bool Enabled>
void template_branch(int limit, int* output) {
  for (int i = 0; i < column_bound; i += 1) {
    if (i >= limit) break;
    if (Enabled) i += 1; else output[i] = i;
  }
}
template void template_branch<false>(int, int*);
template void template_branch<true>(int, int*);

void literal_false(int limit, int* output) {
  for (int i = 0; i < column_bound; i += 1) {
    if (i >= limit) break;
    if (false) i += 1; else output[i] = i;
  }
}
void paren_not(int limit, int* output) {
  for (int i = 0; i < column_bound; i += 1) {
    if (i >= limit) break;
    if (!((false))) output[i] = i; else i += 1;
  }
}
void dynamic_branch(int limit, bool enabled, int* output) {
  for (int i = 0; i < column_bound; i += 1) {
    if (i >= limit) break;
    if (enabled) i += 1; else output[i] = i;
  }
}
void comma_call_false(int limit, int* output) {
  for (int i = 0; i < column_bound; i += 1) {
    if (i >= limit) break;
    if ((unknown_int(), false)) output[i] = i; else output[i] = 0;
  }
}
void init_side_effect(int limit, int* output) {
  for (int i = 0; i < column_bound; i += 1) {
    if (i >= limit) break;
    if (int value = unknown_int(); false) output[i] = value; else output[i] = 0;
  }
}
void unreachable_nested(int limit, int* output) {
  for (int i = 0; i < column_bound; i += 1) {
    if (i >= limit) break;
    if (false) {
      for (int j = 0; j < 2; ++j) output[i] = j;
    } else output[i] = i;
  }
}
void reachable_nested(int limit, int* output) {
  for (int i = 0; i < column_bound; i += 1) {
    if (i >= limit) break;
    if (true) {
      for (int j = 0; j < 2; ++j) output[i] = j;
    } else output[i] = i;
  }
}
"""


@unittest.skipUnless(CLANG, "requires real clang++")
class LoopExitStaticBranchesClangTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="wb-loop-static-branches-")
        cls.source = Path(cls.temporary.name) / "loop_exit_static_branches.cpp"
        cls.source.write_text(SOURCE)
        report = collect(cls.source, CLANG, ["-std=c++17"], "literal_false",
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

    def loop(self, name):
        functions = [node for node in self.functions if node.get("name") == name and
                     any(isinstance(child, dict) and child.get("kind") == "CompoundStmt"
                         for child in node.get("inner", []))]
        self.assertEqual(len(functions), 1, name)
        loops = [node for node in _walk(functions[0]) if node.get("kind") == "ForStmt"]
        self.assertTrue(loops, name)
        return loops[0]

    def template_loop(self, value):
        clang_value = -1 if value is True else 0
        matches = []
        for function in self.functions:
            if function.get("name") != "template_branch":
                continue
            arguments = [child for child in function.get("inner", [])
                         if isinstance(child, dict) and child.get("kind") == "TemplateArgument"]
            loops = [node for node in _walk(function) if node.get("kind") == "ForStmt"]
            if (len(arguments) == 1 and arguments[0].get("value") == clang_value
                    and len(loops) == 1):
                matches.append(loops[0])
        self.assertEqual(len(matches), 1, value)
        return matches[0]

    def check_loop(self, loop, protocols=None, **kwargs):
        return check_work_preservation(
            self.payload, loop["id"], 32, {} if protocols is None else protocols, **kwargs)

    def check(self, name, **kwargs):
        return self.check_loop(self.loop(name), **kwargs)

    def test_template_false_selects_safe_branch_without_changing_default_mode(self):
        false_loop = self.template_loop(False)
        legacy = self.check_loop(false_loop)
        self.assertEqual(legacy["status"], "unknown", legacy)
        self.assertEqual(legacy["schema_version"], "loop-exit-work-preservation/v1")

        selected = self.check_loop(false_loop, use_static_branches=True)
        self.assertEqual(selected["status"], "checked", selected)
        self.assertEqual(selected["schema_version"],
                         "loop-exit-work-preservation-with-static-branches/v1")
        self.assertTrue(selected["static_branch_decisions"])
        self.assertTrue(any(decision.get("condition_value") is False
                            for decision in selected["static_branch_decisions"]))
        self.assertEqual(selected["work_preserves_protected"], "conditional")
        self.assertFalse(selected["full_iteration_domain_established"])
        self.assertFalse(selected["source_program_checked"])
        self.assertFalse(selected["deployable"])

        true_result = self.check_loop(self.template_loop(True), use_static_branches=True)
        self.assertEqual(true_result["status"], "unknown", true_result)

    def test_literal_parentheses_and_not_are_selected_only_in_new_mode(self):
        for name in ("literal_false", "paren_not"):
            with self.subTest(name=name):
                self.assertEqual(self.check(name)["status"], "unknown")
                result = self.check(name, use_static_branches=True)
                self.assertEqual(result["status"], "checked", result)
                self.assertTrue(result["static_branch_decisions"])

    def test_dynamic_and_effectful_conditions_never_skip_a_branch(self):
        for name in ("dynamic_branch", "comma_call_false", "init_side_effect"):
            with self.subTest(name=name):
                result = self.check(name, use_static_branches=True)
                self.assertEqual(result["status"], "unknown", result)
                self.assertNotEqual(result.get("work_preserves_protected"), "conditional")

    def test_only_unreachable_nested_loop_is_skipped(self):
        unreachable = self.check("unreachable_nested", use_static_branches=True)
        self.assertEqual(unreachable["status"], "checked", unreachable)
        self.assertTrue(unreachable["static_branch_decisions"])
        reachable = self.check("reachable_nested", use_static_branches=True)
        self.assertEqual(reachable["status"], "unknown", reachable)

    def test_unused_protocol_and_nonboolean_mode_fail_closed(self):
        protocol = {
            "schema_version": "scalar-leaf-effect-assumption/v1",
            "root_sha256": "unused",
            "call_expression_id": "unused-call",
            "leaf_declaration_id": "unused-leaf",
            "leaf_no_memory_write_assumed": True,
            "valid_call_and_normal_return_assumed": True,
            "evidence_reference": "unused-protocol",
        }
        unused = self.check(
            "literal_false", protocols={"unused-call": deepcopy(protocol)},
            use_static_branches=True)
        self.assertEqual(unused["status"], "unknown", unused)
        self.assertEqual(unused["reason"], "unused_call_protocols")
        for mode in (1, None, "true"):
            with self.subTest(use_static_branches=mode):
                result = self.check("literal_false", use_static_branches=mode)
                self.assertEqual(result["status"], "unknown", result)


if __name__ == "__main__":
    unittest.main()
