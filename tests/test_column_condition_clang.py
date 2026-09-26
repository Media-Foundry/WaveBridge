"""Real-Clang body-effect checks for conditional expressions.

These tests establish only the supported body's non-modification property.
They do not evaluate a condition, delete a dead branch, prove termination, or
discharge the existing source-validity and no-alias premises.
"""

from __future__ import annotations

from pathlib import Path
import shutil
import tempfile
import unittest

from wavebridge.analysis.column_loops import recover
from wavebridge.frontend.clang_ast import _walk, collect


CLANG = shutil.which("clang++")

SOURCE = r"""
extern int opaque();

void value_condition(int n, int* output, int flag, int left, int right) {
  for (int i = 0; i < n; i += 1) output[i] = flag ? left : right;
}
void condition_writes_induction(int n, int* output, int left, int right) {
  for (int i = 0; i < n; i += 1) output[i] = (i = 1) ? left : right;
}
void true_branch_writes_induction(int n, int* output, int flag, int right) {
  for (int i = 0; i < n; i += 1) output[i] = flag ? (i = 2) : right;
}
void false_branch_writes_induction(int n, int* output, int flag, int left) {
  for (int i = 0; i < n; i += 1) output[i] = flag ? left : (i = 2);
}
void true_branch_writes_bound(int n, int* output, int flag, int right) {
  for (int i = 0; i < n; i += 1) output[i] = flag ? (n = 2) : right;
}
void false_branch_writes_bound(int n, int* output, int flag, int left) {
  for (int i = 0; i < n; i += 1) output[i] = flag ? left : (n = 2);
}
void conditional_lvalue_target(int n, int* output, int flag, int other) {
  for (int i = 0; i < n; i += 1) (flag ? i : other) = 3;
}
void call_in_true_branch(int n, int* output, int flag) {
  for (int i = 0; i < n; i += 1) output[i] = flag ? opaque() : 0;
}
void call_in_false_branch(int n, int* output, int flag) {
  for (int i = 0; i < n; i += 1) output[i] = flag ? 0 : opaque();
}
void false_literal_still_checks_true_branch(int n, int* output) {
  for (int i = 0; i < n; i += 1) output[i] = false ? opaque() : 0;
}
void true_literal_still_checks_false_branch(int n, int* output) {
  for (int i = 0; i < n; i += 1) output[i] = true ? 0 : opaque();
}
"""


@unittest.skipUnless(CLANG, "requires real clang++")
class ColumnConditionClangTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.source = Path(cls.temporary.name) / "column_condition.cpp"
        cls.source.write_text(SOURCE)
        report = collect(cls.source, CLANG, ["-std=c++17"], "value_condition",
                         full_translation_unit=True)
        if report["status"] != "collected":
            raise AssertionError(report.get("execution"))
        cls.root = report["ast_roots"][0]
        cls.functions = {node["name"]: node for node in _walk(cls.root)
                         if node.get("kind") == "FunctionDecl" and node.get("name")}

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def recover(self, name):
        return recover(self.root, self.functions[name]["id"], 32)

    def test_value_conditional_preserves_induction_and_bound(self):
        result = self.recover("value_condition")
        self.assertEqual(result["status"], "recovered", result)
        loop = result["loops"][0]
        self.assertTrue(loop["header_recurrence_observed"])
        self.assertEqual(loop["body_preserves_induction"],
                         "established_in_supported_effect_subset")
        self.assertEqual(loop["body_preserves_bound"],
                         "established_in_supported_effect_subset")
        self.assertFalse(result["checked"])
        self.assertFalse(result["deployable"])

    def test_condition_and_either_value_branch_cannot_write_protected_storage(self):
        expected = {
            "condition_writes_induction": "protected_variable_may_be_modified",
            "true_branch_writes_induction": "protected_variable_may_be_modified",
            "false_branch_writes_induction": "protected_variable_may_be_modified",
            "true_branch_writes_bound": "protected_variable_may_be_modified",
            "false_branch_writes_bound": "protected_variable_may_be_modified",
            "conditional_lvalue_target": "unsupported_storage_target",
        }
        for name, reason in expected.items():
            with self.subTest(name=name):
                result = self.recover(name)
                self.assertEqual(result["status"], "unknown", result)
                loop = result["loops"][0]
                self.assertTrue(loop["header_recurrence_observed"])
                self.assertEqual(loop["reason"], reason)
                self.assertEqual(loop["body_preserves_induction"], "not_established")

    def test_calls_in_every_branch_are_checked_without_dead_branch_deletion(self):
        names = (
            "call_in_true_branch", "call_in_false_branch",
            "false_literal_still_checks_true_branch",
            "true_literal_still_checks_false_branch",
        )
        for name in names:
            with self.subTest(name=name):
                result = self.recover(name)
                self.assertEqual(result["status"], "unknown", result)
                loop = result["loops"][0]
                self.assertTrue(loop["header_recurrence_observed"])
                self.assertEqual(loop["reason"], "call_in_body")
                self.assertEqual(loop["body_preserves_bound"], "not_established")


if __name__ == "__main__":
    unittest.main()
