import copy
import unittest
from unittest.mock import patch

from wavebridge.verification.row_offset import check


ABI = {
    "int": {"bits": 32, "signed": True},
    "long": {"bits": 64, "signed": True},
    "unsigned char": {"bits": 8, "signed": False},
}
ROW = {"lower": 0, "upper": 7}
COUNT = {"lower": 1, "upper": 1023}


def node(kind, ty="long", category="prvalue", **fields):
    return {"kind": kind, "type": {"qualType": ty}, "valueCategory": category, **fields}


def ref(identifier, ty="const int"):
    return node("DeclRefExpr", ty, "lvalue", referencedDecl={
        "id": identifier, "kind": "VarDecl"})


def cast(expression, ty="long", kind="IntegralCast", *, static=False):
    return node("CXXStaticCastExpr" if static else "ImplicitCastExpr", ty, "prvalue",
                castKind=kind, inner=[expression])


def widened(identifier, *, typedef=False):
    loaded = cast(ref(identifier), "int", "LValueToRValue")
    target = "Index" if typedef else "long"
    widened_value = cast(loaded, target, "IntegralCast", static=True)
    if typedef:
        widened_value["type"] = {"qualType": "Index", "desugaredQualType": "long"}
    return widened_value


def product(left_id="row", right_id="count", *, typedef=False):
    expression = node("BinaryOperator", "Index" if typedef else "long", "prvalue",
                      opcode="*", inner=[widened(left_id, typedef=typedef),
                                         widened(right_id, typedef=typedef)])
    if typedef:
        expression["type"] = {"qualType": "Index", "desugaredQualType": "long"}
    return expression


class RowOffsetTests(unittest.TestCase):
    def test_exact_row_times_count_is_checked(self):
        result = check(product(), "row", "count", ROW, COUNT, ABI)
        self.assertEqual(result["status"], "checked", result)
        self.assertEqual(result["symbolic_relation"], {
            "coefficient": 1, "row_power": 1, "count_power": 1})
        self.assertEqual(result["value_interval"], {"lower": 0, "upper": 7161})
        self.assertFalse(result["source_program_checked"])
        self.assertFalse(result["deployable"])

    def test_typedef_uses_desugared_integer_type(self):
        expression = product(typedef=True)
        result = check(expression, "row", "count", ROW, COUNT, ABI)
        self.assertEqual(result["status"], "checked", result)
        self.assertEqual(result["result_type"], "long")

    def test_wrong_id_is_unknown_and_row_squared_is_rejected(self):
        wrong = product("other", "count")
        self.assertEqual(check(wrong, "row", "count", ROW, COUNT, ABI)["status"], "unknown")
        squared = product("row", "row")
        result = check(squared, "row", "count", ROW, ROW, ABI)
        self.assertEqual(result["status"], "rejected", result)
        self.assertEqual(result["symbolic_relation"]["row_power"], 2)

    def test_non_value_preserving_cast_is_rejected(self):
        expression = cast(product(), "unsigned char", "IntegralCast")
        result = check(expression, "row", "count", ROW, COUNT, ABI)
        self.assertEqual(result["status"], "rejected", result)
        self.assertEqual(result["reason"], "integer_cast_not_value_preserving")

    def test_multiplication_overflow_is_unknown(self):
        expression = node("BinaryOperator", "int", "prvalue", opcode="*", inner=[
            cast(ref("row"), "int", "LValueToRValue"),
            cast(ref("count"), "int", "LValueToRValue")])
        huge = {"lower": 0, "upper": 1 << 30}
        result = check(expression, "row", "count", huge, {"lower": 2, "upper": 3}, ABI)
        self.assertEqual(result["status"], "unknown", result)
        self.assertEqual(result["reason"], "multiplication_may_overflow")

    def test_unknown_abi_unsupported_node_and_invalid_intervals(self):
        self.assertEqual(check(product(), "row", "count", ROW, COUNT, {})["status"], "unknown")
        unsupported = node("BinaryOperator", "long", "prvalue", opcode="+", inner=[
            widened("row"), widened("count")])
        self.assertEqual(check(unsupported, "row", "count", ROW, COUNT, ABI)["status"], "unknown")
        for interval in ({"lower": True, "upper": 7}, {"lower": -1, "upper": 7},
                         {"lower": 8, "upper": 7}):
            with self.subTest(interval=interval):
                self.assertEqual(check(product(), "row", "count", interval, COUNT, ABI)["status"],
                                 "unknown")

    def test_literal_coefficient_and_symbolic_identity(self):
        one = node("IntegerLiteral", "long", "prvalue", value="1")
        expression = node("BinaryOperator", "long", "prvalue", opcode="*",
                          inner=[one, product()])
        self.assertEqual(check(expression, "row", "count", ROW, COUNT, ABI)["status"], "checked")
        two = copy.deepcopy(expression); two["inner"][0]["value"] = "2"
        self.assertEqual(check(two, "row", "count", ROW, COUNT, ABI)["status"], "rejected")

    def test_depth_and_node_budgets_are_unknown(self):
        expression = product()
        for _ in range(33):
            expression = node("ParenExpr", "long", "prvalue", inner=[expression])
        self.assertEqual(check(expression, "row", "count", ROW, COUNT, ABI)["status"], "unknown")
        with patch("wavebridge.verification.row_offset.MAX_NODES", 2):
            self.assertEqual(check(product(), "row", "count", ROW, COUNT, ABI)["status"], "unknown")

    def test_ids_must_be_distinct_and_hashes_bind_inputs(self):
        self.assertEqual(check(product(), "same", "same", ROW, COUNT, ABI)["status"], "unknown")
        result = check(product(), "row", "count", ROW, COUNT, ABI)
        self.assertEqual(set(result["input_sha256"]), {
            "expression", "row_declaration_id", "count_declaration_id",
            "row_interval", "count_interval", "integer_types"})


if __name__ == "__main__":
    unittest.main()
