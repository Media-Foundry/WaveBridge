from fractions import Fraction as F
import itertools
import unittest

from experiments.reduction_rounding_witness import model, witness
from tests.test_block_roundoff import fraction, small_model
from wavebridge.verification.block_roundoff import compare_sum_squares, MAX_FINITE


def power(exponent):
    return F(2 ** exponent) if exponent >= 0 else F(1, 2 ** -exponent)


def nearest(value):
    """Independent rational-to-binary32 rounding for the finite test domain."""
    if value == 0:
        return F(0)
    exponent = value.numerator.bit_length() - value.denominator.bit_length()
    if value < power(exponent):
        exponent -= 1
    step = power(max(-149, exponent - 23))
    scaled = value / step
    q, r = divmod(scaled.numerator, scaled.denominator)
    if 2 * r > scaled.denominator or (2 * r == scaled.denominator and q % 2):
        q += 1
    return q * step


def simulate(row, width, mode):
    leaves = []
    for t in range(4):
        acc = F(0)
        for value in row[t::4]:
            square = value * value
            acc = nearest(acc + (nearest(square) if mode == "separate" else square))
        leaves.append(acc)
    def reduce(values):
        for distance in ([1] if width == 2 else [2, 1]):
            old = values
            values = [nearest(old[t] + old[t // width * width + ((t % width) ^ distance)])
                      for t in range(4)]
        return values
    partial = reduce(leaves)[::width]
    return reduce([partial[t % width] if t % width < len(partial) else F(0) for t in range(4)])


class SumSquaresRoundoffTests(unittest.TestCase):
    def compare(self, ncols=1023, magnitude=F(2), modes=("fma", "separate"), small=False):
        models = (small_model(2), small_model(4)) if small else (model(32), model(64))
        return compare_sum_squares(*models, ncols=ncols, input_abs_bound=magnitude,
                                  source_accumulation=modes[0], target_accumulation=modes[1])

    def test_actual_size_partition_and_composed_coefficients(self):
        report = self.compare()
        self.assertEqual(report["status"], "checked", report)
        self.assertEqual(report["domain"]["iteration_counts"], [4] * 255 + [3])
        self.assertEqual(sum(report["domain"]["iteration_counts"]), 1023)
        for side, exponent in (("source", 14), ("target", 17)):
            result = report["sides"][side]
            self.assertEqual(fraction(result["relative_coefficient"]), (1 + F(1, 1 << 24)) ** exponent - 1)
            self.assertGreater(fraction(result["computed_leaf_upper_bound"]), 16)
            self.assertLess(fraction(result["computed_leaf_upper_bound"]), 17)
        self.assertFalse(report["common_computed_leaf_values_assumed"])
        self.assertNotIn("route_comparison", report)
        self.assertEqual(set(report["route_checks"]), {"source", "target"})
        self.assertFalse(report["numeric_contract_checked"])
        self.assertFalse(report["source_to_model_correspondence_established"])
        self.assertFalse(report["deployable"])

    def test_small_domain_all_modes_against_exact_rational_rounding(self):
        for modes in itertools.product(("fma", "separate"), repeat=2):
            report = self.compare(ncols=5, magnitude=F(2), modes=modes, small=True)
            self.assertEqual(report["status"], "checked")
            for row in itertools.product((power(-149), -F(1, 2), 1 + power(-23)), repeat=5):
                q = sum((v * v for v in row), F(0))
                outputs = [simulate(row, width, mode) for width, mode in zip((2, 4), modes)]
                for side, actual in zip(("source", "target"), outputs):
                    bounds = report["sides"][side]
                    allowance = fraction(bounds["relative_coefficient"]) * q + fraction(bounds["absolute_allowance"])
                    self.assertTrue(all(abs(value - q) <= allowance for value in actual))
                bound = report["difference_bound"]
                allowance = fraction(bound["relative_coefficient"]) * q + fraction(bound["absolute_allowance"])
                self.assertTrue(all(abs(a - b) <= allowance for a, b in zip(*outputs)))

    def test_single_column_and_zero_input_bound(self):
        report = self.compare(ncols=1, magnitude=F(0))
        self.assertEqual(report["status"], "checked")
        self.assertEqual(report["domain"]["iteration_counts"], [1] + [0] * 255)
        self.assertEqual(fraction(report["difference_bound"]["Q_upper_bound"]), 0)

    def test_earlier_witness_is_in_composed_bound(self):
        report = self.compare(ncols=34, magnitude=F(1), modes=("fma", "fma"))
        observed = witness()
        delta = F(abs(int(observed["source_thread0_units"]) - int(observed["target_thread0_units"])), 1 << 149)
        bound = report["difference_bound"]
        self.assertGreater(delta, 0)
        self.assertLessEqual(delta, fraction(bound["relative_coefficient"]) * (1 + power(-23)) +
                             fraction(bound["absolute_allowance"]))

    def test_invalid_inputs_and_exhausted_budget_are_unknown(self):
        for n in (0, -1, True, 2.0, 256 * 64 + 1):
            self.assertEqual(self.compare(ncols=n)["status"], "unknown")
        for magnitude in (-F(1), 2.0, True, MAX_FINITE + 1):
            self.assertEqual(self.compare(magnitude=magnitude)["status"], "unknown")
        self.assertEqual(self.compare(modes=("unspecified", "fma"))["status"], "unknown")
        self.assertEqual(self.compare(magnitude=MAX_FINITE)["status"], "unknown")

    def test_invalid_route_cannot_bypass_local_composition(self):
        wrong = model(32)
        wrong["second_offsets"] = [16, 8, 4, 2]
        report = compare_sum_squares(wrong, model(64), ncols=34, input_abs_bound=F(1),
                                     source_accumulation="fma", target_accumulation="fma")
        self.assertEqual(report["status"], "rejected")


if __name__ == "__main__":
    unittest.main()
