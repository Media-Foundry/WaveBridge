"""Explicit-axis launch comparison, not a GPU semantics test."""
import copy
import unittest

from test_constructor_values import constructor, fields, ABI
from wavebridge.verification.block_configuration import check


class BlockConfigurationTests(unittest.TestCase):
    def setUp(self):
        c = constructor((256, 1, 1))
        c["field_initialization"] = fields()
        self.chain = {"status": "recovered", "function_id": "kernel", "block_threads": 256, "int_bits": 32}
        self.site = {"launch_id": "launch", "kernel_declaration_id": "kernel",
                     "configuration_constructor_arguments": [{}, c]}
        self.axes = {"schema_version": "launch-axis-assumptions/v1", "launch_id": "launch", "constructor_declaration_id": "ctor",
                     "fields": dict(zip(("x", "y", "z"), [m["field_id"] for m in fields()["field_mappings"]]))}

    def test_exact_block_checked_under_explicit_axes(self):
        result = check(self.chain, self.site, ABI, self.axes)
        self.assertEqual("checked", result["status"], result)
        self.assertEqual({"x": 256, "y": 1, "z": 1}, result["dimensions"])
        self.assertFalse(result["source_program_checked"])
        self.assertFalse(result["deployable"])

    def test_field_swap_is_not_hidden_by_matching_population(self):
        self.site["configuration_constructor_arguments"][1]["field_initialization"] = fields((1, 0, 2))
        result = check(self.chain, self.site, ABI, self.axes)
        self.assertEqual("rejected", result["status"])
        self.assertEqual({"x": 1, "y": 256, "z": 1}, result["dimensions"])

    def test_wrong_model_or_extra_dimension_rejects(self):
        self.chain["block_threads"] = 128
        self.assertEqual("rejected", check(self.chain, self.site, ABI, self.axes)["status"])
        self.chain["block_threads"] = 256
        self.site["configuration_constructor_arguments"][1] = constructor((16, 16, 1))
        self.site["configuration_constructor_arguments"][1]["field_initialization"] = fields()
        self.assertEqual("rejected", check(self.chain, self.site, ABI, self.axes)["status"])

    def test_missing_wrong_and_duplicate_axis_id_stay_unknown(self):
        for key in ("launch_id", "constructor_declaration_id", "fields"):
            axes = copy.deepcopy(self.axes)
            axes.pop(key)
            self.assertEqual("unknown", check(self.chain, self.site, ABI, axes)["status"])
        self.axes["fields"]["y"] = self.axes["fields"]["x"]
        self.assertEqual("unknown", check(self.chain, self.site, ABI, self.axes)["status"])

    def test_abi_and_kernel_mismatch_stay_unknown(self):
        self.assertEqual("unknown", check(self.chain, self.site, {}, self.axes)["status"])
        self.site["kernel_declaration_id"] = "other"
        self.assertEqual("unknown", check(self.chain, self.site, ABI, self.axes)["status"])

    def test_wrong_axis_namespace_coverage_and_schema_stay_unknown(self):
        for key in ("launch_id", "constructor_declaration_id", "schema_version"):
            axes = copy.deepcopy(self.axes)
            axes[key] = "different"
            self.assertEqual("unknown", check(self.chain, self.site, ABI, axes)["status"])
        axes = copy.deepcopy(self.axes)
        axes["fields"]["z"] = "not-a-record-field"
        self.assertEqual("unknown", check(self.chain, self.site, ABI, axes)["status"])
        abi = dict(ABI)
        abi.pop("unsigned int")
        self.assertEqual("unknown", check(self.chain, self.site, abi, self.axes)["status"])
        self.axes["extra"] = float("nan")
        self.assertEqual("input_hash_unsupported", check(self.chain, self.site, ABI, self.axes)["reason"])
