import unittest

from tests.test_local_contribution import R, ref, var
from tests.test_normalization_output import normalized_fixture
from wavebridge.analysis.row_prefix import recover


def cast_row(row_id="row", destination="int64_t"):
    return {"kind": "CXXStaticCastExpr", "castKind": "IntegralCast", "range": R,
            "type": {"qualType": destination}, "inner": [ref(row_id)]}


def pointer_update(pointer_id, row_id="row", count_id="bound", destination="int64_t"):
    count = {"kind": "ImplicitCastExpr", "castKind": "IntegralCast", "range": R,
             "type": {"qualType": "int64_t"}, "inner": [ref(count_id, "ParmVarDecl")]}
    product = {"kind": "BinaryOperator", "opcode": "*", "range": R,
               "type": {"qualType": "int64_t"}, "inner": [cast_row(row_id, destination), count]}
    return {"kind": "CompoundAssignOperator", "opcode": "+=", "range": R,
            "inner": [ref(pointer_id, "ParmVarDecl"), product]}


def prefixed_fixture():
    tree = normalized_fixture()
    statements = tree["inner"][-2]["inner"][-1]["inner"]
    prefix = [
        {"kind": "DeclStmt", "range": R, "inner": [var("row", "const int", ref("row_get"))]},
        {"kind": "DeclStmt", "range": R, "inner": [var("start", "const int", ref("start_get"))]},
        pointer_update("input"), pointer_update("output")]
    statements[:0] = prefix
    return tree


class RowPrefixTests(unittest.TestCase):
    def test_recovers_exact_prefix_and_preserves_initializers(self):
        result = recover(prefixed_fixture(), "kernel", 32)
        self.assertEqual("recovered", result["status"])
        self.assertEqual("row", result["row_declaration_id"])
        self.assertEqual("start", result["start_declaration_id"])
        self.assertEqual("input", result["source_parameter_id"])
        self.assertEqual("output", result["output_parameter_id"])
        self.assertEqual("not_established", result["coordinate_semantics"])
        self.assertTrue(result["casts"])
        self.assertFalse(result["checked"])

    def test_wrong_row_count_and_output_are_unknown(self):
        tree = prefixed_fixture()
        statements = tree["inner"][-2]["inner"][-1]["inner"]
        statements[3] = pointer_update("output", row_id="other")
        self.assertEqual("offset_uses_other_row", recover(tree, "kernel", 32)["reason"])
        tree = prefixed_fixture()
        statements = tree["inner"][-2]["inner"][-1]["inner"]
        statements[2] = pointer_update("input", count_id="other")
        self.assertEqual("offset_uses_other_count", recover(tree, "kernel", 32)["reason"])
        tree = prefixed_fixture()
        statements = tree["inner"][-2]["inner"][-1]["inner"]
        statements[3] = pointer_update("input")
        self.assertEqual("prefix_pointer_update_target_mismatch", recover(tree, "kernel", 32)["reason"])

    def test_wrong_start_extra_prefix_and_control_flow_are_unknown(self):
        tree = prefixed_fixture()
        tree["inner"][-2]["inner"][-1]["inner"][1]["inner"][0]["id"] = "other-start"
        self.assertEqual("start_not_local_loop_start", recover(tree, "kernel", 32)["reason"])
        tree = prefixed_fixture()
        tree["inner"][-2]["inner"][-1]["inner"].insert(0, {"kind": "NullStmt"})
        self.assertEqual("prefix_not_exactly_four_statements", recover(tree, "kernel", 32)["reason"])
        tree = prefixed_fixture()
        tree["inner"][-2]["inner"][-1]["inner"][2] = {"kind": "IfStmt", "inner": []}
        self.assertEqual("prefix_pointer_update_not_plus_equal", recover(tree, "kernel", 32)["reason"])

    def test_cast_chain_mismatch_and_non_int64_static_cast_are_unknown(self):
        tree = prefixed_fixture()
        statements = tree["inner"][-2]["inner"][-1]["inner"]
        statements[3] = pointer_update("output", destination="short")
        self.assertEqual("row_not_explicit_int64_static_cast", recover(tree, "kernel", 32)["reason"])
        tree = prefixed_fixture()
        statements = tree["inner"][-2]["inner"][-1]["inner"]
        count_operand = statements[3]["inner"][1]["inner"][1]
        count_operand["castKind"] = "NoOp"
        self.assertEqual("source_output_offset_cast_structure_mismatch", recover(tree, "kernel", 32)["reason"])

    def test_product_outer_cast_must_match_and_integer_width_is_unproven(self):
        tree = prefixed_fixture()
        statements = tree["inner"][-2]["inner"][-1]["inner"]
        product = statements[3]["inner"][1]
        statements[3]["inner"][1] = {
            "kind": "ImplicitCastExpr", "castKind": "IntegralCast", "range": R,
            "type": {"qualType": "long long"}, "inner": [product]}
        result = recover(tree, "kernel", 32)
        self.assertEqual("source_output_offset_cast_structure_mismatch", result["reason"])
        result = recover(prefixed_fixture(), "kernel", 32)
        self.assertEqual("not_established", result["offset_integer_width"])
        self.assertEqual("not_established", result["preconditions"]["offset_integer_abi_width"])


if __name__ == "__main__":
    unittest.main()
