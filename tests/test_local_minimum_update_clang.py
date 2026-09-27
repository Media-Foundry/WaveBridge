"""Real Clang coverage for one exact mutable integer minimum update."""

import copy
from pathlib import Path
import shutil
import unittest

from wavebridge.frontend.clang_ast import _walk, collect
from wavebridge.verification.integer_selection import check_local_minimum_update


CLANG = shutil.which("clang++")
ABI = {
    "int": {"bits": 32, "signed": True},
    "unsigned int": {"bits": 32, "signed": False},
    "short": {"bits": 16, "signed": True},
}


@unittest.skipUnless(CLANG, "requires clang++")
class LocalMinimumUpdateClangTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        report = collect(
            Path(__file__).parent / "fixtures/local_minimum_update.cpp",
            CLANG,
            ["-std=c++17"],
            "lvalue_minimum",
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

    def assignment(self, name, root=None):
        function = self.function(name, root)
        matches = [node for node in _walk(function)
                   if node.get("kind") == "BinaryOperator" and node.get("opcode") == "="]
        if name == "lambda_owned_assignment":
            self.assertGreaterEqual(len(matches), 1)
            self.assertEqual({node.get("id") for node in matches}, {matches[0].get("id")})
            return matches[0]
        self.assertEqual(len(matches), 1, (name, matches))
        return matches[0]

    def run_check(self, name, root=None, **kwargs):
        root = self.root if root is None else root
        return check_local_minimum_update(
            root, self.assignment(name, root)["id"], ABI, **kwargs)

    def test_lvalue_prvalue_and_local_minimum_updates(self):
        for name in ("lvalue_minimum", "prvalue_minimum", "local_minimum"):
            with self.subTest(name=name):
                report = self.run_check(name)
                self.assertEqual(report["status"], "checked", report)
                self.assertEqual(report["operation"], "minimum")
                self.assertIsInstance(report["target_declaration_id"], str)
                self.assertEqual(len(report["operand_declaration_ids"]), 2)
                self.assertIn(report["target_declaration_id"],
                              report["operand_declaration_ids"])
                self.assertEqual(report["scope"], "selected_assignment_state_transition")
                self.assertFalse(report["history_preserved_to_use"])
                self.assertFalse(report["source_program_checked"])
                self.assertFalse(report["deployable"])

    def test_comparison_or_branch_changes_are_not_minimum(self):
        for name in ("maximum_instead", "swapped_branches"):
            with self.subTest(name=name):
                report = self.run_check(name)
                self.assertNotEqual(report["status"], "checked", report)

    def test_reference_volatile_calls_and_nonplain_target_are_unknown(self):
        for name in ("reference_target", "volatile_target", "call_in_condition",
                     "call_in_branch", "indirect_target"):
            with self.subTest(name=name):
                report = self.run_check(name)
                self.assertEqual(report["status"], "unknown", report)
                self.assertFalse(report["history_preserved_to_use"])

    def test_implicit_operand_conversion_is_not_accepted(self):
        report = self.run_check("converted_operand")
        self.assertEqual(report["status"], "unknown", report)

    def test_target_branch_effect_owner_and_parent_scope_are_exact(self):
        for name in ("target_not_an_operand", "hidden_write_in_branch",
                     "nested_assignment_expression", "lambda_owned_assignment"):
            with self.subTest(name=name):
                report = self.run_check(name)
                self.assertEqual(report["status"], "unknown", report)

    def test_hidden_or_shared_declref_identity_is_unknown(self):
        for mutation in ("hidden_child", "shared_identity"):
            root = copy.deepcopy(self.root)
            assignment = self.assignment("lvalue_minimum", root)
            reference = next(node for node in _walk(assignment)
                             if node.get("kind") == "DeclRefExpr")
            if mutation == "hidden_child":
                reference["inner"] = [{"kind": "UnknownEffectExpr"}]
            else:
                root.setdefault("inner", []).append(copy.deepcopy(reference))
            report = check_local_minimum_update(root, assignment["id"], ABI)
            with self.subTest(mutation=mutation):
                self.assertEqual(report["status"], "unknown", report)

    def test_missing_conflicting_identity_and_budget_are_unknown(self):
        assignment = self.assignment("lvalue_minimum")
        missing = check_local_minimum_update(self.root, "missing-assignment", ABI)
        self.assertEqual(missing["status"], "unknown", missing)

        root = copy.deepcopy(self.root)
        duplicate = self.assignment("lvalue_minimum", root)
        root.setdefault("inner", []).append(copy.deepcopy(duplicate))
        conflict = check_local_minimum_update(root, duplicate["id"], ABI)
        self.assertEqual(conflict["status"], "unknown", conflict)

        for budget in (0, True, 1, 10_000_001):
            with self.subTest(budget=budget):
                report = check_local_minimum_update(
                    self.root, assignment["id"], ABI, max_ast_nodes=budget)
                self.assertEqual(report["status"], "unknown", report)


if __name__ == "__main__":
    unittest.main()
