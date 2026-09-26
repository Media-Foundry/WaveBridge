"""Mocked source/integer evidence; real finite route checks, not source proof."""
import copy
import unittest
from unittest.mock import patch

from wavebridge.device_evidence import collect_rmsnorm


class RMSNormEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.protocol = {"int_bits": 32, "sizeof_bytes": {"float": 4}}
        self.chain = {"status": "recovered", "function_id": "kernel", "int_bits": 32,
                      "width": 32, "block_threads": 256, "offsets": [16, 8, 4, 2, 1],
                      "accumulator_declaration_id": "acc", "shared_storage": {
                          "parameter_id": "scratch_arg", "array_declaration_id": "scratch"},
                      "links": [{"caller_id": "kernel", "callee_id": "helper", "parameter_id": "value",
                                 "argument_index": 0, "call_range": {"begin": 100, "end": 110}},
                                {"caller_id": "helper", "callee_id": "xor"},
                                {"caller_id": "xor", "callee_id": "shuffle"}]}
        self.helper = {"status": "recovered", "function_id": "helper", "width": 32, "block_threads": 256,
                       "reduce_declaration_id": "xor", "barrier_declaration_id": "barrier", "writer_lane": 0,
                       "bindings": {"value_parameter_id": "value", "shared_parameter_id": "scratch_arg"},
                       "call_bindings": {"first_reduce": "xor", "final_reduce": "xor", "barrier": "barrier"},
                       "stage_sequence": ["local_reduce", "group_index", "lane_index", "shared_write",
                                          "barrier", "shared_gather", "final_reduce"]}
        prefix = {"source_parameter_id": "input", "output_parameter_id": "out", "count_parameter_id": "count"}
        loops = [{"range": {"begin": pos, "end": pos + 10}, "step": 256,
                  "start": {"declaration_id": "tid"}, "bound": {"declaration_id": "count"}} for pos in (10, 200)]
        self.output = {**prefix, "status": "recovered", "function_id": "kernel", "int_bits": 32,
                       "consumer_declaration_id": "helper", "local_loop": loops[0], "output_loop": loops[1],
                       "operation": {"local": "sum_of_squares", "output": "scale_times_input",
                                     "scale_argument": "total_div_count_plus_epsilon", "shared_argument_id": "scratch"},
                       "local_contribution": {"accumulator_declaration_id": "acc", "consumer_declaration_id": "helper",
                           "input_parameter_id": "input", "input_declaration_id": "input",
                           "consumer": {"callee_declaration_id": "helper", "argument_index": 0,
                                        "call_range": {"begin": 100, "end": 110}}}}
        self.shared = {"helper_declaration_id": "helper", "array_declaration_id": "scratch",
                       "chain_recovery": self.chain,
                       "indexing": {"coordinates": {"helper_recovery": self.helper},
                                    "indexing": {"schema_version": "shared-indexing-check/v1", "status": "checked",
                                                 "width": 32, "block_threads": 256, "groups": 8}},
                       "capacity": {"status": "checked", "required_elements": 8,
                                    "required_bytes": 32, "available_bytes": 128}}
        self.thread = {"start_declaration_id": "tid", "recovery": {"chain": copy.deepcopy(self.chain)}}
        self.integers = {"status": "evidence", "all_selected_integer_checks_passed": True,
                         "remaining_obligations": ["FP", "visibility"], "kernel_declaration_id": "kernel",
                         "launch_id": "launch", "checks": {"shared_storage": self.shared, "row_offsets": {
                             "count_parameter_id": "count", "checks": {"thread": self.thread,
                             "row": {"prefix_recovery": prefix}, "columns": {"loops": [
                                 {"loop_range": l["range"], "parameter_declaration_id": "count"} for l in loops]}}}}}

    def run_bundle(self):
        with patch("wavebridge.device_evidence.collect", return_value=self.integers), \
                patch("wavebridge.device_evidence.recover_output", return_value=self.output):
            return collect_rmsnorm({}, self.protocol)

    def test_connected_models_run_real_routes_without_upgrading_output(self):
        result = self.run_bundle()
        self.assertEqual("evidence", result["status"], result)
        self.assertEqual("checked", result["checks"]["block_routes"]["status"])
        self.assertEqual(32, result["route_binding"]["inputs"]["shared_slots"])
        self.assertEqual("recovered", result["checks"]["output_structure"]["status"])
        self.assertEqual(["FP", "visibility"], result["remaining_obligations"])
        self.assertFalse(result["source_program_checked"])
        self.assertFalse(result["deployable"])

    def test_wrong_stage_list_is_rejected_by_real_route_checker(self):
        self.chain["offsets"] = [16, 8, 4, 2, 2]
        self.thread["recovery"]["chain"] = copy.deepcopy(self.chain)
        result = self.run_bundle()
        self.assertEqual("rejected", result["status"])
        self.assertEqual("xor_routes_not_checked", result["reason"])
        self.assertFalse(result["all_selected_relations_connected"])

    def test_mismatched_chains_or_calls_do_not_select_defaults(self):
        self.chain["offsets"] = [1]
        self.assertEqual("same_invocation_reduction_chains_disagree", self.run_bundle()["reason"])
        self.chain["offsets"] = [16, 8, 4, 2, 1]
        self.helper["call_bindings"]["final_reduce"] = "other"
        self.assertEqual("two_stage_call_sequence_not_bound", self.run_bundle()["reason"])

    def test_wrong_array_or_consumer_is_unknown(self):
        self.output["operation"]["shared_argument_id"] = "other"
        self.assertEqual("output_operation_or_shared_array_not_bound", self.run_bundle()["reason"])
        self.output["consumer_declaration_id"] = "other"
        self.assertEqual("output_consumer_or_accumulator_not_bound", self.run_bundle()["reason"])

    def test_wrong_column_step_or_location_is_unknown(self):
        self.output["output_loop"]["step"] = 32
        self.assertEqual("output_loop_not_bound_to_checked_columns", self.run_bundle()["reason"])
        self.output["output_loop"]["step"] = 256
        self.output["output_loop"]["range"] = {"begin": 999, "end": 1000}
        self.assertEqual("output_loop_not_bound_to_checked_columns", self.run_bundle()["reason"])

    def test_missing_barrier_or_fractional_capacity_is_unknown(self):
        self.shared["capacity"]["available_bytes"] = 127
        self.assertEqual("route_capacity_or_shared_parameter_not_bound", self.run_bundle()["reason"])
        self.helper["stage_sequence"].remove("barrier")
        self.assertEqual("two_stage_call_sequence_not_bound", self.run_bundle()["reason"])

    def test_integer_or_output_unknown_is_not_upgraded(self):
        self.output["status"] = "unknown"
        self.assertEqual("output_structure_not_recovered", self.run_bundle()["reason"])
        self.integers["status"] = "unknown"
        result = self.run_bundle()
        self.assertEqual("integer_evidence_incomplete", result["reason"])
        self.assertNotIn("output_structure", result["checks"])


if __name__ == "__main__":
    unittest.main()
