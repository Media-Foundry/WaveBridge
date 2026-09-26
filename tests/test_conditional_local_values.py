"""Transparent composition fixtures; these are not source or floating-point proofs."""

import copy
import unittest
from unittest.mock import patch

from wavebridge.device_evidence import (
    _conditional_local_values,
    compare_rmsnorm_local_values,
)


def comparison_fixture():
    template = {
        "accumulator": {"kind": "VarDecl", "type": {"qualType": "float"},
                        "inner": [{"kind": "FloatingLiteral",
                                   "type": {"qualType": "float"}, "value": "0"}]},
        "loop": {"kind": "ForStmt", "inner": [{
            "kind": "CompoundAssignOperator", "opcode": "+=",
            "type": {"qualType": "float"},
            "computeLHSType": {"qualType": "float"},
            "computeResultType": {"qualType": "float"},
            "fpoptions": {"AllowFPContract": False},
        }]},
    }
    checks = {"local_structure": {"status": "evidence", "local_structure_equal": True,
                                   "checks": {}},
              "load_index_relation": {"status": "checked", "normal_form": "fixture"}}
    for side in ("source", "target"):
        checks[side] = {
            "input_sha256": {"root": f"{side}-root", "protocol": f"{side}-protocol"},
            "kernel_declaration_id": f"{side}-kernel", "launch_id": f"{side}-launch",
        }
        checks["local_structure"]["checks"][side] = {
            "role_bindings": {
                "input": {"declaration_id": f"{side}-input"},
                "bound": {"declaration_id": f"{side}-count"},
            },
            "template": copy.deepcopy(template),
        }
    return {
        "schema_version": "rmsnorm-route-comparison/v5", "status": "evidence",
        "reason": None, "source_program_checked": False, "deployable": False,
        "leaf_value_correspondence": "not_established",
        "checks": checks, "remaining_obligations": {},
    }


def assumptions_for(comparison):
    assumptions = {
        "schema_version": "paired-local-input-assumptions/v1",
        "common_count_and_coordinates_assumed": True,
        "coordinate_domain": "common_tuple_in_both_checked_domains",
        "input_origin": "kernel_entry_parameter_before_row_offset",
        "same_immutable_logical_input_array_assumed": True,
        "valid_complete_local_executions_assumed": True,
        "evaluation_model":
            "common_total_deterministic_order_preserving_typed_AST_interpretation",
        "evidence_reference": "fixture-only paired abstract input premise",
    }
    for side in ("source", "target"):
        report = comparison["checks"][side]
        snapshot = comparison["checks"]["local_structure"]["checks"][side]
        assumptions[side] = {
            "root_sha256": report["input_sha256"]["root"],
            "protocol_sha256": report["input_sha256"]["protocol"],
            "kernel_declaration_id": report["kernel_declaration_id"],
            "launch_id": report["launch_id"],
            "input_parameter_id": snapshot["role_bindings"]["input"]["declaration_id"],
            "count_parameter_id": snapshot["role_bindings"]["bound"]["declaration_id"],
        }
    return assumptions


class ConditionalLocalValuesTests(unittest.TestCase):
    def test_success_is_conditional_abstract_loop_exit_only(self):
        comparison = comparison_fixture()
        result = _conditional_local_values(comparison, assumptions_for(comparison))
        self.assertEqual(result["status"], "checked", result)
        self.assertEqual(
            result["conclusion"]["property"],
            "equal_loop_exit_accumulators_in_the_common_abstract_interpretation",
        )
        self.assertFalse(result["external_premises_verified"])
        self.assertFalse(result["actual_FP_semantics_verified"])
        self.assertFalse(result["source_program_checked"])
        self.assertFalse(result["deployable"])

    def test_strict_booleans_exact_keys_and_no_circular_output_assumption(self):
        comparison = comparison_fixture()
        base = assumptions_for(comparison)
        cases = []
        for key in ("common_count_and_coordinates_assumed",
                    "same_immutable_logical_input_array_assumed",
                    "valid_complete_local_executions_assumed"):
            changed = copy.deepcopy(base)
            changed[key] = 1
            cases.append(changed)
        changed = copy.deepcopy(base)
        del changed["coordinate_domain"]
        cases.append(changed)
        changed = copy.deepcopy(base)
        changed["output_equal"] = True
        cases.append(changed)
        for index, assumptions in enumerate(cases):
            with self.subTest(index=index):
                result = _conditional_local_values(comparison, assumptions)
                self.assertEqual(result["status"], "unknown", result)
                self.assertNotIn("conclusion", result)

    def test_each_side_binding_mismatch_is_unknown(self):
        for side in ("source", "target"):
            for key in ("root_sha256", "protocol_sha256", "kernel_declaration_id",
                        "launch_id", "input_parameter_id", "count_parameter_id"):
                comparison = comparison_fixture()
                assumptions = assumptions_for(comparison)
                assumptions[side][key] = "wrong"
                with self.subTest(side=side, key=key):
                    result = _conditional_local_values(comparison, assumptions)
                    self.assertEqual(result["status"], "unknown", result)
                    self.assertNotIn("conclusion", result)

    def test_template_seed_and_explicit_fp_differences_are_unknown(self):
        mutations = [
            lambda template: template.update(different_shape=True),
            lambda template: template["accumulator"]["inner"][0].update(value="1"),
            lambda template: template["loop"]["inner"][0]["fpoptions"].update(
                AllowFPContract=True),
        ]
        for index, mutate in enumerate(mutations):
            comparison = comparison_fixture()
            assumptions = assumptions_for(comparison)
            mutate(comparison["checks"]["local_structure"]["checks"]["target"]["template"])
            with self.subTest(index=index):
                result = _conditional_local_values(comparison, assumptions)
                self.assertEqual(result["status"], "unknown", result)
                self.assertNotIn("conclusion", result)

    def test_fresh_parent_unknown_propagates_without_conditional_upgrade(self):
        comparison = comparison_fixture()
        assumptions = assumptions_for(comparison)
        for status in ("unknown", "rejected"):
            parent = copy.deepcopy(comparison)
            parent["status"] = status
            result = _conditional_local_values(parent, assumptions)
            self.assertEqual(result["status"], "unknown", result)
            self.assertNotIn("conclusion", result)
        comparison["checks"]["load_index_relation"]["status"] = "unknown"
        result = _conditional_local_values(comparison, assumptions)
        self.assertEqual(result["status"], "unknown", result)

    def test_public_wrapper_freshly_calls_route_comparison(self):
        comparison = comparison_fixture()
        assumptions = assumptions_for(comparison)
        source_root, target_root = {"source": "AST"}, {"target": "AST"}
        source_protocol, target_protocol = {"source": "protocol"}, {"target": "protocol"}
        with patch("wavebridge.device_evidence.compare_rmsnorm_routes",
                   return_value=comparison) as fresh:
            result = compare_rmsnorm_local_values(
                source_root, source_protocol, target_root, target_protocol, assumptions,
                max_ast_nodes=123,
            )
        fresh.assert_called_once_with(source_root, source_protocol, target_root, target_protocol,
                                      max_ast_nodes=123)
        self.assertEqual(result["status"], "evidence", result)
        self.assertEqual(result["schema_version"], "rmsnorm-local-value-comparison/v1")
        self.assertEqual(result["checks"]["conditional_local_values"]["status"], "checked")
        self.assertEqual(result["leaf_value_correspondence"], "not_established")
        self.assertFalse(result["source_program_checked"])
        self.assertFalse(result["deployable"])

    def test_public_wrapper_does_not_hide_fresh_parent_failure(self):
        comparison = comparison_fixture()
        comparison.update(status="unknown", reason="fresh_parent_failed")
        assumptions = assumptions_for(comparison)
        with patch("wavebridge.device_evidence.compare_rmsnorm_routes",
                   return_value=comparison), \
                patch("wavebridge.device_evidence._conditional_local_values") as conditional:
            result = compare_rmsnorm_local_values({}, {}, {}, {}, assumptions)
        conditional.assert_not_called()
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["reason"], "fresh_parent_failed")
        self.assertNotIn("conditional_local_values", result["checks"])


if __name__ == "__main__":
    unittest.main()
