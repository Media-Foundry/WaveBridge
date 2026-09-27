"""Real argument effects remain independent of constructor value checking."""
import copy
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch

from wavebridge.frontend.clang_ast import collect, _walk
from wavebridge.verification.constructor_argument_effects import check_scalar_evaluations


@unittest.skipUnless(shutil.which("clang++"), "requires real Clang")
class ConstructorScalarEvaluationsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        report = collect(Path(__file__).parent / "fixtures/constructor_scalar_evaluations.cpp",
                         shutil.which("clang++"), ["-std=c++17"], "good",
                         full_translation_unit=True, dependency_binding="required")
        if report["status"] != "collected":
            raise AssertionError(report)
        cls.root = report["ast_roots"][0]

    def expression(self, name, root=None):
        root = self.root if root is None else root
        function = next(n for n in _walk(root) if n.get("kind") == "FunctionDecl" and n.get("name") == name)
        return next(n for n in _walk(function) if n.get("kind") == "CXXConstructExpr")

    def test_independent_effects_do_not_call_value_checker(self):
        expression = self.expression("good")
        with patch("wavebridge.verification.constructor_argument_effects.check_constructor_source",
                   side_effect=AssertionError("must not depend on value domains")):
            report = check_scalar_evaluations(self.root, expression["id"])
        self.assertEqual(report["status"], "checked", report)
        self.assertTrue(report["all_arguments_no_memory_write"])
        self.assertEqual([r["expression_id"] for r in report["argument_effects"]],
                         [n["id"] for n in expression["inner"]])
        for key in ("field_values_established", "constructor_body_checked", "constructor_declaration_binding_checked",
                    "conversion_value_preservation_established", "source_program_checked", "deployable"):
            self.assertFalse(report[key])

    def test_changed_effects_and_unsupported_defaults_are_unknown(self):
        for name in ("bad_write", "bad_call", "default_argument"):
            with self.subTest(name=name):
                report = check_scalar_evaluations(self.root, self.expression(name)["id"])
                self.assertEqual(report["status"], "unknown", report)
                self.assertFalse(report["all_arguments_no_memory_write"])

    def test_identity_budget_and_shape(self):
        expression = self.expression("good")
        for budget in (0, True, 1, 10_000_001):
            self.assertEqual(check_scalar_evaluations(self.root, expression["id"],
                                                     max_ast_nodes=budget)["status"], "unknown")
        root = copy.deepcopy(self.root)
        root["inner"].append(copy.deepcopy(self.expression("good", root)))
        self.assertEqual(check_scalar_evaluations(root, expression["id"])["status"], "unknown")
        for mutation in ("empty", "placeholder"):
            root = copy.deepcopy(self.root)
            target = self.expression("good", root)
            target["inner"] = [] if mutation == "empty" else [{}]
            self.assertEqual(check_scalar_evaluations(root, target["id"])["status"], "unknown")
