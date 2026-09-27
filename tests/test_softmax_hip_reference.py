"""CPU-only tests for the frozen manual HIP softmax numeric protocol."""

from __future__ import annotations

import json
import math
from pathlib import Path
import unittest

from experiments.softmax_hip_reference import (
    ABS_TOLERANCE,
    REL_TOLERANCE,
    ROW_SUM_TOLERANCE,
    evaluate,
    make_input,
    reference,
)


PROTOCOL = Path(__file__).parents[1] / "benchmarks" / "intake" / "pytorch-softmax-hip-protocol.json"


class SoftmaxHipReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.protocol = json.loads(PROTOCOL.read_text())

    def test_all_eighteen_frozen_reference_cases_self_compare(self):
        cases = self.protocol["cases"]
        observed = []
        for columns in cases["columns"]:
            for rows in cases["rows"]:
                for pattern in cases["patterns"]:
                    with self.subTest(rows=rows, columns=columns, pattern=pattern):
                        values = make_input(rows, columns, pattern)
                        expected = reference(values, rows, columns)
                        result = evaluate(expected, expected, rows, columns)
                        self.assertEqual(result["status"], "passed", result)
                        self.assertEqual(result["max_abs_error"], 0.0)
                        self.assertLessEqual(result["max_row_sum_error"], ROW_SUM_TOLERANCE)
                        observed.append((rows, columns, pattern))
        self.assertEqual(len(observed), cases["count"])
        self.assertEqual(len(set(observed)), 18)

    def test_incorrect_finite_output_is_failed(self):
        expected = reference(make_input(1, 65, "zero"), 1, 65)
        result = evaluate([0.0] * 65, expected, 1, 65)
        self.assertEqual(result["status"], "failed", result)
        self.assertGreater(result["max_abs_error"], ABS_TOLERANCE)
        self.assertEqual(result["max_row_sum_error"], 1.0)

    def test_nonfinite_and_length_errors_are_not_silently_truncated(self):
        expected = [0.5, 0.5]
        for actual in ([0.5], [0.5, 0.5, 0.0], [float("nan"), 0.5],
                       [float("inf"), 0.5]):
            with self.subTest(actual=actual), self.assertRaises(ValueError):
                evaluate(actual, expected, 1, 2)
        with self.assertRaises(ValueError):
            evaluate(expected, [0.5], 1, 2)
        with self.assertRaises(ValueError):
            reference([0.0, float("nan")], 1, 2)

    def test_element_and_row_sum_tolerance_boundaries(self):
        expected = [0.5, 0.5]
        threshold = ABS_TOLERANCE + REL_TOLERANCE * 0.5
        # Select adjacent representable values on either side of the mixed bound.
        upper = 0.5 + threshold
        if upper - 0.5 > threshold:
            upper = math.nextafter(upper, 0.5)
        at_boundary = [upper, 1.0 - upper]
        self.assertEqual(evaluate(at_boundary, expected, 1, 2)["status"], "passed")

        beyond = math.nextafter(upper, math.inf)
        element_failure = evaluate([beyond, 1.0 - beyond], expected, 1, 2)
        self.assertEqual(element_failure["status"], "failed", element_failure)

        # Each element remains within its mixed tolerance, but the row sum does not.
        row_failure = evaluate([0.500011, 0.500011], expected, 1, 2)
        self.assertLessEqual(row_failure["max_abs_error"], threshold)
        self.assertGreater(row_failure["max_row_sum_error"], ROW_SUM_TOLERANCE)
        self.assertEqual(row_failure["status"], "failed", row_failure)

    def test_protocol_constants_and_claim_boundaries_match_module(self):
        protocol = self.protocol
        self.assertEqual(protocol["cases"], {
            "columns": [65, 128], "rows": [1, 3, 17],
            "patterns": ["zero", "sawtooth", "alternating"],
            "count": 18, "cartesian_product_required": True,
        })
        numeric = protocol["reference"]
        self.assertEqual(numeric["absolute_tolerance"], ABS_TOLERANCE)
        self.assertEqual(numeric["relative_tolerance"], REL_TOLERANCE)
        self.assertEqual(numeric["maximum_row_sum_error"], ROW_SUM_TOLERANCE)
        self.assertEqual(protocol["status"], "numeric_panel_frozen_execution_harness_revised")
        self.assertTrue(protocol["post_pilot_engineering_revision"])
        for key in ("formal_correctness", "performance", "automatic_source_relation_recovery",
                    "automatic_adaptation", "source_program_checked", "deployable"):
            self.assertFalse(protocol["claims"][key])


if __name__ == "__main__":
    unittest.main()
