"""Mock source discovery only; use actual getter/domain/partition checkers."""
import copy
import unittest
from unittest.mock import patch

from wavebridge.block_coordinate_check import check
from wavebridge.verification.getter_returns import _hash
from tests.test_getter_returns import fixture, call, ABI
from tests.test_index_partition import expr, width_ref, cast


class BlockCoordinateCompositionTests(unittest.TestCase):
    def setUp(self):
        self.root, domain = fixture()
        self.binding = {
            "schema_version": "thread-start-assumptions/v1", "ast_root_sha256": _hash(self.root),
            "kernel_declaration_id": "kernel", "launch_id": "launch",
            "coordinate": {"semantics": "workgroup_local_id", "axis": 0,
                           "declaration_id": "leaf", "return_type": {"qualType": "unsigned long"}},
        }
        self.thread = {
            "schema_version": "conditional-thread-start-check/v1", "status": "checked", "int_bits": 32,
            "kernel_declaration_id": "kernel", "launch_id": "launch", "derived_leaf_domain": domain,
            "input_sha256": {"root": _hash(self.root), "integer_types": _hash(ABI), "binding": _hash(self.binding)},
            "recovery": {"chain": {"status": "recovered", "block_threads": 256, "width": 32,
                                   "links": [{"caller_id": "kernel", "callee_id": "helper"}]}},
        }
        self.block = {"status": "recovered", "function_id": "helper", "block_threads": 256, "width": 32,
                      "bindings": {"width_declaration_id": "width"}, "coordinate_asts": {}, "index_initializers": {}}
        for name, operation in (("group", "/"), ("lane", "%")):
            anchor = call(name + "-coordinate", "middle", "unimportant", return_type="unsigned int")
            right = cast(cast(width_ref("const int"), "int", "LValueToRValue"), "unsigned int")
            expression = cast(expr("BinaryOperator", "unsigned int", opcode=operation,
                                   inner=[anchor, right]), "const int")
            self.block["coordinate_asts"][name + "_coordinate"] = anchor
            self.block["index_initializers"][name] = expression

    def run_check(self):
        with patch("wavebridge.block_coordinate_check.discover", return_value={
                "traversal_budget_complete": True, "block_candidates": [self.block]}):
            return check(self.root, self.thread, ABI, self.binding)

    def test_two_distinct_reads_connect_to_same_external_protocol_and_partition(self):
        result = self.run_check()
        self.assertEqual(result["status"], "checked", result)
        self.assertEqual(result["checks"]["group"]["partition"]["output_range"], {"lower": 0, "upper": 7})
        self.assertEqual(result["checks"]["lane"]["partition"]["output_range"], {"lower": 0, "upper": 31})
        self.assertFalse(result["source_program_checked"])
        self.assertFalse(result["deployable"])

    def test_unbound_root_abi_protocol_and_unchecked_thread_do_not_pass(self):
        original = copy.deepcopy(self.thread)
        for key in ("root", "integer_types", "binding"):
            self.thread = copy.deepcopy(original)
            self.thread["input_sha256"][key] = "stale"
            self.assertEqual(self.run_check()["status"], "unknown")
        self.thread = copy.deepcopy(original)
        self.thread["status"] = "unknown"
        self.assertEqual(self.run_check()["status"], "unknown")

    def test_wrong_operator_or_coordinate_expression_is_not_accepted(self):
        original = copy.deepcopy(self.block)
        self.block["index_initializers"]["lane"]["inner"][0]["opcode"] = "/"
        self.assertEqual(self.run_check()["status"], "rejected")
        self.block = original
        # Keep the partition's original source expression; mismatched anchor is unknown.
        self.block["coordinate_asts"]["lane_coordinate"] = copy.deepcopy(self.block["coordinate_asts"]["lane_coordinate"])
        self.block["coordinate_asts"]["lane_coordinate"]["id"] = "other-read"
        self.assertEqual(self.run_check()["status"], "unknown")

    def test_model_and_external_domain_mismatch_stay_unknown(self):
        self.block["width"] = 64
        self.assertEqual(self.run_check()["status"], "unknown")
        self.block["width"] = 32
        self.thread["derived_leaf_domain"]["upper"] = 31
        self.assertEqual(self.run_check()["status"], "unknown")


if __name__ == "__main__":
    unittest.main()
