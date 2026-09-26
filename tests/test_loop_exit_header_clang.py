"""Real-Clang binding of restricted loop headers to direct exit guards."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import shutil
import tempfile
import unittest

from wavebridge.analysis.column_loops import observe_header
from wavebridge.frontend.clang_ast import _walk, collect
from wavebridge.verification.loop_exit_guards import check_header_connection


CLANG = shutil.which("clang++")

SOURCE = r"""
constexpr int column_bound = 8;
constexpr int other_bound = 9;

void leading(int limit, int* output) {
  for (int i = 0; i < column_bound; i += 1) {
    if (i >= limit) break;
    output[i] = i;
  }
}
void trailing(int limit, int base, int stride, int* output) {
  for (int i = 0; i < column_bound; i += 1) {
    int idx = base + i * stride;
    if (idx < limit) { output[i] = idx; } else break;
  }
}
void renamed(int limit, int* output) {
  for (int position = 0; position < column_bound; position += 1) {
    if (position >= limit) break;
    output[position] = position;
  }
}
void body_writes_induction(int limit, int* output) {
  for (int i = 0; i < column_bound; i += 1) {
    if (i >= limit) break;
    i = 3;
    output[0] = i;
  }
}
void guard_reads_other(int limit, int other, int* output) {
  for (int i = 0; i < column_bound; i += 1) {
    if (other >= limit) break;
    output[i] = other;
  }
}
void less_equal_header(int limit, int* output) {
  for (int i = 0; i <= column_bound; i += 1) {
    if (i >= limit) break;
    output[i] = i;
  }
}
void wrong_increment(int limit, int* output) {
  for (int i = 0; i < column_bound; i = i + 1) {
    if (i >= limit) break;
    output[i] = i;
  }
}
void static_induction(int limit, int* output) {
  for (static int i = 0; i < column_bound; i += 1) {
    if (i >= limit) break;
    output[i] = i;
  }
}
void tls_induction(int limit, int* output) {
  for (thread_local int i = 0; i < column_bound; i += 1) {
    if (i >= limit) break;
    output[i] = i;
  }
}
void float_induction(int limit, int* output) {
  for (float i = 0; i < column_bound; i += 1) {
    if (i >= limit) break;
    output[0] = int(i);
  }
}
void zero_step(int limit, int* output) {
  for (int i = 0; i < column_bound; i += 0) {
    if (i >= limit) break;
    output[i] = i;
  }
}
"""


@unittest.skipUnless(CLANG, "requires real clang++")
class LoopExitHeaderClangTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="wb-loop-exit-header-")
        cls.source = Path(cls.temporary.name) / "loop_exit_header.cpp"
        cls.source.write_text(SOURCE)
        report = collect(cls.source, CLANG, ["-std=c++17"], "leading",
                         full_translation_unit=True)
        if report["status"] != "collected":
            raise AssertionError(report.get("execution"))
        cls.root = report["ast_roots"][0]
        cls.functions = [node for node in _walk(cls.root)
                         if node.get("kind") == "FunctionDecl" and node.get("name")]

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def loop(self, name, root=None):
        tree = self.root if root is None else root
        functions = [node for node in _walk(tree)
                     if node.get("kind") == "FunctionDecl" and node.get("name") == name and
                     any(isinstance(child, dict) and child.get("kind") == "CompoundStmt"
                         for child in node.get("inner", []))]
        self.assertEqual(len(functions), 1, name)
        loops = [node for node in _walk(functions[0]) if node.get("kind") == "ForStmt"]
        self.assertEqual(len(loops), 1, name)
        return loops[0]

    def observe(self, name, root=None, **kwargs):
        tree = self.root if root is None else root
        return observe_header(tree, self.loop(name, tree)["id"], 32, **kwargs)

    def connect(self, name, root=None, **kwargs):
        tree = self.root if root is None else root
        return check_header_connection(tree, self.loop(name, tree)["id"], 32, **kwargs)

    def test_leading_header_and_guard_induction_are_connected(self):
        observed = self.observe("leading")
        self.assertEqual(observed["status"], "observed", observed)
        header = observed["header"]
        self.assertEqual(header["status"], "observed")
        self.assertEqual(header["start"]["kind"], "integer_literal")
        self.assertEqual(header["start"]["value"], 0)
        self.assertEqual(header["step"], 1)
        self.assertEqual(header["body_preserves_induction"], "not_established")

        result = self.connect("leading")
        self.assertEqual(result["status"], "checked", result)
        self.assertEqual(result["scope"], "header_induction_to_exit_guard")
        self.assertEqual(result["header_check"]["status"], "observed")
        self.assertEqual(result["prefix_check"]["status"], "checked")
        induction = header["induction"]["declaration_id"]
        self.assertTrue(result["induction_guard_references"])
        self.assertTrue(all(item["declaration_id"] == induction
                            for item in result["induction_guard_references"]))
        self.assertFalse(result["full_iteration_domain_established"])
        self.assertFalse(result["source_program_checked"])
        self.assertFalse(result["deployable"])

    def test_prefix_dag_and_renamed_induction_connect_by_identity(self):
        trailing = self.connect("trailing")
        self.assertEqual(trailing["status"], "checked", trailing)
        prefix_ids = {item["declaration_id"]
                      for item in trailing["prefix_check"]["prefix_values"]}
        references = trailing["induction_guard_references"]
        self.assertTrue(references)
        self.assertTrue(any(item.get("definition") in prefix_ids
                            for item in references))

        renamed = self.connect("renamed")
        self.assertEqual(renamed["status"], "checked", renamed)
        induction = renamed["header_check"]["header"]["induction"]["declaration_id"]
        self.assertTrue(all(item["declaration_id"] == induction
                            for item in renamed["induction_guard_references"]))

    def test_body_write_does_not_upgrade_header_observation_or_connection(self):
        observed = self.observe("body_writes_induction")
        self.assertEqual(observed["status"], "observed", observed)
        self.assertEqual(observed["header"]["body_preserves_induction"], "not_established")
        connected = self.connect("body_writes_induction")
        self.assertEqual(connected["status"], "checked", connected)
        self.assertFalse(connected["full_iteration_domain_established"])
        self.assertFalse(connected["work_effects_checked"])
        self.assertFalse(connected["cross_iteration_stability_checked"])
        self.assertEqual(connected["header_check"]["header"]["body_preserves_induction"],
                         "not_established")

    def test_unconnected_guard_or_unsupported_headers_stay_unknown(self):
        disconnected = self.connect("guard_reads_other")
        self.assertEqual(disconnected["status"], "unknown", disconnected)
        for name in ("less_equal_header", "wrong_increment", "static_induction",
                     "tls_induction", "float_induction", "zero_step"):
            with self.subTest(name=name):
                observed = self.observe(name)
                self.assertEqual(observed["status"], "unknown", observed)
                self.assertEqual(self.connect(name)["status"], "unknown")

    def test_identity_constant_budget_and_integer_abi_fail_closed(self):
        loop = self.loop("leading")
        self.assertEqual(observe_header(self.root, "missing-loop", 32)["status"], "unknown")
        self.assertEqual(check_header_connection(self.root, "missing-loop", 32)["status"], "unknown")
        for bits in (True, 1, 129):
            with self.subTest(int_bits=bits):
                self.assertEqual(observe_header(self.root, loop["id"], bits)["status"], "unknown")
                self.assertEqual(check_header_connection(self.root, loop["id"], bits)["status"],
                                 "unknown")
        for budget in (1, True):
            with self.subTest(max_ast_nodes=budget):
                self.assertEqual(observe_header(
                    self.root, loop["id"], 32, max_ast_nodes=budget)["status"], "unknown")
                self.assertEqual(check_header_connection(
                    self.root, loop["id"], 32, max_ast_nodes=budget)["status"], "unknown")

        duplicate_loop = deepcopy(self.root)
        duplicate_loop["inner"].append(deepcopy(loop))
        self.assertEqual(observe_header(duplicate_loop, loop["id"], 32)["status"], "unknown")
        self.assertEqual(check_header_connection(
            duplicate_loop, loop["id"], 32)["status"], "unknown")

        duplicate_bound = deepcopy(self.root)
        bounds = [node for node in _walk(duplicate_bound)
                  if node.get("kind") == "VarDecl" and node.get("name") == "column_bound"]
        self.assertEqual(len(bounds), 1)
        duplicate_bound["inner"].append(deepcopy(bounds[0]))
        copied_loop = self.loop("leading", duplicate_bound)
        self.assertEqual(observe_header(
            duplicate_bound, copied_loop["id"], 32)["status"], "unknown")
        self.assertEqual(check_header_connection(
            duplicate_bound, copied_loop["id"], 32)["status"], "unknown")


if __name__ == "__main__":
    unittest.main()
