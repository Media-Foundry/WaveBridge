"""Real native AST composition with explicitly hypothetical API contracts."""
import copy
import os
from pathlib import Path
import unittest

from wavebridge.frontend.native_captures import collect
from wavebridge.frontend.clang_ast import _walk
from wavebridge.verification.field_snapshot import check_query_object, check_query_output, check_query_initializer, check_query_initializer_to_statement, FIELD_READ_PREMISE
from wavebridge.verification.normal_return_guard import check_enum_binding
from wavebridge.verification.field_snapshot import check_query_power_minimum, check_query_power_quotient

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
        cls.variables = {n["name"]: n["id"] for n in _walk(cls.payload["ast"]) if n.get("kind") == "VarDecl"}
        cls.targets = {n["name"]: next(c["id"] for body in n["inner"] if body.get("kind") == "CompoundStmt"
                                      for c in body["inner"] if c.get("kind") == "BinaryOperator" and c.get("opcode") == "=")
                       for n in _walk(cls.payload["ast"]) if n.get("kind") == "FunctionDecl" and n.get("name", "").startswith("history_")}

    def composed_selection(self, name="composed_dispatch", caller_name="composed_caller"):
        functions = {n.get("name"): n for n in _walk(self.payload["ast"]) if n.get("kind") == "FunctionDecl"}
        function, caller = functions[name], functions[caller_name]
        variables = {n.get("name"): n["id"] for n in _walk(function) if n.get("kind") == "VarDecl"}
        assignment = next(n["id"] for n in _walk(function) if n.get("kind") == "BinaryOperator" and n.get("opcode") == "=")
        selection = {"caller_id": caller["id"], "callee_id": function["id"], "argument_position": 0,
                     "local_id": next(n["id"] for n in _walk(caller) if n.get("name") == "composed_input"),
                     "guard_id": next(n["id"] for n in _walk(caller) if n.get("kind") == "IfStmt"),
                     "call_id": next(n["id"] for n in _walk(caller) if n.get("kind") == "CallExpr"),
                     "exponent_id": variables["composed_log"], "power_id": variables["composed_power"]}
        return variables["composed_width"], assignment, selection

    def test_minimum_freshly_binds_two_origins_without_inventing_query_range(self):
        result = check_query_power_minimum(self.payload, *self.composed_selection(), *self.contracts("guarded_snapshot"))
        self.assertEqual(result["status"], "checked", result)
        self.assertTrue(result["conditional_assignment_relation"])
        self.assertEqual(result["state_relation"]["power_operand"]["value_set"], [128])
        self.assertEqual(result["checks"]["power"]["entry_values"], [65, 128])
        self.assertEqual(result["state_relation"]["query_operand_origin"], result["checks"]["query"]["value_origin"])
        for field in ("query_numeric_domain", "result_numeric_domain"):
            self.assertIsNone(result[field])
        for field in ("deployable", "source_program_checked", "later_history_checked", "API_protocol_verified"):
            self.assertFalse(result[field])

    def quotient_selection(self, name="composed_dispatch", caller_name="composed_caller"):
        initial, assignment, selection = self.composed_selection(name, caller_name)
        function = next(n for n in _walk(self.payload["ast"]) if n.get("id") == selection["callee_id"])
        quotient = next(n["id"] for n in _walk(function) if n.get("kind") == "VarDecl" and n.get("name") == "composed_quotient")
        return initial, assignment, quotient, selection

    def test_quotient_substitutes_origins_but_does_not_discharge_nonzero(self):
        result = check_query_power_quotient(self.payload, *self.quotient_selection(), *self.contracts("guarded_snapshot"))
        self.assertEqual(result["status"], "checked", result)
        self.assertTrue(result["conditional_quotient_relation"])
        relation = result["quotient_relation"]
        self.assertEqual(relation["numerator"], 128)
        self.assertEqual(relation["denominator"], result["checks"]["origins"]["state_relation"])
        self.assertEqual(result["unresolved_obligations"], [{"property": "denominator_nonzero_at_division",
                         "declaration_id": self.quotient_selection()[0], "established": False}])
        self.assertTrue(any("nonzero" in a for a in result["assumptions"]))
        for key in ("division_safety_established", "launch_dimension_usable", "later_history_checked", "source_program_checked", "deployable"):
            self.assertFalse(result[key])
        self.assertIsNone(result["query_numeric_domain"])
        self.assertIsNone(result["quotient_numeric_domain"])

    def test_quotient_rechecks_changed_escaped_and_wrong_denominator(self):
        contracts = self.contracts("guarded_snapshot")
        for name in ("quotient_changed", "quotient_wrong", "quotient_escaped"):
            result = check_query_power_quotient(self.payload, *self.quotient_selection(name, name + "_caller"), *contracts)
            self.assertEqual(result["status"], "unknown", (name, result))
            self.assertEqual(result["checks"]["origins"]["status"], "checked", result)
            self.assertFalse(result["conditional_quotient_relation"])

    def test_quotient_wrong_identity_budget_contract_and_input_immutability(self):
        contracts = self.contracts("guarded_snapshot")
        initial, assignment, quotient, selection = self.quotient_selection()
        before = copy.deepcopy(self.payload)
        check_query_power_quotient(self.payload, initial, assignment, quotient, selection, *contracts)
        self.assertEqual(before, self.payload)
        other = self.quotient_selection("quotient_wrong", "quotient_wrong_caller")[2]
        for identifier in ("missing", initial, other):
            result = check_query_power_quotient(self.payload, initial, assignment, identifier, selection, *contracts)
            self.assertEqual(result["status"], "unknown", result)
        self.assertEqual(check_query_power_quotient(self.payload, initial, assignment, quotient, selection, *contracts,
                                                 max_ast_nodes=1)["status"], "unknown")
        self.assertEqual(check_query_power_quotient(self.payload, initial, assignment, quotient, selection,
                                                 None, contracts[1])["status"], "unknown")

    def test_minimum_changed_source_and_missing_contract_stay_unknown(self):
        contracts = self.contracts("guarded_snapshot")
        for name in ("composed_write", "composed_max", "composed_escape"):
            result = check_query_power_minimum(self.payload, *self.composed_selection(name, name + "_caller"), *contracts)
            self.assertEqual(result["status"], "unknown", (name, result))
            self.assertFalse(result["conditional_assignment_relation"])
        self.assertEqual(check_query_power_minimum(self.payload, *self.composed_selection(), None, contracts[1])["status"], "unknown")

    def test_minimum_selection_identity_ABI_budget_and_immutability(self):
        contracts = self.contracts("guarded_snapshot")
        initial, assignment, selection = self.composed_selection()
        before = copy.deepcopy(self.payload)
        check_query_power_minimum(self.payload, initial, assignment, selection, *contracts)
        self.assertEqual(before, self.payload)
        for key, value in (("power_id", initial), ("callee_id", self.ids["history_good"]),
                           ("call_id", "missing"), ("argument_position", True), ("result_values", [128])):
            result = check_query_power_minimum(self.payload, initial, assignment, {**selection, key: value}, *contracts)
            self.assertEqual(result["status"], "unknown", (key, result))
        for kwargs in ({"max_ast_nodes": 1}, {"int_bits": 16}, {"int_bits": True}):
            self.assertEqual(check_query_power_minimum(self.payload, initial, assignment, selection, *contracts, **kwargs)["status"], "unknown")

    def test_history_stops_before_target_evaluation(self):
        contracts = self.contracts("guarded_snapshot")
        result = check_query_initializer_to_statement(self.payload, self.variables["history_value"],
                                                       self.targets["history_good"], *contracts)
        self.assertEqual(result["status"], "checked", result)
        self.assertTrue(result["value_preserved_to_target_entry"])
        self.assertFalse(result["target_statement_checked"])
        self.assertIsNone(result["runtime_return_interval"])
        self.assertTrue(result["preservation_check"]["excluded_target_and_later_reference_ids"])
        self.assertEqual(result["preservation_check"]["reference_audit_scope"], "before_first_target_entry_only")
        self.assertEqual(result["value_origin"], result["initializer_check"]["initial_value_origin"])

    def test_history_rejects_earlier_writes_escape_and_later_control(self):
        contracts = self.contracts("guarded_snapshot")
        for variable, function in (("history_written", "history_write"), ("history_escaped", "history_escape"),
                                   ("history_jumped", "history_jump"), ("history_captured", "history_lambda")):
            result = check_query_initializer_to_statement(self.payload, self.variables[variable], self.targets[function], *contracts)
            self.assertEqual(result["status"], "unknown", (function, result))
            self.assertFalse(result["value_preserved_to_target_entry"])
        self.assertEqual(check_query_initializer_to_statement(self.payload, self.variables["history_value"],
                         self.targets["history_write"], *contracts)["status"], "unknown")

    def test_history_identity_budget_and_immutable_input(self):
        contracts = self.contracts("guarded_snapshot")
        before = copy.deepcopy(self.payload)
        args = (self.variables["history_value"], self.targets["history_good"], *contracts)
        check_query_initializer_to_statement(self.payload, *args)
        self.assertEqual(before, self.payload)
        self.assertEqual(check_query_initializer_to_statement(self.payload, *args, max_ast_nodes=1)["status"], "unknown")
        self.assertEqual(check_query_initializer_to_statement(self.payload, args[0], "missing", *contracts)["status"], "unknown")

    def test_initializer_relation_stops_before_later_writes(self):
        for name, getter in (("local_good", "guarded_snapshot"), ("local_other", "reordered_snapshot"),
                             ("local_nested", "guarded_snapshot"), ("local_branch", "guarded_snapshot")):
            result = check_query_initializer(self.payload, self.variables[name], *self.contracts(getter))
            self.assertEqual(result["status"], "checked", result)
            self.assertTrue(result["conditional_initial_value_relation"])
            for key in ("history_preserved_to_use", "getter_purity_verified", "initializer_reached_or_completed", "branch_reachability_proved",
                        "runtime_implementation_linkage_verified", "source_program_checked", "deployable"):
                self.assertFalse(result[key])
            self.assertIsNone(result["runtime_return_interval"])
        templates = [n["id"] for n in _walk(self.payload["ast"]) if n.get("kind") == "VarDecl" and n.get("name") == "local_template"]
        self.assertEqual(len(templates), 2)
        for identifier in templates:
            result = check_query_initializer(self.payload, identifier, *self.contracts("guarded_snapshot"))
            self.assertEqual(result["status"], "checked", result)
            self.assertEqual(result["callee_reference_occurrences"], 2)

    def test_initializer_unsupported_shapes_and_wrong_protocol(self):
        contracts = self.contracts("guarded_snapshot")
        for name in ("local_static", "local_tls", "local_const", "local_long", "local_comma",
                     "local_indirect", "local_multi", "local_try", "local_other"):
            self.assertEqual(check_query_initializer(self.payload, self.variables[name], *contracts)["status"], "unknown", name)
        self.assertEqual(check_query_initializer(self.payload, self.variables["local_good"], *contracts,
                                                 max_ast_nodes=1)["status"], "unknown")

    def test_initializer_shared_reference_conflicts_and_unique_selection(self):
        contracts = self.contracts("guarded_snapshot")
        identifier = self.variables["local_template"]
        before = copy.deepcopy(self.payload)
        check_query_initializer(self.payload, identifier, *contracts)
        self.assertEqual(before, self.payload)
        variable = next(n for n in _walk(before["ast"]) if n.get("id") == identifier)
        leaf_id = variable["inner"][0]["inner"][0]["inner"][0]["id"]
        refs = [n for n in _walk(before["ast"]) if n.get("id") == leaf_id]
        refs[0]["referencedDecl"]["id"] = "wrong"
        self.assertEqual(check_query_initializer(before, identifier, *contracts)["status"], "unknown")
        duplicate = copy.deepcopy(self.payload)
        duplicate["ast"]["inner"].append(copy.deepcopy(next(n for n in _walk(duplicate["ast"]) if n.get("id") == identifier)))
        self.assertEqual(check_query_initializer(duplicate, identifier, *contracts)["status"], "unknown")

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
