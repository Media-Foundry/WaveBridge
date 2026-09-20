import unittest

from wavebridge.verification.integer_conversion import check_interval


class IntegerConversionTests(unittest.TestCase):
    def test_launch_constants_fit_explicit_int_to_unsigned_widths(self):
        for value in (1, 256):
            result = check_interval(value, value, 32, True, 32, False)
            self.assertEqual(result["status"], "checked")
            self.assertFalse(result["source_program_checked"])

    def test_negative_and_narrowing_are_not_preserving(self):
        self.assertEqual(check_interval(-1, 256, 32, True, 32, False)["status"], "rejected")
        self.assertEqual(check_interval(0, 256, 32, True, 8, False)["status"], "rejected")
        self.assertEqual(check_interval(0, 255, 32, True, 8, False)["status"], "checked")

    def test_invalid_source_domain_is_unknown(self):
        self.assertEqual(check_interval(0, 256, 8, False, 32, True)["status"], "unknown")
        self.assertEqual(check_interval(1, 0, 32, True, 32, False)["status"], "unknown")
        self.assertEqual(check_interval(True, 1, 32, True, 32, False)["status"], "unknown")

    def test_small_intervals_agree_with_enumerated_representability(self):
        for source_signed in (False, True):
            source_values = range(-8, 8) if source_signed else range(16)
            for target_signed in (False, True):
                target_values = set(range(-4, 4) if target_signed else range(8))
                for lower in source_values:
                    for upper in range(lower, source_values.stop):
                        expected = all(value in target_values for value in range(lower, upper + 1))
                        result = check_interval(lower, upper, 4, source_signed, 3, target_signed)
                        self.assertEqual(result["status"] == "checked", expected)


if __name__ == "__main__":
    unittest.main()
