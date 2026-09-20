import copy
import unittest

from tests.test_constructor_values import ABI, argument, constructor, fields
from wavebridge.verification.grid_configuration import check


def symbolic_grid(lower=1, upper=8):
    report = constructor((0, 1, 1))
    report["arguments"][0] = argument(0, 0, source="signed_int_declaration", symbolic=True)
    report["field_initialization"] = fields()
    intervals = [{"declaration_id": "decl0", "lower": lower, "upper": upper,
                  "type": {"qualType": "const int"}}]
    return report, intervals


class GridConfigurationTests(unittest.TestCase):
    def setUp(self):
        grid, self.intervals = symbolic_grid()
        self.site = {"launch_id": "launch", "kernel_declaration_id": "kernel",
                     "configuration_constructor_arguments": [grid, {}]}
        self.axes = {
            "schema_version": "launch-axis-assumptions/v1", "launch_id": "launch",
            "constructor_declaration_id": "ctor",
            "fields": {axis: field_id for axis, field_id in zip(
                ("x", "y", "z"), [item["field_id"] for item in fields()["field_mappings"]])},
        }

    def test_symbolic_x_and_constant_yz_are_checked_as_intervals(self):
        result = check(self.site, ABI, self.axes, self.intervals)
        self.assertEqual(result["status"], "checked", result)
        self.assertEqual(result["dimensions"], {
            "x": {"lower": 1, "upper": 8},
            "y": {"lower": 1, "upper": 1},
            "z": {"lower": 1, "upper": 1},
        })
        self.assertFalse(result["source_program_checked"])
        self.assertFalse(result["deployable"])
        self.assertIn("interval values are not claimed to be reachable", result["limitations"])

    def test_constant_grid_is_normalized_to_singleton_intervals(self):
        grid = constructor((7, 1, 1)); grid["field_initialization"] = fields()
        self.site["configuration_constructor_arguments"][0] = grid
        result = check(self.site, ABI, self.axes, [])
        self.assertEqual(result["status"], "checked", result)
        self.assertEqual(result["dimensions"]["x"], {"lower": 7, "upper": 7})

    def test_nonpositive_x_and_nonunit_yz_are_conditional_rejections(self):
        cases = []
        grid, intervals = symbolic_grid(0, 8)
        cases.append((grid, intervals, "x"))
        grid = constructor((0, 1, 1)); grid["field_initialization"] = fields()
        cases.append((grid, [], "x"))
        grid = constructor((4, 2, 1)); grid["field_initialization"] = fields()
        cases.append((grid, [], "y"))
        grid = constructor((4, 1, 2)); grid["field_initialization"] = fields()
        cases.append((grid, [], "z"))
        for grid, intervals, axis in cases:
            with self.subTest(axis=axis, intervals=intervals):
                self.site["configuration_constructor_arguments"][0] = grid
                result = check(self.site, ABI, self.axes, intervals)
                self.assertEqual(result["status"], "rejected", result)
                self.assertEqual(result["counterexample"]["axis"], axis)
                self.assertTrue(result["counterexample"]["conditional_domain_counterexample"])

    def test_launch_constructor_and_axis_ids_are_exact(self):
        cases = []
        axes = copy.deepcopy(self.axes); axes["launch_id"] = "other"
        cases.append((self.site, axes))
        axes = copy.deepcopy(self.axes); axes["constructor_declaration_id"] = "other"
        cases.append((self.site, axes))
        axes = copy.deepcopy(self.axes); axes["fields"]["y"] = axes["fields"]["x"]
        cases.append((self.site, axes))
        axes = copy.deepcopy(self.axes); axes["fields"]["z"] = "not-a-field"
        cases.append((self.site, axes))
        site = copy.deepcopy(self.site); site["launch_id"] = ""
        cases.append((site, self.axes))
        for site, axes in cases:
            with self.subTest(site=site, axes=axes):
                self.assertEqual(check(site, ABI, axes, self.intervals)["status"], "unknown")

    def test_missing_duplicate_fields_intervals_and_abi_are_unknown(self):
        site = copy.deepcopy(self.site)
        site["configuration_constructor_arguments"] = [{}]
        self.assertEqual(check(site, ABI, self.axes, self.intervals)["status"], "unknown")
        duplicate = self.intervals + [copy.deepcopy(self.intervals[0])]
        self.assertEqual(check(self.site, ABI, self.axes, duplicate)["status"], "unknown")
        site = copy.deepcopy(self.site)
        site["configuration_constructor_arguments"][0]["field_initialization"]["field_mappings"].pop()
        self.assertEqual(check(site, ABI, self.axes, self.intervals)["status"], "unknown")
        self.assertEqual(check(self.site, {}, self.axes, self.intervals)["status"], "unknown")

    def test_no_default_hardware_x_limit_or_block_semantics(self):
        grid = constructor((1_000_000_000, 1, 1)); grid["field_initialization"] = fields()
        self.site["configuration_constructor_arguments"][0] = grid
        result = check(self.site, ABI, self.axes, [])
        self.assertEqual(result["status"], "checked", result)
        self.assertEqual(result["dimensions"]["x"], {"lower": 1_000_000_000,
                                                      "upper": 1_000_000_000})
        self.assertIn("no hardware grid limit or block-index execution semantics is inferred",
                      result["limitations"])

    def test_hash_binds_all_inputs_and_nonfinite_values_are_unknown(self):
        result = check(self.site, ABI, self.axes, self.intervals)
        self.assertEqual(set(result["input_sha256"]),
                         {"site", "integer_types", "axis_binding", "declaration_intervals"})
        axes = copy.deepcopy(self.axes); axes["extra"] = float("nan")
        self.assertEqual(check(self.site, ABI, axes, self.intervals)["status"], "unknown")


if __name__ == "__main__":
    unittest.main()
