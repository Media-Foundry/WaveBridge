import unittest

from wavebridge.verification.integer_conversion import check_interval, check_bitpattern_equality


class IntegerConversionTests(unittest.TestCase):
    def test_full_bitpattern_model_is_injective_not_value_preserving(self):
        for bits in range(2, 11):
            patterns = range(1 << bits)
            signed = [p if p < (1 << (bits - 1)) else p - (1 << bits) for p in patterns]
            self.assertEqual(len(set(signed)), len(patterns))
            self.assertEqual([v % (1 << bits) for v in signed], list(patterns))
            report = check_bitpattern_equality(bits)
            self.assertEqual(report["status"], "checked")
            self.assertFalse(report["numeric_value_preservation_established"])
        self.assertEqual(check_bitpattern_equality(32)["domain"]["upper"], 2**32 - 1)

    def test_bitpattern_width_is_strict_and_bounded(self):
        for bits in (True, False, None, "32", 1, 129, 32.0):
            self.assertEqual(check_bitpattern_equality(bits)["status"], "unknown")

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
