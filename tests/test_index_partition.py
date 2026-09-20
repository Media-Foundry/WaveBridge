import copy
import unittest

from wavebridge.verification.index_partition import check


ABI = {
    "int": {"bits": 32, "signed": True},
    "unsigned int": {"bits": 32, "signed": False},
    "unsigned char": {"bits": 8, "signed": False},
}


def expr(kind, ty="int", category="prvalue", **fields):
    return {"kind": kind, "type": {"qualType": ty}, "valueCategory": category, **fields}


def coordinate(ty="int", node_id="coord"):
    return expr("OpaqueValueExpr", ty, "prvalue", id=node_id)


def width_ref(ty="int", declaration_id="width"):
    return expr("DeclRefExpr", ty, "lvalue", id="width-ref",
                referencedDecl={"id": declaration_id, "kind": "VarDecl", "name": "logical_width"})


def cast(node, target, cast_kind="IntegralCast"):
    return expr("ImplicitCastExpr", target, "prvalue", castKind=cast_kind, inner=[node])


def partition(op="/", coord_type="int", binary_type="int", outer=None):
    anchor = coordinate(coord_type)
    left = anchor if coord_type == binary_type else cast(anchor, binary_type)
    right = width_ref(binary_type)
    value = expr("BinaryOperator", binary_type, "prvalue", opcode=op, inner=[left, right])
    return (cast(value, outer) if outer else value), anchor


class IndexPartitionTests(unittest.TestCase):
    def test_equal_output_ranges_do_not_hide_wrong_thread_mapping(self):
        # Both floor(t/16) and t%16 range over 0..15 on 256 threads.
        # Preserve the expected outer division but permute the contributions.
        remainder, anchor = partition("%")
        expression = expr("BinaryOperator", opcode="/", inner=[
            remainder, expr("IntegerLiteral", value="1")])
        result = check(expression, anchor, "width", 16, 256, ABI, operation="/")
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(result["counterexample"], {"thread": 1, "actual": 1, "expected": 0})
    def test_malformed_operator_kind_and_cast_return_unknown(self):
        expression, anchor = partition()
        for operation in ([], {}, None):
            self.assertEqual(check(expression, anchor, "width", 32, 256, ABI,
                                   operation=operation)["status"], "unknown")
        for field in ("kind", "opcode"):
            changed = copy.deepcopy(expression)
            changed[field] = []
            self.assertEqual(check(changed, anchor, "width", 32, 256, ABI,
                                   operation="/")["status"], "unknown")
        changed = cast(expression, "int", cast_kind={})
        self.assertEqual(check(changed, anchor, "width", 32, 256, ABI,
                               operation="/")["status"], "unknown")
    def test_signed_division_and_remainder_are_checked_pointwise(self):
        for operation, expected_range in (("/", {"lower": 0, "upper": 7}),
                                          ("%", {"lower": 0, "upper": 31})):
            expression, anchor = partition(operation)
            result = check(expression, anchor, "width", 32, 256, ABI, operation=operation)
            self.assertEqual(result["status"], "checked", result)
            self.assertEqual(result["output_range"], expected_range)
            self.assertFalse(result["source_program_checked"])
            self.assertFalse(result["deployable"])

    def test_unsigned_operands_and_value_preserving_outer_cast_are_checked(self):
        expression, anchor = partition("%", "unsigned int", "unsigned int", outer="int")
        result = check(expression, anchor, "width", 32, 256, ABI, operation="%")
        self.assertEqual(result["status"], "checked", result)
        self.assertTrue(result["conversion_checks"])

    def test_swapped_operation_and_wrong_width_value_are_rejected(self):
        expression, anchor = partition("%")
        self.assertEqual(check(expression, anchor, "width", 32, 256, ABI,
                               operation="/")["status"], "rejected")
        expression, anchor = partition("/")
        expression["inner"][1] = expr("IntegerLiteral", "int", "prvalue", value="31")
        result = check(expression, anchor, "width", 32, 256, ABI, operation="/")
        self.assertEqual(result["status"], "rejected", result)
        self.assertIsNotNone(result["counterexample"])

    def test_coordinate_identity_missing_anchor_and_width_id_are_unknown(self):
        expression, anchor = partition("/")
        other = copy.deepcopy(anchor); other["id"] = "other-coordinate"
        self.assertEqual(check(expression, other, "width", 32, 256, ABI,
                               operation="/")["status"], "unknown")
        no_anchor = copy.deepcopy(expression)
        no_anchor["inner"][0] = expr("IntegerLiteral", "int", "prvalue", value="0")
        self.assertEqual(check(no_anchor, anchor, "width", 32, 256, ABI,
                               operation="/")["status"], "unknown")
        wrong_width, anchor = partition("/")
        wrong_width["inner"][1]["referencedDecl"]["id"] = "other-width"
        self.assertEqual(check(wrong_width, anchor, "width", 32, 256, ABI,
                               operation="/")["status"], "unknown")

    def test_truncating_cast_is_rejected_and_missing_abi_is_unknown(self):
        expression, anchor = partition("%", outer="unsigned char")
        result = check(expression, anchor, "width", 300, 512, ABI, operation="%")
        self.assertEqual(result["status"], "rejected", result)
        expression, anchor = partition("/")
        self.assertEqual(check(expression, anchor, "width", 32, 256, {},
                               operation="/")["status"], "unknown")

    def test_zero_divisor_and_budgets_are_unknown(self):
        expression, anchor = partition("/")
        zero = copy.deepcopy(expression)
        zero["inner"][1] = expr("IntegerLiteral", "int", "prvalue", value="0")
        self.assertEqual(check(zero, anchor, "width", 32, 256, ABI,
                               operation="/")["status"], "unknown")
        self.assertEqual(check(expression, anchor, "width", 0, 256, ABI,
                               operation="/")["status"], "unknown")
        deep = expression
        for _ in range(33):
            deep = expr("ParenExpr", "int", "prvalue", inner=[deep])
        self.assertEqual(check(deep, anchor, "width", 32, 256, ABI,
                               operation="/")["status"], "unknown")
        many = expression
        for _ in range(128):
            many = expr("ParenExpr", "int", "prvalue", inner=[many])
        self.assertEqual(check(many, anchor, "width", 32, 256, ABI,
                               operation="/")["status"], "unknown")

    def test_coordinate_cannot_be_binary_or_width_reference(self):
        expression, anchor = partition("/")
        self.assertEqual(check(expression, expression, "width", 32, 256, ABI,
                               operation="/")["status"], "unknown")
        reference = width_ref(); reference["id"] = "coordinate"
        self.assertEqual(check(expression, reference, "width", 32, 256, ABI,
                               operation="/")["status"], "unknown")


if __name__ == "__main__":
    unittest.main()
