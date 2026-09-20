import unittest

from wavebridge.analysis.block_reduction import recover


R = {"begin": {"offset": 1}, "end": {"offset": 2}}


def ref(identifier, kind):
    return {"kind": "DeclRefExpr", "referencedDecl": {"id": identifier, "kind": kind}, "range": R}


def integer(value):
    return {"kind": "IntegerLiteral", "type": {"qualType": "int"}, "value": str(value), "range": R}


def constant(identifier, value):
    return {"id": identifier, "kind": "VarDecl", "type": {"qualType": "const int"},
            "constexpr": True, "init": "c", "inner": [integer(value)], "range": R}


def call(target, args):
    return {"kind": "CallExpr", "range": R, "inner": [ref(target, "FunctionDecl"), *args]}


def assignment(lhs, rhs):
    return {"kind": "BinaryOperator", "opcode": "=", "range": R, "inner": [lhs, rhs]}


def fixture(width=32, block=256):
    value = {"id": "value", "kind": "ParmVarDecl", "type": {"qualType": "float"}, "range": R}
    shared = {"id": "shared", "kind": "ParmVarDecl", "type": {"qualType": "float *"}, "range": R}
    coordinate1 = {"kind": "OpaqueValueExpr", "id": "coord1", "range": R}
    coordinate2 = {"kind": "OpaqueValueExpr", "id": "coord2", "range": R}
    group = {"id": "group", "kind": "VarDecl", "type": {"qualType": "const int"}, "init": "c",
             "range": R, "inner": [{"kind": "BinaryOperator", "opcode": "/", "range": R,
                                     "inner": [coordinate1, ref("width", "VarDecl")]}]}
    lane = {"id": "lane", "kind": "VarDecl", "type": {"qualType": "const int"}, "init": "c",
            "range": R, "inner": [{"kind": "BinaryOperator", "opcode": "%", "range": R,
                                    "inner": [coordinate2, ref("width", "VarDecl")]}]}
    subscript_group = {"kind": "ArraySubscriptExpr", "inner": [ref("shared", "ParmVarDecl"), ref("group", "VarDecl")]}
    writer = {"kind": "IfStmt", "range": R, "inner": [
        {"kind": "BinaryOperator", "opcode": "==", "inner": [ref("lane", "VarDecl"), integer(0)]},
        assignment(subscript_group, ref("value", "ParmVarDecl"))]}
    group_count = {"kind": "BinaryOperator", "opcode": "/", "inner": [
        ref("block", "VarDecl"), ref("width", "VarDecl")]}
    predicate = {"kind": "BinaryOperator", "opcode": "<", "inner": [ref("lane", "VarDecl"), group_count]}
    shared_lane = {"kind": "ArraySubscriptExpr", "inner": [ref("shared", "ParmVarDecl"), ref("lane", "VarDecl")]}
    select = {"kind": "ConditionalOperator", "inner": [predicate, shared_lane,
              {"kind": "FloatingLiteral", "value": "0.0", "range": R}]}
    statements = [
        assignment(ref("value", "ParmVarDecl"), call("reduce", [ref("value", "ParmVarDecl")])),
        {"kind": "DeclStmt", "inner": [group]}, {"kind": "DeclStmt", "inner": [lane]}, writer,
        call("barrier", []), assignment(ref("value", "ParmVarDecl"), select),
        {"kind": "ReturnStmt", "inner": [call("reduce", [ref("value", "ParmVarDecl")])]}]
    function = {"id": "helper", "kind": "FunctionDecl", "range": R,
                "inner": [value, shared, {"kind": "CompoundStmt", "range": R, "inner": statements}]}
    return {"kind": "TranslationUnitDecl", "inner": [constant("width", width), constant("block", block),
            {"id": "reduce", "kind": "FunctionDecl"}, {"id": "barrier", "kind": "FunctionDecl"}, function]}


class BlockReductionTests(unittest.TestCase):
    def test_recovers_exact_seven_stage_structure(self):
        result = recover(fixture(), "helper", "reduce", "barrier", 32)
        self.assertEqual("recovered", result["status"])
        self.assertEqual((32, 256, 0), (result["width"], result["block_threads"], result["writer_lane"]))
        self.assertEqual(7, len(result["stage_sequence"]))
        self.assertEqual("not_established", result["coordinate_equality"])
        self.assertFalse(result["checked"])

    def test_parameter_and_shared_index_mismatch_are_unknown(self):
        root = fixture()
        function = root["inner"][-1]
        function["inner"][1]["type"]["qualType"] = "double *"
        self.assertEqual("parameter_types_not_float_and_float_pointer",
                         recover(root, "helper", "reduce", "barrier", 32)["reason"])
        root = fixture()
        store = root["inner"][-1]["inner"][-1]["inner"][3]["inner"][1]
        store["inner"][0]["inner"][1] = ref("lane", "VarDecl")
        self.assertEqual("writer_shared_or_index_mismatch",
                         recover(root, "helper", "reduce", "barrier", 32)["reason"])

    def test_missing_barrier_order_and_predicate_changes_are_unknown(self):
        root = fixture()
        root["inner"][-1]["inner"][-1]["inner"][4] = {"kind": "NullStmt"}
        self.assertIn(recover(root, "helper", "reduce", "barrier", 32)["reason"],
                      {"unexpected_call_shape", "unexpected_call_target"})
        root = fixture()
        statements = root["inner"][-1]["inner"][-1]["inner"]
        statements[3], statements[4] = statements[4], statements[3]
        self.assertEqual("writer_not_single_if", recover(root, "helper", "reduce", "barrier", 32)["reason"])
        root = fixture()
        root["inner"][-1]["inner"][-1]["inner"][5]["inner"][1]["inner"][0]["opcode"] = "<="
        self.assertEqual("second_stage_predicate_not_lane_lt_groups",
                         recover(root, "helper", "reduce", "barrier", 32)["reason"])

    def test_invalid_block_width_relationship_is_unknown(self):
        self.assertEqual("invalid_block_width_relationship",
                         recover(fixture(32, 250), "helper", "reduce", "barrier", 32)["reason"])
        self.assertEqual("invalid_block_width_relationship",
                         recover(fixture(4, 32), "helper", "reduce", "barrier", 32)["reason"])

    def test_integral_casts_are_recorded_without_establishing_conversion_semantics(self):
        root = fixture()
        group = root["inner"][-1]["inner"][-1]["inner"][1]["inner"][0]
        expression = group["inner"][0]
        expression["type"] = {"qualType": "unsigned int"}
        expression["inner"][1] = {
            "kind": "ImplicitCastExpr", "castKind": "IntegralCast", "range": R,
            "type": {"qualType": "unsigned int"}, "inner": [expression["inner"][1]]}
        group["inner"][0] = {
            "kind": "ImplicitCastExpr", "castKind": "IntegralCast", "range": R,
            "type": {"qualType": "int"}, "inner": [expression]}
        result = recover(root, "helper", "reduce", "barrier", 32)
        self.assertEqual("recovered", result["status"])
        self.assertEqual(2, len([cast for cast in result["casts"]
                                if cast["cast_kind"] == "IntegralCast"]))
        self.assertEqual("not_established", result["conversion_semantics"])
        self.assertEqual("unsigned int", result["casts"][0]["source_type"])

    def test_other_cast_remains_unknown(self):
        root = fixture()
        group = root["inner"][-1]["inner"][-1]["inner"][1]["inner"][0]
        group["inner"][0] = {"kind": "ImplicitCastExpr", "castKind": "FloatingToIntegral",
                              "range": R, "inner": [group["inner"][0]]}
        self.assertEqual("unsupported_cast",
                         recover(root, "helper", "reduce", "barrier", 32)["reason"])


if __name__ == "__main__":
    unittest.main()
