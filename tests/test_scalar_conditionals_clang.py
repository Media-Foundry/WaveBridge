"""Real-Clang scalar comparisons and conditional-expression effects."""

from __future__ import annotations

from pathlib import Path
import shutil
import tempfile
import unittest

from wavebridge.frontend.clang_ast import _walk, collect
from wavebridge.verification.scalar_expression_effects import check_no_memory_write


CLANG = shutil.which("clang++")

SOURCE = r"""
float unknown_float();

float lvalue_min(float a, float b) { return a < b ? a : b; }
int lvalue_max(int a, int b) { return a > b ? a : b; }
float arithmetic_branch(float a, float b) { return a <= b ? a + 1.0f : b - 1.0f; }
bool comparison_only(int a, int b) { return a != b; }
bool bool_literal() { return true; }
bool bool_branches(int a, int b, bool left, bool right) {
  return a < b ? left : right;
}
float condition_assignment(float a, float b) { return (a = 1.0f) < b ? a : b; }
float condition_increment(float a, float b) { return a++ < b ? a : b; }
float branch_assignment(float a, float b) { return a < b ? (a = 2.0f) : b; }
float false_branch_assignment(float a, float b) { return a < b ? a : (b = 2.0f); }
float condition_call(float a, float b) { return unknown_float() < b ? a : b; }
float branch_call(float a, float b) { return a < b ? unknown_float() : b; }
float false_branch_call(float a, float b) { return a < b ? a : unknown_float(); }
float reference_branch(bool choose, float& reference, float other) {
  return choose ? reference : other;
}
float local_reference_branch(bool choose, float a, float b) {
  float& alias = a;
  return choose ? alias : b;
}
"""


@unittest.skipUnless(CLANG, "requires real clang++")
class ScalarConditionalsClangTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="wb-scalar-conditionals-")
        cls.source = Path(cls.temporary.name) / "scalar_conditionals.cpp"
        cls.source.write_text(SOURCE)
        report = collect(cls.source, CLANG, ["-std=c++17"], "lvalue_min",
                         full_translation_unit=True)
        if report["status"] != "collected":
            raise AssertionError(report.get("execution"))
        cls.root = report["ast_roots"][0]
        cls.functions = [node for node in _walk(cls.root)
                         if node.get("kind") == "FunctionDecl" and node.get("name")]

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def expression(self, name):
        functions = [node for node in self.functions if node.get("name") == name and
                     any(isinstance(child, dict) and child.get("kind") == "CompoundStmt"
                         for child in node.get("inner", []))]
        self.assertEqual(len(functions), 1, name)
        returns = [node for node in _walk(functions[0]) if node.get("kind") == "ReturnStmt"]
        self.assertEqual(len(returns), 1, name)
        children = returns[0].get("inner", [])
        self.assertEqual(len(children), 1, name)
        return children[0]

    def check(self, name, **kwargs):
        expression = self.expression(name)
        return check_no_memory_write(self.root, expression["id"], **kwargs)

    def test_lvalue_and_prvalue_numeric_conditionals_are_checked(self):
        for name, result_type in (("lvalue_min", "float"), ("lvalue_max", "int"),
                                  ("arithmetic_branch", "float")):
            with self.subTest(name=name):
                expression = self.expression(name)
                result = self.check(name)
                self.assertEqual(result["status"], "checked", result)
                self.assertEqual(result["result_type"], result_type)
                self.assertEqual(result["conclusion"]["subject"], "exact_scalar_expression")
                self.assertEqual(result["conclusion"]["expression_id"], expression["id"])
                self.assertFalse(result["source_program_checked"])
                self.assertFalse(result["deployable"])

    def test_boolean_literals_comparisons_and_branches_are_checked(self):
        for name in ("comparison_only", "bool_literal", "bool_branches"):
            with self.subTest(name=name):
                result = self.check(name)
                self.assertEqual(result["status"], "checked", result)
                self.assertEqual(result["result_type"], "bool")
                self.assertEqual(result["value_semantics"], "not_established")

    def test_writes_and_unknown_calls_in_condition_or_either_branch_are_unknown(self):
        names = ("condition_assignment", "condition_increment", "branch_assignment",
                 "false_branch_assignment", "condition_call", "branch_call",
                 "false_branch_call")
        for name in names:
            with self.subTest(name=name):
                result = self.check(name)
                self.assertEqual(result["status"], "unknown", result)
                self.assertFalse(result["source_program_checked"])
                self.assertFalse(result["deployable"])

    def test_reference_parameter_and_local_alias_reads_remain_unknown(self):
        for name in ("reference_branch", "local_reference_branch"):
            with self.subTest(name=name):
                result = self.check(name)
                self.assertEqual(result["status"], "unknown", result)

    def test_missing_identity_and_budget_fail_closed(self):
        self.assertEqual(check_no_memory_write(self.root, "missing-expression")["status"],
                         "unknown")
        expression_id = self.expression("lvalue_min")["id"]
        for budget in (1, True):
            with self.subTest(max_ast_nodes=budget):
                result = check_no_memory_write(
                    self.root, expression_id, max_ast_nodes=budget)
                self.assertEqual(result["status"], "unknown", result)


if __name__ == "__main__":
    unittest.main()
