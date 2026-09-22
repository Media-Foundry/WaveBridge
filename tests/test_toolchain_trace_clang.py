"""Real driver dry-runs remain distinct from actual AST process identity."""
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from wavebridge.frontend.clang_ast import collect, invoke
from wavebridge.source import run


@unittest.skipUnless(shutil.which("clang++"), "requires real clang++")
class ToolchainTraceClangTests(unittest.TestCase):
    def test_source_reports_planned_job_without_process_attestation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "input.cpp"
            source.write_text("void target() {}\n")
            report = run(source, shutil.which("clang++"), [], "target", 32,
                         root / "out", toolchain_trace=True)
            self.assertEqual("analyzed", report["status"], report)
            trace = report["toolchain_trace"]
            self.assertEqual("observed", trace["status"], trace)
            self.assertIn("-###", trace["execution"]["command"])
            self.assertNotIn("-###", report["command"])
            self.assertFalse(trace["actual_ast_process_identity_established"])
            self.assertFalse(report["compilation_input_closure_established"])
            self.assertFalse(report["checked"])

    def test_failed_dry_run_is_recorded_not_upgraded_by_successful_ast(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "input.cpp"
            source.write_text("void target() {}\n")

            def execute(command, timeout, cwd):
                if "-###" in command:
                    return {"status": "timeout", "returncode": None,
                            "stdout": "", "stderr": "", "command": command}
                return invoke(command, timeout, cwd)

            with patch("wavebridge.frontend.clang_ast.invoke", side_effect=execute):
                report = collect(source, shutil.which("clang++"), [], "target",
                                 toolchain_trace=True)
            self.assertEqual("collected", report["status"])
            self.assertEqual("unknown", report["toolchain_trace"]["status"])
            self.assertEqual("driver_trace_execution_failed", report["toolchain_trace"]["reason"])

    def test_default_does_not_claim_trace_and_invalid_mode_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "input.cpp"
            source.write_text("void target() {}\n")
            report = collect(source, shutil.which("clang++"), [], "target")
            self.assertEqual("not_requested", report["toolchain_trace"]["status"])
            report = collect(source, shutil.which("clang++"), [], "target", toolchain_trace="yes")
            self.assertEqual("input_error", report["status"])


if __name__ == "__main__":
    unittest.main()
