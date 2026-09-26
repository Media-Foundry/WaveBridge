"""Compile-only collector tests. All compiler invocations are mocked; no GPU is used."""

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from wavebridge.frontend.device_compile import _command_hash, collect


def completed(*, returncode=0, stderr=""):
    return {"status": "completed", "returncode": returncode, "stdout": "",
            "stderr": stderr, "duration_seconds": 0.01}


class DeviceCompileTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.source = self.directory / "kernel.hip.cpp"
        self.protocol = self.directory / "protocol.json"
        self.compiler = self.directory / "hipcc"
        self.output_parent = self.directory / "runs"
        self.source.write_text("__global__ void kernel() {}\n")
        self.protocol.write_text('{"logical_width":32}\n')
        self.compiler.write_bytes(b"mock compiler\n")
        self.output_parent.mkdir()

    def fake_invoke(self, commands, *, output="normal", mutate=None):
        def invoke(command, timeout, cwd):
            commands.append((list(command), timeout, cwd))
            if command[-1] == "--version":
                result = completed()
                result.update(command=list(command), timeout_seconds=timeout, cwd=str(cwd))
                return result
            if command[-1] == "-###":
                result = completed(stderr="planned cc1")
                result.update(command=list(command), timeout_seconds=timeout, cwd=str(cwd))
                return result
            if mutate is not None:
                mutate()
            artifact = Path(command[command.index("-o") + 1])
            if output == "normal":
                artifact.write_bytes(b"IR\n" if artifact.suffix == ".ll" else b"ASM\n")
            elif output == "empty":
                artifact.write_bytes(b"")
            elif output == "missing":
                pass
            else:
                raise AssertionError(output)
            result = completed()
            result.update(command=list(command), timeout_seconds=timeout, cwd=str(cwd))
            return result
        return invoke

    def run_collect(self, invoke, *, contraction="default"):
        trace = {"status": "observed", "source_program_checked": False,
                 "deployable": False, "actual_ast_process_identity_established": False}
        with patch("wavebridge.frontend.device_compile.clang_ast.invoke", side_effect=invoke), \
                patch("wavebridge.frontend.device_compile.toolchain_trace.observe",
                      return_value=trace) as observe:
            report = collect(self.source, self.protocol, self.compiler, self.output_parent,
                             target="gfx1100", contraction=contraction, timeout=17)
        return report, observe

    def test_success_records_two_artifacts_commands_hashes_and_limits(self):
        commands = []
        report, observe = self.run_collect(self.fake_invoke(commands), contraction="off")
        self.assertEqual(report["status"], "compiled", report)
        self.assertEqual([job["kind"] for job in report["jobs"]], ["ir", "assembly"])
        self.assertEqual([job["status"] for job in report["jobs"]], ["compiled", "compiled"])
        self.assertEqual(observe.call_count, 2)
        for job in report["jobs"]:
            artifact = Path(job["artifact"]["path"])
            self.assertTrue(artifact.is_file())
            self.assertGreater(job["artifact"]["size"], 0)
            self.assertEqual(job["artifact"]["sha256"],
                             hashlib.sha256(artifact.read_bytes()).hexdigest())
            for execution in (job["execution"], job["driver_dry_run"]):
                self.assertEqual(execution["command_sha256"],
                                 _command_hash(execution["command"]))
            self.assertIn("-ffp-contract=off", job["execution"]["command"])
            self.assertIn("--offload-arch=gfx1100", job["execution"]["command"])
        self.assertEqual(report["version"]["command_sha256"],
                         _command_hash(report["version"]["command"]))
        self.assertTrue(report["direct_inputs_unchanged"])
        self.assertFalse(report["numeric_protocol_validated"])
        self.assertFalse(report["source_program_checked"])
        self.assertFalse(report["floating_point_equivalence_checked"])
        self.assertFalse(report["runtime_verified"])
        self.assertFalse(report["deployable"])
        saved = json.loads((Path(report["run_directory"]) / "report.json").read_text())
        self.assertEqual(saved["status"], "compiled")
        self.assertEqual(saved["jobs"], report["jobs"])

    def test_compile_failure_is_retained(self):
        commands = []

        def invoke(command, timeout, cwd):
            commands.append(list(command))
            if command[-1] in {"--version", "-###"}:
                return completed(stderr="planned" if command[-1] == "-###" else "")
            return completed(returncode=1, stderr="compile failed")

        report, _ = self.run_collect(invoke)
        self.assertEqual(report["status"], "incomplete")
        self.assertEqual([job["status"] for job in report["jobs"]],
                         ["compile_failed", "compile_failed"])
        self.assertTrue(all(job["execution"]["stderr"] == "compile failed"
                            for job in report["jobs"]))
        self.assertFalse(report["deployable"])

    def test_timeout_is_retained(self):
        def invoke(command, timeout, cwd):
            if command[-1] in {"--version", "-###"}:
                return completed(stderr="planned" if command[-1] == "-###" else "")
            return {"status": "timeout", "returncode": None, "stdout": "",
                    "stderr": "timed out", "duration_seconds": timeout}

        report, _ = self.run_collect(invoke)
        self.assertEqual(report["status"], "incomplete")
        self.assertEqual([job["status"] for job in report["jobs"]], ["timeout", "timeout"])
        self.assertFalse(report["runtime_verified"])

    def test_compiler_launch_failure_is_retained(self):
        def invoke(command, timeout, cwd):
            if command[-1] in {"--version", "-###"}:
                return completed(stderr="planned" if command[-1] == "-###" else "")
            return {"status": "launch_failed", "returncode": None, "stdout": "",
                    "stderr": "cannot execute compiler", "duration_seconds": 0.01}

        report, _ = self.run_collect(invoke)
        self.assertEqual(report["status"], "incomplete")
        self.assertEqual([job["status"] for job in report["jobs"]],
                         ["launch_failed", "launch_failed"])
        self.assertTrue(all(job["execution"]["stderr"] == "cannot execute compiler"
                            for job in report["jobs"]))
        self.assertFalse(report["deployable"])

    def test_dry_run_failure_does_not_upgrade_planned_toolchain(self):
        commands = []

        def invoke(command, timeout, cwd):
            commands.append(list(command))
            if command[-1] == "--version":
                result = completed()
                result.update(command=list(command), timeout_seconds=timeout, cwd=str(cwd))
                return result
            if command[-1] == "-###":
                return {"status": "launch_failed", "returncode": None, "stdout": "",
                        "stderr": "dry run failed", "duration_seconds": 0.01,
                        "command": list(command), "timeout_seconds": timeout,
                        "cwd": str(cwd)}
            artifact = Path(command[command.index("-o") + 1])
            artifact.write_bytes(b"compiled artifact\n")
            result = completed()
            result.update(command=list(command), timeout_seconds=timeout, cwd=str(cwd))
            return result

        trace = {"status": "unknown", "reason": "planned_cc1_job_not_unique",
                 "source_program_checked": False, "deployable": False}
        with patch("wavebridge.frontend.device_compile.clang_ast.invoke", side_effect=invoke), \
                patch("wavebridge.frontend.device_compile.toolchain_trace.observe",
                      return_value=trace) as observe:
            report = collect(self.source, self.protocol, self.compiler, self.output_parent,
                             target="gfx1100", contraction="default", timeout=17)
        self.assertEqual(report["status"], "compiled", report)
        self.assertEqual(observe.call_count, 2)
        for job in report["jobs"]:
            self.assertEqual(job["status"], "compiled")
            self.assertEqual(job["driver_dry_run"]["status"], "launch_failed")
            self.assertEqual(job["planned_toolchain"]["status"], "unknown")
            self.assertFalse(job["planned_toolchain"]["deployable"])
            self.assertNotIn("-ffp-contract=off", job["execution"]["command"])
        self.assertFalse(report["compilation_input_closure_established"])
        self.assertFalse(report["deployable"])

    def test_success_without_nonempty_output_is_incomplete(self):
        for output in ("missing", "empty"):
            with self.subTest(output=output):
                commands = []
                report, _ = self.run_collect(self.fake_invoke(commands, output=output))
                self.assertEqual(report["status"], "incomplete")
                self.assertEqual([job["status"] for job in report["jobs"]],
                                 ["output_missing_or_empty", "output_missing_or_empty"])
                for job in report["jobs"]:
                    self.assertFalse(job["artifact"]["size"])
                    if output == "missing":
                        self.assertIsNone(job["artifact"]["sha256"])

    def test_direct_input_change_overrides_success(self):
        changed = False

        def mutate():
            nonlocal changed
            if not changed:
                self.protocol.write_text('{"logical_width":64}\n')
                changed = True

        commands = []
        report, _ = self.run_collect(self.fake_invoke(commands, mutate=mutate))
        self.assertEqual([job["status"] for job in report["jobs"]], ["compiled", "compiled"])
        self.assertEqual(report["status"], "input_changed")
        self.assertFalse(report["direct_inputs_unchanged"])
        self.assertNotEqual(report["inputs"]["numeric_protocol"]["sha256"],
                            report["input_hashes_after"]["numeric_protocol"])
        self.assertFalse(report["deployable"])

    def test_invalid_configuration_does_not_invoke_compiler(self):
        invalid = [
            {"target": "gfx1100;bad"},
            {"target": "sm80"},
            {"target": "gfx1100", "contraction": "fast"},
            {"target": "gfx1100", "timeout": True},
            {"target": "gfx1100", "timeout": 0},
            {"target": "gfx1100", "timeout": float("inf")},
        ]
        for kwargs in invalid:
            with self.subTest(kwargs=kwargs), \
                    patch("wavebridge.frontend.device_compile.clang_ast.invoke") as invoke:
                with self.assertRaises(ValueError):
                    collect(self.source, self.protocol, self.compiler, self.output_parent,
                            **kwargs)
                invoke.assert_not_called()

    def test_consecutive_runs_use_independent_directories(self):
        reports = []
        for _ in range(2):
            commands = []
            report, _ = self.run_collect(self.fake_invoke(commands))
            reports.append(report)
        directories = [Path(report["run_directory"]) for report in reports]
        self.assertNotEqual(directories[0], directories[1])
        self.assertTrue(all(directory.is_dir() for directory in directories))
        self.assertTrue(all((directory / "ir.ll").is_file() and
                            (directory / "assembly.s").is_file()
                            for directory in directories))
        self.assertEqual([report["status"] for report in reports], ["compiled", "compiled"])


if __name__ == "__main__":
    unittest.main()
