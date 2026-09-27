"""Real Clang checks for preserving one minimum update to a later statement."""

from pathlib import Path
import shutil
import unittest

from wavebridge.frontend.clang_ast import _walk, collect
from wavebridge.verification.integer_selection import check_minimum_to_statement


CLANG = shutil.which("clang++")
ABI = {"int": {"bits": 32, "signed": True}}


@unittest.skipUnless(CLANG, "requires clang++")
class MinimumHistoryClangTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        report = collect(
            Path(__file__).parent / "fixtures/minimum_history.cpp",
            CLANG,
            ["-std=c++17"],
            "nested_else_history",
            full_translation_unit=True,
            dependency_binding="required",
        )
        if report["status"] != "collected":
            raise AssertionError(report)
        cls.root = report["ast_roots"][0]

    def function(self, name):
        matches = [node for node in _walk(self.root)
                   if node.get("kind") == "FunctionDecl" and node.get("name") == name and
                   any(child.get("kind") == "CompoundStmt"
                       for child in node.get("inner", []))]
        self.assertEqual(len(matches), 1, (name, matches))
        return matches[0]

    def assignment(self, name):
        matches = [node for node in _walk(self.function(name))
                   if node.get("kind") == "BinaryOperator" and node.get("opcode") == "=" and
                   any(child.get("kind") in {"ConditionalOperator", "ImplicitCastExpr", "ParenExpr"}
                       for child in node.get("inner", [])[1:])]
        minimum = [node for node in matches
                   if any(descendant.get("kind") == "ConditionalOperator"
                          for descendant in _walk(node))]
        self.assertEqual(len(minimum), 1, (name, minimum))
        return minimum[0]

    def target_call(self, name):
        calls = []
        for node in _walk(self.function(name)):
            if node.get("kind") != "CallExpr":
                continue
            references = [child.get("referencedDecl", {}) for child in _walk(node)
                          if child.get("kind") == "DeclRefExpr"]
            if any(reference.get("kind") == "FunctionDecl" and
                   reference.get("name") == "observe" for reference in references):
                calls.append(node)
        self.assertEqual(len(calls), 1, (name, calls))
        return calls[0]

    def run_check(self, name, **kwargs):
        return check_minimum_to_statement(
            self.root,
            self.assignment(name)["id"],
            self.target_call(name)["id"],
            ABI,
            **kwargs,
        )

    def later_write(self, name):
        minimum_id = self.assignment(name)["id"]
        writes = [node for node in _walk(self.function(name))
                  if node.get("kind") == "BinaryOperator" and node.get("opcode") == "=" and
                  node.get("id") != minimum_id]
        self.assertEqual(len(writes), 1, (name, writes))
        return writes[0]

    def test_nested_else_and_empty_prefix_preserve_to_first_entry(self):
        for name in ("nested_else_history", "no_intervening_statement",
                     "endpoints_inside_outer_else"):
            with self.subTest(name=name):
                report = self.run_check(name)
                self.assertEqual(report["status"], "checked", report)
                self.assertTrue(report["history_preserved_to_use"])
                self.assertFalse(report["target_statement_checked"])
                self.assertFalse(report["source_program_checked"])
                self.assertFalse(report["deployable"])
                self.assertEqual(report["assignment_id"], self.assignment(name)["id"])
                self.assertEqual(report["statement_id"], self.target_call(name)["id"])

    def test_writes_aliases_and_array_filler_escape_are_unknown(self):
        for name in ("direct_rewrite", "reference_alias", "array_filler_escape"):
            with self.subTest(name=name):
                report = self.run_check(name)
                self.assertEqual(report["status"], "unknown", report)
                self.assertFalse(report["history_preserved_to_use"])

    def test_opaque_call_and_goto_are_unknown(self):
        for name in ("opaque_intermediate_call", "goto_control"):
            with self.subTest(name=name):
                report = self.run_check(name)
                self.assertEqual(report["status"], "unknown", report)

    def test_target_must_be_a_later_direct_statement_in_same_compound(self):
        for name in ("target_in_nested_compound", "target_before_update"):
            with self.subTest(name=name):
                report = self.run_check(name)
                self.assertEqual(report["status"], "unknown", report)
                self.assertFalse(report["target_statement_checked"])

    def test_full_function_audit_conservatively_rejects_aliases_and_later_writes(self):
        for name in ("alias_before_update", "write_after_target"):
            with self.subTest(name=name):
                report = self.run_check(name)
                self.assertEqual(report["status"], "unknown", report)
                self.assertFalse(report["history_preserved_to_use"])

    def test_writing_target_statement_is_not_misreported_as_checked(self):
        name = "writing_target_statement"
        report = check_minimum_to_statement(
            self.root,
            self.assignment(name)["id"],
            self.later_write(name)["id"],
            ABI,
        )
        self.assertEqual(report["status"], "unknown", report)
        self.assertFalse(report["target_statement_checked"])
        self.assertFalse(report["history_preserved_to_use"])

    def test_missing_identity_and_budget_are_unknown(self):
        assignment = self.assignment("no_intervening_statement")
        target = self.target_call("no_intervening_statement")
        for assignment_id, statement_id in (
                ("missing-assignment", target["id"]),
                (assignment["id"], "missing-statement")):
            report = check_minimum_to_statement(
                self.root, assignment_id, statement_id, ABI)
            self.assertEqual(report["status"], "unknown", report)
        for budget in (0, True, 1, 10_000_001):
            with self.subTest(budget=budget):
                report = check_minimum_to_statement(
                    self.root, assignment["id"], target["id"], ABI,
                    max_ast_nodes=budget)
                self.assertEqual(report["status"], "unknown", report)


if __name__ == "__main__":
    unittest.main()
