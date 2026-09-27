"""Real Clang checks for preserving a conditional quotient to a later statement."""

from pathlib import Path
import shutil
import unittest

from wavebridge.frontend.clang_ast import _walk, collect
from wavebridge.verification.integer_selection import check_quotient_to_statement


CLANG = shutil.which("clang++")
ABI = {"int": {"bits": 32, "signed": True}}


@unittest.skipUnless(CLANG, "requires clang++")
class QuotientHistoryClangTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        report = collect(
            Path(__file__).parent / "fixtures/quotient_history.cpp",
            CLANG,
            ["-std=c++17"],
            "outer_else_quotient_history",
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

    def inputs(self, name):
        function = self.function(name)
        assignments = [node for node in _walk(function)
                       if node.get("kind") == "BinaryOperator" and node.get("opcode") == "=" and
                       any(child.get("kind") == "ConditionalOperator"
                           for child in _walk(node))]
        quotients = [node for node in _walk(function)
                     if node.get("kind") == "VarDecl" and node.get("name") == "quotient"]
        self.assertEqual(len(assignments), 1, (name, assignments))
        self.assertEqual(len(quotients), 1, (name, quotients))
        return assignments[0], quotients[0]

    def target_call(self, name):
        calls = []
        for node in _walk(self.function(name)):
            if node.get("kind") != "CallExpr":
                continue
            references = [child.get("referencedDecl", {}) for child in _walk(node)
                          if child.get("kind") == "DeclRefExpr"]
            if any(reference.get("kind") == "FunctionDecl" and
                   reference.get("name") == "observe_threads" for reference in references):
                calls.append(node)
        self.assertEqual(len(calls), 1, (name, calls))
        return calls[0]

    def run_check(self, name, **kwargs):
        assignment, quotient = self.inputs(name)
        return check_quotient_to_statement(
            self.root,
            assignment["id"],
            quotient["id"],
            self.target_call(name)["id"],
            ABI,
            **kwargs,
        )

    def test_outer_else_and_zero_intervening_history(self):
        for name in ("outer_else_quotient_history", "zero_intervening_quotient"):
            with self.subTest(name=name):
                report = self.run_check(name)
                self.assertEqual(report["status"], "checked", report)
                self.assertTrue(report["quotient_history_preserved_to_use"])
                self.assertFalse(report["target_statement_checked"])
                self.assertFalse(report["division_safety_established"])
                self.assertFalse(report["source_program_checked"])
                self.assertFalse(report["deployable"])
                self.assertEqual(report["preservation_check"]["target_declaration_id"],
                                 self.inputs(name)[1]["id"])
                self.assertEqual(report["unresolved_obligations"],
                                 report["quotient_check"]["unresolved_obligations"])

    def test_quotient_write_alias_and_array_filler_escape_are_unknown(self):
        for name in ("rewrite_quotient", "alias_quotient",
                     "escape_quotient_in_array_filler"):
            with self.subTest(name=name):
                report = self.run_check(name)
                self.assertEqual(report["status"], "unknown", report)
                self.assertFalse(report["quotient_history_preserved_to_use"])

    def test_opaque_call_is_not_treated_as_preservation(self):
        report = self.run_check("opaque_between_quotient_and_use")
        self.assertEqual(report["status"], "unknown", report)
        self.assertFalse(report["target_statement_checked"])

    def test_target_scope_order_and_static_quotient_are_rejected(self):
        for name in ("nested_target_quotient", "target_before_quotient",
                     "static_quotient_history"):
            with self.subTest(name=name):
                report = self.run_check(name)
                self.assertEqual(report["status"], "unknown", report)
                self.assertFalse(report["quotient_history_preserved_to_use"])

    def test_missing_identity_and_budget_are_unknown(self):
        assignment, quotient = self.inputs("zero_intervening_quotient")
        target = self.target_call("zero_intervening_quotient")
        for assignment_id, quotient_id, statement_id in (
                ("missing-assignment", quotient["id"], target["id"]),
                (assignment["id"], "missing-quotient", target["id"]),
                (assignment["id"], quotient["id"], "missing-statement")):
            report = check_quotient_to_statement(
                self.root, assignment_id, quotient_id, statement_id, ABI)
            self.assertEqual(report["status"], "unknown", report)
        for budget in (0, True, 1, 10_000_001):
            with self.subTest(budget=budget):
                report = check_quotient_to_statement(
                    self.root, assignment["id"], quotient["id"], target["id"], ABI,
                    max_ast_nodes=budget)
                self.assertEqual(report["status"], "unknown", report)


if __name__ == "__main__":
    unittest.main()
