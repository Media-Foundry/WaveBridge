"""Real-Clang tests for symbolic converted-argument field forwarding."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import shutil
import unittest

from wavebridge.frontend.clang_ast import _walk, collect
from wavebridge.verification.constructor_argument_effects import check_scalar_field_forwarding


CLANG = shutil.which("clang++")
FIXTURE = Path(__file__).parent / "fixtures" / "constructor_scalar_forwarding.cpp"
ABI = {"int": {"bits": 32, "signed": True},
       "unsigned int": {"bits": 32, "signed": False}}


@unittest.skipUnless(CLANG, "requires real clang++")
class ConstructorScalarForwardingClangTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        report = collect(FIXTURE, CLANG, ["-std=c++17"], "forwarded",
                         full_translation_unit=True, dependency_binding="required")
        if report["status"] != "collected":
            raise AssertionError(report)
        cls.root = report["ast_roots"][0]

    def expression(self, name, root=None):
        root = self.root if root is None else root
        functions = [node for node in _walk(root)
                     if node.get("kind") == "FunctionDecl" and node.get("name") == name and
                     any(child.get("kind") == "CompoundStmt"
                         for child in node.get("inner", []) if isinstance(child, dict))]
        self.assertEqual(len(functions), 1, name)
        expressions = [node for node in _walk(functions[0])
                       if node.get("kind") == "CXXConstructExpr"]
        self.assertEqual(len(expressions), 1, name)
        return expressions[0]

    def check(self, name, root=None, integer_types=ABI, **kwargs):
        root = self.root if root is None else root
        expression = self.expression(name, root)
        return check_scalar_field_forwarding(
            root, expression["id"], integer_types, **kwargs)

    def assert_relation(self, name, expected_positions):
        expression = self.expression(name)
        result = self.check(name)
        self.assertEqual(result["status"], "checked", result)
        relations = result["field_relations"]
        self.assertEqual(len(relations), 3)
        self.assertEqual([item["parameter_position"] for item in relations], expected_positions)
        argument_ids = [child["id"] for child in expression["inner"]]
        for relation in relations:
            self.assertEqual(relation["argument_expression_id"],
                             argument_ids[relation["parameter_position"]])
            self.assertEqual(relation["relation"],
                             "field_equals_converted_argument_at_construction")
            self.assertIsInstance(relation["field_id"], str)
            self.assertIsInstance(relation["parameter_id"], str)
        self.assertEqual(len({item["field_id"] for item in relations}), 3)
        self.assertEqual(len({item["parameter_id"] for item in relations}), 3)
        self.assertFalse(result["field_numeric_domains_established"])
        self.assertFalse(result["argument_conversion_value_preservation_established"])
        self.assertFalse(result["source_program_checked"])
        self.assertFalse(result["deployable"])

    def test_alias_record_and_exact_positional_forwarding_are_checked(self):
        self.assert_relation("forwarded", [0, 1, 2])

    def test_swapped_fields_report_the_actual_parameter_mapping(self):
        self.assert_relation("swapped", [1, 0, 2])

    def test_body_argument_and_field_shapes_remain_unknown(self):
        for name in ("body_write", "parameter_write", "call_argument", "narrow_field",
                     "default_argument"):
            with self.subTest(name=name):
                result = self.check(name)
                self.assertEqual(result["status"], "unknown", result)
                self.assertFalse(result["field_numeric_domains_established"])
                self.assertFalse(result["source_program_checked"])
                self.assertFalse(result["deployable"])

        # Prove the forwarding boundary rejects narrowing even when the
        # constructor-effects checker has a complete ABI and succeeds.
        result = self.check("narrow_field", integer_types={
            **ABI, "unsigned short": {"bits": 16, "signed": False}})
        self.assertEqual(result["constructor_effects"]["status"], "checked", result)
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["reason"], "field_not_bijective_nonconverting_parameter_forward")

    def test_missing_abi_and_duplicate_constructor_identity_fail_closed(self):
        self.assertEqual(self.check("forwarded", integer_types={})["status"], "unknown")

        root = deepcopy(self.root)
        expression = self.expression("forwarded", root)
        root["inner"].append(deepcopy(expression))
        result = check_scalar_field_forwarding(root, expression["id"], ABI)
        self.assertEqual(result["status"], "unknown", result)


if __name__ == "__main__":
    unittest.main()
