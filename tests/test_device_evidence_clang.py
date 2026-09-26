"""Unmocked real-AST bundle boundary: launch binding is not device evidence."""
from pathlib import Path
import shutil
import unittest

from wavebridge.analysis.launch_facts import inspect
from wavebridge.device_evidence import collect as collect_evidence, collect_rmsnorm
from wavebridge.frontend.clang_ast import collect
from wavebridge.verification.getter_returns import _hash


@unittest.skipUnless(shutil.which("clang++"), "requires real clang++")
class DeviceEvidenceClangTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        artifact = collect(Path(__file__).parent / "fixtures/lambda_launch.cu", shutil.which("clang++"),
                           ["-std=c++17", "--cuda-host-only", "-nocudainc", "-nocudalib"],
                           "target", full_translation_unit=True, dependency_binding="required")
        if artifact["status"] != "collected":
            raise AssertionError(artifact)
        cls.root = artifact["ast_roots"][0]
        kernel = artifact["function_locations"][0]["id"]
        site = inspect(cls.root, kernel)["sites"][0]
        binding = {"ast_root_sha256": _hash(cls.root), "kernel_declaration_id": kernel,
                   "launch_id": site["launch_id"]}
        cls.protocol = {"schema_version": "device-integer-protocol/v1", "selection": {
            **binding, "schema_version": "launch-selection/v1",
            "configuration_declaration_id": site["configuration_declaration_id"],
            "configuration_expression_ids": [a["id"] for a in site["configuration_arguments"]]},
            "row_binding": {**binding, "schema_version": "row-coordinate-assumptions/v1"},
            "thread_binding": {**binding, "schema_version": "thread-start-assumptions/v1"},
            "integer_types": {"int": {"bits": 32, "signed": True}}, "sizeof_bytes": {"float": 4},
            "int_bits": 32, "use_host_guard_assumptions": True}

    def test_real_paired_launch_does_not_supply_missing_device_protocol(self):
        result = collect_evidence(self.root, self.protocol)
        self.assertEqual("unknown", result["status"])
        self.assertEqual("checked", result["checks"]["launch_binding"]["status"])
        row = result["checks"]["row_offsets"]
        self.assertEqual("workgroup_coordinate_protocol_missing", row["checks"]["row"]["reason"])
        self.assertNotIn("shared_storage", result["checks"])
        self.assertFalse(result["all_selected_integer_checks_passed"])
        self.assertFalse(result["deployable"])

    def test_wrong_real_slot_selection_stops_before_device_checks(self):
        selection = {**self.protocol["selection"], "configuration_expression_ids":
                     self.protocol["selection"]["configuration_expression_ids"][::-1]}
        result = collect_evidence(self.root, {**self.protocol, "selection": selection})
        self.assertEqual("launch_binding_not_checked", result["reason"])
        self.assertNotIn("row_offsets", result["checks"])
        self.assertFalse(result["deployable"])

    def test_rmsnorm_composition_does_not_upgrade_unknown_integer_path(self):
        result = collect_rmsnorm(self.root, self.protocol)
        self.assertEqual("integer_evidence_incomplete", result["reason"])
        self.assertEqual("unknown", result["status"])
        self.assertFalse(result["all_selected_relations_connected"])
        self.assertNotIn("output_structure", result["checks"])


if __name__ == "__main__":
    unittest.main()
