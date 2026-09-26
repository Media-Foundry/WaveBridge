"""Real-Clang conditional value history from initialization to statement entry."""

from __future__ import annotations

from pathlib import Path
import shutil
import tempfile
import unittest

from wavebridge.frontend.clang_ast import _walk, collect
from wavebridge.verification.initializer_domain import check_to_statement


CLANG = shutil.which("clang++")
ABI = {
    "int": {"bits": 32, "signed": True},
    "unsigned int": {"bits": 32, "signed": False},
}

SOURCE = r"""
unsigned int external_leaf();
unsigned int renamed_getter() { return external_leaf(); }
int unknown_int();

int preserved(int* output) {
  int value = renamed_getter();
  int observed = value;
  for (int k = 0; k < 2; ++k) output[k] = value;
  for (int target = 0; target < 1; ++target) value = 99;
  value = 7;
  return observed;
}
int hinted_target(int* output) {
  int value = renamed_getter();
  output[0] = value;
#pragma unroll
  for (int target = 0; target < 1; ++target) output[target] = value;
  return value;
}
int hinted_count_target(int* output) {
  int value = renamed_getter();
  output[0] = value;
#pragma unroll 2
  for (int target = 0; target < 1; ++target) output[target] = value;
  return value;
}
int direct_write(int* output) {
  int value = renamed_getter();
  value = 2;
  for (int target = 0; target < 1; ++target) output[target] = value;
  return value;
}
int alias_write(int* output) {
  int value = renamed_getter();
  int& alias = value;
  alias = 2;
  for (int target = 0; target < 1; ++target) output[target] = value;
  return value;
}
int loop_header_write(int* output) {
  int value = renamed_getter();
  for (int k = (value = 1); k < 2; ++k) output[k] = value;
  for (int target = 0; target < 1; ++target) output[target] = value;
  return value;
}
int unknown_call(int* output) {
  int value = renamed_getter();
  output[0] = unknown_int();
  for (int target = 0; target < 1; ++target) output[target] = value;
  return value;
}
int target_before_declaration(int* output) {
  for (int target = 0; target < 1; ++target) output[target] = 0;
  int value = renamed_getter();
  return value;
}
int declaration_in_other_scope(int* output) {
  { int value = renamed_getter(); output[0] = value; }
  for (int target = 0; target < 1; ++target) output[target] = 0;
  return 0;
}
int static_false_branch(int* output) {
  int value = renamed_getter();
  if (false) value = 2; else output[0] = value;
  for (int target = 0; target < 1; ++target) output[target] = value;
  return value;
}
int goto_history(int* output) {
  int value = renamed_getter();
  goto after;
  output[0] = value;
after:
  ;
  for (int target = 0; target < 1; ++target) output[target] = value;
  return value;
}
"""


@unittest.skipUnless(CLANG, "requires real clang++")
class InitializerHistoryClangTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="wb-initializer-history-")
        cls.source = Path(cls.temporary.name) / "initializer_history.cpp"
        cls.source.write_text(SOURCE)
        report = collect(cls.source, CLANG, ["-std=c++17"], "preserved",
                         full_translation_unit=True)
        if report["status"] != "collected":
            raise AssertionError(report.get("execution"))
        cls.root = report["ast_roots"][0]
        cls.payload = {"ast": cls.root}
        cls.functions = [node for node in _walk(cls.root)
                         if node.get("kind") == "FunctionDecl" and node.get("name")]
        leaves = [node for node in cls.functions if node.get("name") == "external_leaf" and
                  not any(isinstance(child, dict) and child.get("kind") == "CompoundStmt"
                          for child in node.get("inner", []))]
        if len(leaves) != 1:
            raise AssertionError(leaves)
        cls.leaf = leaves[0]

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def function(self, name):
        matches = [node for node in self.functions if node.get("name") == name and
                   any(isinstance(child, dict) and child.get("kind") == "CompoundStmt"
                       for child in node.get("inner", []))]
        self.assertEqual(len(matches), 1, name)
        return matches[0]

    def variable(self, name):
        matches = [node for node in _walk(self.function(name))
                   if node.get("kind") == "VarDecl" and node.get("name") == "value"]
        self.assertEqual(len(matches), 1, name)
        return matches[0]

    def target(self, name):
        function = self.function(name)
        bodies = [child for child in function.get("inner", [])
                  if isinstance(child, dict) and child.get("kind") == "CompoundStmt"]
        self.assertEqual(len(bodies), 1, name)
        direct = bodies[0].get("inner", [])
        attributed = [node for node in direct if node.get("kind") == "AttributedStmt"]
        if name in {"hinted_target", "hinted_count_target"}:
            self.assertEqual(len(attributed), 1)
            loops = [node for node in attributed[0].get("inner", [])
                     if node.get("kind") == "ForStmt"]
            self.assertEqual(len(loops), 1)
            return loops[0]
        loops = [node for node in direct if node.get("kind") == "ForStmt"]
        self.assertTrue(loops, name)
        return loops[-1] if name != "target_before_declaration" else loops[0]

    def contract(self):
        return {
            "schema_version": "getter-leaf-domain/v1",
            "declaration_id": self.leaf["id"],
            "arguments": [],
            "return_type": {"qualType": "unsigned int"},
            "lower": 0,
            "upper": 255,
        }

    def check(self, name, **kwargs):
        return check_to_statement(
            self.payload, self.variable(name)["id"], self.target(name)["id"],
            self.contract(), ABI, {}, **kwargs)

    def test_read_only_and_ordinary_loop_history_reaches_target_entry(self):
        result = self.check("preserved")
        self.assertEqual(result["status"], "checked", result)
        self.assertTrue(result["value_preserved_to_statement"])
        self.assertEqual(result["initializer_check"]["status"], "checked")
        self.assertTrue(result["statement_checks"])
        self.assertFalse(result["source_program_checked"])
        self.assertFalse(result["deployable"])
        self.assertFalse(result["target_body_checked"])
        # The selected target body and statements after it write value, but the
        # conclusion is deliberately only about first entry to that statement.
        self.assertEqual(self.target("preserved")["kind"], "ForStmt")

        hinted = self.check("hinted_target")
        self.assertEqual(hinted["status"], "checked", hinted)
        self.assertEqual(self.target("hinted_target")["kind"], "ForStmt")
        counted = self.check("hinted_count_target")
        self.assertEqual(counted["status"], "unknown", counted)

    def test_direct_alias_header_and_call_effects_break_history(self):
        for name in ("direct_write", "alias_write", "loop_header_write", "unknown_call"):
            with self.subTest(name=name):
                result = self.check(name)
                self.assertEqual(result["status"], "unknown", result)
                self.assertFalse(result.get("value_preserved_to_statement", False))

    def test_target_order_and_scope_are_exact(self):
        for name in ("target_before_declaration", "declaration_in_other_scope"):
            with self.subTest(name=name):
                result = self.check(name)
                self.assertEqual(result["status"], "unknown", result)

    def test_static_false_branch_requires_explicit_mode(self):
        legacy = self.check("static_false_branch")
        self.assertEqual(legacy["status"], "unknown", legacy)
        selected = self.check("static_false_branch", use_static_branches=True)
        self.assertEqual(selected["status"], "checked", selected)
        self.assertTrue(selected["value_preserved_to_statement"])
        self.assertTrue(selected["static_branch_decisions"])

    def test_goto_is_rejected_globally_and_budget_is_bounded(self):
        result = self.check("goto_history")
        self.assertEqual(result["status"], "unknown", result)
        for budget in (1, True):
            with self.subTest(max_ast_nodes=budget):
                limited = self.check("preserved", max_ast_nodes=budget)
                self.assertEqual(limited["status"], "unknown", limited)


if __name__ == "__main__":
    unittest.main()
