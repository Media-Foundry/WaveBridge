"""Synthetic record mutations; no GPU evidence is created by these tests."""
import copy
import itertools
import json
from pathlib import Path
import tempfile
import unittest

from experiments.softmax_panel_audit import audit_panel, digest, run, strict_json
from experiments import softmax_hip_reference as reference


class PanelAuditTests(unittest.TestCase):
    def panel(self):
        protocol = json.loads(Path("benchmarks/intake/pytorch-softmax-hip-protocol.json").read_text())
        report = {"schema_version": "softmax-manual-hip-pilot/v1", "status": "finite_numeric_cases_passed",
                  "GPU_executed": True, "inputs_unchanged": True, "adapted_inputs_unchanged": True,
                  "binary_unchanged": True, "protocol": protocol, "cases": []}
        for rows, columns, pattern in itertools.product([1, 3, 17], [65, 128], ["zero", "sawtooth", "alternating"]):
            observed = {"rows": rows, "columns": columns, "api_width": 32, "device_width": 32,
                        "api_calls": 1, "softmax_dispatch_launch_count": 1,
                        "padded_rows": ((rows + 7) // 8) * 8, "grid": (rows + 7) // 8,
                        "block": [32, 4, 1], "padding_sentinel_preserved": True,
                        "output": reference.reference(reference.make_input(rows, columns, pattern), rows, columns)}
            report["cases"].append({"rows": rows, "columns": columns, "pattern": pattern,
                "execution": {"command": ["/tmp/softmax-hip", str(rows), str(columns), pattern],
                              "status": "completed", "returncode": 0, "stdout": json.dumps(observed)},
                "observed": observed, "loaded_hip_api_library": {"path": "/fake/library", "sha256": "fixture"}})
        return report

    def test_complete_panel_reports_discrete_observations_only(self):
        result = audit_panel(self.panel())
        self.assertEqual(result["case_count"], 18)
        self.assertEqual(result["observed_columns"], [65, 128])
        for key in ("continuous_interval_gpu_tested", "host_parameter_domain_proved",
                    "API_semantics_proved", "GPU_executed_by_audit", "deployable"):
            self.assertFalse(result[key])

    def test_missing_duplicate_command_raw_output_and_false_pass_are_rejected(self):
        base = self.panel()
        for mutation in ("missing", "duplicate", "command", "stdout", "numeric", "bool", "width", "library"):
            report = copy.deepcopy(base)
            case = report["cases"][0]
            if mutation == "missing": report["cases"].pop()
            elif mutation == "duplicate": report["cases"][-1] = copy.deepcopy(case)
            elif mutation == "command": case["execution"]["command"][2] = "64"
            elif mutation == "stdout": case["observed"]["api_width"] = 64
            elif mutation == "bool": case["rows"] = True
            elif mutation == "library": case["loaded_hip_api_library"]["sha256"] = "other"
            else:
                if mutation == "numeric":
                    case["observed"]["output"][0] = 100.0
                    case["numerical"] = {"status": "passed"}
                else: case["observed"]["api_width"] = 64
                case["execution"]["stdout"] = json.dumps(case["observed"])
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                audit_panel(report)

    def test_artifacts_and_pinned_report_are_checked_without_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = self.panel()
            names = ("PersistentSoftmax.hip.cuh", "wavebridge_softmax_compat.h", "pytorch-softmax-hip.hip.cpp")
            for name in (*names, "softmax-hip"):
                (root / name).write_bytes(b"not executable fixture")
            report["adapted_input_hashes"] = {n: digest((root / n).read_bytes()) for n in names}
            report["binary_sha256"] = digest((root / "softmax-hip").read_bytes())
            for case in report["cases"]:
                case["execution"]["command"][0] = str(root / "softmax-hip")
            path = root / "report.json"
            path.write_text(json.dumps(report))
            expected = digest(path.read_bytes())
            run(path, expected, root / "audit.json")
            self.assertTrue((root / "audit.json").exists())
            with self.assertRaises(ValueError): run(path, "wrong", root / "bad.json")
            (root / names[0]).write_bytes(b"changed")
            with self.assertRaises(ValueError): run(path, expected, root / "bad.json")
            self.assertFalse((root / "bad.json").exists())

    def test_nonstandard_or_ambiguous_json_is_rejected(self):
        for raw in ('{"width":64,"width":32}', '{"unused":NaN}', '{"unused":Infinity}'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                strict_json(raw)
        report = self.panel()
        original = report["cases"][0]["execution"]["stdout"]
        report["cases"][0]["execution"]["stdout"] = '{"rows":99,' + original[1:]
        with self.assertRaises(ValueError):
            audit_panel(report)
