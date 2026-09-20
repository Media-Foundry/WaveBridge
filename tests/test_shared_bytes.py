import copy
import unittest
from unittest.mock import patch

from wavebridge.verification.shared_bytes import check


ABI = {"int": {"bits": 32, "signed": True},
       "unsigned long": {"bits": 64, "signed": False},
       "unsigned char": {"bits": 8, "signed": False}}
SIZES = {"float": 4}


def literal(value, type_name="int"):
    return {"kind": "IntegerLiteral", "value": str(value),
            "type": {"qualType": type_name}}


def sizeof(type_name="float"):
    return {"kind": "UnaryExprOrTypeTraitExpr", "name": "sizeof",
            "argType": {"qualType": type_name},
            "type": {"qualType": "unsigned long"}}


def cast(node, type_name="unsigned long", kind="IntegralCast"):
    return {"kind": "ImplicitCastExpr", "castKind": kind,
            "type": {"qualType": type_name}, "inner": [node]}


def product(left=None, right=None):
    return {"kind": "BinaryOperator", "opcode": "*",
            "type": {"qualType": "unsigned long"},
            "inner": [cast(literal(32)) if left is None else left,
                      sizeof() if right is None else right]}


class SharedByteExpressionTests(unittest.TestCase):
    def test_checks_explicit_sizeof_product_without_promoting_source(self):
        expression = product()
        before = copy.deepcopy((expression, ABI, SIZES))
        result = check(expression, ABI, SIZES)
        self.assertEqual("checked", result["status"])
        self.assertEqual(128, result["value_bytes"])
        self.assertTrue(result["checked"])
        self.assertFalse(result["source_program_checked"])
        self.assertFalse(result["deployable"])
        self.assertEqual("float", result["sizeof_evidence"][0]["type"])
        self.assertEqual(before, (expression, ABI, SIZES))

    def test_missing_abi_or_size_remains_unknown(self):
        self.assertEqual("integer_type_missing_from_abi",
                         check(product(), {"int": ABI["int"]}, SIZES)["reason"])
        self.assertEqual("sizeof_type_missing_from_table",
                         check(product(), ABI, {})["reason"])
        bad = dict(SIZES)
        bad["float"] = True
        self.assertEqual("invalid_sizeof_table", check(product(), ABI, bad)["reason"])

    def test_negative_overflow_and_narrowing_remain_unknown(self):
        self.assertEqual("negative_integer_literal_unsupported",
                         check(literal(-1), ABI, SIZES)["reason"])
        overflow = product(cast(literal(128), "unsigned char"),
                           cast(literal(2), "unsigned char"))
        overflow["type"] = {"qualType": "unsigned char"}
        self.assertEqual("integer_expression_overflow", check(overflow, ABI, SIZES)["reason"])
        narrowing = cast(literal(256), "unsigned char")
        self.assertEqual("integer_cast_not_value_preserving",
                         check(narrowing, ABI, SIZES)["reason"])

    def test_call_dynamic_symbol_and_expression_sizeof_are_unsupported(self):
        call = {"kind": "CallExpr", "type": {"qualType": "int"}}
        self.assertEqual("unsupported_expression_kind", check(call, ABI, SIZES)["reason"])
        reference = {"kind": "DeclRefExpr", "type": {"qualType": "int"},
                     "referencedDecl": {"kind": "VarDecl", "id": "count"}}
        self.assertEqual("unsupported_expression_kind", check(reference, ABI, SIZES)["reason"])
        dynamic = sizeof()
        dynamic["inner"] = [reference]
        self.assertEqual("unsupported_unary_or_dynamic_sizeof",
                         check(dynamic, ABI, SIZES)["reason"])

    def test_wrappers_types_and_budgets_are_strict(self):
        wrapped = {"kind": "ParenExpr", "type": {"qualType": "int"},
                   "inner": [literal(7)]}
        self.assertEqual(7, check(wrapped, ABI, SIZES)["value_bytes"])
        wrong = copy.deepcopy(wrapped)
        wrong["type"] = {"qualType": "unsigned long"}
        self.assertEqual("paren_expression_changes_type", check(wrong, ABI, SIZES)["reason"])
        malformed = product()
        malformed["inner"] = None
        self.assertEqual("expression_children_malformed", check(malformed, ABI, SIZES)["reason"])
        malformed = product()
        malformed["inner"].append(None)
        self.assertEqual("expression_children_malformed", check(malformed, ABI, SIZES)["reason"])
        disguised_literal = literal(1)
        disguised_literal["inner"] = [literal(2)]
        self.assertEqual("integer_literal_has_children",
                         check(disguised_literal, ABI, SIZES)["reason"])
        with patch("wavebridge.verification.shared_bytes.MAX_NODES", 2):
            self.assertEqual("expression_node_budget_exceeded",
                             check(product(), ABI, SIZES)["reason"])
        deep = literal(1)
        for _ in range(34):
            deep = {"kind": "ParenExpr", "type": {"qualType": "int"}, "inner": [deep]}
        self.assertEqual("expression_depth_budget_exceeded", check(deep, ABI, SIZES)["reason"])

    def test_excessive_hash_depth_is_unknown_instead_of_crashing(self):
        deep = literal(1)
        for _ in range(20000):
            deep = {"kind": "ParenExpr", "type": {"qualType": "int"}, "inner": [deep]}
        result = check(deep, ABI, SIZES)
        self.assertEqual("unknown", result["status"])
        self.assertEqual("input_hash_unsupported", result["reason"])


if __name__ == "__main__":
    unittest.main()
