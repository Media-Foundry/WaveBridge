import copy
import unittest
from unittest.mock import patch

from wavebridge.analysis.width_uses import inspect


R = lambda n: {"begin": {"offset": n}, "end": {"offset": n + 1}}


def ref(identifier, n):
    return {"id": f"ref{n}", "kind": "DeclRefExpr", "type": {"qualType": "const int"},
            "valueCategory": "lvalue", "range": R(n),
            "referencedDecl": {"id": identifier, "kind": "VarDecl",
                               "type": {"qualType": "const int"}}}


def reports(root):
    block_function, xor_function = root["inner"][1:3]
    group, lane, gather = block_function["inner"][0]["inner"]
    xor_division, xor_call = xor_function["inner"][0]["inner"][:2]
    block = {"status": "recovered", "function_id": "block",
             "bindings": {"width_declaration_id": "width"},
             "index_initializers": {"group": group, "lane": lane},
             "shared_access_asts": {"gather_predicate": gather}}
    xor = {"status": "recovered", "function_id": "xor",
           "bindings": {"width_declaration_id": "width"},
           "ranges": {"initializer": xor_division["range"], "call": xor_call["range"]}}
    chain = {"status": "recovered", "width": 32,
             "links": [{"callee_id": "block"}, {"callee_id": "xor"}]}
    discovery = {"status": "analyzed", "traversal_budget_complete": True,
                 "block_candidates": [block], "xor_candidates": [xor]}
    return chain, discovery


def fixture(extra=None):
    width = {"id": "width", "kind": "VarDecl", "type": {"qualType": "const int"},
             "constexpr": True, "range": R(1)}
    group = {"kind": "BinaryOperator", "opcode": "/", "range": R(10),
             "inner": [{"kind": "OpaqueValueExpr"}, ref("width", 11)]}
    lane = {"kind": "BinaryOperator", "opcode": "%", "range": R(20),
            "inner": [{"kind": "OpaqueValueExpr"}, ref("width", 21)]}
    group_count = {"kind": "BinaryOperator", "opcode": "/", "range": R(30),
                   "inner": [ref("block_threads", 31), ref("width", 32)]}
    gather = {"kind": "BinaryOperator", "opcode": "<", "range": R(29),
              "inner": [ref("lane", 33), group_count]}
    block = {"id": "block", "kind": "FunctionDecl", "inner": [
        {"kind": "CompoundStmt", "inner": [group, lane, gather]}]}
    initial = {"kind": "BinaryOperator", "opcode": "/", "range": R(40),
               "inner": [ref("width", 41), {"kind": "IntegerLiteral", "value": "2"}]}
    call = {"kind": "CallExpr", "range": R(50), "inner": [
        {"kind": "DeclRefExpr", "referencedDecl": {"id": "shuffle", "kind": "FunctionDecl"}},
        ref("value", 51), ref("offset", 52), ref("width", 53)]}
    xor = {"id": "xor", "kind": "FunctionDecl", "inner": [
        {"kind": "CompoundStmt", "inner": [initial, call]}]}
    children = [width, block, xor]
    if extra is not None:
        children.append(extra)
    return {"kind": "TranslationUnitDecl", "inner": children}


class WidthUsesTests(unittest.TestCase):
    def run_inspect(self, root, **kwargs):
        chain, discovery = reports(root)
        with (patch("wavebridge.analysis.width_uses.recover_chain", return_value=chain),
              patch("wavebridge.analysis.width_uses.discover", return_value=discovery)):
            return inspect(root, "kernel", 32, **kwargs)

    def test_classifies_exact_five_explicit_roles_as_evidence_only(self):
        result = self.run_inspect(fixture())
        self.assertEqual("evidence", result["status"], result)
        self.assertEqual(5, result["explicit_reference_count"])
        self.assertEqual({role: 1 for role in sorted(result["role_counts"])},
                         result["role_counts"])
        self.assertTrue(result["all_explicit_declref_uses_classified"])
        self.assertFalse(result["implicit_or_constant_folded_uses_covered"])
        for key in ("checked", "source_program_checked", "deployable"):
            self.assertFalse(result[key])
        self.assertTrue(all(item["ancestors_outer_to_inner"] for item in result["uses"]))

    def test_external_or_diagnostic_reference_keeps_partial_inventory_unknown(self):
        extra = {"id": "diagnostic", "kind": "FunctionDecl", "inner": [
            {"kind": "CompoundStmt", "inner": [ref("width", 90)]}]}
        result = self.run_inspect(fixture(extra))
        self.assertEqual("unknown", result["status"])
        self.assertEqual("explicit_width_uses_not_fully_classified", result["reason"])
        self.assertEqual("external_other", result["uses"][-1]["role"])
        self.assertFalse(result["all_explicit_declref_uses_classified"])

    def test_same_function_but_wrong_syntax_is_not_classified(self):
        root = fixture()
        root["inner"][2]["inner"][0]["inner"].append(ref("width", 80))
        result = self.run_inspect(root)
        self.assertEqual("explicit_width_uses_not_fully_classified", result["reason"])
        self.assertEqual("external_other", result["uses"][-1]["role"])

    def test_declaration_reference_identity_type_and_children_are_fail_closed(self):
        root = fixture()
        root["inner"].append(copy.deepcopy(root["inner"][0]))
        self.assertEqual("width_declaration_not_globally_unique", self.run_inspect(root)["reason"])

        root = fixture()
        root["inner"][1]["inner"][0]["inner"][0]["inner"][1]["type"] = {"qualType": "int"}
        self.assertEqual("width_reference_shape_or_type_mismatch", self.run_inspect(root)["reason"])

        root = fixture()
        stub = root["inner"][1]["inner"][0]["inner"][0]["inner"][1]["referencedDecl"]
        stub["type"] = {"qualType": "int"}
        self.assertEqual("width_reference_shape_or_type_mismatch", self.run_inspect(root)["reason"])

        root = fixture()
        del root["inner"][1]["inner"][0]["inner"][0]["inner"][1]["referencedDecl"]["type"]
        self.assertEqual("width_reference_shape_or_type_mismatch", self.run_inspect(root)["reason"])

        root = fixture()
        root["inner"][0]["type"] = {"qualType": "Width", "typeAliasDeclId": "alias"}
        self.assertEqual("width_declaration_type_missing", self.run_inspect(root)["reason"])

        root = fixture()
        root["inner"][1]["inner"][0]["inner"][0]["inner"][1]["inner"] = [
            {"kind": "IntegerLiteral", "value": "0"}]
        self.assertEqual("width_reference_shape_or_type_mismatch", self.run_inspect(root)["reason"])

    def test_recovery_and_budget_failures_are_unknown(self):
        root = fixture()
        chain, discovery = reports(root)
        chain["status"] = "unknown"
        with (patch("wavebridge.analysis.width_uses.recover_chain", return_value=chain),
              patch("wavebridge.analysis.width_uses.discover", return_value=discovery)):
            self.assertEqual("reduction_chain_not_recovered", inspect(root, "kernel", 32)["reason"])
        result = self.run_inspect(fixture(), max_ast_nodes=2)
        self.assertEqual("ast_node_budget_exceeded", result["reason"])
        self.assertEqual("invalid_max_ast_nodes",
                         inspect(fixture(), "kernel", 32, max_ast_nodes=True)["reason"])

        root = fixture()
        root["kind"] = "CompoundStmt"
        self.assertEqual("root_not_translation_unit", inspect(root, "kernel", 32)["reason"])

        deep = {"kind": "TranslationUnitDecl", "inner": []}
        current = deep
        for _ in range(1200):
            child = {"kind": "CompoundStmt", "inner": []}
            current["inner"] = [child]
            current = child
        self.assertEqual("ast_recursion_limit_exceeded", inspect(deep, "kernel", 32)["reason"])

    def test_unsupported_cast_does_not_classify_a_role(self):
        root = fixture()
        division = root["inner"][2]["inner"][0]["inner"][0]
        division["inner"][0] = {"kind": "ImplicitCastExpr", "castKind": "BitCast",
                                "inner": [division["inner"][0]]}
        result = self.run_inspect(root)
        self.assertEqual("required_width_role_use_missing_or_duplicated", result["reason"])
        self.assertIn("external_other", result["role_counts"])


if __name__ == "__main__":
    unittest.main()
