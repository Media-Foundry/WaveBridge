import unittest
from pathlib import Path
import shutil
import tempfile
import json
from unittest.mock import patch

from wavebridge.analysis.xor_reduction import recover, main
from wavebridge.frontend.clang_ast import collect, _walk


R = {"begin": {"offset": 1}, "end": {"offset": 2}}


def ref(identifier, kind):
    return {"kind": "DeclRefExpr", "range": R, "referencedDecl": {"id": identifier, "kind": kind}}


def lit(value):
    return {"kind": "IntegerLiteral", "type": {"qualType": "int"}, "value": str(value), "range": R}


def unsigned_lit(value):
    return {"kind": "IntegerLiteral", "type": {"qualType": "unsigned int"},
            "value": str(value), "range": R}


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


def sync_fixture(width=32, mask=None):
    root = fixture(width)
    call = root["inner"][-1]["inner"][-1]["inner"][0]["inner"][4]["inner"][0]["inner"][1]
    call["inner"].insert(1, unsigned_lit(4294967295) if mask is None else mask)
    return root


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

    def test_recovers_explicit_full_logical32_mask_without_dropping_evidence(self):
        result = recover(sync_fixture(), "helper", "shuffle", int_bits=32)
        self.assertEqual("recovered", result["status"])
        self.assertEqual(4, result["shuffle_call_arity"])
        self.assertEqual(4294967295, result["mask"]["value"])
        self.assertEqual({"qualType": "unsigned int"}, result["mask"]["type"])
        self.assertEqual(R, result["mask"]["range"])
        self.assertEqual("IntegerLiteral", result["mask"]["ast"]["kind"])
        self.assertFalse(result["conditional_route_check"]["models_mask"])
        self.assertEqual(2, len(result["conditional_route_check"]["external_preconditions"]))
        self.assertEqual("not_established", result["external_shuffle_semantics"])
        self.assertFalse(result["checked"])
        self.assertFalse(result["deployable"])

    def test_partial_dynamic_wrong_type_width_and_int_bits_masks_are_unknown(self):
        cases = [
            (sync_fixture(mask=unsigned_lit(4294967294)), 32,
             "shuffle_mask_not_supported_full_logical32"),
            (sync_fixture(mask=ref("dynamic", "VarDecl")), 32,
             "shuffle_mask_not_explicit_integer_literal"),
            (sync_fixture(mask=lit(4294967295)), 32, "shuffle_mask_not_unsigned_int"),
            (sync_fixture(), 64, "shuffle_mask_not_supported_full_logical32"),
            (sync_fixture(width=64), 32, "four_argument_shuffle_requires_logical_width_32"),
        ]
        for root, bits, reason in cases:
            with self.subTest(reason=reason):
                result = recover(root, "helper", "shuffle", int_bits=bits)
                self.assertEqual("unknown", result["status"])
                self.assertEqual(reason, result["reason"])
                self.assertIsNone(result["mask"])

    def test_four_argument_order_and_conversions_remain_strict(self):
        root = sync_fixture()
        call = root["inner"][-1]["inner"][-1]["inner"][0]["inner"][4]["inner"][0]["inner"][1]
        call["inner"][2], call["inner"][3] = call["inner"][3], call["inner"][2]
        self.assertEqual("unexpected_referenced_declaration_kind",
                         recover(root, "helper", "shuffle")["reason"])
        root = sync_fixture(mask={"kind": "ImplicitCastExpr", "castKind": "IntegralCast",
                                  "type": {"qualType": "unsigned int"},
                                  "inner": [lit(-1)], "range": R})
        self.assertEqual("shuffle_mask_not_explicit_integer_literal",
                         recover(root, "helper", "shuffle")["reason"])

    def test_cli_does_not_check_routes_for_unsupported_mask(self):
        with tempfile.TemporaryDirectory() as directory:
            ast = Path(directory) / "ast.json"
            output = Path(directory) / "result.json"
            ast.write_text(json.dumps({"schema_version": "clang-ast-source/v1",
                                       "status": "collected", "ast_roots": [
                                           sync_fixture(mask=unsigned_lit(1))]}))
            with patch("wavebridge.verification.xor_routes.check") as checker:
                code = main([str(ast), "--root-index", "0", "--function-id", "helper",
                             "--shuffle-id", "shuffle", "--int-bits", "32",
                             "--output", str(output)])
                checker.assert_not_called()
            self.assertEqual(2, code)
            self.assertIsNone(json.loads(output.read_text())["conditional_route_check"])

    @unittest.skipUnless(shutil.which("clang++"), "requires real clang++")
    def test_real_clang_cpu_declaration_recovers_renamed_four_argument_helper(self):
        source = """
        float renamed_exchange(unsigned int, float, int, int);
        constexpr int renamed_width = 32;
        float arbitrary_helper(float state) {
          for (int distance = renamed_width / 2; distance > 0; distance >>= 1)
            state += renamed_exchange(4294967295u, state, distance, renamed_width);
          return state;
        }
        """
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sync_reduction.cpp"
            path.write_text(source)
            report = collect(path, shutil.which("clang++"), ["-std=c++17"],
                             "arbitrary_helper", full_translation_unit=True)
        self.assertEqual("collected", report["status"], report.get("execution"))
        declarations = {node["name"]: node["id"] for node in _walk(report["ast_roots"][0])
                        if node.get("kind") == "FunctionDecl" and
                        node.get("name") in ("renamed_exchange", "arbitrary_helper")}
        result = recover(report["ast_roots"][0], declarations["arbitrary_helper"],
                         declarations["renamed_exchange"], 32)
        self.assertEqual("recovered", result["status"], result)
        self.assertEqual(4294967295, result["mask"]["value"])
        self.assertEqual([16, 8, 4, 2, 1], result["offsets"])


if __name__ == "__main__":
    unittest.main()
