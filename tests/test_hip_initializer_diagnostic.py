"""Diagnostic driver fixtures; no native source/launch guarantees are mocked in."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from experiments.hip_initializer_diagnostic import run, literal_arguments, NATIVE_SHA, DECLARATION_ID


class HipInitializerDiagnosticTests(unittest.TestCase):
    def test_external_literal_leaf_is_freshly_checked(self):
        for literal in (True, False):
            with self.subTest(literal=literal), tempfile.TemporaryDirectory() as directory:
                argument = ({"kind": "IntegerLiteral", "value": "0"} if literal else
                            {"kind": "DeclRefExpr"})
                call = {"kind": "CallExpr", "id": "call", "type": {"qualType": "size_t",
                        "desugaredQualType": "unsigned long"}, "inner": [
                        {"kind": "DeclRefExpr", "referencedDecl": {"kind": "FunctionDecl", "id": "leaf"}},
                        {"kind": "ImplicitCastExpr", "castKind": "IntegralCast", "inner": [argument]}]}
                root = {"kind": "TranslationUnitDecl", "inner": [
                    {"kind": "FunctionDecl", "id": "getter", "inner": [{"kind": "CompoundStmt", "inner": [call]}]},
                    {"kind": "FunctionDecl", "id": "leaf", "type": {"qualType": "size_t (unsigned int)"}}]}
                native, output = Path(directory) / "native", Path(directory) / "output"
                native.write_text(json.dumps({"status": "collected", "payload": {"ast": root, "builtin_calls": []}}))
                first = {"checks": {"value_link": {"status": "recovered", "callee_declaration_id": "getter"}}}
                with patch("experiments.hip_initializer_diagnostic.sha", return_value=NATIVE_SHA), \
                        patch("experiments.hip_initializer_diagnostic.implementation_hashes", return_value={}), \
                        patch("experiments.hip_initializer_diagnostic.check_source", side_effect=[first, {"status": "unknown"}]) as fresh:
                    result = run(native, output)
                self.assertEqual(fresh.call_count, 2 if literal else 1)
                if literal:
                    self.assertEqual(result["leaf_contract"]["arguments"], [0])
                    self.assertEqual(result["leaf_contract"]["upper"], (1 << 64) - 1)
                    self.assertEqual(result["leaf_contract"]["return_type"], call["type"])
                    self.assertEqual(result["external_leaf_observation"]["id"], "leaf")
                    self.assertEqual(result["full_type_domain_check"]["status"], "unknown")
                else:
                    self.assertEqual(result["diagnostic_reason"], "diagnostic_argument_not_literal")
                    self.assertIsNone(result["full_type_domain_check"])
                self.assertFalse(result["lane_range_established"])

    def test_unsupported_argument_cast_is_not_stripped(self):
        with self.assertRaisesRegex(ValueError, "not_literal"):
            literal_arguments({"inner": [{}, {"kind": "ImplicitCastExpr", "castKind": "BitCast",
                "inner": [{"kind": "IntegerLiteral", "value": "0"}]}]})

    def test_hash_mismatch_stops_before_reading(self):
        with patch("experiments.hip_initializer_diagnostic.sha", return_value="wrong"):
            with self.assertRaisesRegex(ValueError, "fixed_input_mismatch"):
                run("missing", "output")

    def test_full_unsigned_range_is_not_replaced_with_lane_guess(self):
        call = {"kind": "CallExpr", "id": "call", "type": {"qualType": "unsigned int"},
                "inner": [{"kind": "DeclRefExpr", "referencedDecl": {"kind": "FunctionDecl", "id": "leaf"}}]}
        root = {"kind": "TranslationUnitDecl", "inner": [{"kind": "FunctionDecl", "id": "getter",
                "inner": [{"kind": "CompoundStmt", "inner": [call]}]}]}
        payload = {"ast": root, "builtin_calls": [{"call_expression_id": "call", "callee_declaration_id": "leaf"}]}
        first = {"status": "unknown", "checks": {"value_link": {"status": "recovered", "callee_declaration_id": "getter"}}}
        rejected = {"status": "rejected", "reason": "conversion_fixture"}
        with tempfile.TemporaryDirectory() as directory:
            native, output = Path(directory) / "native", Path(directory) / "output"
            native.write_text(json.dumps({"status": "collected", "payload": payload}))
            with patch("experiments.hip_initializer_diagnostic.sha", return_value=NATIVE_SHA), \
                    patch("experiments.hip_initializer_diagnostic.implementation_hashes", return_value={}), \
                    patch("experiments.hip_initializer_diagnostic.check_source", side_effect=[first, rejected]) as fresh:
                result = run(native, output)
            self.assertEqual(fresh.call_count, 2)
            self.assertEqual(fresh.call_args_list[1].args[0], root)
            self.assertEqual(fresh.call_args_list[1].args[1], DECLARATION_ID)
            contract = fresh.call_args_list[1].args[2]
            self.assertEqual((contract["lower"], contract["upper"]), (0, 4294967295))
            self.assertEqual(contract["declaration_id"], "leaf")
            self.assertEqual(contract["return_type"], call["type"])
            self.assertEqual(result["full_type_domain_check"], rejected)
            self.assertFalse(result["lane_range_established"])
            self.assertFalse(result["source_program_checked"])
            self.assertFalse(result["deployable"])
