"""Mocked child checkers test orchestration, not real source/device correctness."""
import copy
import unittest
from unittest.mock import patch

from wavebridge.device_evidence import collect
from wavebridge.verification.getter_returns import _hash


class DeviceEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.root = {"kind": "TranslationUnitDecl"}
        binding = {"ast_root_sha256": _hash(self.root), "kernel_declaration_id": "k", "launch_id": "l"}
        self.protocol = {"schema_version": "device-integer-protocol/v1", "selection": dict(binding),
                         "row_binding": dict(binding), "thread_binding": dict(binding),
                         "integer_types": {"int": {"bits": 32, "signed": True}},
                         "sizeof_bytes": {"float": 4}, "int_bits": 32,
                         "use_host_guard_assumptions": True}
        common = {"root": _hash(self.root), "integer_types": _hash(self.protocol["integer_types"])}
        self.thread = {"schema_version": "conditional-thread-start-check/v1", "status": "checked",
                       "kernel_declaration_id": "k", "launch_id": "l", "int_bits": 32,
                       "input_sha256": {**common, "binding": _hash(binding)}}
        self.offsets = {"status": "checked", "checks": {"thread": self.thread}, "input_sha256": {
            **common, "row_binding": _hash(binding), "thread_binding": _hash(binding),
            "int_bits": _hash(32), "kernel_id": _hash("k"), "launch_id": _hash("l"),
            "use_host_guard_assumptions": _hash(True)}}
        self.shared = {"status": "checked", "kernel_declaration_id": "k", "launch_id": "l",
                       "input_sha256": {**common, "binding": _hash(binding)},
                       "sizeof_bytes_sha256": _hash(self.protocol["sizeof_bytes"])}
        self.paired = {"status": "checked", "kernel_declaration_id": "k", "launch_id": "l",
                       "input_sha256": {"root": _hash(self.root), "selection": _hash(binding)}}

    def run_bundle(self):
        with patch("wavebridge.device_evidence.check_launch", return_value=self.paired), \
                patch("wavebridge.device_evidence.check_offsets", return_value=self.offsets) as offsets, \
                patch("wavebridge.device_evidence.check_shared", return_value=self.shared) as shared:
            result = collect(self.root, self.protocol)
        return result, offsets, shared

    def test_only_fresh_thread_is_forwarded_and_result_is_not_proof(self):
        result, _, shared = self.run_bundle()
        self.assertEqual("evidence", result["status"])
        self.assertIs(self.thread, shared.call_args.args[1])
        self.assertTrue(result["all_selected_integer_checks_passed"])
        self.assertFalse(result["deployable"])
        self.assertFalse(result["source_program_checked"])
        self.assertTrue(result["remaining_obligations"])

    def test_invalid_protocol_stops_before_children(self):
        for key in ("selection", "thread_binding", "row_binding"):
            original = copy.deepcopy(self.protocol[key])
            self.protocol[key]["launch_id"] = "other"
            result, offsets, shared = self.run_bundle()
            self.assertEqual("unknown", result["status"])
            offsets.assert_not_called()
            shared.assert_not_called()
            self.protocol[key] = original

    def test_upstream_unknown_or_rejection_does_not_call_dependents(self):
        original = self.paired
        for status in ("unknown", "rejected"):
            self.paired = {"status": status}
            result, offsets, shared = self.run_bundle()
            self.assertEqual(status, result["status"])
            offsets.assert_not_called()
            shared.assert_not_called()
        self.paired = original
        self.offsets["status"] = "unknown"
        result, _, shared = self.run_bundle()
        self.assertEqual("unknown", result["status"])
        shared.assert_not_called()

    def test_stale_fresh_thread_or_offset_is_not_forwarded(self):
        self.thread["input_sha256"]["root"] = "stale"
        result, _, shared = self.run_bundle()
        self.assertEqual("fresh_thread_binding_mismatch", result["reason"])
        shared.assert_not_called()
        self.offsets["input_sha256"]["launch_id"] = _hash("other")
        self.assertEqual("fresh_offset_input_binding_mismatch", self.run_bundle()[0]["reason"])

    def test_fresh_launch_binding_mismatch_stops_children(self):
        self.paired["launch_id"] = "other"
        result, offsets, shared = self.run_bundle()
        self.assertEqual("fresh_launch_input_binding_mismatch", result["reason"])
        offsets.assert_not_called()
        shared.assert_not_called()

    def test_shared_unknown_rejection_and_mismatch_remain_fail_closed(self):
        for status in ("unknown", "rejected"):
            self.shared["status"] = status
            result = self.run_bundle()[0]
            self.assertEqual(status, result["status"])
            self.assertFalse(result["all_selected_integer_checks_passed"])
        self.shared["status"] = "checked"
        self.shared["launch_id"] = "other"
        self.assertEqual("fresh_shared_input_binding_mismatch", self.run_bundle()[0]["reason"])

    def test_missing_or_mistyped_protocol_is_unknown(self):
        for protocol in ({}, None, {**self.protocol, "int_bits": True},
                         {**self.protocol, "use_host_guard_assumptions": 1}):
            self.assertEqual("unknown", collect(self.root, protocol)["status"])


if __name__ == "__main__":
    unittest.main()
