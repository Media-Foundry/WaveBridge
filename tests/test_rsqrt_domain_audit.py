from fractions import Fraction as F
import unittest

from experiments.rsqrt_domain_audit import argument_interval, MIN_NORMAL


class RsqrtDomainAuditTests(unittest.TestCase):
    def test_protocol_extremes_both_modes_and_widths(self):
        for n in (1, 32, 33, 256, 257, 1023):
            for mode in ("fma", "separate"):
                intervals = argument_interval(n, mode, F(2), F(1, 1000000), F(1, 1000))
                self.assertEqual(set(intervals), {32, 64})
                for lo, hi in intervals.values():
                    self.assertGreater(lo, MIN_NORMAL)
                    self.assertGreaterEqual(lo, F(1, 1 << 20))
                    self.assertLess(hi, 16)
                    self.assertLess(lo, F(1, 1000000))
                    self.assertGreater(hi, F(4001, 1000))

    def test_invalid_domain_is_not_accepted(self):
        for n, mode in ((0, "fma"), (1023, "unknown")):
            with self.assertRaises(ValueError):
                argument_interval(n, mode, F(2), F(1, 1000000), F(1, 1000))
        with self.assertRaises(ValueError):
            argument_interval(1, "fma", F(2), F(1), F(0))

    def test_tiny_epsilon_is_not_implicitly_raised_to_normal(self):
        for lo, _ in argument_interval(1, "fma", F(0), F(1, 1 << 149), F(1, 1 << 149)).values():
            self.assertLess(lo, MIN_NORMAL)


if __name__ == "__main__":
    unittest.main()
