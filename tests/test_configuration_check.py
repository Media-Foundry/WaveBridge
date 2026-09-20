import json
from pathlib import Path
import tempfile
import unittest

from wavebridge.configuration_check import run


class ConfigurationCheckTests(unittest.TestCase):
    def test_empty_launches_cannot_pass_and_outputs_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            source = directory / "source.json"
            source.write_text(json.dumps({"schema_version": "source-column-evidence/v1",
                                          "status": "analyzed", "launch_facts": {"sites": []}}))
            abi = Path(__file__).parents[1] / "examples/abi/int32-conditional.json"
            result = run(source, abi, directory / "check.json")
            self.assertEqual(result["status"], "unknown")
            self.assertFalse(result["all_configuration_models_checked"])
            self.assertFalse(result["source_program_checked"])
            self.assertEqual(len(result["source_report_sha256"]), 64)
            with self.assertRaises(FileExistsError):
                run(source, abi, source)
            with self.assertRaises(FileExistsError):
                run(source, abi, directory / "check.json")

    def test_missing_constructor_positions_remain_unknown(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            source = directory / "source.json"
            source.write_text(json.dumps({"schema_version": "source-column-evidence/v1",
                                          "status": "analyzed", "launch_facts": {"sites": [{}]}}))
            abi = Path(__file__).parents[1] / "examples/abi/int32-conditional.json"
            result = run(source, abi, directory / "check.json")
            self.assertEqual(len(result["checks"]), 2)
            self.assertEqual(result["status"], "unknown")

    def test_malformed_or_duplicate_fields_do_not_produce_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            source = directory / "source.json"
            abi = Path(__file__).parents[1] / "examples/abi/int32-conditional.json"
            for content in (
                '{"status":"analyzed", "status":"unknown"}',
                '{"value": NaN}',
                '{"value": Infinity}',
                json.dumps({"schema_version": "source-column-evidence/v1", "status": "analyzed",
                            "launch_facts": None}),
            ):
                source.write_text(content)
                with self.assertRaises(ValueError):
                    run(source, abi, directory / "check.json")
                self.assertFalse((directory / "check.json").exists())


if __name__ == "__main__":
    unittest.main()
