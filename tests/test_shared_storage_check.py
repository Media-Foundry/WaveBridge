import copy
import unittest
from unittest.mock import patch

from wavebridge.shared_storage_check import check


ABI = {"int": {"bits": 32, "signed": True}}
SIZES = {"float": 4}


def byte_literal(value):
    return {"kind": "IntegerLiteral", "value": str(value),
            "type": {"qualType": "int"}, "valueCategory": "prvalue"}


class SharedStorageCompositionTests(unittest.TestCase):
    def setUp(self):
        self.root = {"kind": "TranslationUnitDecl", "inner": []}
        self.thread = {"kernel_declaration_id": "kernel", "launch_id": "launch"}
        self.binding = {"schema_version": "thread-start-assumptions/v1"}
        self.indexing = {
            "schema_version": "conditional-shared-index-check/v1", "status": "checked",
            "helper_declaration_id": "helper", "input_sha256": {"root": "hash"},
            "coordinates": {
                "helper_declaration_id": "helper",
                "helper_recovery": {
                    "function_id": "helper", "width": 32, "block_threads": 256,
                    "bindings": {"value_parameter_id": "value",
                                 "shared_parameter_id": "shared",
                                 "group_declaration_id": "group",
                                 "lane_declaration_id": "lane",
                                 "width_declaration_id": "width",
                                 "block_declaration_id": "block"},
                },
            },
        }
        self.chain = {
            "schema_version": "reduction-chain/v1", "status": "recovered",
            "function_id": "kernel", "int_bits": 32, "width": 32, "block_threads": 256,
            "links": [{"caller_id": "kernel", "callee_id": "helper"}],
            "shared_storage": {
                "schema_version": "source-array-binding/v1", "status": "recovered",
                "parameter_id": "shared", "array_declaration_id": "shared-array",
                "storage_kind": "shared_dynamic", "storage_class": "extern",
                "shared_attribute_present": True, "capacity_status": "launch_bytes_required",
            },
        }
        self.site = {
            "launch_id": "launch", "kernel_declaration_id": "kernel",
            "configuration_arguments": [{}, {}, byte_literal(128), {}],
        }
        self.launches = {"status": "evidence", "sites": [self.site]}

    def run_check(self):
        with patch("wavebridge.shared_storage_check.check_indices",
                   return_value=self.indexing) as indices, \
                patch("wavebridge.shared_storage_check.recover_chain",
                      return_value=self.chain) as chain, \
                patch("wavebridge.shared_storage_check.inspect_launch",
                      return_value=self.launches) as launches:
            result = check(self.root, self.thread, ABI, SIZES, self.binding)
        return result, indices, chain, launches

    def test_dynamic_capacity_128_32_and_31_bytes(self):
        for available, expected in ((128, "checked"), (32, "checked"), (31, "rejected")):
            self.site["configuration_arguments"][2] = byte_literal(available)
            with self.subTest(available=available):
                result, _, _, _ = self.run_check()
                self.assertEqual(result["status"], expected, result)
                self.assertEqual(result["capacity"]["required_bytes"], 32)
                self.assertEqual(result["capacity"]["available_bytes"], available)
                self.assertFalse(result["source_program_checked"])
                self.assertFalse(result["deployable"])

    def test_missing_or_disconnected_storage_is_unknown(self):
        mutations = []
        chain = copy.deepcopy(self.chain); chain.pop("shared_storage")
        mutations.append(chain)
        chain = copy.deepcopy(self.chain); chain["shared_storage"]["array_declaration_id"] = ""
        mutations.append(chain)
        chain = copy.deepcopy(self.chain); chain["shared_storage"]["parameter_id"] = "other"
        mutations.append(chain)
        for chain in mutations:
            with self.subTest(chain=chain):
                self.chain = chain
                self.assertEqual(self.run_check()[0]["status"], "unknown")

    def test_static_extent_uses_same_bound_array_not_launch_bytes(self):
        storage = self.chain["shared_storage"]
        storage.update(storage_kind="shared_static", storage_class=None,
                       capacity_status="declared_static_extent", extent_elements=8)
        self.site["configuration_arguments"][2] = {"kind": "UnknownExpr"}
        self.assertEqual(self.run_check()[0]["status"], "checked")
        storage["extent_elements"] = 7
        self.assertEqual(self.run_check()[0]["status"], "rejected")

    def test_wrong_chain_helper_or_model_is_unknown(self):
        mutations = []
        chain = copy.deepcopy(self.chain); chain["function_id"] = "other-kernel"
        mutations.append(chain)
        chain = copy.deepcopy(self.chain); chain["links"][0]["caller_id"] = "other-kernel"
        mutations.append(chain)
        chain = copy.deepcopy(self.chain); chain["links"][0]["callee_id"] = "other-helper"
        mutations.append(chain)
        chain = copy.deepcopy(self.chain); chain["width"] = 64
        mutations.append(chain)
        chain = copy.deepcopy(self.chain); chain["block_threads"] = 128
        mutations.append(chain)
        for chain in mutations:
            with self.subTest(chain=chain):
                self.chain = chain
                self.assertEqual(self.run_check()[0]["status"], "unknown")

    def test_selected_launch_must_be_unique(self):
        self.launches["sites"] = []
        self.assertEqual(self.run_check()[0]["status"], "unknown")
        self.launches["sites"] = [self.site, copy.deepcopy(self.site)]
        self.assertEqual(self.run_check()[0]["status"], "unknown")
        self.launches["sites"] = [{**self.site, "launch_id": "other"}]
        self.assertEqual(self.run_check()[0]["status"], "unknown")

    def test_upstream_unknown_or_rejected_short_circuits_fresh_recovery(self):
        for status in ("unknown", "rejected"):
            self.indexing["status"] = status
            with self.subTest(status=status):
                result, _, chain, launches = self.run_check()
                self.assertEqual(result["status"], status, result)
                chain.assert_not_called()
                launches.assert_not_called()
                self.assertNotIn("capacity", result)

    def test_outputs_retain_component_evidence(self):
        result, indices, chain, launches = self.run_check()
        self.assertEqual(result["schema_version"], "conditional-shared-storage-check/v1")
        self.assertEqual(result["indexing"], self.indexing)
        self.assertEqual(result["chain_recovery"], self.chain)
        self.assertEqual(result["capacity"]["status"], "checked")
        indices.assert_called_once_with(self.root, self.thread, ABI, self.binding)
        chain.assert_called_once()
        launches.assert_called_once_with(self.root, "kernel")


if __name__ == "__main__":
    unittest.main()
