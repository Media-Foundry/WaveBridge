from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from wavebridge.cli import main
from wavebridge.frontend.fixture import MAX_FIXTURE_BYTES, from_dict, load
from wavebridge.ir.model import example_source

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples" / "qdot"


class FrontendTests(unittest.TestCase):
    def test_round_trip_preserves_fingerprint(self):
        source = example_source()
        restored = from_dict(json.loads(json.dumps(source.to_dict())))
        self.assertEqual(restored, source)
        self.assertEqual(restored.fingerprint(), source.fingerprint())

    def test_example_matches_builtin(self):
        self.assertEqual(load(EXAMPLES / "source.json"), example_source())

    def test_unknown_field_rejected(self):
        value = example_source().to_dict()
        value["kernel"]["physical_wave_width"] = 64
        with self.assertRaises(ValueError):
            from_dict(value)

    def test_missing_numeric_contract_rejected(self):
        value = example_source().to_dict()
        del value["numeric_contract"]
        with self.assertRaises(ValueError):
            from_dict(value)

    def test_invalid_numbers_rejected(self):
        for number in (True, 0, -1, 3.5, "32"):
            with self.subTest(number=number):
                value = example_source().to_dict()
                value["kernel"]["cooperation_width"] = number
                with self.assertRaises(ValueError):
                    from_dict(value)

    def test_unknown_schema_rejected(self):
        value = example_source().to_dict()
        value["schema_version"] = "future/v2"
        with self.assertRaises(ValueError):
            from_dict(value)

    def test_duplicate_fields_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "duplicate.json"
            path.write_text('{"domain": {}, "domain": {}}')
            with self.assertRaisesRegex(ValueError, "duplicate"):
                load(path)

    def test_oversize_input_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "oversize.json"
            path.write_bytes(b" " * (MAX_FIXTURE_BYTES + 1))
            with self.assertRaisesRegex(ValueError, "exceeds"):
                load(path)


class CliTests(unittest.TestCase):
    def run_cli(self, args):
        stdout, stderr = StringIO(), StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(args)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_correct_fixture_accepted(self):
        code, out, err = self.run_cli(["check", str(EXAMPLES / "source.json"),
                                      str(EXAMPLES / "logical64.json")])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["verdict"], "checked")
        self.assertEqual(err, "")

    def test_incorrect_fixture_rejected(self):
        code, out, _ = self.run_cli(["check", str(EXAMPLES / "source.json"),
                                    str(EXAMPLES / "wrong_quant64.json")])
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(out)["verdict"], "rejected")

    def test_unknown_contract_exit_code(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "float.json"
            value = example_source().to_dict()
            value["numeric_contract"] = "float32"
            path.write_text(json.dumps(value))
            code, out, _ = self.run_cli(["check", str(path), str(path)])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(out)["verdict"], "unknown")

    def test_missing_file_is_input_error(self):
        code, out, err = self.run_cli(["inspect", str(EXAMPLES / "missing.json")])
        self.assertEqual(code, 3)
        self.assertEqual(out, "")
        self.assertEqual(json.loads(err)["verdict"], "input_error")

    def test_bad_command_is_input_error(self):
        code, _, _ = self.run_cli(["demo", "--target-width", "16"])
        self.assertEqual(code, 3)

    def test_inspect_does_not_claim_source_recovery(self):
        code, out, _ = self.run_cli(["inspect", str(EXAMPLES / "source.json")])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["source_recovery"], "not_implemented")

    def test_module_entrypoint(self):
        result = subprocess.run([sys.executable, "-m", "wavebridge", "demo"],
                                capture_output=True, text=True, cwd=ROOT, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["decision"], "accept_model_candidate")
