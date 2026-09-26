"""Build-binding and phase-integrity tests for the frozen RMSNorm runner.

All process calls are mocked.  These tests do not compile code or use a GPU.
"""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tests.test_rmsnorm_case import runner
from tests.test_rmsnorm_runner_gates import IDENTITY, completed, probe


class RmsNormBuildBindingTests(unittest.TestCase):
    def run_case(self, command, *, compare=True):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        probe_path = root / "probe.json"
        probe(probe_path)
        comparison = {"passed": True}
        with patch.object(runner, "command", side_effect=command) as mocked_command, \
                patch.object(runner.reference, "compare", return_value=comparison) as mocked_compare:
            code, report_path = runner.run(root, "hipcc", probe_path, 1, 1, 1)
        report = json.loads(report_path.read_text())
        if compare:
            mocked_compare.assert_called_once()
        else:
            mocked_compare.assert_not_called()
        return code, report, mocked_command.call_args_list

    @staticmethod
    def successful_command(args, timeout):
        if args[-1] == "--version":
            return completed(args, "mock hipcc")
        if "-o" in args:
            Path(args[-1]).write_bytes(b"binary")
            return completed(args)
        Path(args[2]).write_bytes((0).to_bytes(4, "little"))
        lines = [*(f"{key}={value}" for key, value in IDENTITY.items()),
                 "logical_width=32"]
        return completed(args, "\n".join(lines) + "\n")

    def test_success_binds_command_inputs_and_binary_at_all_boundaries(self):
        code, report, calls = self.run_case(self.successful_command)
        self.assertEqual((0, "passed"), (code, report["status"]))
        binding = report["build_binding"]
        self.assertEqual("rmsnorm-baseline-build-binding/v1", binding["schema_version"])
        self.assertEqual(["hipcc", "-O2", binding["files"]["source"]["path"],
                          "-o", binding["command"][-1]], binding["command"])
        self.assertNotIn("-ffp-contract=off", binding["command"])
        self.assertEqual(binding["command"], calls[1].args[0])
        self.assertEqual(set(binding["files"]),
                         {"source", "protocol", "reference", "runner", "provenance",
                          "input", "expected", "probe_report", "binary"})
        self.assertEqual(report["binary_sha256"], binding["files"]["binary"]["sha256"])
        self.assertEqual(
            {"before_compile", "before_execute", "after_execute"},
            set(report["artifact_integrity"]),
        )
        self.assertTrue(all(item["status"] == "unchanged"
                            for item in report["artifact_integrity"].values()))
        self.assertFalse(binding["compiler_process_identity_established"])
        self.assertFalse(binding["compilation_input_closure_established"])
        self.assertFalse(binding["floating_point_equivalence_checked"])

    def test_version_stage_protocol_change_stops_before_compile(self):
        calls = []

        def command(args, timeout):
            calls.append(args)
            self.assertEqual("--version", args[-1])
            # The copied protocol is the binding sibling of the copied source.
            artifacts = list(self.root_for_command.glob("wb02-*/protocol.json"))
            self.assertEqual(1, len(artifacts))
            artifacts[0].write_text('{"changed":true}\n')
            return completed(args, "mock hipcc")

        with tempfile.TemporaryDirectory() as directory:
            self.root_for_command = Path(directory)
            probe_path = self.root_for_command / "probe.json"
            probe(probe_path)
            with patch.object(runner, "command", side_effect=command), \
                    patch.object(runner.reference, "compare") as compare:
                code, report_path = runner.run(self.root_for_command, "hipcc", probe_path,
                                               1, 1, 1)
            report = json.loads(report_path.read_text())
        self.assertEqual((2, "artifact_integrity_mismatch"), (code, report["status"]))
        self.assertEqual(["protocol"], report["artifact_integrity"]["before_compile"]["changed"])
        self.assertEqual(1, len(calls))
        self.assertIsNone(report["compile"])
        compare.assert_not_called()

    def test_compile_stage_source_or_input_change_stops_before_execute(self):
        for changed_name in ("source", "input"):
            with self.subTest(changed_name=changed_name):
                calls = []

                def command(args, timeout):
                    calls.append(args)
                    if args[-1] == "--version":
                        return completed(args, "mock hipcc")
                    self.assertIn("-o", args)
                    binary = Path(args[-1])
                    binary.write_bytes(b"binary")
                    target = Path(args[2]) if changed_name == "source" else binary.parent / "input.f32"
                    target.write_bytes(target.read_bytes() + b"changed")
                    return completed(args)

                code, report, _ = self.run_case(command, compare=False)
                self.assertEqual((2, "artifact_integrity_mismatch"),
                                 (code, report["status"]))
                self.assertEqual([changed_name],
                                 report["artifact_integrity"]["before_execute"]["changed"])
                self.assertEqual(2, len(calls))
                self.assertIsNone(report["execute"])

    def test_execute_stage_binary_or_input_change_stops_before_compare(self):
        for changed_name in ("binary", "input"):
            with self.subTest(changed_name=changed_name):
                def command(args, timeout):
                    if args[-1] == "--version":
                        return completed(args, "mock hipcc")
                    if "-o" in args:
                        Path(args[-1]).write_bytes(b"binary")
                        return completed(args)
                    binary = Path(args[0])
                    target = binary if changed_name == "binary" else Path(args[1])
                    target.write_bytes(target.read_bytes() + b"changed")
                    Path(args[2]).write_bytes((0).to_bytes(4, "little"))
                    return completed(args, "logical_width=32\n")

                code, report, _ = self.run_case(command, compare=False)
                self.assertEqual((2, "artifact_integrity_mismatch"),
                                 (code, report["status"]))
                self.assertEqual([changed_name],
                                 report["artifact_integrity"]["after_execute"]["changed"])
                self.assertIsNone(report["comparison"])

    def test_successful_compile_without_nonempty_binary_is_invalid_binary(self):
        for output in ("missing", "empty"):
            with self.subTest(output=output):
                def command(args, timeout):
                    if args[-1] == "--version":
                        return completed(args, "mock hipcc")
                    self.assertIn("-o", args)
                    if output == "empty":
                        Path(args[-1]).write_bytes(b"")
                    return completed(args)

                code, report, calls = self.run_case(command, compare=False)
                self.assertEqual((2, "invalid_binary"), (code, report["status"]))
                self.assertEqual(2, len(calls))
                self.assertIsNone(report["execute"])

    def test_existing_process_failure_classifications_are_preserved(self):
        scenarios = (
            ("version", "completed", 1, "toolchain_unavailable"),
            ("compile", "completed", 1, "compile_failed"),
            ("compile", "timeout", None, "compile_timeout"),
            ("execute", "completed", 1, "run_failed"),
            ("execute", "timeout", None, "run_timeout"),
        )
        for phase, status, returncode, expected in scenarios:
            with self.subTest(phase=phase, status=status):
                def command(args, timeout):
                    current = ("version" if args[-1] == "--version" else
                               "compile" if "-o" in args else "execute")
                    if current == phase:
                        return {"command": args, "status": status,
                                "returncode": returncode, "stdout": "", "stderr": "failed",
                                "duration_seconds": 0.0}
                    return self.successful_command(args, timeout)

                code, report, _ = self.run_case(command, compare=False)
                self.assertEqual((2, expected), (code, report["status"]))


if __name__ == "__main__":
    unittest.main()
