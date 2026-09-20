"""Composition fixtures do not prove source reachability."""
import copy
import unittest
from unittest.mock import patch

from wavebridge.entry_loop_check import check
from wavebridge.verification.column_coverage import check_interval


class EntryLoopCheckTests(unittest.TestCase):
    def setUp(self):
        self.location = {"begin": {"offset": 1}, "end": {"offset": 20}}
        self.call_range = {"begin": {"offset": 30}, "end": {"offset": 40}}
        self.thread = {"kernel_declaration_id": "kernel", "int_bits": 32}
        self.columns = {"status": "checked", "input_sha256": {"root": "hash"}, "loops": [
            {"loop_range": self.location, "coverage": check_interval(1, 1023, list(range(256)), 256)}]}
        self.entry = {"schema_version": "entry-control-obligations/v1", "status": "recovered",
                      "function_id": "kernel", "callee_id": "helper", "call_range": self.call_range,
                      "loop_obligations": [{"range": self.location}],
                      "call_obligations": [{"declaration_id": "getter", "normal_return": "not_established"}]}
        self.chain = {"status": "recovered", "function_id": "kernel", "entry_control": self.entry,
                      "links": [{"caller_id": "kernel", "callee_id": "helper", "call_range": self.call_range}]}

    def run_check(self):
        with patch("wavebridge.entry_loop_check.check_columns", return_value=self.columns), \
                patch("wavebridge.entry_loop_check.recover_chain", return_value=self.chain):
            return check({}, self.thread, {}, {}, use_host_guard_assumptions=True)

    def test_finite_bound_keeps_calls_and_participation_unproved(self):
        result = self.run_check()
        self.assertEqual(result["status"], "checked", result)
        self.assertEqual(result["loops"][0]["max_iterations"], 4)
        self.assertEqual(result["loops"][0]["max_iterations_per_thread"][-1], 3)
        self.assertEqual(result["remaining_call_obligations"], self.entry["call_obligations"])
        self.assertEqual(result["participation"], "not_established")
        self.assertFalse(result["source_program_checked"])
        self.assertFalse(result["deployable"])

    def test_column_failure_and_default_opt_in_short_circuit(self):
        for status in ("unknown", "rejected"):
            with patch("wavebridge.entry_loop_check.check_columns", return_value={"status": status}) as columns, \
                    patch("wavebridge.entry_loop_check.recover_chain") as chain:
                result = check({}, {}, {}, {})
            self.assertEqual(result["status"], status)
            columns.assert_called_once_with({}, {}, {}, {}, use_host_guard_assumptions=False)
            chain.assert_not_called()

    def test_entry_status_and_call_binding_mismatch(self):
        original = copy.deepcopy(self.entry)
        for key, value in (("status", "unknown"), ("callee_id", "other"), ("call_range", {}),
                           ("function_id", "other")):
            self.chain["entry_control"] = {**original, key: value}
            self.assertEqual(self.run_check()["status"], "unknown")

    def test_missing_duplicate_or_unmatched_loop_domain(self):
        for loops in ([], [self.columns["loops"][0], self.columns["loops"][0]],
                      [{"loop_range": {"begin": 99}}]):
            self.columns["loops"] = loops
            self.assertEqual(self.run_check()["status"], "unknown")

    def test_invalid_or_duplicate_obligation_locations(self):
        for obligations in ([], [{"range": {}}], [{"range": self.location}] * 2):
            self.entry["loop_obligations"] = obligations
            self.assertEqual(self.run_check()["status"], "unknown")

    def test_iteration_metadata_must_be_present_and_consistent(self):
        coverage = self.columns["loops"][0]["coverage"]
        for key, value in (("max_iterations", True), ("max_iterations_per_thread", []),
                           ("max_iterations_per_thread", [4]), ("max_iterations", 5)):
            self.columns["loops"][0]["coverage"] = {**coverage, key: value}
            self.assertEqual(self.run_check()["status"], "unknown")


if __name__ == "__main__":
    unittest.main()
