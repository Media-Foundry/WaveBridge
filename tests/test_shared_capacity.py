"""Conditional capacity tests; synthetic reports are not source proof."""
import json
from pathlib import Path
import tempfile
import unittest

from wavebridge.verification.shared_capacity import check
from wavebridge.shared_capacity_check import run


class SharedCapacityTests(unittest.TestCase):
    def setUp(self):
        self.abi = {"int": {"bits": 32, "signed": True}}
        self.sizes = {"float": 4}
        self.chain = {"status": "recovered", "function_id": "kernel", "int_bits": 32,
                      "width": 32, "block_threads": 256,
                      "shared_storage": {"schema_version": "source-array-binding/v1",
                      "status": "recovered", "storage_kind": "shared_dynamic", "storage_class": "extern",
                      "shared_attribute_present": True, "capacity_status": "launch_bytes_required"}}
        self.site = {"launch_id": "launch", "kernel_declaration_id": "kernel", "configuration_arguments": [
            {}, {}, {"kind": "IntegerLiteral", "value": "128", "type": {"qualType": "int"}}, {}]}

    def test_sufficient_exact_and_short_allocations(self):
        for size, status in ((128, "checked"), (32, "checked"), (31, "rejected"), (0, "rejected")):
            self.site["configuration_arguments"][2]["value"] = str(size)
            result = check(self.chain, self.site, self.abi, self.sizes)
            self.assertEqual(status, result["status"])
            self.assertEqual(32, result["required_bytes"])
            self.assertEqual(size, result["available_bytes"])
            self.assertFalse(result["source_program_checked"])
            self.assertFalse(result["deployable"])

    def test_unknown_binding_abi_and_dynamic_expression(self):
        for field, value in (("function_id", "another"), ("int_bits", 64), ("width", True), ("block_threads", 255)):
            chain = dict(self.chain, **{field: value})
            self.assertEqual("unknown", check(chain, self.site, self.abi, self.sizes)["status"])
        self.assertEqual("unknown", check(self.chain, self.site, self.abi, {})["status"])
        self.site["configuration_arguments"][2] = {"kind": "DeclRefExpr"}
        self.assertEqual("unknown", check(self.chain, self.site, self.abi, self.sizes)["status"])

    def test_static_capacity_does_not_use_launch_bytes(self):
        self.chain["shared_storage"] = {"schema_version": "source-array-binding/v1", "status": "recovered",
            "storage_kind": "shared_static", "extent_elements": 2, "shared_attribute_present": True,
            "capacity_status": "declared_static_extent"}
        result = check(self.chain, self.site, self.abi, self.sizes)
        self.assertEqual("rejected", result["status"])
        self.assertEqual(8, result["available_bytes"])
        self.chain["shared_storage"]["extent_elements"] = 8
        self.assertEqual("checked", check(self.chain, self.site, self.abi, self.sizes)["status"])
        self.chain["shared_storage"]["storage_class"] = "extern"
        self.assertEqual("unknown", check(self.chain, self.site, self.abi, self.sizes)["status"])
        self.chain["shared_storage"]["storage_kind"] = "not_proven_shared"
        self.assertEqual("unknown", check(self.chain, self.site, self.abi, self.sizes)["status"])

    def test_cli_artifact_binding_and_unresolved_launches(self):
        source = {"schema_version": "source-column-evidence/v1", "status": "analyzed",
                  "reduction_chain": self.chain, "launch_facts": {"status": "evidence",
                  "unresolved_sites": [], "sites": [self.site]}}
        abi = {"schema_version": "storage-abi-assumptions/v1", "integer_types": self.abi, "sizeof_bytes": self.sizes}
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            src, abi_file = directory / "source.json", directory / "abi.json"
            abi_file.write_text(json.dumps(abi))
            for index, unresolved in enumerate(([], [{"reason": "unknown_launch"}])):
                source["launch_facts"]["unresolved_sites"] = unresolved
                src.write_text(json.dumps(source))
                output = directory / f"check-{index}.json"
                report = run(src, abi_file, output)
                self.assertEqual("unknown" if unresolved else "checked", report["status"])
                self.assertEqual(64, len(report["source_report_sha256"]))
                with self.assertRaises(FileExistsError):
                    run(src, abi_file, output)
            source["launch_facts"]["sites"] = []
            src.write_text(json.dumps(source))
            self.assertEqual("unknown", run(src, abi_file, directory / "empty.json")["status"])
            source["launch_facts"]["unresolved_sites"] = []
            source["launch_facts"]["sites"] = [self.site, self.site]
            src.write_text(json.dumps(source))
            self.assertEqual("unknown", run(src, abi_file, directory / "duplicate.json")["status"])

    def test_missing_launch_id_and_inconsistent_storage_stay_unknown(self):
        self.site["launch_id"] = None
        self.assertEqual("unknown", check(self.chain, self.site, self.abi, self.sizes)["status"])
        self.site["launch_id"] = "launch"
        for key in ("schema_version", "shared_attribute_present", "capacity_status", "storage_class"):
            value = self.chain["shared_storage"].pop(key)
            self.assertEqual("unknown", check(self.chain, self.site, self.abi, self.sizes)["status"])
            self.chain["shared_storage"][key] = value
