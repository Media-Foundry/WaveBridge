"""Real native AST composition with explicitly hypothetical API contracts."""
import copy
import os
from pathlib import Path
import unittest

from wavebridge.frontend.native_captures import collect
from wavebridge.frontend.clang_ast import _walk
from wavebridge.verification.field_snapshot import check_query_object, check_query_output, check_query_initializer, check_query_initializer_to_statement, FIELD_READ_PREMISE
from wavebridge.verification.normal_return_guard import check_enum_binding, check_local_equality
from wavebridge.verification.field_snapshot import check_query_power_minimum, check_query_power_quotient, check_guarded_query_constructor
from wavebridge.verification.field_snapshot import check_guarded_query_constructor_copy

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

    def source_guard_selection(self, name):
        args = self.quotient_selection(name, name + "_caller")
        function = next(n for n in _walk(self.payload["ast"]) if n.get("id") == args[3]["callee_id"])
        guard = next(n["id"] for n in _walk(function) if n.get("kind") == "IfStmt")
        return args, guard

    def test_source_guard_supplies_domain_without_external_numeric_protocol(self):
        args, guard = self.source_guard_selection("source_gate")
        contracts = self.contracts("guarded_snapshot")
        result = check_query_power_quotient(self.payload, *args, *contracts, query_guard_id=guard)
        self.assertEqual(result["status"], "checked", result)
        self.assertTrue(result["division_safe_under_source_guard"])
        self.assertFalse(result["division_safe_under_domain_assumption"])
        self.assertEqual(result["conditional_quotient_interval"], {"lower": 4, "upper": 4})
        self.assertNotIn("external_query_domain_contract", result)
        self.assertFalse(result["deployable"])
        self.assertTrue(any("noreturn" in a for a in result["assumptions"]))
        self.assertEqual(check_query_power_quotient(self.payload, *args, *contracts)["status"], "unknown")
        self.assertEqual(check_query_power_quotient(self.payload, *args, *contracts,
                         query_guard_id=guard, query_domain_contract={})["status"], "unknown")

    def test_source_guard_zero_or_invalid_control_is_not_accepted(self):
        contracts = self.contracts("guarded_snapshot")
        for name in ("source_gate_zero", "source_gate_wrong", "source_gate_returns", "source_gate_write",
                     "source_gate_changed_condition"):
            args, guard = self.source_guard_selection(name)
            result = check_query_power_quotient(self.payload, *args, *contracts, query_guard_id=guard)
            self.assertEqual(result["status"], "rejected" if name == "source_gate_zero" else "unknown", (name, result))
            self.assertFalse(result["division_safe_under_source_guard"])

    def test_source_guard_identity_budget_and_input_immutability(self):
        args, guard = self.source_guard_selection("source_gate")
        contracts = self.contracts("guarded_snapshot")
        before = copy.deepcopy(self.payload)
        check_query_power_quotient(self.payload, *args, *contracts, query_guard_id=guard)
        self.assertEqual(before, self.payload)
        for selected in ("missing", self.source_guard_selection("source_gate_wrong")[1]):
            self.assertEqual(check_query_power_quotient(self.payload, *args, *contracts, query_guard_id=selected)["status"], "unknown")
        self.assertEqual(check_query_power_quotient(self.payload, *args, *contracts,
                         query_guard_id=guard, max_ast_nodes=1)["status"], "unknown")

    def constructor_args(self, name):
        args, guard = self.source_guard_selection(name)
        function = next(n for n in _walk(self.payload["ast"]) if n.get("id") == args[3]["callee_id"])
        obj = next(n["id"] for n in _walk(function) if n.get("kind") == "VarDecl" and n.get("name") == "composed_dims")
        abi = {"int": {"bits": 32, "signed": True}, "unsigned int": {"bits": 32, "signed": False}}
        return (*args[:3], obj, args[3], *self.contracts("guarded_snapshot"), abi), guard

    def test_constructor_fields_use_real_mapping_not_field_names(self):
        for name, expected in (("constructed_guard", [32, 4, 1]), ("constructed_swap", [4, 32, 1])):
            args, guard = self.constructor_args(name)
            report = check_guarded_query_constructor(self.payload, *args, query_guard_id=guard)
            self.assertEqual(report["status"], "checked", report)
            self.assertTrue(report["field_domains_under_source_guard"])
            self.assertEqual([f["interval"] for f in report["fields"]], [{"lower": v, "upper": v} for v in expected])
            self.assertFalse(report["post_construction_history_checked"])
            self.assertFalse(report["launch_binding_checked"])
            self.assertFalse(report["deployable"])

    def copy_args(self, name):
        args, guard = self.constructor_args(name)
        function = next(n for n in _walk(self.payload["ast"]) if n.get("id") == args[4]["callee_id"])
        copies = [n["id"] for n in _walk(function) if n.get("kind") == "CXXConstructExpr"
                  and "const " in n.get("ctorType", {}).get("qualType", "")]
        return args, guard, copies

    def test_copy_domains_are_conditional_and_cover_all_switch_references(self):
        args, guard, copies = self.copy_args("copied_guard")
        self.assertEqual(len(copies), 2)
        before = copy.deepcopy(self.payload)
        for selected in copies:
            report = check_guarded_query_constructor_copy(self.payload, *args,
                         query_guard_id=guard, copy_expression_id=selected)
            self.assertEqual(report["status"], "checked", report)
            self.assertEqual([f["interval"]["lower"] for f in report["fields"]], [32, 4, 1])
            self.assertEqual(report["invariant"]["static_copy_count"], 2)
            self.assertIsNone(report["instantiated_function_id"])
            self.assertEqual(report["input_sha256"]["instantiated_function_id"],
                             report["checks"]["uses"]["input_sha256"]["instantiated_function_id"])
            self.assertTrue(report["selected_source_address_publication_not_observed_in_supported_ast_subset"])
            self.assertEqual(report["field_values_preserved_to_selected_copy_evaluation"], "conditional")
            for key in ("deployable", "source_program_checked", "launch_binding_checked",
                        "runtime_object_provenance_verified", "selected_copy_reachability_proved",
                        "other_argument_and_cleanup_purity_checked"):
                self.assertFalse(report[key])
        self.assertEqual(self.payload, before)

    def test_copy_rejects_explicit_alias_writes_lifetime_asm_and_publication(self):
        for name in ("copied_write", "copied_alias", "copied_destroy", "copied_asm",
                     "copied_capture", "copied_ctor_escape", "copied_copy_escape"):
            args, guard, copies = self.copy_args(name)
            report = check_guarded_query_constructor_copy(self.payload, *args,
                         query_guard_id=guard, copy_expression_id=copies[0])
            self.assertEqual(report["status"], "unknown", (name, report))
            self.assertFalse(report["copy_field_domains_under_model"])

    def test_retained_pointer_effect_is_excluded_by_model_not_proved_absent(self):
        args, guard, copies = self.copy_args("copied_retained")
        report = check_guarded_query_constructor_copy(self.payload, *args,
                     query_guard_id=guard, copy_expression_id=copies[0])
        self.assertEqual(report["status"], "checked", report)
        self.assertTrue(report["restricted_object_provenance_assumed"])
        self.assertFalse(report["runtime_object_provenance_verified"])
        self.assertNotIn("syntactic_no_alias_generation_established", report)
        self.assertTrue(any("stale stack addresses" in a for a in report["assumptions"]))
        self.assertFalse(report["source_program_checked"])

    def test_copy_selection_and_budget_fail_closed(self):
        args, guard, copies = self.copy_args("copied_guard")
        for selected, budget in (("missing", 1000000), (copies[0], 1),
                                  (self.copy_args("copied_retained")[2][0], 1000000)):
            report = check_guarded_query_constructor_copy(self.payload, *args,
                         query_guard_id=guard, copy_expression_id=selected, max_ast_nodes=budget)
            self.assertEqual(report["status"], "unknown", report)

    def test_constructor_rejects_history_escape_wrong_source_and_body_effects(self):
        for name in ("constructed_write", "constructed_alias", "constructed_wrong", "constructed_body"):
            args, guard = self.constructor_args(name)
            report = check_guarded_query_constructor(self.payload, *args, query_guard_id=guard)
            self.assertEqual(report["status"], "unknown", (name, report))
            self.assertFalse(report["field_domains_under_source_guard"])

    def test_constructor_wrong_identity_ABI_budget_and_input_immutability(self):
        args, guard = self.constructor_args("constructed_guard")
        before = copy.deepcopy(self.payload)
        check_guarded_query_constructor(self.payload, *args, query_guard_id=guard)
        self.assertEqual(before, self.payload)
        for obj in ("missing", self.constructor_args("constructed_swap")[0][3]):
            bad = list(args); bad[3] = obj
            self.assertEqual(check_guarded_query_constructor(self.payload, *bad, query_guard_id=guard)["status"], "unknown")
        bad = list(args); bad[-1] = {}
        self.assertEqual(check_guarded_query_constructor(self.payload, *bad, query_guard_id=guard)["status"], "unknown")
        self.assertEqual(check_guarded_query_constructor(self.payload, *args, query_guard_id=guard, max_ast_nodes=1)["status"], "unknown")

    def test_constructor_hidden_semantic_literal_conflict_is_rejected(self):
        original = self.payload
        try:
            self.payload = copy.deepcopy(original)
            args, guard = self.constructor_args("constructed_guard")
            obj = next(n for n in _walk(self.payload["ast"]) if n.get("id") == args[3])
            literal = next(n for n in _walk(obj) if n.get("kind") == "IntegerLiteral")
            conflict = copy.deepcopy(literal); conflict["value"] = "2"
            self.payload["ast"]["array_filler"] = [conflict]
            # Rebind external premises to the modified payload so rejection
            # cannot be explained by an unrelated stale protocol hash.
            args, guard = self.constructor_args("constructed_guard")
            result = check_guarded_query_constructor(self.payload, *args, query_guard_id=guard)
            self.assertEqual(result["status"], "unknown", result)
            self.assertEqual(result["reason"], "literal_identity_conflict", result)
        finally:
            self.payload = original

    def test_guard_shared_literals_conflicts_and_strict_flags(self):
        functions = [n for n in _walk(self.payload["ast"]) if n.get("kind") == "FunctionDecl" and n.get("name") == "shared_literal_guard"]
        self.assertEqual(len(functions), 2)
        for function in functions:
            local = next(n["id"] for n in _walk(function) if n.get("kind") == "VarDecl")
            guard = next(n for n in _walk(function) if n.get("kind") == "IfStmt")
            target = next(n["id"] for n in _walk(function) if n.get("kind") == "BinaryOperator" and n.get("opcode") == "=")
            result = check_local_equality(self.payload["ast"], local, guard["id"], target)
            self.assertEqual(result["status"], "checked", result)
            self.assertEqual(result["terminal_reference_occurrences"], 2)
            literal_id = guard["inner"][0]["inner"][1]["id"]
            bad = copy.deepcopy(self.payload["ast"])
            occurrences = [n for n in _walk(bad) if n.get("id") == literal_id]
            self.assertEqual(len(occurrences), 2)
            occurrences[0]["value"] = "33"
            self.assertEqual(check_local_equality(bad, local, guard["id"], target)["status"], "unknown")
            bad = copy.deepcopy(self.payload["ast"])
            terminal_id = guard["inner"][1]["inner"][0]["inner"][0]["id"]
            next(n for n in _walk(bad) if n.get("id") == terminal_id)["referencedDecl"]["id"] = "conflicting-callee"
            self.assertEqual(check_local_equality(bad, local, guard["id"], target)["status"], "unknown")
            for flag in (0, "", True):
                bad = copy.deepcopy(self.payload["ast"])
                next(n for n in _walk(bad) if n.get("id") == guard["id"])["hasElse"] = flag
                self.assertEqual(check_local_equality(bad, local, guard["id"], target)["status"], "unknown")

    def test_quotient_domain_is_an_explicit_invocation_bound_assumption(self):
        args = (*self.quotient_selection(), *self.contracts("guarded_snapshot"))
        symbolic = check_query_power_quotient(self.payload, *args)
        origins = symbolic["checks"]["origins"]
        contract = {"schema_version": "query-value-domain/v1",
                    "payload_sha256": origins["input_sha256"]["payload"],
                    "output_contract_sha256": origins["input_sha256"]["output_contract"],
                    "query_origin": origins["state_relation"]["query_operand_origin"],
                    "power_selection": args[3], "scope": "this_query_invocation_in_selected_guarded_call",
                    "basis": "explicit_external_assumption_not_inferred_from_measurements", "lower": 32, "upper": 32}
        result = check_query_power_quotient(self.payload, *args, query_domain_contract=contract)
        self.assertEqual(result["status"], "checked", result)
        self.assertEqual(result["conditional_quotient_interval"], {"lower": 4, "upper": 4})
        self.assertTrue(result["division_safe_under_domain_assumption"])
        self.assertFalse(result["division_safety_established"])
        self.assertFalse(result["query_domain_contract_verified"])
        self.assertFalse(result["launch_dimension_usable"])
        self.assertEqual(result["unresolved_obligations"], symbolic["unresolved_obligations"])
        for key, value in (("lower", 0), ("payload_sha256", "wrong"), ("basis", "observed_once"),
                           ("lower", True), ("scope", "all_calls")):
            bad = {**contract, key: value}
            result = check_query_power_quotient(self.payload, *args, query_domain_contract=bad)
            self.assertNotEqual(result["status"], "checked", (key, result))
            self.assertFalse(result["division_safe_under_domain_assumption"])
        bad = copy.deepcopy(contract)
        bad["query_origin"]["getter_call_id"] = "other_dynamic_call"
        self.assertEqual(check_query_power_quotient(self.payload, *args, query_domain_contract=bad)["status"], "unknown")

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
