import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import subprocess

from runtime.probes import probe


class DeviceProbeTests(unittest.TestCase):
    def test_semantics_accepts_consistent_wave32(self):
        expected_shuffle = [31] * 32 + [63] * 32
        values = {
            "host_reported_warp_size": "32",
            "device_warp_sizes": ",".join(["32"] * 64),
            "ballots": ",".join(["00000000ffffffff"] * 64),
            "shuffles": ",".join(map(str, expected_shuffle)),
        }
        result = probe.validate_semantics(values)
        self.assertEqual(result["status"], "consistent")
        self.assertEqual(result["physical_wave_width"], 32)

    def test_semantics_rejects_width64_label_with_wave32_behavior(self):
        values = {
            "host_reported_warp_size": "64",
            "device_warp_sizes": ",".join(["64"] * 64),
            "ballots": ",".join(["00000000ffffffff"] * 64),
            "shuffles": ",".join(map(str, [31] * 32 + [63] * 32)),
        }
        result = probe.validate_semantics(values)
        self.assertEqual(result["status"], "semantic_mismatch")

    def test_missing_tool_writes_unknown_report_without_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.object(probe.shutil, "which", return_value=None):
                code1, path1, report1 = probe.run(Path(directory), 1)
                code2, path2, _ = probe.run(Path(directory), 1)
            self.assertEqual(code1, 2)
            self.assertEqual(report1["reason"], "tool_missing")
            self.assertEqual(report1["stages"]["compile"]["status"], "not_run")
            self.assertEqual(report1["stages"]["execute"]["status"], "not_run")
            self.assertNotEqual(path1, path2)
            self.assertEqual(json.loads(path1.read_text())["overall_status"], "unknown")

    def test_metadata_absence_is_not_success(self):
        attempts = []

        def fake_which(tool):
            return f"/fake/{tool}"

        def fake_invoke(command, timeout, cwd=None):
            attempts.append(command)
            return {"command": command, "timeout_seconds": timeout,
                    "status": "completed", "returncode": 0,
                    "stdout": "no relevant metadata", "stderr": "",
                    "duration_seconds": 0.0}

        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / "probe"
            binary.write_bytes(b"binary")
            with mock.patch.object(probe.shutil, "which", side_effect=fake_which), \
                 mock.patch.object(probe, "invoke", side_effect=fake_invoke):
                result = probe.extract_metadata(binary, Path(directory), 1)
        self.assertEqual(result["status"], "metadata_unestablished")
        self.assertTrue(attempts)

    def test_timeout_preserves_byte_logs_and_kills_process_group(self):
        process = mock.Mock(pid=123, returncode=None)
        process.communicate.side_effect = [
            subprocess.TimeoutExpired(["fake"], 1, output=b"partial-out",
                                      stderr=b"partial-err"),
            (b"partial-out-tail", b"partial-err-tail"),
        ]
        with mock.patch.object(probe.subprocess, "Popen", return_value=process), \
             mock.patch.object(probe.os, "killpg") as killpg:
            result = probe.invoke(["fake"], 1)
        self.assertEqual(result["status"], "timeout")
        self.assertIn("partial-out", result["stdout"])
        self.assertIn("partial-err", result["stderr"])
        self.assertEqual(result["stdout"], "partial-out-tail")
        killpg.assert_called_once_with(123, probe.signal.SIGKILL)

    def test_compile_failure_has_distinct_status(self):
        def fake_invoke(command, timeout, cwd=None):
            if "--version" in command:
                return record("completed", 0, "InstalledDir: /missing\n")
            if "--save-temps" in command:
                return record("completed", 1, stderr="link failed")
            return record("completed", 0)

        with tempfile.TemporaryDirectory() as directory, \
             mock.patch.object(probe.shutil, "which", side_effect=lambda tool: f"/fake/{tool}"), \
             mock.patch.object(probe, "invoke", side_effect=fake_invoke):
            code, _, report = probe.run(Path(directory), 1)
        self.assertEqual(code, 1)
        self.assertEqual(report["reason"], "compile_failed")
        self.assertEqual(report["stages"]["execute"]["status"], "not_run")

    def test_metadata_runtime_disagreement_fails(self):
        result = probe.reconcile_widths(
            {"status": "established", "physical_wave_width": 64},
            {"status": "consistent", "physical_wave_width": 32})
        self.assertEqual(result["status"], "failed")

    def test_no_device_and_runtime_error_are_distinct(self):
        no_device = probe.parse_probe_output("device_count=0\nfailure_kind=no_device\n")
        runtime_error = probe.parse_probe_output("failure_kind=runtime_error\n")
        self.assertEqual(no_device["failure_kind"], "no_device")
        self.assertNotEqual(runtime_error["failure_kind"], "no_device")

    def test_kernel_metadata_is_bound_to_named_entry(self):
        text = """
amdhsa.kernels:
  - .agpr_count: 0
    .name: unrelated
    .wavefront_size: 64
  - .agpr_count: 0
    .name: _Z16wavebridge_probePi
    .wavefront_size: 32
"""
        self.assertEqual(probe.kernel_metadata_widths(text), {32})

    def test_kernel_metadata_does_not_require_agpr_count(self):
        text = """
amdhsa.kernels:
  - .args:
      - .name: input
        .value_kind: global_buffer
    .name: _Z16wavebridge_probePi
    .wavefront_size: 32
  - .args: []
    .name: unrelated
    .wavefront_size: 64
amdhsa.target: amdgcn-amd-amdhsa--gfx1100
"""
        self.assertEqual(probe.kernel_metadata_widths(text), {32})

    def test_next_kernel_width_cannot_fill_missing_probe_width(self):
        text = """
amdhsa.kernels:
  - .args: []
    .name: _Z16wavebridge_probePi
  - .args: []
    .name: unrelated
    .wavefront_size: 64
amdhsa.target: amdgcn-amd-amdhsa--gfx1100
"""
        self.assertEqual(probe.kernel_metadata_widths(text), set())

    def test_run_timeout_is_unknown(self):
        code, report = self.run_with_execution(record("timeout", None,
                                                      stdout="partial"))
        self.assertEqual(code, 2)
        self.assertEqual(report["reason"], "run_timeout")

    def test_no_device_run_is_unknown_not_failure(self):
        code, report = self.run_with_execution(
            record("completed", 4, stdout="failure_kind=no_device\n"))
        self.assertEqual(code, 2)
        self.assertEqual(report["reason"], "no_device")

    def run_with_execution(self, execution):
        def fake_invoke(command, timeout, cwd=None):
            if "--version" in command:
                return record("completed", 0, "InstalledDir: /missing\n")
            if "--save-temps" in command:
                Path(command[-1]).write_bytes(b"binary")
                return record("completed", 0)
            if len(command) == 1 and command[0].endswith("device_probe"):
                return execution
            return record("completed", 0)

        with tempfile.TemporaryDirectory() as directory, \
             mock.patch.object(probe.shutil, "which", side_effect=lambda tool: f"/fake/{tool}"), \
             mock.patch.object(probe, "invoke", side_effect=fake_invoke), \
             mock.patch.object(probe, "extract_metadata",
                               return_value={"status": "metadata_unestablished"}):
            code, _, report = probe.run(Path(directory), 1)
        return code, report


def record(status, returncode, stdout="", stderr=""):
    return {"command": [], "timeout_seconds": 1, "status": status,
            "returncode": returncode, "stdout": stdout, "stderr": stderr,
            "duration_seconds": 0.0}


if __name__ == "__main__":
    unittest.main()
