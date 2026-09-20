import unittest

from wavebridge.analysis.xor_reduction import recover


R = {"begin": {"offset": 1}, "end": {"offset": 2}}


def ref(identifier, kind):
    return {"kind": "DeclRefExpr", "range": R, "referencedDecl": {"id": identifier, "kind": kind}}


def lit(value):
    return {"kind": "IntegerLiteral", "type": {"qualType": "int"}, "value": str(value), "range": R}


def fixture(width=32, selected="shuffle", call_target="shuffle"):
    width_decl = {"id": "width", "kind": "VarDecl", "type": {"qualType": "const int"},
                  "constexpr": True, "init": "c", "inner": [lit(width)]}
    accumulator = {"id": "acc", "kind": "ParmVarDecl", "type": {"qualType": "float"}, "range": R}
    offset = {"id": "off", "kind": "VarDecl", "type": {"qualType": "int"}, "init": "c",
              "inner": [{"kind": "BinaryOperator", "opcode": "/", "range": R,
                         "inner": [ref("width", "VarDecl"), lit(2)]}]}
    init = {"kind": "DeclStmt", "inner": [offset]}
    condition = {"kind": "BinaryOperator", "opcode": ">", "range": R,
                 "inner": [ref("off", "VarDecl"), lit(0)]}
    increment = {"kind": "CompoundAssignOperator", "opcode": ">>=", "range": R,
                 "inner": [ref("off", "VarDecl"), lit(1)]}
    call = {"kind": "CallExpr", "range": R, "inner": [
        ref(call_target, "FunctionDecl"), ref("acc", "ParmVarDecl"),
        ref("off", "VarDecl"), ref("width", "VarDecl")]}
    update = {"kind": "CompoundAssignOperator", "opcode": "+=", "range": R,
              "inner": [ref("acc", "ParmVarDecl"), call]}
    loop = {"kind": "ForStmt", "range": R,
            "inner": [init, {}, condition, increment, {"kind": "CompoundStmt", "inner": [update]}]}
    function = {"id": "helper", "kind": "FunctionDecl", "range": R,
                "inner": [accumulator, {"kind": "CompoundStmt", "range": R,
                                              "inner": [loop, {"kind": "ReturnStmt", "range": R,
                                                               "inner": [ref("acc", "ParmVarDecl")]}]}]}
    shuffle = {"id": selected, "kind": "FunctionDecl", "range": R}
    return {"kind": "TranslationUnitDecl", "inner": [width_decl, shuffle, function]}


class XorReductionTests(unittest.TestCase):
    def test_recovers_structure_by_ids_and_computes_offsets(self):
        result = recover(fixture(32), "helper", "shuffle")
        self.assertEqual("recovered", result["status"])
        self.assertEqual(32, result["width"])
        self.assertEqual([16, 8, 4, 2, 1], result["offsets"])
        self.assertEqual("add", result["operation"])
        self.assertEqual("not_established", result["external_shuffle_semantics"])
        self.assertFalse(result["checked"])

    def test_width_changes_and_attributed_loop_are_structural(self):
        root = fixture(64)
        body = root["inner"][-1]["inner"][-1]
        body["inner"][0] = {"kind": "AttributedStmt", "inner": [
            {"kind": "LoopHintAttr"}, body["inner"][0]]}
        result = recover(root, "helper", "shuffle")
        self.assertEqual([32, 16, 8, 4, 2, 1], result["offsets"])

    def test_wrong_shuffle_id_and_width_argument_are_unknown(self):
        self.assertEqual("call_not_selected_shuffle",
                         recover(fixture(call_target="other"), "helper", "shuffle")["reason"])
        root = fixture()
        call = root["inner"][-1]["inner"][-1]["inner"][0]["inner"][4]["inner"][0]["inner"][1]
        call["inner"][3] = ref("other-width", "VarDecl")
        self.assertEqual("shuffle_width_mismatch", recover(root, "helper", "shuffle")["reason"])

    def test_extra_statement_condition_and_update_changes_are_unknown(self):
        root = fixture()
        body = root["inner"][-1]["inner"][-1]
        body["inner"].insert(0, {"kind": "NullStmt"})
        self.assertEqual("body_not_loop_then_return", recover(root, "helper", "shuffle")["reason"])
        root = fixture()
        loop = root["inner"][-1]["inner"][-1]["inner"][0]
        loop["inner"][2]["opcode"] = ">="
        self.assertEqual("condition_not_offset_gt_zero", recover(root, "helper", "shuffle")["reason"])
        root = fixture()
        loop = root["inner"][-1]["inner"][-1]["inner"][0]
        loop["inner"][3]["opcode"] = "-="
        self.assertEqual("increment_not_offset_shift", recover(root, "helper", "shuffle")["reason"])

    def test_non_power_of_two_and_unsupported_cast_are_unknown(self):
        self.assertEqual("width_not_supported_power_of_two", recover(fixture(24), "helper", "shuffle")["reason"])
        root = fixture()
        loop = root["inner"][-1]["inner"][-1]["inner"][0]
        original = loop["inner"][2]["inner"][0]
        loop["inner"][2]["inner"][0] = {"kind": "ImplicitCastExpr", "castKind": "IntegralCast",
                                                  "inner": [original]}
        self.assertEqual("unsupported_cast", recover(root, "helper", "shuffle")["reason"])


if __name__ == "__main__":
    unittest.main()
