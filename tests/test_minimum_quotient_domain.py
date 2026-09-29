import unittest

from wavebridge.verification.integer_selection import check_minimum_quotient_domain as check


class QuotientDomainTests(unittest.TestCase):
    def test_small_domains_against_exhaustive_integer_execution(self):
        for numerator in range(8):
            for lower in range(-8, 8):
                for upper in range(lower, 8):
                    result = check(numerator, lower, upper, [1, 3, 7], int_bits=4)
                    if lower <= 0 <= upper:
                        self.assertEqual(result["status"], "rejected")
                        continue
                    values = []
                    for case in result["cases"]:
                        actual = []
                        for query in range(lower, upper + 1):
                            denominator = min(query, case["power"])
                            actual.append((1 if denominator > 0 else -1) * (numerator // abs(denominator)))
                        self.assertEqual(case["quotient_interval"], {"lower": min(actual), "upper": max(actual)})
                        values.extend(actual)
                    self.assertEqual(result["status"], "checked")
                    self.assertEqual(result["quotient_interval"], {"lower": min(values), "upper": max(values)})

    def test_numeric_boundaries_and_non_deployment(self):
        self.assertEqual(check(128, 32, 32, [128])["quotient_interval"], {"lower": 4, "upper": 4})
        self.assertEqual(check(128, 32, 64, [128])["quotient_interval"], {"lower": 2, "upper": 4})
        self.assertEqual(check(128, -64, -32, [128])["quotient_interval"], {"lower": -4, "upper": -2})
        self.assertEqual(check(0, 0, 0, [1])["status"], "rejected")
        result = check((1 << 63) - 1, -(1 << 63), -1, [1], int_bits=64)
        self.assertTrue(result["division_safe_under_domains"])
        self.assertFalse(result["source_domains_verified"])
        self.assertFalse(result["deployable"])

    def test_invalid_domains_fail_closed(self):
        for args in ((True, 1, 2, [1]), (-1, 1, 2, [1]), (1, 3, 2, [1]),
                     (1, 1, 2, [True]), (1, 1, 2, [0]), (1, 1, 2, []),
                     (1, 1, 2, [1, 1]), (1, 1, 2**31, [1])):
            self.assertEqual(check(*args)["status"], "unknown")
        self.assertEqual(check(1, 1, 2, [1], int_bits=True)["status"], "unknown")
