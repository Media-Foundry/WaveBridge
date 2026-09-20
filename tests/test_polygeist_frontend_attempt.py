"""Mock execution-state tests, not evidence about any real cgeist capability."""

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "polygeist_attempt", ROOT / "experiments/baselines/polygeist_frontend.py")
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)


class PolygeistFrontendAttemptTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.source = self.directory / "source.cu"
        self.source.write_text("// execution-state fixture, not a GPU case\n")
        self.tool = self.directory / "cgeist"
        self.tool.write_text("not executed: mocked tool")
        self.output_base = self.directory / "reports"

    def run_attempt(self, *, code=0, status="completed", output=None, cuda_lower=False,
                    emit_llvm=False):
        def invoke(command, timeout, cwd):
            self.assertIn("-S", command)
            self.assertIn("--function=*", command)
            self.assertNotIn("--emit-cuda", command)
            self.assertEqual(cuda_lower, "--cuda-lower" in command)
            self.assertEqual(emit_llvm, "--emit-llvm" in command)
            self.assertEqual(".ll" if emit_llvm else ".mlir", Path(command[-1]).suffix)
            if output is not None:
                Path(command[-1]).write_text(output)
            return {"command": command, "cwd": str(cwd), "status": status,
                    "returncode": code, "stdout": "raw stdout", "stderr": "raw stderr"}
        with patch.object(RUNNER.shutil, "which", return_value=str(self.tool)), \
                patch.object(RUNNER, "invoke", side_effect=invoke):
            return RUNNER.run(self.source, self.tool, self.directory, [], self.output_base,
                              cuda_lower=cuda_lower, emit_llvm=emit_llvm)

    def test_llvm_output_is_separate_and_unverified(self):
        _, report = self.run_attempt(output="not validated LLVM", cuda_lower=True,
                                     emit_llvm=True)
        self.assertEqual("llvm_ir", report["requested_output_kind"])
        self.assertEqual("llvm_ir_emission_only", report["scope"])
        self.assertFalse(report["ir_verified"])
        self.assertFalse(report["deployable"])
        self.assertEqual("not_run", report["gpu_execution"])

    def test_non_boolean_llvm_request_is_rejected_before_creating_output(self):
        for value in (1, "false", None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                RUNNER.run(self.source, self.tool, self.directory, [], self.output_base,
                           emit_llvm=value)
        self.assertFalse(self.output_base.exists())

    def test_lowering_request_is_recorded_without_promoting_guarantees(self):
        _, report = self.run_attempt(output="module {}", cuda_lower=True)
        self.assertTrue(report["cuda_lower_requested"])
        self.assertEqual("cgeist_O0_cuda_lower_passes", report["pipeline"])
        self.assertFalse(report["ir_verified"])
        self.assertFalse(report["deployable"])
        self.assertFalse(report["source_program_checked"])
        self.assertEqual("not_run", report["gpu_execution"])

    def test_non_boolean_lowering_is_rejected_before_creating_output(self):
        for value in (1, "false", None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                RUNNER.run(self.source, self.tool, self.directory, [], self.output_base,
                           cuda_lower=value)
        self.assertFalse(self.output_base.exists())

    def test_emission_does_not_imply_verification(self):
        path, report = self.run_attempt(output="not even valid MLIR")
        self.assertEqual("emitted_unverified_ir", report["status"])
        self.assertFalse(report["ir_verified"])
        self.assertEqual("cgeist_O0_default_passes_not_identity_translation", report["pipeline"])
        self.assertFalse(report["deployable"])
        self.assertFalse(report["source_program_checked"])
        self.assertEqual("not_run", report["gpu_execution"])
        self.assertEqual(report, json.loads(path.read_text()))

    def test_failed_tool_retains_partial_output_and_diagnostics(self):
        _, report = self.run_attempt(code=1, output="partial")
        self.assertEqual("tool_failed", report["status"])
        self.assertEqual(7, report["ir"]["size_bytes"])
        self.assertEqual("raw stderr", report["execution"]["stderr"])

    def test_missing_and_empty_ir_are_not_emission_success(self):
        for output in (None, ""):
            with self.subTest(output=output):
                _, report = self.run_attempt(output=output)
                self.assertEqual("no_ir_emitted", report["status"])

    def test_timeout_and_launch_failure_remain_distinct(self):
        for status in ("timeout", "launch_failed"):
            with self.subTest(status=status):
                _, report = self.run_attempt(status=status, code=None)
                self.assertEqual(status, report["status"])

    def test_missing_tool_never_invokes_process(self):
        with patch.object(RUNNER.shutil, "which", return_value=None), \
                patch.object(RUNNER, "invoke") as invoke:
            _, report = RUNNER.run(self.source, self.tool, self.directory, [], self.output_base)
            self.assertEqual("tool_missing", report["status"])
            invoke.assert_not_called()

    def test_repeated_attempts_do_not_overwrite_evidence(self):
        first, _ = self.run_attempt(code=1, output="first attempt")
        original = first.read_bytes()
        second, _ = self.run_attempt(output="second attempt")
        self.assertNotEqual(first.parent, second.parent)
        self.assertEqual(original, first.read_bytes())

    def test_invalid_timeout_is_rejected_before_creating_output(self):
        for timeout in (0, -1, float("inf"), float("nan"), True):
            with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                RUNNER.run(self.source, self.tool, self.directory, [], self.output_base,
                           timeout=timeout)
        self.assertFalse(self.output_base.exists())


if __name__ == "__main__":
    unittest.main()
