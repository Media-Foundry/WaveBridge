from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest

from experiments.reference_interval_audit import audit, margin, PROTOCOL


class ReferenceIntervalAuditTests(unittest.TestCase):
    def fixture(self, path, reference=0.0):
        report = {"nrows": 1, "ncols": 1, "epsilon": 1.0e-5}
        files = {"input.f32": ("input_sha256", struct.pack("<f", 0)),
                 "expected.f32": ("expected_sha256", struct.pack("<f", reference)),
                 "protocol.json": ("protocol_sha256", PROTOCOL.read_bytes()),
                 "reference.py": ("reference_sha256", b"fixture, never executed")}
        for name, (key, content) in files.items():
            (path/name).write_bytes(content)
            report[key] = hashlib.sha256(content).hexdigest()
        (path/"report.json").write_text(json.dumps(report))

    def test_exact_triangle_margin_and_wrong_reference(self):
        gap, error = margin((F(-2), F(-1)), F(-3, 2), F(1, 10), F(0), F(1), F(0))
        self.assertEqual(error, F(1, 2))
        self.assertEqual(gap, F(3, 10))
        self.assertLess(margin((F(1), F(1)), F(100), F(0), F(0), F(1), F(0))[0], 0)

    def test_finite_fixture_success_is_not_domain_or_gpu_proof(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            self.fixture(path)
            result = audit(path)
        self.assertEqual(result["status"], "checked")
        self.assertEqual(result["stored_points"], 1)
        self.assertEqual(len(result["rows"][0]["conditional_model_tolerance"]), 4)
        self.assertNotEqual(result["ideal_epsilon"], result["device_epsilon_assumption"])
        for flag in ("reference_algorithm_reexecuted", "reference_algorithm_domain_wide_verified",
                     "host_comparator_rounding_verified", "actual_fp_laws_verified",
                     "numeric_contract_checked", "GPU_executed", "deployable"):
            self.assertFalse(result[flag])

    def test_insufficient_bound_stays_unknown_and_hash_mismatch_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            self.fixture(path, reference=100.0)
            self.assertEqual(audit(path)["status"], "unknown")
            (path/"expected.f32").write_bytes(struct.pack("<f", 0))
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                audit(path)


if __name__ == "__main__":
    unittest.main()
