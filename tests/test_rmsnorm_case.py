import importlib.util
import hashlib
import json
import math
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "benchmarks" / "cases" / "llama-rmsnorm"
SPEC = importlib.util.spec_from_file_location("rmsnorm_reference", CASE / "reference.py")
reference = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(reference)
RUNNER_SPEC = importlib.util.spec_from_file_location("rmsnorm_runner", CASE / "runner.py")
runner = importlib.util.module_from_spec(RUNNER_SPEC)
assert RUNNER_SPEC.loader
RUNNER_SPEC.loader.exec_module(runner)


class RmsNormCaseTests(unittest.TestCase):
    def test_zero_row_has_zero_output(self):
        self.assertEqual(reference.rmsnorm([[0.0, 0.0, 0.0]], 1.0e-5),
                         [[0.0, 0.0, 0.0]])

    def test_reference_matches_simple_known_value(self):
        output = reference.rmsnorm([[1.0, -1.0]], 1.0e-5)
        expected = reference.f32(1.0 / math.sqrt(1.0 + 1.0e-5))
        self.assertEqual(output, [[expected, -expected]])

    def test_boundary_columns_are_accepted(self):
        for ncols in (1, 31, 32, 33, 255, 256, 257, 1023):
            with self.subTest(ncols=ncols):
                rows = reference.deterministic_rows(1, ncols)
                self.assertEqual(len(reference.rmsnorm(rows, 1.0e-5)[0]), ncols)

    def test_out_of_domain_shapes_are_rejected(self):
        for rows in ([], [[0.0] * 1024], [[1.0], [1.0, 2.0]]):
            with self.subTest(rows=len(rows)):
                with self.assertRaises(ValueError):
                    reference.rmsnorm(rows, 1.0e-5)

    def test_nonfinite_and_out_of_range_values_are_rejected(self):
        for value in (math.nan, math.inf, -math.inf, 2.01):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    reference.rmsnorm([[value]], 1.0e-5)

    def test_invalid_epsilon_is_rejected(self):
        for epsilon in (0.0, 0.01, math.nan):
            with self.subTest(epsilon=epsilon):
                with self.assertRaises(ValueError):
                    reference.rmsnorm([[1.0]], epsilon)

    def test_comparison_rejects_numeric_error_and_nonfinite(self):
        self.assertFalse(reference.compare([1.1], [1.0])["passed"])
        result = reference.compare([math.nan], [1.0])
        self.assertFalse(result["passed"])
        self.assertIsNone(result["max_absolute_error"])
        self.assertIsNotNone(result["reason"])

    def test_protocol_is_frozen_before_device_run(self):
        protocol = json.loads((CASE / "protocol.json").read_text())
        self.assertEqual(protocol["launch"]["logical_width"], 32)
        self.assertEqual(protocol["launch"]["block"], [256, 1, 1])
        self.assertEqual(protocol["input"]["ncols"]["maximum_exclusive"], 1024)
        self.assertEqual(protocol["comparison"]["absolute_tolerance"], 0.00001)

    def test_manual_oracle_is_separate_from_reference(self):
        oracle = json.loads((CASE / "oracle" / "manual.json").read_text())
        self.assertEqual(oracle["automatic_recovery_status"], "not_implemented")
        self.assertNotIn("oracle", (CASE / "reference.py").read_text())

    def test_provenance_hashes_bind_all_vendored_and_derived_sources(self):
        provenance = json.loads((CASE / "provenance.json").read_text())
        for item in provenance["vendored_files"]:
            path = CASE / item["path"]
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), item["sha256"])
        baseline = CASE / "baseline" / "rmsnorm_logical32.hip.cpp"
        self.assertEqual(hashlib.sha256(baseline.read_bytes()).hexdigest(),
                         provenance["baseline_sha256"])

    def test_evidence_index_covers_declared_boundary_shapes(self):
        evidence = json.loads((CASE / "evidence.json").read_text())
        self.assertEqual([item["ncols"] for item in evidence["reports"]],
                         [1, 31, 32, 33, 255, 256, 257, 777, 1023])
        self.assertIn("not every", evidence["scope_limit"])
        self.assertEqual(evidence["artifact_availability"], "local_only_not_in_git")
        self.assertEqual(evidence["common_conditions"]["baseline_machine_code_wave_metadata"],
                         "not_independently_extracted")

    def test_missing_compiler_is_captured(self):
        result = runner.command(["/definitely/missing/hipcc", "--version"], 1)
        self.assertEqual(result["status"], "launch_failed")
        self.assertIn("No such file", result["stderr"])

    def test_unverified_probe_writes_report_and_evidence_copies(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            probe = root / "probe.json"
            probe.write_text(json.dumps({"overall_status": "unknown"}))
            code, report_path = runner.run(root, "/missing/hipcc", probe, 1, 1, 1)
            report = json.loads(report_path.read_text())
            self.assertEqual(code, 2)
            self.assertEqual(report["status"], "invalid_probe_report")
            for name in ("protocol.json", "reference.py", "provenance.json"):
                self.assertTrue((report_path.parent / name).is_file())


if __name__ == "__main__":
    unittest.main()
