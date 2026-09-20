"""Real Clang structural linking; no GPU or external intrinsic semantics."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from wavebridge.source import run
from wavebridge.analysis.reduction_chain import recover
from wavebridge.analysis import reduction_discovery
from wavebridge.analysis import reduction_chain


@unittest.skipUnless(shutil.which("clang++"), "requires real clang++")
class ReductionChainTests(unittest.TestCase):
    def setUp(self):
        fixture = Path(__file__).parent / "fixtures"
        helpers = (fixture / "reduction_entry.cpp").read_text().split("float entry(")[0]
        entry = (fixture / "normalization_output.cpp").read_text().split("void wrong_column(")[0]
        entry = entry.replace("float reduce_partial(float, float *);", "")
        self.source = helpers + entry.replace("reduce_partial(partial, scratch)", "aggregate(partial, scratch)")

    def analyze(self, source):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "input.cpp"
            path.write_text(source)
            output = Path(temporary) / "report"
            report = run(path, shutil.which("clang++"), ["-std=c++17"], "entry", 32, output)
            root = json.loads((output / "ast.json").read_text())["ast_roots"][0]
            return report, root

    def test_connects_renamed_source_without_oracle_and_keeps_obligations(self):
        source = self.source.replace("aggregate", "different_block").replace("subgroup", "different_warp")
        report, _ = self.analyze(source)
        chain = report["reduction_chain"]
        self.assertEqual("recovered", chain["status"], chain)
        self.assertEqual([16, 8, 4, 2, 1], chain["offsets"])
        self.assertEqual(256, chain["block_threads"])
        self.assertEqual(32, chain["width"])
        self.assertEqual(3, len(chain["links"]))
        self.assertEqual(chain["links"][0]["callee_id"], chain["links"][1]["caller_id"])
        self.assertEqual(chain["links"][1]["callee_id"], chain["links"][2]["caller_id"])
        self.assertFalse(chain["checked"])
        self.assertFalse(chain["deployable"])
        self.assertTrue(chain["unresolved_calls"])
        self.assertIn("analysis/reduction_chain.py", report["implementation_sha256"])

    def test_value_parameter_is_not_assumed_to_be_first(self):
        source = self.source.replace("aggregate(float value, float *shared)", "aggregate(float *shared, float value)")
        source = source.replace("aggregate(partial, scratch)", "aggregate(scratch, partial)")
        report, _ = self.analyze(source)
        self.assertEqual("recovered", report["reduction_chain"]["status"])
        self.assertEqual(1, report["reduction_chain"]["links"][0]["argument_index"])

    def test_inconsistent_width_and_step_are_not_connected(self):
        variants = [
            (self.source.replace("constexpr int step = 256", "constexpr int step = 128"),
             "column_step_block_threads_mismatch"),
            (self.source.replace("constexpr int width = 32;", "constexpr int width = 32; constexpr int different_width = 16;")
             .replace("coordinate() / width", "coordinate() / different_width")
             .replace("coordinate() % width", "coordinate() % different_width")
             .replace("threads / width", "threads / different_width"), "block_xor_width_mismatch")]
        for source, reason in variants:
            with self.subTest(reason=reason):
                report, _ = self.analyze(source)
                self.assertEqual("unknown", report["reduction_chain"]["status"])
                self.assertEqual(reason, report["reduction_chain"]["reason"])

    def test_missing_consumer_definition_and_budget_remain_unknown(self):
        source = self.source.replace("void entry(", "float external(float, float *);\nvoid entry(")
        report, _ = self.analyze(source.replace("aggregate(partial, scratch)", "external(partial, scratch)"))
        self.assertEqual("consumer_block_not_unique", report["reduction_chain"]["reason"])
        report, root = self.analyze(self.source)
        with patch.object(reduction_discovery, "MAX_CANDIDATE_ATTEMPTS", 0):
            result = recover(root, report["reduction_chain"]["function_id"], 32)
        self.assertEqual("discovery_budget_incomplete", result["reason"])

    def test_ambiguous_component_reports_are_not_resolved_by_list_order(self):
        report, root = self.analyze(self.source)
        function_id = report["reduction_chain"]["function_id"]
        for key, reason in (("block_candidates", "consumer_block_not_unique"),
                            ("xor_candidates", "block_xor_not_unique")):
            discovered = reduction_discovery.discover(root, function_id, 32)
            discovered[key].append(discovered[key][0])
            with self.subTest(key=key), patch.object(reduction_chain, "discover", return_value=discovered):
                result = recover(root, function_id, 32)
                self.assertEqual("unknown", result["status"])
                self.assertEqual(reason, result["reason"])


if __name__ == "__main__":
    unittest.main()
