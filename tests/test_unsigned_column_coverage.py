import itertools
import unittest

from wavebridge.verification.column_coverage import check_unsigned_compound_interval


def simulate(columns, block_threads, bits):
    signed_maximum = (1 << (bits - 1)) - 1
    unsigned_maximum = (1 << bits) - 1
    if block_threads - 1 > signed_maximum or block_threads > unsigned_maximum:
        return "unknown"
    contributions = []
    for start in range(block_threads):
        induction = start
        while induction < columns:
            contributions.append(induction)
            mathematical = induction + block_threads
            unsigned_result = mathematical & unsigned_maximum
            # Model two's-complement assignment for the witness, but never
            # accept a changed value or depend on that choice for a proof.
            signed_result = (unsigned_result if unsigned_result <= signed_maximum
                             else unsigned_result - (1 << bits))
            if unsigned_result != mathematical or signed_result != unsigned_result:
                return "unknown"
            induction = signed_result
    return "checked" if sorted(contributions) == list(range(columns)) else "rejected"


class UnsignedCompoundColumnCoverageTests(unittest.TestCase):
    def test_normal_vllm_shaped_domain_is_conditionally_checked(self):
        report = check_unsigned_compound_interval(1, 1023, 256)
        self.assertEqual(report["status"], "checked", report)
        self.assertEqual(report["interval_checked"], {"lower": 1, "upper": 1023})
        self.assertEqual(report["max_iterations"], 4)
        self.assertFalse(report["source_program_checked"])
        self.assertFalse(report["deployable"])

    def test_zero_columns_and_idle_threads_still_check_initial_conversion(self):
        report = check_unsigned_compound_interval(0, 0, 4, int_bits=4, unsigned_bits=4)
        self.assertEqual(report["status"], "checked", report)
        self.assertEqual(report["max_iterations_per_thread"], [0, 0, 0, 0])
        self.assertEqual([item["stage"] for item in report["conversion_checks"]], [
            "initial_unsigned_local_id_to_signed_int", "unsigned_step_representability"])
        too_many_threads = check_unsigned_compound_interval(
            0, 0, 9, int_bits=4, unsigned_bits=4)
        self.assertEqual(too_many_threads["status"], "unknown")
        self.assertEqual(too_many_threads["reason"],
                         "initial_conversion_not_value_preserving")
        idle = check_unsigned_compound_interval(1, 3, 4, int_bits=4, unsigned_bits=4)
        self.assertEqual(idle["status"], "checked", idle)
        self.assertEqual(idle["max_iterations_per_thread"], [1, 1, 1, 0])

    def test_final_increment_at_and_beyond_signed_maximum(self):
        checked = check_unsigned_compound_interval(0, 7, 1, int_bits=4, unsigned_bits=4)
        self.assertEqual(checked["status"], "checked", checked)
        unknown = check_unsigned_compound_interval(0, 7, 2, int_bits=4, unsigned_bits=4)
        self.assertEqual(unknown["status"], "unknown", unknown)
        self.assertEqual(unknown["reason"], "final_assignment_not_value_preserving")

    def test_width_mismatch_invalid_values_and_bool_are_unknown(self):
        cases = (
            (0, 1, 1, {"int_bits": 8, "unsigned_bits": 16}),
            (0, 1, 0, {}), (0, 1, 1025, {}),
            (True, 1, 1, {}), (-1, 1, 1, {}), (2, 1, 1, {}),
        )
        for lower, upper, block, keywords in cases:
            with self.subTest(arguments=(lower, upper, block, keywords)):
                self.assertEqual(check_unsigned_compound_interval(
                    lower, upper, block, **keywords)["status"], "unknown")

    def test_exhaustive_small_widths_match_explicit_unsigned_machine_recurrence(self):
        for bits in range(3, 7):
            signed_maximum = (1 << (bits - 1)) - 1
            for upper, block_threads in itertools.product(
                    range(signed_maximum + 1), range(1, signed_maximum + 2)):
                expected = simulate(upper, block_threads, bits)
                report = check_unsigned_compound_interval(
                    0, upper, block_threads, int_bits=bits, unsigned_bits=bits)
                self.assertEqual(report["status"], expected,
                                 (bits, upper, block_threads, report))


if __name__ == "__main__":
    unittest.main()
