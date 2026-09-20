import hashlib
import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "benchmarks" / "cases" / "llama-rmsnorm"
HIP = CASE / "baseline" / "rmsnorm_logical32.hip.cpp"
CUDA = CASE / "baseline" / "rmsnorm_logical32.cu"


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


class RmsNormCudaPortTests(unittest.TestCase):
    def test_manifest_binds_parent_cuda_protocol_and_license_hashes(self):
        manifest = json.loads((CASE / "cuda-port.json").read_text())
        self.assertEqual("manual-cuda-port/v1", manifest["schema_version"])
        self.assertFalse(manifest["automatic_recovery"])
        for section in ("parent", "cuda_source", "protocol", "license"):
            item = manifest[section]
            self.assertEqual(item["sha256"], sha256(CASE / item["path"]))
        self.assertEqual("7284151f806d710ff3396b94b62b3ec35d5bef3f44815e1e7837aad66dc85823",
                         manifest["parent"]["sha256"])
        self.assertEqual("not_run", manifest["validation"]["cuda_gpu_execution"])
        self.assertEqual("host_and_device_syntax_only_passed", manifest["validation"]["cuda_compile"])
        self.assertEqual("not_run", manifest["validation"]["cuda_codegen_and_link"])

    def test_syntax_evidence_does_not_authorize_execution(self):
        evidence = json.loads((CASE / "cuda-syntax-evidence.json").read_text())
        self.assertEqual(sha256(CUDA), evidence["source_sha256"])
        self.assertFalse(evidence["deployable"])
        self.assertFalse(evidence["source_program_checked"])
        self.assertEqual({"host", "device"}, {r["mode"] for r in evidence["successful_reports"]})
        self.assertEqual(4, len(evidence["failed_reports"]))
        self.assertIn("partially supported", evidence["compiler_warning"])

    def test_frozen_protocol_and_launch_shape_are_preserved(self):
        protocol = json.loads((CASE / "protocol.json").read_text())
        source = CUDA.read_text()
        self.assertEqual([256, 1, 1], protocol["launch"]["block"])
        self.assertEqual(32, protocol["launch"]["logical_width"])
        self.assertEqual(128, protocol["launch"]["dynamic_shared_bytes"])
        self.assertEqual(1, protocol["input"]["ncols"]["minimum"])
        self.assertEqual(1024, protocol["input"]["ncols"]["maximum_exclusive"])
        self.assertIn("constexpr int kLogicalWidth = 32;", source)
        self.assertIn("constexpr int kBlockSize = 256;", source)
        self.assertIn("ncols < 1 || ncols >= 1024", source)
        self.assertIn("dim3(nrows), dim3(kBlockSize), 32 * sizeof(float), 0", source)

    def test_reduction_and_column_structure_remain_present(self):
        source = CUDA.read_text()
        warp = function_body(source, "warp_reduce_sum_logical32")
        block = function_body(source, "block_reduce_sum_logical32")
        kernel = function_body(source, "rms_norm_f32_logical32")
        self.assertIn("offset = kLogicalWidth / 2", warp)
        self.assertIn("offset >>= 1", warp)
        self.assertEqual(1, warp.count("__shfl_xor_sync"))
        self.assertIn("0xffffffffu", warp)
        self.assertIn("shared_values[logical_group] = value", block)
        self.assertEqual(1, block.count("__syncthreads"))
        self.assertEqual(2, block.count("warp_reduce_sum_logical32"))
        self.assertEqual(2, len(re.findall(r"for \(int col = tid; col < ncols; col \+= kBlockSize\)", kernel)))
        self.assertIn("partial += value * value", kernel)
        self.assertIn("dst[col] = scale * x[col]", kernel)

    def test_api_edits_are_explicit_and_hip_tokens_do_not_leak(self):
        source = CUDA.read_text()
        manifest = json.loads((CASE / "cuda-port.json").read_text())
        areas = {item["area"] for item in manifest["manual_changes"]}
        self.assertEqual({"runtime_header_and_math_shim", "xor_shuffle_intrinsic", "runtime_api",
                          "launch_syntax", "device_identity_output", "typed_allocation"}, areas)
        self.assertNotRegex(source, r"\bhip(?:Error|Malloc|Memcpy|Free|Launch|Get|Device|Runtime|Driver)")
        self.assertNotIn("__ocml_rsqrt_f32", source)
        self.assertIn("__shfl_xor_sync(0xffffffffu, value, offset, kLogicalWidth)", source)
        self.assertIn("full_active_converged", manifest["manual_changes"][1]["semantic_claim"])

    def test_computation_bodies_match_parent_except_explicit_shuffle_edit(self):
        parent = HIP.read_text()
        port = CUDA.read_text()
        for signature in ("warp_reduce_sum_logical32", "block_reduce_sum_logical32",
                          "rms_norm_f32_logical32"):
            with self.subTest(signature=signature):
                expected = function_body(parent, signature).replace(
                    "__shfl_xor(value, offset, kLogicalWidth)",
                    "__shfl_xor_sync(0xffffffffu, value, offset, kLogicalWidth)")
                self.assertEqual(expected, function_body(port, signature))

    def test_port_record_does_not_claim_cuda_validation(self):
        manifest = json.loads((CASE / "cuda-port.json").read_text())
        documentation = (CASE / "cuda-port.md").read_text()
        self.assertEqual("source_port_not_cuda_gpu_validated", manifest["status"])
        self.assertIn("not an automatically recovered candidate", documentation)
        self.assertIn("has not been executed on a CUDA GPU", documentation)
        self.assertIn("external assumption", documentation)


if __name__ == "__main__":
    unittest.main()
