"""Model diagnostics, not source/GPU or full floating-point contract tests."""
import unittest

from experiments.reduction_rounding_witness import bits, evaluate, model, rounded_add, witness
from tests.test_rmsnorm_case import reference


class BlockRouteRoundingTests(unittest.TestCase):
    def test_concrete_row_is_in_frozen_input_domain(self):
        row = [0.0] * 34
        row[0], row[1], row[33] = 1.0, 2.0 ** -12, 2.0 ** -12
        self.assertEqual(reference.validate([row], 1e-5), (1, 34))
        self.assertEqual(row[1] * row[1], 2.0 ** -24)

    def test_exact_known_encodings_and_subnormal_add(self):
        for units, expected in ((0, "0x00000000"), (1, "0x00000001"),
                                (1 << 23, "0x00800000"), (1 << 149, "0x3f800000"),
                                (1 << 125, "0x33800000")):
            self.assertEqual(bits(units), expected)
        self.assertEqual(rounded_add((1 << 23) - 1, 1), 1 << 23)

    def test_ties_even_and_carry(self):
        one, half_ulp, ulp = 1 << 149, 1 << 125, 1 << 126
        self.assertEqual(rounded_add(one, half_ulp), one)
        self.assertEqual(rounded_add(one + ulp, half_ulp), one + 2 * ulp)
        self.assertEqual(rounded_add(one, half_ulp + 1), one + ulp)
        self.assertEqual(rounded_add(2 * one - ulp, half_ulp), 2 * one)

    def test_unsupported_and_overflow_are_not_silent(self):
        for value in (-1, True, 1.5):
            with self.assertRaises(ValueError):
                rounded_add(value, 0)
        with self.assertRaises(ValueError):
            rounded_add(((1 << 24) - 1) << 253, 1 << 252)
        with self.assertRaises(ValueError):
            bits((1 << 149) + 1)

    def test_witness_has_equal_counts_but_different_rounded_totals(self):
        result = witness()
        comparison = result["route_comparison"]
        self.assertTrue(comparison["contribution_multisets_equal"])
        self.assertFalse(comparison["ordered_add_dags_equal"])
        self.assertEqual(set(result["source_output_bits"]), {"0x3f800000"})
        self.assertEqual(set(result["target_output_bits"]), {"0x3f800001"})
        self.assertEqual(result["different_threads"], list(range(256)))
        self.assertFalse(result["numeric_tolerance_violation_established"])
        self.assertFalse(result["deployable"])

    def test_exact_integer_inputs_have_equal_totals(self):
        leaves = [1 << 149] * 256
        for width in (32, 64):
            self.assertEqual(evaluate(leaves, model(width)), [256 << 149] * 256)

    def test_modified_routes_are_not_silently_interpreted(self):
        for key, value in (("load_offset", 1), ("barrier", False), ("shared_slots", 0),
                           ("writer_lane", 1), ("offsets", [16, 8, 4, 2])):
            route = model(32)
            route[key] = value
            with self.assertRaises(ValueError):
                evaluate([0] * 256, route)


if __name__ == "__main__":
    unittest.main()
