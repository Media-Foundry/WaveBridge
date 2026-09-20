import unittest

from wavebridge.verification.xor_routes import check


class XorRouteTests(unittest.TestCase):
    def test_all_reduce_covers_every_input_once_for_every_lane(self):
        for width, offsets in ((32, [16, 8, 4, 2, 1]), (64, [32, 16, 8, 4, 2, 1])):
            result = check(width, offsets)
            self.assertEqual(result["status"], "checked")
            self.assertEqual(result["lanes_checked"], width)
            self.assertEqual(result["floating_point_equivalence"], "not_checked")
            self.assertFalse(result["deployable"])

    def test_missing_and_duplicate_stages_reject(self):
        for offsets in ([16, 8, 4, 2], [16, 8, 4, 2, 1, 1], [0, 16, 8, 4, 2, 1], []):
            result = check(32, offsets)
            self.assertEqual(result["status"], "rejected")
            self.assertTrue(result["mismatches"])

    def test_independent_stage_order_checks_dependencies_not_fp_order(self):
        self.assertEqual(check(32, [1, 2, 4, 8, 16])["status"], "checked")

    def test_out_of_scope_is_unknown(self):
        for width, offsets in ((True, [1]), (128, [1]), (3, [1]), (32, [32]),
                               (32, [True]), (32, [1] * 17), (32, None)):
            self.assertEqual(check(width, offsets)["status"], "unknown")


if __name__ == "__main__":
    unittest.main()
