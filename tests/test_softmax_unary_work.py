"""Driver input-boundary fixtures, not evidence of source or GPU correctness."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from experiments.softmax_unary_work import run


class UnaryWorkDriverTests(unittest.TestCase):
    def test_recurrence_option_is_strict_boolean(self):
        with self.assertRaisesRegex(ValueError, "invalid_recurrence_option"):
            run("native", "math", "zero", "output", recurrence=1)

    def test_unsealed_input_fails_before_loading_or_output(self):
        with patch("experiments.softmax_unary_work.sha", return_value="wrong"):
            with self.assertRaisesRegex(ValueError, "sealed_input_mismatch"):
                run("native", "math", "zero", "output")

    def test_protocol_collision_is_not_silently_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = [Path(directory) / name for name in ("native", "math", "zero")]
            data = [{"status": "collected", "payload": {"ast": {}}},
                    {"external_effect_protocols": {"same": {}}},
                    {"call_protocols": {"same": {}}}]
            for path, value in zip(paths, data):
                path.write_text(json.dumps(value))
            from experiments.softmax_unary_work import NATIVE_SHA, MATH_SHA, ZERO_SHA
            with patch("experiments.softmax_unary_work.sha", side_effect=[NATIVE_SHA, MATH_SHA, ZERO_SHA, "driver"]), \
                    patch("experiments.softmax_unary_work.implementation_hashes", return_value={}), \
                    patch("experiments.softmax_unary_work.select_entry", return_value={}):
                output = Path(directory) / "output"
                with self.assertRaisesRegex(ValueError, "protocol_identity_collision"):
                    run(*paths, output)
                self.assertFalse(output.exists())

    def test_recurrence_driver_uses_fresh_result_not_prior_success(self):
        from experiments.softmax_unary_work import NATIVE_SHA, MATH_SHA, ZERO_SHA
        with tempfile.TemporaryDirectory() as directory:
            paths = [Path(directory) / name for name in ("native", "math", "zero")]
            payload = {"ast": {"kind": "TranslationUnitDecl"}}
            data = [{"status": "collected", "payload": payload},
                    {"status": "checked", "external_effect_protocols": {"math": {"unverified": True}}},
                    {"status": "checked", "call_protocols": {"zero": {"unverified": True}}}]
            for path, value in zip(paths, data):
                path.write_text(json.dumps(value))
            digests = dict(zip(paths, (NATIVE_SHA, MATH_SHA, ZERO_SHA)))
            with patch("experiments.softmax_unary_work.sha", side_effect=lambda p: digests.get(Path(p), "driver")), \
                    patch("experiments.softmax_unary_work.implementation_hashes", return_value={}), \
                    patch("experiments.softmax_unary_work.select_entry", return_value={"id": "entry"}), \
                    patch("experiments.softmax_unary_work.recover_with_call_effects",
                          return_value={"status": "unknown", "reason": "fresh_fixture_unknown"}) as fresh, \
                    patch("experiments.softmax_unary_work.check_work_preservation") as work:
                result = run(*paths, Path(directory) / "output", recurrence=True)
            self.assertEqual(fresh.call_count, 2)
            work.assert_not_called()
            self.assertEqual(result["checks"], [])
            self.assertEqual(result["mode"], "entry_recurrence")
            self.assertEqual(result["schema_version"], "softmax-unary-entry-recurrence/v1")
            self.assertIn("no guarded-loop preselection", result["selection"])
            for label in ("default", "unary_enabled"):
                self.assertEqual(result["recurrence_checks"][label]["status"], "unknown")
            for call, enabled in zip(fresh.call_args_list, (False, True)):
                self.assertEqual(call.args, (payload, "entry", 32,
                    {"zero": {"unverified": True}, "math": {"unverified": True}}))
                self.assertEqual(call.kwargs, {"allow_unary_float": enabled, "allow_using_shadows": enabled})
            self.assertFalse(result["source_program_checked"])
            self.assertFalse(result["deployable"])
