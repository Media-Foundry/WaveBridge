import unittest
from unittest.mock import patch

import wavebridge.analysis.reduction_discovery as discovery


R = {"begin": {"offset": 1}, "end": {"offset": 2}}


def call(target=None, kind="CallExpr", call_id=None):
    inner = [] if target is None else [{"kind": "ImplicitCastExpr", "castKind": "FunctionToPointerDecay",
        "inner": [{"kind": "DeclRefExpr", "referencedDecl": {
            "id": target, "kind": "FunctionDecl", "name": "renamed"}}]}]
    return {"id": call_id, "kind": kind, "range": R, "inner": inner}


def function(identifier, calls, parameters=None):
    return {"id": identifier, "kind": "FunctionDecl", "name": "arbitrary", "inner": [
        *(parameters or []), {"kind": "CompoundStmt", "inner": calls}]}


def parameter(identifier, qual_type):
    return {"id": identifier, "kind": "ParmVarDecl", "type": {"qualType": qual_type}}


def root(*functions):
    return {"kind": "TranslationUnitDecl", "inner": list(functions)}


def recovered(kind):
    return {"status": "recovered", "kind": kind, "checked": False}


class ReductionDiscoveryTests(unittest.TestCase):
    def test_renamed_reachable_chain_finds_candidates_by_ids(self):
        tree = root(function("entry", [call("xor-helper"), call("block-helper")]),
                    function("xor-helper", [call("shuffle"), {"kind": "ReturnStmt"}],
                             [parameter("value", "float")]),
                    function("block-helper", [call("shuffle"), call("barrier"),
                             *({"kind": "NullStmt"} for _ in range(5))],
                             [parameter("value2", "float"), parameter("shared", "float *")]),
                    function("shuffle", []), function("barrier", []),
                    function("unreachable", [call("decoy")]), function("decoy", []))
        with patch.object(discovery, "recover_xor", side_effect=lambda r, f, s, b:
                          recovered("xor") if (f, s) == ("xor-helper", "shuffle") else {"status": "unknown"}), \
             patch.object(discovery, "recover_block", side_effect=lambda r, f, rd, bd, b:
                          recovered("block") if (f, rd, bd) == ("block-helper", "shuffle", "barrier") else {"status": "unknown"}):
            result = discovery.discover(tree, "entry", 32)
        self.assertEqual("analyzed", result["status"])
        self.assertEqual({"entry", "xor-helper", "block-helper", "shuffle", "barrier"},
                         set(result["reachable_function_ids"]))
        self.assertNotIn("unreachable", result["reachable_function_ids"])
        self.assertEqual("xor-helper", result["xor_candidates"][0]["function_id"])
        self.assertEqual("block-helper", result["block_candidates"][0]["function_id"])
        self.assertEqual("direct_call_candidate_not_semantic_identification",
                         result["xor_candidates"][0]["shuffle_declaration_selection"])
        self.assertFalse(result["checked"])

    def test_indirect_special_and_missing_calls_are_preserved_unknown(self):
        indirect = {"kind": "CallExpr", "range": R, "inner": [{"kind": "DeclRefExpr",
                    "referencedDecl": {"id": "callback", "kind": "ParmVarDecl"}}]}
        tree = root(function("entry", [indirect, call(kind="CUDAKernelCallExpr"), call("missing")]))
        result = discovery.discover(tree, "entry", 32)
        reasons = {item["reason"] for item in result["unresolved_calls"]}
        self.assertIn("indirect_or_unresolved_callee", reasons)
        self.assertIn("unsupported_call_kind", reasons)
        self.assertIn("callee_unique_definition_not_found", reasons)
        self.assertFalse(result["analysis_complete"])

    def test_nested_callable_body_is_not_treated_as_reachable_call(self):
        nested = {"kind": "LambdaExpr", "range": R, "inner": [
            {"kind": "CompoundStmt", "inner": [call("hidden")]}]}
        tree = root(function("entry", [nested]), function("hidden", []))
        result = discovery.discover(tree, "entry", 32)
        self.assertEqual(["entry"], result["reachable_function_ids"])
        self.assertEqual("unsupported_nested_callable", result["unresolved_calls"][0]["reason"])

    def test_entry_and_input_errors_are_unknown(self):
        self.assertEqual("root_not_object", discovery.discover([], "entry", 32)["reason"])
        self.assertEqual("invalid_int_bits", discovery.discover({}, "entry", 1)["reason"])
        self.assertEqual("entry_unique_definition_not_found", discovery.discover(root(), "entry", 32)["reason"])

    def test_candidate_budget_preserves_partial_results(self):
        targets = [f"f{i}" for i in range(7)]
        tree = root(function("entry", [call(target) for target in targets],
                             [parameter("value", "float"), parameter("shared", "float *")]),
                    *(function(target, []) for target in targets))
        with patch.object(discovery, "MAX_CANDIDATE_ATTEMPTS", 2), \
             patch.object(discovery, "recover_xor", return_value={"status": "unknown"}), \
             patch.object(discovery, "recover_block", return_value=recovered("block")):
            result = discovery.discover(tree, "entry", 32)
        self.assertEqual("analyzed", result["status"])
        self.assertTrue(result["budget"]["candidate_budget_exhausted"])
        self.assertFalse(result["analysis_complete"])
        self.assertEqual(2, len(result["block_candidates"]))

    def test_reachable_function_budget_reports_incomplete(self):
        tree = root(function("entry", [call("a")]), function("a", [call("b")]), function("b", []))
        with patch.object(discovery, "MAX_REACHABLE_FUNCTIONS", 1):
            result = discovery.discover(tree, "entry", 32)
        self.assertTrue(result["budget"]["reachable_function_budget_exhausted"])
        self.assertFalse(result["analysis_complete"])


if __name__ == "__main__":
    unittest.main()
