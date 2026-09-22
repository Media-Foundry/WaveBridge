"""Real source -> exact selected function body -> conditional integer minimum."""
import copy
from pathlib import Path
import shutil
import unittest

from wavebridge.frontend.clang_ast import collect, _walk
from wavebridge.verification.integer_selection import check


ABI = {
    "int": {"bits": 32, "signed": True},
    "unsigned int": {"bits": 32, "signed": False},
    "long": {"bits": 64, "signed": True},
    "unsigned long": {"bits": 64, "signed": False},
    "unsigned char": {"bits": 8, "signed": False},
}


@unittest.skipUnless(shutil.which("clang++"), "requires real clang++")
class IntegerSelectionClangTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        report = collect(Path(__file__).parent / "fixtures/integer_selection.cpp",
                         shutil.which("clang++"), ["-std=c++17"], "good",
                         full_translation_unit=True, dependency_binding="required")
        if report["status"] != "collected":
            raise AssertionError(report)
        cls.root = report["ast_roots"][0]

    def inputs(self, name="good", bounds=((1, 4096),), root=None):
        root = self.root if root is None else root
        function = next(node for node in _walk(root)
                        if node.get("kind") == "FunctionDecl" and node.get("name") == name)
        expression = next(node for node in _walk(function) if node.get("kind") == "ReturnStmt")["inner"][0]
        # Check the original value expression, not enclosing cleanup semantics.
        # The complete, unmodified root remains the checker input.
        if expression.get("kind") == "ExprWithCleanups":
            expression = expression["inner"][0]
        parameters = [node for node in function["inner"] if node.get("kind") == "ParmVarDecl"]
        domains = [{"declaration_id": parameter["id"], "type": parameter["type"],
                    "lower": bound[0], "upper": bound[1]}
                   for parameter, bound in zip(parameters, bounds)]
        return expression["id"], domains

    def run_check(self, name="good", bounds=((1, 4096),), root=None, **kwargs):
        root = self.root if root is None else root
        expression_id, domains = self.inputs(name, bounds, root)
        return check(root, expression_id, domains, ABI, **kwargs)

    def test_minimum_is_derived_from_body_not_name_or_operand_order(self):
        for name in ("good", "reversed", "wide"):
            with self.subTest(name=name):
                result = self.run_check(name)
                self.assertEqual(result["status"], "checked", result)
                self.assertEqual(result["return_interval"], {"lower": 1, "upper": 1024})
                self.assertFalse(result["source_program_checked"])
                self.assertFalse(result["deployable"])
                expected_order = (1, 0) if name == "reversed" else (0, 1)
                self.assertEqual(result["selection_expression"]["true_parameter"], expected_order[0])
                self.assertEqual(result["selection_expression"]["false_parameter"], expected_order[1])
                self.assertEqual(result["selection_expression"]["tie_parameter"], expected_order[1])

    def test_wrong_selection_or_side_effects_never_check(self):
        for name in ("wrong", "duplicate", "side_effect", "computed", "call_argument", "escapes", "alias"):
            with self.subTest(name=name):
                self.assertNotEqual(self.run_check(name)["status"], "checked")

    def test_value_preserving_conversion_not_modular_narrowing(self):
        self.assertEqual(self.run_check("narrow")["status"], "rejected")
        self.assertEqual(self.run_check("good", ((-8, 40),))["status"], "rejected")
        result = self.run_check("signed_result", ((-8, 40),))
        self.assertEqual(result["status"], "checked", result)
        self.assertEqual(result["return_interval"], {"lower": -8, "upper": 40})

    def test_two_variable_domains_match_small_integer_enumeration(self):
        intervals = [(-3, -1), (-1, 2), (0, 0), (2, 4)]
        for left in intervals:
            for right in intervals:
                result = self.run_check("two_variables", (left, right))
                values = [min(a, b) for a in range(left[0], left[1] + 1)
                          for b in range(right[0], right[1] + 1)]
                self.assertEqual(result["status"], "checked", result)
                self.assertEqual(result["return_interval"], {"lower": min(values), "upper": max(values)})

    def test_missing_misbound_or_unrepresentable_domains_stay_unknown(self):
        expression_id, domains = self.inputs()
        for mutation in ("missing", "id", "type", "reversed", "huge", "bool", "duplicate"):
            changed = copy.deepcopy(domains)
            if mutation == "missing":
                changed = []
            elif mutation == "id":
                changed[0]["declaration_id"] = "absent"
            elif mutation == "type":
                changed[0]["type"] = {"qualType": "unsigned int"}
            elif mutation == "reversed":
                changed[0]["lower"] = 5000
            elif mutation == "huge":
                changed[0]["upper"] = 1 << 40
            elif mutation == "bool":
                changed[0]["lower"] = True
            else:
                changed.append(copy.deepcopy(changed[0]))
            with self.subTest(mutation=mutation):
                self.assertNotEqual(check(self.root, expression_id, changed, ABI)["status"], "checked")

    def test_root_identity_and_budget_are_not_optional(self):
        expression_id, domains = self.inputs()
        for budget in (0, True, 1, 10_000_001):
            self.assertEqual(check(self.root, expression_id, domains, ABI,
                                   max_ast_nodes=budget)["status"], "unknown")
        self.assertEqual(check(self.root, "absent", domains, ABI)["status"], "unknown")
        root = copy.deepcopy(self.root)
        expression = next(node for node in _walk(root) if node.get("id") == expression_id)
        root["inner"].append(copy.deepcopy(expression))
        self.assertEqual(check(root, expression_id, domains, ABI)["status"], "unknown")

    def test_read_only_check_preserves_ast_and_binds_inputs(self):
        root = copy.deepcopy(self.root)
        before = copy.deepcopy(root)
        result = self.run_check(root=root)
        self.assertEqual(result["status"], "checked", result)
        self.assertEqual(root, before)
        self.assertIn("input_sha256", result)
        other = self.run_check(bounds=((2, 4096),))
        self.assertNotEqual(result["input_sha256"], other["input_sha256"])

    def test_selected_declaration_and_reference_identity_cannot_be_substituted(self):
        expression_id, domains = self.inputs()
        for mutation in ("missing", "duplicate", "parameter", "comparison", "temporary",
                         "callee_type", "parameter_duplicate", "conditional_type", "widget"):
            root = copy.deepcopy(self.root)
            expression = next(node for node in _walk(root) if node.get("id") == expression_id)
            call = next(node for node in _walk(expression) if node.get("kind") == "CallExpr")
            callee = call["inner"][0]["inner"][0]
            target = next(node for node in _walk(root)
                          if node.get("id") == callee["referencedDecl"]["id"])
            if mutation == "missing":
                callee["referencedDecl"]["id"] = "absent"
            elif mutation == "duplicate":
                root["inner"].append(copy.deepcopy(target))
            elif mutation == "parameter":
                reference = next(node for node in _walk(target) if node.get("kind") == "DeclRefExpr")
                reference["referencedDecl"]["id"] = "absent"
            elif mutation == "comparison":
                compare = next(node for node in _walk(target) if node.get("kind") == "BinaryOperator")
                compare["opcode"] = ">"
            elif mutation == "temporary":
                temporary = next(node for node in _walk(expression)
                                 if node.get("kind") == "MaterializeTemporaryExpr")
                temporary["storageDuration"] = "static"
            elif mutation == "callee_type":
                callee["referencedDecl"]["type"] = {"qualType": "int ()"}
            elif mutation == "parameter_duplicate":
                parameter = next(node for node in target["inner"] if node.get("kind") == "ParmVarDecl")
                root["inner"].append(copy.deepcopy(parameter))
            elif mutation == "conditional_type":
                conditional = next(node for node in _walk(target) if node.get("kind") == "ConditionalOperator")
                conditional["type"] = {"qualType": "int"}
            else:
                expression["type"] = {"qualType": "Widget"}
            abi = dict(ABI, Widget={"bits": 32, "signed": False})
            with self.subTest(mutation=mutation):
                self.assertNotEqual(check(root, expression_id, domains, abi)["status"], "checked")
