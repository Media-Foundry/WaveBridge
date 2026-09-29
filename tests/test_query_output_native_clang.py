"""Real native AST composition with explicitly hypothetical API contracts."""
import copy
import os
from pathlib import Path
import unittest

from wavebridge.frontend.native_captures import collect
from wavebridge.frontend.clang_ast import _walk
from wavebridge.verification.field_snapshot import check_query_object, check_query_output, FIELD_READ_PREMISE
from wavebridge.verification.normal_return_guard import check_enum_binding

PLUGIN = os.environ.get("WB_ENUM_CAPTURE_PLUGIN") or os.environ.get("WB_NATIVE_CAPTURE_PLUGIN")
COMPILER = os.environ.get("WB_ENUM_CAPTURE_COMPILER") or os.environ.get("WB_NATIVE_CAPTURE_COMPILER", "clang++")


@unittest.skipUnless(PLUGIN, "requires compiler-matched native plugin")
class QueryOutputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        report = collect(Path(__file__).parent / "fixtures/field_snapshot.cpp", COMPILER,
                         Path(PLUGIN), ["-std=c++17"])
        if report["status"] != "collected": raise AssertionError(report)
        cls.payload = report["payload"]
        cls.ids = {n["name"]: n["id"] for n in _walk(cls.payload["ast"]) if n.get("kind") == "FunctionDecl"}

    def contracts(self, name):
        objects = check_query_object(self.payload["ast"], self.ids[name])
        binding = check_enum_binding(self.payload, self.ids["guard"])
        conversion = {
            "schema_version": "enum-bitpattern-contract/v1",
            "payload_sha256": binding["input_sha256"]["payload"],
            "function_id": self.ids["guard"], "parameter_id": binding["parameter_id"],
            "constant_id": binding["constant_id"], "enum_declaration_id": binding["enum_declaration_id"],
            "converted_operand_ids": binding["converted_operand_ids"],
            "bits": binding["enum_observation"]["underlying_bits"],
            "semantics": "both_casts_preserve_all_bits_of_determinate_full_underlying_representation",
            "equality": "enum_and_int_equality_compare_all_representation_bits",
            "representation": "padding_free_trap_free_unique_bitvectors_twos_complement_signed_decode"}
        output = {key: objects[key] for key in
                  ("function_id", "wrapper_call_id", "query_call_id", "query_declaration_id",
                   "query_parameter_id", "argument_position", "argument_expression_id",
                   "object_declaration_id", "field_declaration_id", "field_read_id")}
        output.update(schema_version="query-field-output-contract/v1",
                      payload_sha256=binding["input_sha256"]["payload"], status_constant_id=binding["constant_id"],
                      arguments=[{key: arg[key] for key in ("position", "parameter_id", "expression_id")}
                                 for arg in objects["query_result_check"]["query_arguments"]],
                      effect="on_equal_status_selected_field_holds_API_initialized_determinate_plain_int_in_completed_query_poststate",
                      validity="all_argument_evaluations_and_API_preconditions_hold_including_aliasing_layout_alignment_and_live_readable_writable_object_field",
                      preservation="query_poststate_field_and_lifetime_remain_unchanged_through_selected_read_including_callbacks_and_retained_aliases",
                      linkage="selected_query_declaration_invokes_implementation_obeying_this_contract")
        return conversion, output

    def test_conditional_output_relation_and_read_premise_discharge(self):
        for name, position in (("guarded_snapshot", 0), ("reordered_snapshot", 1)):
            result = check_query_output(self.payload, self.ids[name], *self.contracts(name))
            self.assertEqual(result["status"], "checked", result)
            self.assertEqual(result["argument_position"], position)
            self.assertTrue(result["conditional_output_to_return_relation"])
            self.assertNotIn(FIELD_READ_PREMISE, result["assumptions"])
            self.assertIn(FIELD_READ_PREMISE, result["object_check"]["assumptions"])
            self.assertIn("counter increment has defined behavior", result["assumptions"])
            self.assertEqual(result["returned_value_origin"]["query_call_id"], result["query_call_id"])
            self.assertIsNone(result["field_numeric_domain"])
            for key in ("API_output_contract_verified", "query_output_effects_verified", "actual_lowering_verified",
                        "dynamic_lifetime_verified", "function_reachability_proved", "call_normal_return_proved",
                        "source_program_checked", "deployable"):
                self.assertFalse(result[key])

    def test_missing_or_misbound_contracts_are_unknown(self):
        conversion, output = self.contracts("guarded_snapshot")
        for key in output:
            bad = dict(output)
            bad.pop(key)
            self.assertEqual(check_query_output(self.payload, self.ids["guarded_snapshot"], conversion, bad)["status"], "unknown", key)
        for key, value in (("argument_position", True), ("argument_position", 1),
                           ("field_declaration_id", "wrong"), ("status_constant_id", "wrong"),
                           ("effect", "may_write"), ("validity", "unverified"), ("field_numeric_domain", [32, 32])):
            bad = {**output, key: value}
            self.assertEqual(check_query_output(self.payload, self.ids["guarded_snapshot"], conversion, bad)["status"], "unknown", key)
        bad = copy.deepcopy(output)
        bad["arguments"][0]["position"] = False
        self.assertEqual(check_query_output(self.payload, self.ids["guarded_snapshot"], conversion, bad)["status"], "unknown")
        self.assertEqual(check_query_output(self.payload, self.ids["reordered_snapshot"], conversion, output)["status"], "unknown")
        self.assertEqual(check_query_output(self.payload, self.ids["guarded_snapshot"], None, output)["status"], "unknown")

    def test_wrong_object_intervening_call_and_unsupported_source(self):
        contracts = self.contracts("guarded_snapshot")
        for name in ("wrong_query_object", "query_not_adjacent", "query_pointer_alias", "ambiguous_query_role",
                     "result_discarded", "good", "changed_value"):
            self.assertEqual(check_query_output(self.payload, self.ids[name], *contracts)["status"], "unknown", name)
        before = copy.deepcopy(self.payload)
        check_query_output(self.payload, self.ids["guarded_snapshot"], *contracts)
        self.assertEqual(before, self.payload)
        self.assertEqual(check_query_output(self.payload, self.ids["guarded_snapshot"], *contracts,
                                            max_ast_nodes=1)["status"], "unknown")
