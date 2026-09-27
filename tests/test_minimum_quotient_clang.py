"""Real Clang coverage for a quotient consuming one preserved minimum update."""

import copy
import json
from pathlib import Path
import shutil
import unittest

from wavebridge.frontend.clang_ast import _walk, collect
from wavebridge.verification.integer_selection import check_minimum_quotient


CLANG = shutil.which("clang++")
ABI = {"int": {"bits": 32, "signed": True}, "short": {"bits": 16, "signed": True}}


@unittest.skipUnless(CLANG, "requires clang++")
class MinimumQuotientClangTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        report = collect(
            Path(__file__).parent / "fixtures/minimum_quotient.cpp",
            CLANG,
            ["-std=c++17"],
            "nested_constant_quotient",
            full_translation_unit=True,
            dependency_binding="required",
        )
        if report["status"] != "collected":
            raise AssertionError(report)
        cls.root = report["ast_roots"][0]

    def function(self, name, root=None):
        root = self.root if root is None else root
        matches = [node for node in _walk(root)
                   if node.get("kind") == "FunctionDecl" and node.get("name") == name and
                   any(child.get("kind") == "CompoundStmt"
                       for child in node.get("inner", []))]
        self.assertEqual(len(matches), 1, (name, matches))
        return matches[0]

    def inputs(self, name, root=None):
        root = self.root if root is None else root
        function = self.function(name, root)
        assignments = [node for node in _walk(function)
                       if node.get("kind") == "BinaryOperator" and node.get("opcode") == "=" and
                       any(descendant.get("kind") == "ConditionalOperator"
                           for descendant in _walk(node))]
        quotients = [node for node in _walk(function)
                     if node.get("kind") == "VarDecl" and node.get("name") == "quotient"]
        self.assertEqual(len(assignments), 1, (name, assignments))
        self.assertEqual(len(quotients), 1, (name, quotients))
        return assignments[0], quotients[0]

    def run_check(self, name, root=None, **kwargs):
        root = self.root if root is None else root
        assignment, quotient = self.inputs(name, root)
        return check_minimum_quotient(
            root, assignment["id"], quotient["id"], ABI, **kwargs)

    def test_nested_constant_numerator_yields_only_conditional_quotient_relation(self):
        report = self.run_check("nested_constant_quotient")
        self.assertEqual(report["status"], "checked", report)
        relation = report["quotient_relation"]
        self.assertEqual(relation["operation"], "truncate_toward_zero_division")
        self.assertEqual(relation["numerator"], 128)
        self.assertEqual(relation["denominator"]["after_target"], "minimum")
        self.assertEqual(
            relation["denominator"]["before_operands"],
            report["history_check"]["state_relation"]["before_operands"],
        )
        self.assertEqual(relation["evaluation_point"],
                         next(node for node in _walk(self.inputs(
                             "nested_constant_quotient")[1])
                              if node.get("kind") == "BinaryOperator" and
                              node.get("opcode") == "/")["id"])
        self.assertFalse(report["division_safety_established"])
        self.assertFalse(report["quotient_history_preserved_to_use"])
        self.assertFalse(report["source_program_checked"])
        self.assertFalse(report["deployable"])
        self.assertEqual(report["unresolved_obligations"], [{
            "property": "denominator_nonzero_at_division",
            "declaration_id": report["denominator_declaration_id"],
            "established": False,
        }])
        self.assertIn("nonzero", json.dumps(report, sort_keys=True).lower())

    def test_operator_order_and_denominator_binding_are_exact(self):
        for name in ("multiplied_instead", "reversed_division", "wrong_denominator"):
            with self.subTest(name=name):
                report = self.run_check(name)
                self.assertEqual(report["status"], "unknown", report)
                self.assertFalse(report["division_safety_established"])

    def test_intervening_write_or_reference_alias_is_unknown(self):
        for name in ("rewritten_between", "aliased_denominator"):
            with self.subTest(name=name):
                report = self.run_check(name)
                self.assertEqual(report["status"], "unknown", report)

    def test_storage_type_and_nonnegative_constant_boundaries(self):
        for name in ("static_quotient", "narrow_quotient", "negative_numerator",
                     "multiple_declarators", "aliased_numerator", "cast_numerator",
                     "boolean_quotient"):
            with self.subTest(name=name):
                report = self.run_check(name)
                self.assertEqual(report["status"], "unknown", report)
                self.assertFalse(report["quotient_history_preserved_to_use"])

    def test_hidden_numerator_reference_child_is_unknown(self):
        root = copy.deepcopy(self.root)
        assignment, quotient = self.inputs("nested_constant_quotient", root)
        division = next(node for node in _walk(quotient)
                        if node.get("kind") == "BinaryOperator" and node.get("opcode") == "/")
        numerator_reference = next(node for node in _walk(division["inner"][0])
                                   if node.get("kind") == "DeclRefExpr")
        numerator_reference["inner"] = [{"kind": "UnknownEffectExpr"}]
        report = check_minimum_quotient(
            root, assignment["id"], quotient["id"], ABI)
        self.assertEqual(report["status"], "unknown", report)

    def test_missing_conflicting_identity_and_budget_are_unknown(self):
        assignment, quotient = self.inputs("nested_constant_quotient")
        for assignment_id, quotient_id in (
                ("missing-assignment", quotient["id"]),
                (assignment["id"], "missing-quotient")):
            report = check_minimum_quotient(
                self.root, assignment_id, quotient_id, ABI)
            self.assertEqual(report["status"], "unknown", report)

        root = copy.deepcopy(self.root)
        duplicated_assignment, duplicated_quotient = self.inputs(
            "nested_constant_quotient", root)
        root.setdefault("inner", []).append(copy.deepcopy(duplicated_quotient))
        report = check_minimum_quotient(
            root, duplicated_assignment["id"], duplicated_quotient["id"], ABI)
        self.assertEqual(report["status"], "unknown", report)

        for budget in (0, True, 1, 10_000_001):
            with self.subTest(budget=budget):
                report = check_minimum_quotient(
                    self.root, assignment["id"], quotient["id"], ABI,
                    max_ast_nodes=budget)
                self.assertEqual(report["status"], "unknown", report)


if __name__ == "__main__":
    unittest.main()
