import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tests.test_rmsnorm_case import runner


IDENTITY = {
    "device_name": "mock", "gcn_arch_name": "mock-gfx", "pci_bus_id": "0000:00:00.0",
    "hip_runtime_version": "1", "hip_driver_version": "1",
}


def probe(path: Path):
    visible = {key: None for key in
               ("HIP_VISIBLE_DEVICES", "ROCR_VISIBLE_DEVICES", "CUDA_VISIBLE_DEVICES")}
    path.write_text(json.dumps({"overall_status": "verified",
                                "visible_device_environment": visible,
                                "physical_wave_width": 32, "device_identity": IDENTITY}))


def completed(args, stdout=""):
    return {"command": args, "status": "completed", "returncode": 0,
            "stdout": stdout, "stderr": "", "duration_seconds": 0.0}


class RmsNormRunnerGateTests(unittest.TestCase):
    def execute(self, logical_lines, *, compare=True):
        directory = tempfile.TemporaryDirectory()
        root = Path(directory.name)
        probe_path = root / "probe.json"
        probe(probe_path)
        calls = []

        def fake_command(args, timeout):
            calls.append(args)
            if args[-1] == "--version":
                return completed(args, "mock hipcc")
            if "-o" in args:
                Path(args[-1]).write_bytes(b"binary")
                return completed(args)
            Path(args[2]).write_bytes((0).to_bytes(4, "little"))
            lines = [*(f"{key}={value}" for key, value in IDENTITY.items()), *logical_lines]
            return completed(args, "\n".join(lines) + "\n")

        comparison = {"passed": True}
        compare_patch = patch.object(runner.reference, "compare", return_value=comparison)
        command_patch = patch.object(runner, "command", side_effect=fake_command)
        with command_patch, compare_patch as mocked_compare:
            code, report_path = runner.run(root, "hipcc", probe_path, 1, 1, 1)
        report = json.loads(report_path.read_text())
        if compare:
            mocked_compare.assert_called_once()
        else:
            mocked_compare.assert_not_called()
        directory.cleanup()
        return code, report, calls

    def test_changed_source_is_rejected_before_any_process(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            changed = root / "candidate.hip.cpp"
            changed.write_bytes(runner.SOURCE.read_bytes().replace(b"kLogicalWidth = 32",
                                                                   b"kLogicalWidth = 64", 1))
            probe_path = root / "probe.json"
            probe(probe_path)
            with patch.object(runner, "SOURCE", changed), patch.object(runner, "command") as command:
                code, report_path = runner.run(root, "hipcc", probe_path, 1, 1, 1)
            report = json.loads(report_path.read_text())
            self.assertEqual((2, "invalid_baseline_inputs"), (code, report["status"]))
            self.assertEqual("baseline_source_provenance_mismatch",
                             report["input_protocol_validation"]["reason"])
            command.assert_not_called()

    def test_protocol_mismatch_is_rejected_before_any_process(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            probe_path = root / "probe.json"
            probe(probe_path)
            altered = copy.deepcopy(runner.reference.PROTOCOL)
            altered["launch"]["logical_width"] = 64
            with (patch.object(runner.reference, "PROTOCOL", altered),
                  patch.object(runner, "command") as command):
                code, report_path = runner.run(root, "hipcc", probe_path, 1, 1, 1)
            report = json.loads(report_path.read_text())
            self.assertEqual((2, "invalid_baseline_inputs"), (code, report["status"]))
            self.assertEqual("copied_protocol_reference_mismatch",
                             report["input_protocol_validation"]["reason"])
            command.assert_not_called()

    def test_missing_or_malformed_frozen_inputs_write_structured_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            probe_path = root / "probe.json"
            probe(probe_path)
            missing = root / "missing.hip.cpp"
            with patch.object(runner, "SOURCE", missing), patch.object(runner, "command") as command:
                code, report_path = runner.run(root, "hipcc", probe_path, 1, 1, 1)
            report = json.loads(report_path.read_text())
            self.assertEqual((2, "invalid_baseline_inputs"), (code, report["status"]))
            self.assertEqual("baseline_input_copy_failed",
                             report["input_protocol_validation"]["reason"])
            command.assert_not_called()

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            probe_path = root / "probe.json"
            probe(probe_path)
            original_copy = runner.shutil.copyfile

            def malformed_provenance(source, destination):
                result = original_copy(source, destination)
                if Path(destination).name == "provenance.json":
                    Path(destination).write_text("{")
                return result

            with (patch.object(runner.shutil, "copyfile", side_effect=malformed_provenance),
                  patch.object(runner, "command") as command):
                code, report_path = runner.run(root, "hipcc", probe_path, 1, 1, 1)
            report = json.loads(report_path.read_text())
            self.assertEqual((2, "invalid_baseline_inputs"), (code, report["status"]))
            self.assertEqual("baseline_input_missing_or_malformed",
                             report["input_protocol_validation"]["reason"])
            command.assert_not_called()

    def test_frozen_baseline_reaches_existing_probe_and_runtime_path(self):
        code, report, calls = self.execute(["logical_width=32"])
        self.assertEqual((0, "passed"), (code, report["status"]))
        self.assertEqual("verified_frozen_logical32_baseline",
                         report["input_protocol_validation"]["status"])
        self.assertEqual("verified_runtime_logical_width",
                         report["runtime_protocol_validation"]["status"])
        self.assertFalse(report["runtime_protocol_validation"]["physical_wave_width_inferred"])
        self.assertEqual(3, len(calls))

    def test_protocol_comparison_is_type_sensitive_and_json_is_strict(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.cpp"
            protocol = root / "protocol.json"
            provenance = root / "provenance.json"
            source.write_bytes(b"source")
            provenance.write_text(json.dumps({"baseline_sha256": runner.digest(source)}))
            changed = copy.deepcopy(runner.reference.PROTOCOL)
            changed["launch"]["logical_width"] = 32.0
            protocol.write_text(json.dumps(changed))
            result = runner.validate_baseline_inputs(source, protocol, provenance)
            self.assertEqual("copied_protocol_reference_mismatch", result["reason"])

            protocol.write_text('{"launch":{},"launch":{}}')
            result = runner.validate_baseline_inputs(source, protocol, provenance)
            self.assertEqual("baseline_input_missing_or_malformed", result["reason"])

            protocol.write_text('{"value":NaN}')
            result = runner.validate_baseline_inputs(source, protocol, provenance)
            self.assertEqual("baseline_input_missing_or_malformed", result["reason"])

    def test_missing_repeated_or_mismatched_runtime_width_stops_before_compare(self):
        for lines in ([], ["logical_width=32", "logical_width=32"], ["logical_width=64"],
                      ["logical_width=" + "9" * 5000]):
            with self.subTest(lines=lines):
                code, report, calls = self.execute(lines, compare=False)
                self.assertEqual((2, "runtime_protocol_mismatch"), (code, report["status"]))
                self.assertEqual(3, len(calls))
                self.assertEqual("rejected", report["runtime_protocol_validation"]["status"])


if __name__ == "__main__":
    unittest.main()
