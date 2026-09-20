import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "benchmarks" / "cases" / "llama-rmsnorm"
PARENT = CASE / "baseline" / "rmsnorm_logical32.cu"
ADAPTER = CASE / "baseline" / "rmsnorm_logical32_polygeist_adapter.cu"


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def function_body(source, signature):
    start = source.index(signature)
    opening = source.index("{", start)
    depth = 0
    for index in range(opening, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[opening:index + 1]
    raise AssertionError(f"unterminated function: {signature}")


def launch_statement(source):
    match = re.search(
        r"rms_norm_f32_logical32<<<dim3\(nrows\), dim3\(kBlockSize\), "
        r"32 \* sizeof\(float\), 0>>>\(\s*"
        r"device_input, device_output, ncols, 1\.0e-5f\);",
        source,
    )
    if match is None:
        raise AssertionError("launch statement missing")
    return re.sub(r"\s+", " ", match.group(0))


class RmsNormPolygeistAdapterTests(unittest.TestCase):
    def test_manifest_binds_all_inputs_and_limits_claims(self):
        manifest = json.loads((CASE / "polygeist-adapter.json").read_text())
        self.assertEqual("manual-polygeist-host-adapter/v1", manifest["schema_version"])
        self.assertFalse(manifest["automatic_recovery"])
        for field in ("parent_cuda_source", "adapter_source", "derivation_patch",
                      "protocol", "license"):
            item = manifest[field]
            self.assertEqual(item["sha256"], sha256(CASE / item["path"]))
        self.assertEqual("not_established", manifest["claims"]["semantic_equivalence"])
        self.assertEqual("not_run", manifest["claims"]["cuda_gpu_execution"])
        self.assertFalse(manifest["claims"]["deployable"])
        self.assertEqual(2, len(manifest["local_frontend_evidence"]))
        for evidence in manifest["local_frontend_evidence"]:
            self.assertEqual("emitted_unverified_ir", evidence["status"])
            self.assertEqual("local_only_not_in_git", evidence["artifact_availability"])
            self.assertRegex(evidence["report_sha256"], r"^[0-9a-f]{64}$")
            self.assertRegex(evidence["ir_sha256"], r"^[0-9a-f]{64}$")

    def test_computation_constants_and_bodies_are_verbatim(self):
        parent = PARENT.read_text()
        adapter = ADAPTER.read_text()
        self.assertIn("constexpr int kLogicalWidth = 32;", adapter)
        self.assertIn("constexpr int kBlockSize = 256;", adapter)
        for signature in ("warp_reduce_sum_logical32", "block_reduce_sum_logical32",
                          "rms_norm_f32_logical32"):
            with self.subTest(signature=signature):
                self.assertEqual(function_body(parent, signature),
                                 function_body(adapter, signature))

    def test_guard_launch_and_public_entry_are_preserved(self):
        parent = PARENT.read_text()
        adapter = ADAPTER.read_text()
        protocol = json.loads((CASE / "protocol.json").read_text())
        self.assertIn('extern "C" int wavebridge_launch_rms_norm_f32_logical32(', adapter)
        self.assertIn("nrows < 1 || nrows > 8 || ncols < 1 || ncols >= 1024", adapter)
        self.assertEqual(launch_statement(parent), launch_statement(adapter))
        self.assertEqual([256, 1, 1], protocol["launch"]["block"])
        self.assertEqual(128, protocol["launch"]["dynamic_shared_bytes"])
        self.assertEqual(1, protocol["input"]["nrows"]["minimum"])
        self.assertEqual(8, protocol["input"]["nrows"]["maximum"])
        self.assertEqual(1, protocol["input"]["ncols"]["minimum"])
        self.assertEqual(1024, protocol["input"]["ncols"]["maximum_exclusive"])

    def test_host_runtime_and_measurement_stay_outside_adapter(self):
        source = ADAPTER.read_text()
        forbidden = (
            "<cstdio>", "<cstdlib>", "<fstream>", "<vector>", " main(",
            "cudaMalloc", "cudaMemcpy", "cudaFree", "cudaGetLastError",
            "cudaDeviceSynchronize", "cudaGetDeviceProperties",
            "cudaDeviceGetPCIBusId", "cudaRuntimeGetVersion", "cudaDriverGetVersion",
        )
        for token in forbidden:
            with self.subTest(token=token):
                self.assertNotIn(token, source)

    def test_recorded_patch_reproduces_adapter_exactly(self):
        with tempfile.TemporaryDirectory() as directory:
            reconstructed = Path(directory) / "adapter.cu"
            reconstructed.write_bytes(PARENT.read_bytes())
            result = subprocess.run(
                ["patch", str(reconstructed), str(CASE / "polygeist-adapter.patch")],
                text=True, capture_output=True, check=False,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual(ADAPTER.read_bytes(), reconstructed.read_bytes())


if __name__ == "__main__":
    unittest.main()
