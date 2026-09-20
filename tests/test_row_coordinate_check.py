import copy
import unittest
from unittest.mock import patch

from wavebridge.row_coordinate_check import check
from wavebridge.verification.getter_returns import _hash
from tests.test_getter_returns import ABI, fixture
from tests.test_initializer_domain import reports


class RowCoordinateCompositionTests(unittest.TestCase):
    def setUp(self):
        self.root, _ = fixture()
        self.grid_binding = {
            "schema_version": "grid-domain-assumptions/v1",
            "ast_root_sha256": _hash(self.root), "kernel_declaration_id": "kernel",
            "launch_id": "launch", "configuration_position": 0,
            "axis_binding": {"schema_version": "launch-axis-assumptions/v1"},
        }
        self.binding = {
            "schema_version": "row-coordinate-assumptions/v1",
            "ast_root_sha256": _hash(self.root), "kernel_declaration_id": "kernel",
            "launch_id": "launch", "grid_binding": self.grid_binding,
            "coordinate": {"semantics": "workgroup_id", "axis": 0,
                           "declaration_id": "leaf",
                           "return_type": {"qualType": "unsigned long"}},
        }
        self.grid = {
            "schema_version": "conditional-grid-domain-check/v1", "status": "checked",
            "dimensions": {"x": {"lower": 1, "upper": 8},
                           "y": {"lower": 1, "upper": 1},
                           "z": {"lower": 1, "upper": 1}},
        }
        link, _ = reports()
        link["callee_declaration_id"] = "start"
        self.prefix = {
            "status": "recovered", "function_id": "kernel",
            "row_declaration_id": "row",
            "row_initializer_evidence": {"status": "evidence", "value_link": link},
        }

    def run_check(self, *, enabled=True):
        with patch("wavebridge.row_coordinate_check.check_grid", return_value=self.grid) as grid, \
                patch("wavebridge.row_coordinate_check.recover_prefix",
                      return_value=self.prefix) as prefix:
            result = check(self.root, "kernel", "launch", ABI, self.binding,
                           use_host_guard_assumptions=enabled)
        return result, grid, prefix

    def test_checked_grid_derives_block_id_domain_and_row_value(self):
        result, grid, prefix = self.run_check()
        self.assertEqual(result["status"], "checked", result)
        self.assertEqual(result["derived_leaf_domain"], {
            "schema_version": "getter-leaf-domain/v1", "declaration_id": "leaf",
            "arguments": [0], "return_type": {"qualType": "unsigned long"},
            "lower": 0, "upper": 7,
        })
        self.assertEqual(result["row_interval"], {"lower": 0, "upper": 7})
        self.assertEqual(result["row_declaration_id"], "row")
        self.assertFalse(result["source_program_checked"])
        self.assertFalse(result["deployable"])
        grid.assert_called_once_with(
            self.root, "kernel", "launch", ABI, self.grid_binding,
            int_bits=32, use_host_guard_assumptions=True)
        prefix.assert_called_once_with(self.root, "kernel", 32)

    def test_root_kernel_launch_and_coordinate_protocol_are_exact(self):
        original = copy.deepcopy(self.binding)
        mutations = [
            ("ast_root_sha256", "stale"), ("kernel_declaration_id", "other"),
            ("launch_id", "other"), ("schema_version", "other/v1"),
        ]
        for key, value in mutations:
            self.binding = {**original, key: value}
            with self.subTest(key=key):
                self.assertEqual(self.run_check()[0]["status"], "unknown")
        for axis in (1, True, None):
            self.binding = copy.deepcopy(original)
            self.binding["coordinate"]["axis"] = axis
            with self.subTest(axis=axis):
                self.assertEqual(self.run_check()[0]["status"], "unknown")

    def test_grid_unknown_and_explicit_host_flag_propagate_unknown(self):
        self.grid = {"status": "unknown", "reason": "guards_not_enabled"}
        result, grid, prefix = self.run_check(enabled=False)
        self.assertEqual(result["status"], "unknown", result)
        grid.assert_called_once_with(
            self.root, "kernel", "launch", ABI, self.grid_binding,
            int_bits=32, use_host_guard_assumptions=False)
        prefix.assert_not_called()

    def test_prefix_must_bind_same_kernel_and_row_initializer(self):
        cases = [
            {"status": "unknown", "function_id": "kernel"},
            {**self.prefix, "function_id": "other"},
            {**self.prefix, "row_declaration_id": ""},
            {**self.prefix, "row_initializer_evidence": {"status": "unknown"}},
        ]
        for prefix_report in cases:
            self.prefix = prefix_report
            with self.subTest(prefix=prefix_report):
                self.assertEqual(self.run_check()[0]["status"], "unknown")

    def test_getter_narrowing_does_not_establish_row_coordinate(self):
        self.root, _ = fixture(upper=299, start_type="unsigned char")
        self.grid_binding["ast_root_sha256"] = _hash(self.root)
        self.binding["ast_root_sha256"] = _hash(self.root)
        self.grid["dimensions"]["x"] = {"lower": 1, "upper": 300}
        link = self.prefix["row_initializer_evidence"]["value_link"]
        link["call_type"] = "unsigned char"
        link["conversions_outer_to_inner"][0]["source_type"] = "unsigned char"
        result, _, _ = self.run_check()
        self.assertEqual(result["status"], "rejected", result)
        self.assertEqual(result["checks"]["getter"]["status"], "rejected")

    def test_row_initializer_narrowing_is_rejected(self):
        self.grid["dimensions"]["x"] = {"lower": 1, "upper": 300}
        link = self.prefix["row_initializer_evidence"]["value_link"]
        link["conversions_outer_to_inner"][0]["target_type"] = "unsigned char"
        result, _, _ = self.run_check()
        self.assertEqual(result["status"], "rejected", result)
        self.assertEqual(result["checks"]["initializer"]["status"], "rejected")

    def test_malformed_checked_grid_dimensions_are_unknown(self):
        cases = [
            None,
            {"x": {"lower": 0, "upper": 8}, "y": {"lower": 1, "upper": 1},
             "z": {"lower": 1, "upper": 1}},
            {"x": {"lower": 1, "upper": 8}, "y": {"lower": 1, "upper": 2},
             "z": {"lower": 1, "upper": 1}},
            {"x": {"lower": 1, "upper": True}, "y": {"lower": 1, "upper": 1},
             "z": {"lower": 1, "upper": 1}},
        ]
        for dimensions in cases:
            self.grid = {"status": "checked", "dimensions": dimensions}
            with self.subTest(dimensions=dimensions):
                self.assertEqual(self.run_check()[0]["status"], "unknown")


if __name__ == "__main__":
    unittest.main()
