"""Synthetic structural fixtures do not provide native compiler attestation."""
import copy
import unittest

from wavebridge.verification.builtin_calls import inspect_structure


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
