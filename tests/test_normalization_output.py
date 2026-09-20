import unittest

from wavebridge.analysis.normalization_output import recover
from tests.test_local_contribution import R, fixture, ref, var


R2 = {"begin": {"offset": 100}, "end": {"offset": 200}}


def normalized_fixture():
    tree = fixture()
    function = tree["inner"][-1]
    function["inner"].insert(1, {"id": "output", "kind": "ParmVarDecl", "type": {"qualType": "float *"}})
    function["inner"].insert(3, {"id": "epsilon", "kind": "ParmVarDecl", "type": {"qualType": "float"}})
    statements = function["inner"][-1]["inner"]
    division = {"kind": "BinaryOperator", "opcode": "/", "inner": [ref("total"), ref("bound", "ParmVarDecl")]}
    addition = {"kind": "BinaryOperator", "opcode": "+", "inner": [division, ref("epsilon", "ParmVarDecl")]}
    scale_call = {"kind": "CallExpr", "range": R, "inner": [ref("scale_fn", "FunctionDecl"), addition]}
    scale = {"kind": "DeclStmt", "range": R, "inner": [var("scale", "const float", scale_call)]}
    induction = var("out_col", "int", ref("start"))
    condition = {"kind": "BinaryOperator", "opcode": "<", "inner": [ref("out_col"), ref("bound", "ParmVarDecl")]}
    increment = {"kind": "CompoundAssignOperator", "opcode": "+=", "inner": [ref("out_col"),
                                                                                 {"kind": "IntegerLiteral", "value": "4", "type": {"qualType": "int"}}]}
    target = {"kind": "ArraySubscriptExpr", "inner": [ref("output", "ParmVarDecl"), ref("out_col")]}
    source = {"kind": "ArraySubscriptExpr", "inner": [ref("input", "ParmVarDecl"), ref("out_col")]}
    product = {"kind": "BinaryOperator", "opcode": "*", "inner": [ref("scale"), source]}
    store = {"kind": "BinaryOperator", "opcode": "=", "inner": [target, product]}
    output_loop = {"kind": "ForStmt", "range": R2, "inner": [
        {"kind": "DeclStmt", "inner": [induction]}, {}, condition, increment, store]}
    statements.extend([scale, output_loop])
    tree["inner"].append({"id": "scale_fn", "kind": "FunctionDecl"})
    return tree


class NormalizationOutputTests(unittest.TestCase):
    def test_recovers_connected_normalization_suffix(self):
        result = recover(normalized_fixture(), "kernel", 32)
        self.assertEqual("recovered", result["status"])
        self.assertEqual("input", result["source_parameter_id"])
        self.assertEqual("output", result["output_parameter_id"])
        self.assertEqual("scale_fn", result["scale_function_id"])
        self.assertEqual("bound", result["count_parameter_id"])
        self.assertFalse(result["checked"])

    def test_wrong_count_and_recurrence_are_unknown(self):
        tree = normalized_fixture()
        scale = tree["inner"][-2]["inner"][-1]["inner"][-2]
        scale["inner"][0]["inner"][0]["inner"][1]["inner"][0]["inner"][1] = ref("other", "ParmVarDecl")
        self.assertIn(recover(tree, "kernel", 32)["reason"], {"count_not_int_parameter", "count_not_local_loop_bound"})
        tree = normalized_fixture()
        output_loop = tree["inner"][-2]["inner"][-1]["inner"][-1]
        output_loop["inner"][3]["inner"][1]["value"] = "8"
        self.assertEqual("local_and_output_recurrence_mismatch", recover(tree, "kernel", 32)["reason"])

    def test_wrong_output_index_input_and_extra_write_are_unknown(self):
        tree = normalized_fixture()
        output_loop = tree["inner"][-2]["inner"][-1]["inner"][-1]
        output_loop["inner"][4]["inner"][0]["inner"][1] = ref("other")
        self.assertEqual("output_index_not_induction", recover(tree, "kernel", 32)["reason"])
        tree = normalized_fixture()
        output_loop = tree["inner"][-2]["inner"][-1]["inner"][-1]
        output_loop["inner"][4]["inner"][1]["inner"][1]["inner"][0] = ref("other_input", "ParmVarDecl")
        self.assertEqual("output_source_not_local_input", recover(tree, "kernel", 32)["reason"])
        tree = normalized_fixture()
        output_loop = tree["inner"][-2]["inner"][-1]["inner"][-1]
        output_loop["inner"][4] = {"kind": "CompoundStmt", "inner": [output_loop["inner"][4],
                                                                         {"kind": "NullStmt"}]}
        self.assertEqual("output_loop_not_single_write", recover(tree, "kernel", 32)["reason"])

    def test_nested_or_side_effect_scale_call_and_trailing_statement_are_unknown(self):
        tree = normalized_fixture()
        scale = tree["inner"][-2]["inner"][-1]["inner"][-2]
        call = scale["inner"][0]["inner"][0]
        scale["inner"][0]["inner"][0] = {"kind": "BinaryOperator", "opcode": ",", "inner": [call, call]}
        self.assertEqual("expected_direct_call", recover(tree, "kernel", 32)["reason"])
        tree = normalized_fixture()
        tree["inner"][-2]["inner"][-1]["inner"].append({"kind": "NullStmt"})
        self.assertEqual("statements_after_output_loop", recover(tree, "kernel", 32)["reason"])


if __name__ == "__main__":
    unittest.main()
