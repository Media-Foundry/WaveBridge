"""Artifact-binding tests, not independent workload coverage."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from experiments import softmax_constant_followup as followup
from test_pytorch_softmax_intake import entry


class SoftmaxConstantFollowupTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.ast = self.root / "ast.json"
        self.ast.write_text(json.dumps({"status": "collected", "ast_roots": [{"inner": [entry()]}]}))
        self.previous = self.root / "previous.json"
        self.previous.write_text(json.dumps({"ast_report_sha256": followup.sha(self.ast),
                                             "loop_counts": {"unknown": 8},
                                             "loop_reasons": {"unsupported": 8}}))

    def replay(self, *, changed=False):
        original = self.previous.read_bytes()
        with patch.object(followup, "AST_SHA", followup.sha(self.ast)), \
                patch.object(followup, "PREVIOUS_REPORT_SHA", followup.sha(self.previous)), \
                patch.object(followup, "implementation_hashes", side_effect=[
                    {"module": "before"}, {"module": "after" if changed else "before"}]):
            result = followup.run(self.ast, self.previous, self.root / "run")
        self.assertEqual(self.previous.read_bytes(), original)
        return result

    def test_development_replay_never_overwrites_frozen_result_or_deploys(self):
        result = self.replay()
        self.assertEqual(result["status"], "analyzed")
        self.assertIn("development_replay", result["evaluation_role"])
        self.assertEqual(result["previous_loop_counts"], {"unknown": 8})
        for flag in ("source_program_checked", "GPU_executed", "deployable", "frontend_reexecuted"):
            self.assertFalse(result[flag])

    def test_hash_mismatch_refuses_before_analysis_or_output_directory(self):
        with patch.object(followup, "recover") as recover:
            with self.assertRaisesRegex(ValueError, "hash_mismatch"):
                followup.run(self.ast, self.previous, self.root / "run")
            recover.assert_not_called()
        self.assertFalse((self.root / "run").exists())

    def test_implementation_drift_invalidates_replay(self):
        result = self.replay(changed=True)
        self.assertEqual(result["status"], "inputs_changed")
        self.assertFalse(result["inputs_unchanged"])

    def test_old_report_must_bind_exact_ast(self):
        self.previous.write_text(json.dumps({"ast_report_sha256": "wrong"}))
        with self.assertRaisesRegex(ValueError, "ast_binding_mismatch"):
            self.replay()


if __name__ == "__main__":
    unittest.main()
