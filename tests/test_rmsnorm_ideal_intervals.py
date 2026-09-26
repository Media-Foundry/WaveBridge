from fractions import Fraction as F
import unittest

from wavebridge.verification.rmsnorm_roundoff import ideal_intervals, MAX_FINITE


class RMSNormIdealIntervalTests(unittest.TestCase):
    def test_exact_square_and_signs(self):
        result = ideal_intervals([F(-1), F(0), F(1)], epsilon=F(10, 3))
        self.assertEqual(result["denominator"], 4)
        self.assertEqual(result["scale_interval"], (F(1, 2), F(1, 2)))
        self.assertEqual(result["outputs"], [(F(-1, 2), F(-1, 2)), (F(0), F(0)), (F(1, 2), F(1, 2))])

    def test_non_square_bounds_verified_by_exact_squaring(self):
        for row in ([F(0)], [F(-2), F(1, 1 << 149), F(2)], [MAX_FINITE]):
            for epsilon in (F(1, 1000000), F(1, 1000)):
                result = ideal_intervals(row, epsilon=epsilon)
                lo, hi = result["scale_interval"]
                d = result["denominator"]
                self.assertLessEqual(lo * lo * d, 1)
                self.assertGreaterEqual(hi * hi * d, 1)
                self.assertLessEqual(hi-lo, F(1, 1 << 192))
                for x, (a, b) in zip(row, result["outputs"]):
                    self.assertLessEqual(a, b)
                    if x:
                        self.assertLessEqual(min(a*a, b*b)*d, x*x)
                        self.assertGreaterEqual(max(a*a, b*b)*d, x*x)

    def test_precision_refinement_is_nested(self):
        coarse = ideal_intervals([F(1)], epsilon=F(1), precision_bits=16)
        fine = ideal_intervals([F(1)], epsilon=F(1), precision_bits=192)
        self.assertLessEqual(coarse["scale_interval"][0], fine["scale_interval"][0])
        self.assertGreaterEqual(coarse["scale_interval"][1], fine["scale_interval"][1])

    def test_invalid_or_non_binary32_inputs(self):
        for row in ([], [1.0], [F(1, 3)], [F(1, 1 << 150)], [MAX_FINITE+1], [F(1)]*4097):
            with self.assertRaises(ValueError):
                ideal_intervals(row, epsilon=F(1))
        for epsilon in (0.1, F(0), -F(1), F(1, 1 << 4097)):
            with self.assertRaises(ValueError):
                ideal_intervals([F(1)], epsilon=epsilon)
        for precision in (True, 1, 1025):
            with self.assertRaises(ValueError):
                ideal_intervals([F(1)], epsilon=F(1), precision_bits=precision)


if __name__ == "__main__":
    unittest.main()
