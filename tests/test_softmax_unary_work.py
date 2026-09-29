"""Driver input-boundary fixtures, not evidence of source or GPU correctness."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from experiments.softmax_unary_work import run


class UnaryWorkDriverTests(unittest.TestCase):
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
