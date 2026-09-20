from collections import Counter
import itertools
import unittest

from wavebridge.verification.column_coverage import check


class ColumnCoverageTests(unittest.TestCase):
    def test_real_sizes_without_column_expansion(self):
        for columns in (0, 1, 31, 256, 777, 4096, 1000000000):
            result = check(columns, list(range(256)), 256)
            self.assertEqual(result["status"], "checked", result)
            self.assertFalse(result["source_program_checked"])

    def test_missing_repeated_and_shifted_columns(self):
        self.assertEqual(check(100, [0, 1], 3)["reason"], "missing_column")
        self.assertEqual(check(100, [0, 0], 1)["reason"], "duplicate_column")
        self.assertEqual(check(100, [1], 1)["reason"], "missing_column")

    def test_signed_overflow_in_final_increment_is_unknown(self):
        self.assertEqual(check(127, [0], 2, int_bits=8)["reason"], "signed_increment_overflow")
        self.assertEqual(check(127, [127], 2, int_bits=8)["status"], "rejected")
        self.assertEqual(check(126, [0, 1], 2, int_bits=8)["status"], "checked")
        for args in ((True, [0], 1), (2, [-1], 1), (2, [0], 0), (2, [], 1)):
            self.assertEqual(check(*args)["status"], "unknown")

    def test_exhaustive_small_domains_match_enumeration(self):
        for columns in range(9):
            for stride in range(1, 6):
                for starts in itertools.product(range(5), repeat=3):
                    actual = Counter(column for start in starts for column in range(start, columns, stride))
                    expected = Counter(range(columns))
                    result = check(columns, list(starts), stride)
                    self.assertEqual(result["status"] == "checked", actual == expected,
                                     (columns, starts, stride, result))

    def test_small_signed_domains_match_stepwise_overflow_simulation(self):
        for columns in range(8):
            for stride in range(1, 8):
                for starts in itertools.product(range(8), repeat=2):
                    overflow = False
                    contributions = Counter()
                    for start in starts:
                        index = start
                        while index < columns:
                            contributions[index] += 1
                            index += stride
                            if index > 7:
                                overflow = True
                                break
                    result = check(columns, list(starts), stride, int_bits=4)
                    expected = ("unknown" if overflow else
                                "checked" if contributions == Counter(range(columns)) else "rejected")
                    self.assertEqual(result["status"], expected, (columns, starts, stride, result))


if __name__ == "__main__":
    unittest.main()
