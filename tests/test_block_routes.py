import unittest

from wavebridge.verification.block_routes import check


class BlockRouteTests(unittest.TestCase):
    def test_two_stage_routes_cover_every_thread_once(self):
        for block, width, stages in ((256, 32, [16, 8, 4, 2, 1]),
                                     (256, 64, [32, 16, 8, 4, 2, 1])):
            report = check(block, width, stages)
            self.assertEqual(report["status"], "checked")
            self.assertEqual(report["threads_checked"], block)
            self.assertFalse(report["source_program_checked"])

    def test_missing_duplicate_and_shifted_partial_fail(self):
        good = [16, 8, 4, 2, 1]
        for report in (check(256, 32, good[:-1]),
                       check(256, 32, good, second_offsets=good + [1]),
                       check(256, 32, good, load_offset=1),
                       check(256, 32, good, shared_slots=7)):
            self.assertEqual(report["status"], "rejected")

    def test_all_reduce_allows_other_single_writers_under_model(self):
        self.assertEqual(check(256, 32, [16, 8, 4, 2, 1], writer_lane=31)["status"], "checked")

    def test_missing_preconditions_are_unknown(self):
        for report in (check(256, 32, [], barrier=False), check(255, 32, []),
                       check(256, 32, [32]), check(256, 32, [], writer_lane=True)):
            self.assertEqual(report["status"], "unknown")


if __name__ == "__main__":
    unittest.main()
