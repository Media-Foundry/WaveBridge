"""Mock structural recovery; real two-sided route comparison, not source proof."""
import unittest
from unittest.mock import patch

from test_block_route_comparison import model
from wavebridge.device_evidence import compare_rmsnorm_routes


def evidence(width):
    return {"status": "evidence", "all_selected_relations_connected": True,
            "route_binding": {"inputs": model(width)}, "remaining_obligations": ["FP", "source"]}


class RMSNormRouteComparisonTests(unittest.TestCase):
    def test_fresh_both_sides_preserve_obligations_and_leaf_gap(self):
        with patch("wavebridge.device_evidence.collect_rmsnorm",
                   side_effect=[evidence(32), evidence(64)]) as collect:
            result = compare_rmsnorm_routes({"src": 1}, {"src_p": 1}, {"dst": 1}, {"dst_p": 1},
                                            max_ast_nodes=123)
        self.assertEqual(2, collect.call_count)
        self.assertEqual(({"src": 1}, {"src_p": 1}), collect.call_args_list[0].args)
        self.assertEqual(({"dst": 1}, {"dst_p": 1}), collect.call_args_list[1].args)
        self.assertEqual({"max_ast_nodes": 123}, collect.call_args_list[1].kwargs)
        self.assertEqual("evidence", result["status"])
        self.assertFalse(result["checks"]["route_relation"]["ordered_add_dags_equal"])
        self.assertEqual("not_established", result["leaf_value_correspondence"])
        self.assertEqual({"source": ["FP", "source"], "target": ["FP", "source"]},
                         result["remaining_obligations"])
        self.assertFalse(result["deployable"])

    def test_incomplete_or_rejected_side_cannot_be_upgraded(self):
        for status in ("unknown", "rejected"):
            for side in ("source", "target"):
                bad = {**evidence(32), "status": status}
                children = [bad] if side == "source" else [evidence(32), bad]
                with patch("wavebridge.device_evidence.collect_rmsnorm", side_effect=children):
                    result = compare_rmsnorm_routes({}, {}, {}, {})
                self.assertEqual(status, result["status"])
                self.assertNotIn("route_relation", result["checks"])

    def test_route_model_rechecked_not_trusted_from_side_status(self):
        bad = evidence(64)
        bad["route_binding"]["inputs"]["offsets"] = [16, 8, 4, 2, 1]
        with patch("wavebridge.device_evidence.collect_rmsnorm", side_effect=[evidence(32), bad]):
            result = compare_rmsnorm_routes({}, {}, {}, {})
        self.assertEqual("rejected", result["status"])


if __name__ == "__main__":
    unittest.main()
