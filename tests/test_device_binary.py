"""Mock observation failures separately from the recorded real LLVM extraction."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from wavebridge.frontend.device_binary import collect


class DeviceBinaryTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.binary = self.root/"original"
        self.binary.write_bytes(b"saved binary fixture")
        digest = hashlib.sha256(self.binary.read_bytes()).hexdigest()
        self.report = self.root/"original-report.json"
        self.report.write_text(json.dumps({"binary_sha256": digest,
                                          "build_binding": {"files": {"binary": {"sha256": digest}}}}))
        self.tool = self.root/"tool"
        self.tool.write_bytes(b"mock tool")

    def fake(self, *, absent=False, empty=False, fail=None, mutate=False):
        def invoke(command, timeout, cwd):
            result = {"command": command, "cwd": str(cwd), "timeout_seconds": timeout,
                      "status": "completed", "returncode": 0, "stdout": "tool observation\n",
                      "stderr": "", "duration_seconds": 0.0}
            if "--offloading" in command:
                self.assertEqual(Path(command[-1]).parent, cwd)
                self.assertNotEqual(Path(command[-1]), self.binary)
                if not absent:
                    (cwd/"snapshot.0.hipv4-amdgcn-amd-amdhsa--gfx1100").write_bytes(b"" if empty else b"code")
                if mutate:
                    self.binary.write_bytes(b"changed")
            if fail and fail in command:
                result.update(status="timeout", returncode=None, stdout="", stderr="timeout")
            return result
        return invoke

    def run_collect(self, fake):
        with patch("wavebridge.frontend.device_binary.clang_ast.invoke", side_effect=fake):
            return collect(self.binary, self.report, self.tool, self.tool, self.root, timeout=1)

    def test_snapshot_only_and_saved_hash_binding(self):
        result = self.run_collect(self.fake())
        self.assertEqual(result["status"], "observed")
        self.assertTrue(result["saved_binary_hash_matched"])
        self.assertEqual(len(result["device_objects"]), 1)
        self.assertEqual(result["snapshot"]["sha256"], result["inputs"]["binary"]["sha256"])
        self.assertFalse(list(self.root.glob("original.*")))
        for flag in ("source_program_checked", "metadata_semantically_validated",
                     "actual_fp_laws_verified", "dynamic_loader_selection_verified",
                     "GPU_executed", "numeric_contract_checked", "deployable"):
            self.assertFalse(result[flag])
        self.assertTrue(all("command_sha256" in job["execution"] for job in result["jobs"]))
        saved = json.loads((Path(result["run_directory"])/"report.json").read_text())
        self.assertEqual(saved, result)

    def test_mismatched_record_stops_before_tools(self):
        self.binary.write_bytes(b"different")
        result = self.run_collect(self.fake())
        self.assertEqual(result["status"], "saved_binary_hash_mismatch")
        self.assertFalse(result["saved_binary_hash_matched"])
        self.assertEqual(result["jobs"], [])

    def test_no_object_or_empty_object_not_observed(self):
        for opts, status in (({"absent": True}, "no_supported_device_objects"),
                             ({"empty": True}, "empty_device_object")):
            self.assertEqual(self.run_collect(self.fake(**opts))["status"], status)

    def test_timeouts_preserved_by_stage(self):
        for stage, status in (("--version", "tool_version_unavailable"),
                              ("--offloading", "extraction_failed"),
                              ("-d", "device_observation_failed")):
            result = self.run_collect(self.fake(fail=stage))
            self.assertEqual(result["status"], status)
            self.assertEqual(result["jobs"][-1]["execution"]["status"], "timeout")

    def test_changed_historical_input_not_observed(self):
        result = self.run_collect(self.fake(mutate=True))
        self.assertEqual(result["status"], "input_changed")
        self.assertFalse(result["direct_inputs_unchanged"])

    def test_missing_tool_and_bad_timeout_raise(self):
        with self.assertRaises(FileNotFoundError):
            collect(self.binary, self.report, self.root/"missing", self.tool, self.root)
        for timeout in (0, -1, True, float("nan")):
            with self.assertRaises(ValueError):
                collect(self.binary, self.report, self.tool, self.tool, self.root, timeout=timeout)

    def test_invalid_report_shape_and_duplicate_keys_fail_before_tools(self):
        for raw in ("[]", '{"build_binding": []}',
                    '{"build_binding": {"files": {"binary": []}}}',
                    '{"binary_sha256": "a", "binary_sha256": "b"}'):
            self.report.write_text(raw)
            with patch("wavebridge.frontend.device_binary.clang_ast.invoke") as invoke:
                with self.assertRaises(ValueError):
                    collect(self.binary, self.report, self.tool, self.tool, self.root)
                invoke.assert_not_called()


if __name__ == "__main__":
    unittest.main()
