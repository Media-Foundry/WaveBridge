"""Same-invocation compiler enum observations, not runtime range proofs."""
import copy
import os
from pathlib import Path
import unittest
from wavebridge.frontend.native_captures import collect
from wavebridge.frontend.clang_ast import _walk
from wavebridge.verification.normal_return_guard import check_enum_binding, check_enum_equality, check_call_enum_equality

PLUGIN = os.environ.get("WB_ENUM_CAPTURE_PLUGIN") or os.environ.get("WB_NATIVE_CAPTURE_PLUGIN")
COMPILER = os.environ.get("WB_ENUM_CAPTURE_COMPILER") or os.environ.get("WB_NATIVE_CAPTURE_COMPILER", "clang++")


@unittest.skipUnless(PLUGIN, "requires compiler-matched enum observation plugin")
class NativeEnumTypesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = collect(Path(__file__).parent / "fixtures/native_enum_types.cpp", COMPILER,
                             Path(PLUGIN), ["-std=c++17"])
        if cls.report["status"] != "collected": raise AssertionError(cls.report)
        cls.payload = cls.report["payload"]
        cls.declarations = {n["id"]: n for n in _walk(cls.payload["ast"]) if n.get("kind") == "EnumDecl"}
        cls.records = {cls.declarations[r["enum_declaration_id"]]["name"]: r for r in cls.payload["enum_types"]}

    def test_named_values_and_ids_belong_to_same_ast(self):
        raw = self.payload["enum_types"]
        self.assertEqual(len(raw), 3)
        self.assertEqual(len({r["enum_declaration_id"] for r in raw}), len(raw))
        ids = [v["declaration_id"] for r in raw for v in r["enumerators"]]
        self.assertEqual(len(set(ids)), len(ids))
        self.assertEqual(set(self.records), {"Positive", "Signed", "Wide"})
        expected = {"Positive": [0, 1, 1055], "Signed": [-4, 0, 1], "Wide": [9223372036854775815]}
        for name, record in self.records.items():
            declaration = self.declarations[record["enum_declaration_id"]]
            constants = [n for n in declaration["inner"] if n.get("kind") == "EnumConstantDecl"]
            self.assertEqual([n["id"] for n in constants], [v["declaration_id"] for v in record["enumerators"]])
            self.assertEqual([int(v["value_decimal"]) for v in record["enumerators"]], expected[name])

    def test_underlying_and_promotion_are_distinct(self):
        positive = self.records["Positive"]
        self.assertEqual(positive["underlying_type"], "unsigned int")
        self.assertFalse(positive["underlying_signed"])
        self.assertEqual(positive["promotion_type"], "int")
        self.assertTrue(positive["promotion_signed"])
        self.assertEqual(positive["promotion_bits"], self.payload["ast_int_bits"])
        self.assertFalse(positive["is_fixed"])
        self.assertTrue(self.records["Signed"]["underlying_signed"])
        self.assertTrue(self.records["Wide"]["is_fixed"])
        self.assertTrue(self.records["Wide"]["is_scoped"])
        # Clang may populate this internal slot even for scoped enums. It is
        # not evidence that the language permits their implicit conversion.
        self.assertIn(self.records["Wide"]["promotion_type"], (None, "unsigned long long"))

    def test_observation_does_not_claim_exhaustive_runtime_domain(self):
        self.assertIn("not_exhaustive", self.payload["enum_type_coverage"])
        self.assertIn("not_runtime_domain_proof", self.payload["enum_type_semantics"])
        self.assertFalse(self.payload["source_program_checked"])
        self.assertFalse(self.payload["deployable"])
        self.assertTrue(self.report["inputs_stable"])


@unittest.skipUnless(PLUGIN, "requires compiler-matched enum observation plugin")
class NativeGuardEnumBindingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        report = collect(Path(__file__).parent / "fixtures/normal_return_guard.cpp", COMPILER,
                         Path(PLUGIN), ["-std=c++17"])
        if report["status"] != "collected": raise AssertionError(report)
        cls.payload = report["payload"]
        cls.function = next(n["id"] for n in _walk(cls.payload["ast"])
                            if n.get("kind") == "FunctionDecl" and n.get("name") == "good")
        cls.calls = {n["name"]: next(c for c in n["inner"] if c.get("kind") == "CompoundStmt")["inner"][0]["id"]
                     for n in _walk(cls.payload["ast"]) if n.get("kind") == "FunctionDecl"
                     and n.get("name", "").startswith("call_")}

    def contract(self):
        # Test-only external assumption. Binding IDs does not verify lowering.
        binding = check_enum_binding(self.payload, self.function)
        return {
            "schema_version": "enum-bitpattern-contract/v1",
            "payload_sha256": binding["input_sha256"]["payload"],
            "function_id": self.function, "parameter_id": binding["parameter_id"],
            "constant_id": binding["constant_id"],
            "enum_declaration_id": binding["enum_declaration_id"],
            "converted_operand_ids": binding["converted_operand_ids"],
            "bits": binding["enum_observation"]["underlying_bits"],
            "semantics": "both_casts_preserve_all_bits_of_determinate_full_underlying_representation",
            "equality": "enum_and_int_equality_compare_all_representation_bits",
            "representation": "padding_free_trap_free_unique_bitvectors_twos_complement_signed_decode",
        }

    def test_equality_is_conditional_on_exact_external_contract(self):
        report = check_enum_equality(self.payload, self.function, self.contract())
        self.assertEqual(report["status"], "checked", report)
        self.assertTrue(report["conditional_enum_equality_under_external_lowering_assumption"])
        for key in ("conversion_contract_verified", "actual_lowering_verified", "API_success_verified",
                    "source_program_checked", "deployable"):
            self.assertFalse(report[key])
        self.assertFalse(report["conversion_check"]["numeric_value_preservation_established"])

    def test_query_equality_is_bound_to_this_invocation(self):
        reports = [check_call_enum_equality(self.payload, self.calls[name], self.contract())
                   for name in ("call_good", "call_other")]
        for report in reports:
            self.assertEqual(report["status"], "checked", report)
            self.assertTrue(report["conditional_query_enum_equality_under_external_lowering_assumption"])
            self.assertEqual(report["call_check"]["query_call_id"], report["query_call_id"])
            for key in ("actual_lowering_verified", "conversion_contract_verified", "call_normal_return_proved",
                        "API_success_verified", "query_output_effects_verified", "runtime_linkage_verified",
                        "source_program_checked", "deployable"):
                self.assertFalse(report[key])
        self.assertNotEqual(reports[0]["query_declaration_id"], reports[1]["query_declaration_id"])
        self.assertNotEqual(reports[0]["input_sha256"]["selection"], reports[1]["input_sha256"]["selection"])
        self.assertIn("selected wrapper call executes the selected definition", reports[0]["assumptions"])

    def test_query_equality_rechecks_query_and_conversion_contract(self):
        for name in ("call_constant", "call_discarded", "call_converted", "call_conditional",
                     "call_indirect", "call_unguarded"):
            result = check_call_enum_equality(self.payload, self.calls[name], self.contract())
            self.assertEqual(result["status"], "unknown", name)
            self.assertFalse(result["conditional_query_enum_equality_under_external_lowering_assumption"])
        for contract in (None, {}, {**self.contract(), "parameter_id": "wrong"}):
            result = check_call_enum_equality(self.payload, self.calls["call_good"], contract)
            self.assertEqual(result["status"], "unknown")
        self.assertEqual(check_call_enum_equality(self.payload, self.calls["call_good"], self.contract(),
                                                 max_ast_nodes=1)["status"], "unknown")

    def test_query_equality_input_immutability_and_ast_tamper(self):
        original = copy.deepcopy(self.payload)
        check_call_enum_equality(self.payload, self.calls["call_good"], self.contract())
        self.assertEqual(original, self.payload)
        call = next(n for n in _walk(original["ast"]) if n.get("id") == self.calls["call_good"])
        call["inner"][1]["type"] = {"qualType": "int"}
        self.assertEqual(check_call_enum_equality(original, self.calls["call_good"], self.contract())["status"], "unknown")

    def test_equality_rejects_unbound_partial_or_conclusion_contracts(self):
        for key in self.contract():
            contract = self.contract()
            contract.pop(key)
            self.assertEqual(check_enum_equality(self.payload, self.function, contract)["status"], "unknown", key)
        for key, value in (("payload_sha256", "wrong"), ("bits", True), ("bits", 16),
                           ("converted_operand_ids", list(reversed(self.contract()["converted_operand_ids"]))),
                           ("semantics", "uint_max_probe_passed"), ("semantics", "truncate"),
                           ("representation", "may_have_padding"), ("API_success_verified", True)):
            contract = self.contract()
            contract[key] = value
            self.assertEqual(check_enum_equality(self.payload, self.function, contract)["status"], "unknown", key)
        payload = copy.deepcopy(self.payload)
        next(n for n in _walk(payload["ast"]) if n.get("kind") == "BinaryOperator")["opcode"] = "=="
        self.assertEqual(check_enum_equality(payload, self.function, self.contract())["status"], "unknown")
        self.assertEqual(check_enum_equality(self.payload, self.function, None)["status"], "unknown")

    def test_fresh_binding_and_limits(self):
        before = copy.deepcopy(self.payload)
        result = check_enum_binding(self.payload, self.function)
        self.assertEqual(result["status"], "checked", result)
        self.assertEqual(result["constant_value_decimal"], "0")
        self.assertEqual(result["guard_check"]["converted_operand_ids"], result["converted_operand_ids"])
        for key in ("enum_equality_established", "API_success_verified", "source_program_checked", "deployable"):
            self.assertFalse(result[key])
        self.assertEqual(before, self.payload)

    def test_missing_duplicate_or_malformed_metadata(self):
        for mutation in ("missing", "duplicate", "id", "constant", "promotion", "bits", "decimal"):
            payload = copy.deepcopy(self.payload)
            record = payload["enum_types"][0]
            if mutation == "missing": payload.pop("enum_types")
            elif mutation == "duplicate": payload["enum_types"].append(copy.deepcopy(record))
            elif mutation == "id": record["enum_declaration_id"] = "wrong"
            elif mutation == "constant": record["enumerators"][0]["declaration_id"] = "wrong"
            elif mutation == "promotion": record["promotion_type"] = "unsigned int"
            elif mutation == "bits": record["promotion_bits"] = True
            elif mutation == "decimal": record["enumerators"][0]["value_decimal"] = "00"
            self.assertEqual(check_enum_binding(payload, self.function)["status"], "unknown", mutation)

    def test_source_identity_and_guard_are_rechecked(self):
        for mutation in ("alias", "comparison", "constant_owner"):
            payload = copy.deepcopy(self.payload)
            nodes = list(_walk(payload["ast"]))
            function = next(n for n in nodes if n.get("id") == self.function)
            local = list(_walk(function))
            if mutation == "alias":
                next(n for n in local if n.get("kind") == "ParmVarDecl")["type"]["typeAliasDeclId"] = "missing"
            elif mutation == "comparison":
                next(n for n in local if n.get("kind") == "BinaryOperator")["opcode"] = "=="
            else:
                enum = next(n for n in nodes if n.get("kind") == "EnumDecl")
                enum["inner"] = [n for n in enum["inner"] if n.get("name") != "success"]
            self.assertEqual(check_enum_binding(payload, self.function)["status"], "unknown", mutation)
        self.assertEqual(check_enum_binding(self.payload, self.function, max_ast_nodes=1)["status"], "unknown")
