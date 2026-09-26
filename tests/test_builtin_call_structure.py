"""Synthetic structural fixtures do not provide native compiler attestation."""
import copy
import unittest

from wavebridge.verification.builtin_calls import (
    inspect_structure, check_no_memory_write, check_wrapper_no_memory_write)


def fixture():
    declaration = {"id": "decl", "kind": "FunctionDecl", "name": "__builtin_huge_valf",
                   "type": {"qualType": "float () noexcept"}, "inner": [{"kind": "BuiltinAttr"}]}
    ref = {k: v for k, v in declaration.items() if k != "inner"}
    callee = {"id": "ref", "kind": "DeclRefExpr", "type": {"qualType": "<builtin fn type>"},
              "valueCategory": "prvalue", "referencedDecl": ref}
    decay = {"id": "decay", "kind": "ImplicitCastExpr", "castKind": "BuiltinFnToFnPtr",
             "type": {"qualType": "float (*)() noexcept"}, "valueCategory": "prvalue", "inner": [callee]}
    call = {"id": "call", "kind": "CallExpr", "type": {"qualType": "float"},
            "valueCategory": "prvalue", "inner": [decay]}
    return {"schema_version": "clang-native-captures/v1",
            "builtin_call_coverage": "visited_direct_builtin_calls_not_exhaustive",
            "builtin_call_semantics": "compiler_identity_not_value_or_effect_proof",
            "plugin_build_clang_version": "fixture", "ast_target_triple": "fixture",
            "ast": {"kind": "TranslationUnitDecl", "inner": [declaration, call]},
            "builtin_calls": [{"call_expression_id": "call", "callee_declaration_id": "decl",
                               "builtin_name": "__builtin_huge_valf", "builtin_id": 27,
                               "argument_expression_ids": []}]}


class BuiltinCallStructureTests(unittest.TestCase):
    @staticmethod
    def wrapped():
        payload = fixture()
        call = payload["ast"]["inner"].pop()
        wrapper = {"id": "wrapper", "kind": "FunctionDecl", "name": "renamed",
                   "type": {"qualType": "float ()"}, "inner": [{"kind": "CompoundStmt",
                   "inner": [{"kind": "ReturnStmt", "inner": [call]}]}]}
        payload["ast"]["inner"].append(wrapper)
        return payload

    def test_wrapper_preserves_conditional_scope(self):
        payload = self.wrapped()
        result = check_wrapper_no_memory_write(payload, "wrapper", self.protocol(payload))
        self.assertEqual(result["status"], "checked", result)
        self.assertEqual(result["conclusion"]["status"], "conditional")
        self.assertEqual(result["wrapper_declaration_ids"], ["wrapper"])
        self.assertFalse(result["external_leaf_effect_verified"])
        self.assertFalse(result["deployable"])

    def test_wrapper_extra_statements_and_attributes_fail(self):
        for extra in ({"kind": "VarDecl"}, {"kind": "AsmLabelAttr"},
                      {"kind": "NoThrowAttr", "inner": [{"kind": "CallExpr"}]}):
            payload = self.wrapped()
            payload["ast"]["inner"][-1]["inner"].append(extra)
            self.assertEqual(check_wrapper_no_memory_write(payload, "wrapper", self.protocol(payload))["status"], "unknown")
        payload = self.wrapped()
        payload["ast"]["inner"][-1]["inner"][0]["inner"].insert(0, {"kind": "NullStmt"})
        self.assertEqual(check_wrapper_no_memory_write(payload, "wrapper", self.protocol(payload))["status"], "unknown")

    def test_wrapper_ambiguous_identity_and_budget_fail(self):
        payload = self.wrapped()
        protocol = self.protocol(payload)
        self.assertEqual(check_wrapper_no_memory_write(payload, "wrapper", protocol, max_ast_nodes=1)["status"], "unknown")
        payload["ast"]["inner"].append(copy.deepcopy(payload["ast"]["inner"][-1]))
        self.assertEqual(check_wrapper_no_memory_write(payload, "wrapper", protocol)["status"], "unknown")

    @staticmethod
    def protocol(payload):
        report = inspect_structure(payload, "call")
        return {"schema_version": "builtin-leaf-effect-assumption/v1",
                "native_envelope_sha256": report["input_sha256"]["native_envelope"],
                "call_expression_id": "call", "callee_declaration_id": "decl",
                "builtin_no_memory_write_assumed": True,
                "valid_call_and_normal_return_assumed": True,
                "evidence_reference": "test-only external assumption, not attestation"}

    def test_effect_conclusion_remains_conditional(self):
        payload = fixture()
        protocol = self.protocol(payload)
        before = copy.deepcopy((payload, protocol))
        result = check_no_memory_write(payload, "call", protocol)
        self.assertEqual(result["status"], "checked", result)
        self.assertEqual(result["conclusion"]["status"], "conditional")
        self.assertEqual(result["conclusion"]["subject"], "exact_builtin_call_expression")
        self.assertIs(result["external_leaf_effect_verified"], False)
        self.assertEqual(result["effect_evidence"]["verification_status"], "unverified")
        self.assertEqual(result["value_semantics"], "not_established")
        self.assertFalse(result["deployable"])
        self.assertEqual((payload, protocol), before)

    def test_effect_protocol_is_bound_and_boolean_strict(self):
        payload = fixture()
        for field in self.protocol(payload):
            protocol = self.protocol(payload)
            protocol.pop(field)
            with self.subTest(field=field):
                self.assertEqual(check_no_memory_write(payload, "call", protocol)["status"], "unknown")
        for field in ("builtin_no_memory_write_assumed", "valid_call_and_normal_return_assumed"):
            protocol = self.protocol(payload)
            protocol[field] = 1
            self.assertEqual(check_no_memory_write(payload, "call", protocol)["status"], "unknown")
        self.assertEqual(check_no_memory_write(payload, "call", None)["status"], "unknown")

    def test_stale_structure_cannot_override_fresh_failure(self):
        payload = fixture()
        protocol = self.protocol(payload)
        payload["builtin_calls"] = []
        self.assertEqual(check_no_memory_write(payload, "call", protocol)["status"], "unknown")
        payload = fixture()
        payload["plugin_build_clang_version"] = "changed"
        self.assertEqual(check_no_memory_write(payload, "call", protocol)["status"], "unknown")
        self.assertEqual(check_no_memory_write(fixture(), "call", protocol, max_ast_nodes=1)["status"], "unknown")

    def test_checked_scope_and_input_immutability(self):
        payload = fixture()
        before = copy.deepcopy(payload)
        result = inspect_structure(payload, "call")
        self.assertEqual(result["status"], "checked", result)
        self.assertEqual(payload, before)
        self.assertFalse(result["source_program_checked"])
        self.assertFalse(result["deployable"])
        self.assertEqual(result["effect_semantics"], "not_established")
        self.assertEqual(result["value_semantics"], "not_established")
        self.assertEqual(len(result["input_sha256"]["native_envelope"]), 64)

    def test_invalid_budget_and_exhaustion(self):
        for budget in (True, 0, -1, 10_000_001, 1):
            with self.subTest(budget=budget):
                self.assertEqual(inspect_structure(fixture(), "call", max_ast_nodes=budget)["status"], "unknown")

    def test_missing_conflicting_or_forged_identity(self):
        for field, value in (("builtin_id", True), ("builtin_id", 0), ("callee_declaration_id", "other"),
                             ("builtin_name", "ordinary"), ("argument_expression_ids", ["extra"])):
            payload = fixture()
            payload["builtin_calls"][0][field] = value
            with self.subTest(field=field, value=value):
                self.assertEqual(inspect_structure(payload, "call")["status"], "unknown")
        for section in ("ast", "builtin_calls"):
            payload = fixture()
            if section == "ast":
                payload[section]["inner"].append(copy.deepcopy(payload[section]["inner"][0]))
            else:
                payload[section].append(copy.deepcopy(payload[section][0]))
            self.assertEqual(inspect_structure(payload, "call")["status"], "unknown")

    def test_callee_and_declaration_cannot_hide_effects(self):
        for target in ("callee", "declaration"):
            payload = fixture()
            declaration, call = payload["ast"]["inner"]
            node = declaration if target == "declaration" else call["inner"][0]["inner"][0]
            node.setdefault("inner", []).append({"kind": "CompoundStmt", "inner": [{"kind": "CallExpr"}]})
            self.assertEqual(inspect_structure(payload, "call")["status"], "unknown")

    def test_malformed_inputs_and_missing_metadata(self):
        for payload in (None, {}, {**fixture(), "builtin_calls": None},
                        {**fixture(), "plugin_build_clang_version": ""}):
            self.assertEqual(inspect_structure(payload, "call")["status"], "unknown")
        payload = fixture()
        payload["ast"]["inner"].append({"kind": "Bad", "inner": None})
        self.assertEqual(inspect_structure(payload, "call")["status"], "unknown")
