import itertools
import unittest
from unittest.mock import patch

import wavebridge.verification.column_coverage as coverage


class ColumnCoverageIntervalTests(unittest.TestCase):
    def test_exhaustive_small_intervals_match_all_fixed_checks(self):
        priority = {"checked": 0, "rejected": 1, "unknown": 2}
        for int_bits in (3, 4):
            maximum = (1 << (int_bits - 1)) - 1
            for lower in range(maximum + 1):
                for upper in range(lower, maximum + 1):
                    for stride in range(1, maximum + 1):
                        for starts in itertools.product(range(maximum + 1), repeat=2):
                            fixed = [coverage.check(columns, list(starts), stride,
                                                    int_bits=int_bits)
                                     for columns in range(lower, upper + 1)]
                            expected = max((item["status"] for item in fixed),
                                           key=priority.__getitem__)
                            actual = coverage.check_interval(
                                lower, upper, list(starts), stride, int_bits=int_bits)
                            self.assertEqual(actual["status"], expected,
                                             (int_bits, lower, upper, stride, starts, fixed, actual))
                            self.assertEqual(actual["upper_check"], fixed[-1])
                            if expected == "checked":
                                iterations = [len(range(start, upper, stride)) for start in starts]
                                self.assertEqual(actual["max_iterations_per_thread"], iterations)
                                self.assertEqual(actual["max_iterations"], max(iterations))

    def test_zero_column_singleton_and_rejected_upper_evidence(self):
        checked = coverage.check_interval(0, 0, [0, 1], 2)
        self.assertEqual(checked["status"], "checked", checked)
        self.assertEqual(checked["interval_checked"], {"lower": 0, "upper": 0})
        self.assertEqual(checked["max_iterations_per_thread"], [0, 0])
        self.assertEqual(checked["max_iterations"], 0)
        rejected = coverage.check_interval(0, 7, [0], 2)
        self.assertEqual(rejected["status"], "rejected", rejected)
        self.assertEqual(rejected["counterexample"]["columns"], 7)
        self.assertEqual(rejected["upper_check"]["status"], "rejected")

    def test_idle_threads_have_zero_max_iterations(self):
        result = coverage.check_interval(2, 3, [0, 1, 2, 3, 9], 5)
        self.assertEqual(result["status"], "checked", result)
        self.assertEqual(result["max_iterations_per_thread"], [1, 1, 1, 0, 0])
        self.assertEqual(result["max_iterations"], 1)

    def test_invalid_bool_reversed_and_negative_bounds_are_unknown(self):
        cases = [
            (True, 3, [0], 1), (0, False, [0], 1),
            (3, 2, [0], 1), (-1, 2, [0], 1), (0, -1, [0], 1),
            (0, 2, [True], 1), (0, 2, [0], True),
        ]
        for arguments in cases:
            with self.subTest(arguments=arguments):
                self.assertEqual(coverage.check_interval(*arguments)["status"], "unknown")

    def test_upper_endpoint_increment_overflow_remains_unknown(self):
        result = coverage.check_interval(0, 127, [0], 2, int_bits=8)
        self.assertEqual(result["status"], "unknown", result)
        self.assertEqual(result["reason"], "signed_increment_overflow")
        self.assertEqual(result["upper_check"]["reason"], "signed_increment_overflow")

    def test_huge_interval_calls_fixed_checker_once(self):
        original = coverage.check
        with patch.object(coverage, "check", wraps=original) as wrapped:
            result = coverage.check_interval(0, 1_000_000_000,
                                             list(range(256)), 256)
        self.assertEqual(result["status"], "checked", result)
        self.assertEqual(wrapped.call_count, 1)
        wrapped.assert_called_once_with(1_000_000_000, list(range(256)), 256,
                                        int_bits=32)
        self.assertEqual(result["upper_check"]["columns_checked"], 1_000_000_000)
        self.assertFalse(result["source_program_checked"])
        self.assertFalse(result["deployable"])


if __name__ == "__main__":
    unittest.main()
