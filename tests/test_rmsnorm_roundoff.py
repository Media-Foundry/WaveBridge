from fractions import Fraction as F
from itertools import product
from math import isqrt
import unittest

from tests.test_block_roundoff import fraction, small_model
from tests.test_sum_squares_roundoff import nearest, simulate
from wavebridge.verification import rmsnorm_roundoff as checker


def bounded_rsqrt(argument, rho, direction):
    """Rational test implementation, NOT an SDK rsqrt model."""
    grid = 1 << 80
    result = F(isqrt(argument.denominator * grid * grid // argument.numerator), grid)
    result *= 1 + direction * rho / 2
    # Verify the supplied error law without approximating a square root.
    assert (1 - rho) ** 2 <= result * result * argument <= (1 + rho) ** 2
    return result


class RMSNormRoundoffTests(unittest.TestCase):
    def compare(self, **overrides):
        args = dict(ncols=4, input_abs_bound=F(2), source_accumulation="fma",
                    target_accumulation="separate", ideal_epsilon=F(1, 16),
                    source_epsilon=F(1, 16), target_epsilon=F(1, 16),
                    source_rsqrt_relative_error=F(1, 1 << 30),
                    target_rsqrt_relative_error=F(1, 1 << 30))
        args.update(overrides)
        return checker.compare(small_model(2), small_model(4), **args)

    def test_exact_rational_suffix_and_signed_outputs(self):
        for modes in product(("fma", "separate"), repeat=2):
            report = self.compare(source_accumulation=modes[0], target_accumulation=modes[1])
            self.assertEqual(report["status"], "checked")
            for row in product((-F(1, 2), F(0), 1 + F(1, 1 << 23)), repeat=4):
                ideal_argument = sum(x*x for x in row) / 4 + F(1, 16)
                outputs = []
                for side, width, mode, direction in zip(("source", "target"), (2, 4), modes, (-1, 1)):
                    total = simulate(row, width, mode)[0]
                    argument = nearest(nearest(total / 4) + F(1, 16))
                    bounds = report["sides"][side]
                    interval = bounds["rsqrt_input_interval"]
                    self.assertLessEqual(fraction(interval["lower"]), argument)
                    self.assertLessEqual(argument, fraction(interval["upper"]))
                    scale = bounded_rsqrt(argument, F(1, 1 << 30), direction)
                    actual = [nearest(abs(x)*scale) * (-1 if x < 0 else 1) for x in row]
                    outputs.append(actual)
                    c, eta = fraction(bounds["relative_coefficient"]), fraction(bounds["absolute_allowance"])
                    for x, y in zip(row, actual):
                        # Squared positive inequalities exactly encode the error
                        # interval around x/sqrt(D); no host sqrt oracle is used.
                        self.assertLessEqual(max(abs(y)-eta, 0)**2 * ideal_argument, (1+c)**2*x*x)
                        self.assertGreaterEqual((abs(y)+eta)**2 * ideal_argument, max(1-c, 0)**2*x*x)
                bound = report["difference_bound"]
                c, eta = fraction(bound["relative_coefficient"]), fraction(bound["absolute_allowance"])
                for x, a, b in zip(row, *outputs):
                    self.assertLessEqual(max(abs(a-b)-eta, 0)**2 * ideal_argument, c*c*x*x)

    def test_epsilon_representation_error_and_explicit_rsqrt_assumptions(self):
        base = self.compare()
        changed = self.compare(target_epsilon=F(1, 16) + F(1, 1 << 26),
                               target_rsqrt_relative_error=F(1, 1000))
        self.assertEqual(changed["status"], "checked")
        self.assertGreater(fraction(changed["sides"]["target"]["relative_coefficient"]),
                           fraction(base["sides"]["target"]["relative_coefficient"]))
        for flag in ("numeric_contract_checked", "source_program_checked", "deployable",
                     "external_fp_model_verified", "rsqrt_contract_verified",
                     "frozen_reference_implementation_checked"):
            self.assertFalse(changed[flag])
        self.assertEqual(changed["sum_squares_check"]["status"], "checked")

    def test_zero_input_and_single_column(self):
        report = self.compare(ncols=1, input_abs_bound=F(0))
        self.assertEqual(report["status"], "checked")
        self.assertGreater(fraction(report["sides"]["source"]["rsqrt_input_interval"]["lower"]), 0)

    def test_missing_or_invalid_external_parameters(self):
        for field in ("ideal_epsilon", "source_epsilon", "target_epsilon"):
            for value in (None, 0.01, F(0), -F(1), F(1, 1 << 4097)):
                self.assertEqual(self.compare(**{field: value})["status"], "unknown")
        for field in ("source_rsqrt_relative_error", "target_rsqrt_relative_error"):
            for value in (None, 0.0, True, F(1), -F(1)):
                self.assertEqual(self.compare(**{field: value})["status"], "unknown")
        self.assertEqual(self.compare(source_rsqrt_relative_error=F(0))["status"], "checked")

    def test_unestablished_positive_and_finite_ranges(self):
        self.assertIn("positive_rsqrt", self.compare(target_epsilon=F(1))["reason"])
        self.assertIn("finite_division_or_addition", self.compare(
            ideal_epsilon=checker.MAX_FINITE, source_epsilon=checker.MAX_FINITE,
            target_epsilon=checker.MAX_FINITE)["reason"])
        tiny = F(1, 1 << 130)
        self.assertIn("finite_scale_or_output", self.compare(
            ideal_epsilon=tiny, source_epsilon=tiny, target_epsilon=tiny)["reason"])

    def test_upstream_unknown_and_rejection_are_not_upgraded(self):
        self.assertEqual(self.compare(ncols=0)["status"], "unknown")
        wrong = small_model(2)
        wrong["second_offsets"] = []
        report = checker.compare(wrong, small_model(4), ncols=4, input_abs_bound=F(2),
                                 source_accumulation="fma", target_accumulation="fma",
                                 ideal_epsilon=F(1, 16), source_epsilon=F(1, 16),
                                 target_epsilon=F(1, 16), source_rsqrt_relative_error=F(0),
                                 target_rsqrt_relative_error=F(0))
        self.assertEqual(report["status"], "rejected")


if __name__ == "__main__":
    unittest.main()
