"""Build/run a manually integrated HIP baseline; never upgrades static guarantees."""
import argparse
import difflib
import itertools
import json
import os
from pathlib import Path
import re
import shutil

from experiments import softmax_hip_reference as reference
from runtime.probes.probe import invoke, kernel_metadata_widths, sha256

ROOT = Path(__file__).resolve().parents[1]
INTAKE = ROOT / "benchmarks/intake"
SOURCE_SHA = "12436933cae8c1e4096af342313070ce873eefad3d6a1637675ef780d1fdea1e"
REPLACEMENTS = (
    ('#include <cuda_fp16.h>', '#include <hip/hip_fp16.h>', 1),
    ('#include <c10/macros/Macros.h>', '#include "wavebridge_softmax_compat.h"', 1),
    ('#include <ATen/cuda/DeviceUtils.cuh>', '// HIP shuffle mapping is supplied by the explicit compatibility header.', 1),
    ('<<<blocks, threads, 0, at::cuda::getCurrentCUDAStream()>>>',
     '<<<wb_observe_grid(blocks, threads), threads, 0, at::cuda::getCurrentCUDAStream()>>>', 2),
)


def adapt(source):
    for old, new, count in REPLACEMENTS:
        if source.count(old) != count:
            raise ValueError("upstream_patch_context_mismatch")
        source = source.replace(old, new)
    return source


def validate_protocol(protocol):
    expected = {"columns": [65, 128], "rows": [1, 3, 17],
                "patterns": ["zero", "sawtooth", "alternating"], "count": 18,
                "cartesian_product_required": True}
    if protocol.get("cases") != expected:
        raise ValueError("frozen_case_panel_mismatch")
    tolerance = protocol.get("reference", {})
    if (tolerance.get("absolute_tolerance") != reference.ABS_TOLERANCE or
            tolerance.get("relative_tolerance") != reference.REL_TOLERANCE or
            tolerance.get("maximum_row_sum_error") != reference.ROW_SUM_TOLERANCE):
        raise ValueError("frozen_tolerance_mismatch")


def run(source, output, hipcc, execute):
    source, output, hipcc = source.resolve(), output.resolve(), hipcc.absolute()
    if output.exists() or sha256(source) != SOURCE_SHA:
        raise ValueError("output_exists_or_upstream_hash_mismatch")
    output.mkdir(parents=True)
    inputs = [source, INTAKE / "wavebridge_softmax_compat.h", INTAKE / "pytorch-softmax-hip.hip.cpp",
              INTAKE / "pytorch-softmax-hip-protocol.json", Path(__file__),
              Path(reference.__file__), ROOT / "runtime/probes/probe.py"]
    before = {str(p): sha256(p) for p in inputs}
    report = {"schema_version": "softmax-manual-hip-pilot/v1", "status": "not_run",
              "input_hashes": before, "cases": [], "GPU_executed": False,
              "GPU_execution_attempted": False,
              "source_program_checked": False, "deployable": False,
              "automatic_adaptation": False, "pytorch_runtime_linked": False,
              "prior_cuda_ast_guarantees_reused": False,
              "visible_device_environment": {k: os.environ.get(k) for k in
                  ("HIP_VISIBLE_DEVICES", "ROCR_VISIBLE_DEVICES", "CUDA_VISIBLE_DEVICES")}}
    try:
        protocol = json.loads((INTAKE / "pytorch-softmax-hip-protocol.json").read_text())
        validate_protocol(protocol)
        report["protocol"] = protocol
        original = source.read_text()
        adapted = adapt(original)
        (output / "PersistentSoftmax.hip.cuh").write_text(adapted)
        (output / "upstream.patch").write_text("".join(difflib.unified_diff(
            original.splitlines(True), adapted.splitlines(True), fromfile="upstream", tofile="manual-hip")))
        for name in ("wavebridge_softmax_compat.h", "pytorch-softmax-hip.hip.cpp"):
            shutil.copyfile(INTAKE / name, output / name)
        report["adapted_input_hashes"] = {p.name: sha256(p) for p in output.iterdir() if p.is_file()}
        report["toolchain"] = invoke([str(hipcc), "--version"], 30)
        report["compiler_path"] = str(hipcc.resolve())
        report["compiler_wrapper_sha256"] = sha256(hipcc.resolve())
        sdk_manifest = hipcc.parent.parent / "manifest.json"
        if sdk_manifest.is_file():
            sdk = json.loads(sdk_manifest.read_text())
            report["sdk_view_observation"] = {"manifest_path": str(sdk_manifest),
                "manifest_sha256": sha256(sdk_manifest), "inputs": [
                    {"path": item["path"], "recorded_sha256": item["sha256"],
                     "observed_sha256": sha256(Path(item["path"]))} for item in sdk.get("inputs", [])]}
        binary = output / "softmax-hip"
        compiled = invoke([str(hipcc), "-std=c++17", "-O2", "--offload-arch=gfx1100", "--save-temps",
                           "-DWB_COMPILED_COOP_WIDTH=32",
                           str(output / "pytorch-softmax-hip.hip.cpp"), "-I", str(output),
                           "-ldl", "-o", str(binary)], 120, cwd=output)
        report["compile"] = compiled
        if compiled["status"] != "completed" or compiled["returncode"] != 0:
            report["status"] = "compile_failed"
            return
        report["binary_sha256"] = sha256(binary)
        metadata = []
        for assembly in output.glob("*.s"):
            text = assembly.read_text(errors="replace")
            names = {n.strip("\"'") for n in re.findall(r"^\s+(?:-\s+)?\.name:\s+(\S+)\s*$", text, re.M)}
            selected = {n for n in names if "softmax_warp_forward" in n and "Li7ELb0ELb0E" in n}
            if selected:
                metadata.append({"path": str(assembly), "sha256": sha256(assembly),
                                 "kernels": {n: sorted(kernel_metadata_widths(text, {n})) for n in selected}})
        report["compiler_emitted_metadata"] = metadata
        if not metadata or any(widths != [32] for item in metadata for widths in item["kernels"].values()):
            report["status"] = "metadata_unestablished"
            return
        if not execute:
            report["status"] = "compiled_not_executed"
            return
        preflight = invoke(["/opt/rocm/bin/rocm-smi", "--showmeminfo", "vram", "--showuse", "--showproductname"], 30)
        report["preflight"] = preflight
        used = re.findall(r"VRAM Total Used Memory \(B\):\s*(\d+)", preflight.get("stdout", ""))
        if (preflight.get("returncode") != 0 or not used or any(int(v) >= 500 * 1024 * 1024 for v in used)):
            report["status"] = "device_not_available"
            return
        for columns, rows, pattern in itertools.product(protocol["cases"]["columns"],
                                                        protocol["cases"]["rows"], protocol["cases"]["patterns"]):
            record = invoke([str(binary), str(rows), str(columns), pattern], 30, cwd=output)
            case = {"rows": rows, "columns": columns, "pattern": pattern, "execution": record}
            report["cases"].append(case)
            report["GPU_execution_attempted"] = True
            report["GPU_executed"] = None
            if record["status"] != "completed" or record["returncode"] != 0:
                report["status"] = "runtime_failed"
                if "no ROCm-capable device is detected" in record.get("stderr", ""):
                    report["status"] = "device_unavailable"
                    report["GPU_executed"] = False
                return
            observed = json.loads(record["stdout"])
            report["GPU_executed"] = True
            library = Path(observed["hip_api_library"]).resolve(strict=True)
            case["loaded_hip_api_library"] = {"path": str(library), "sha256": sha256(library)}
            expected = reference.reference(reference.make_input(rows, columns, pattern), rows, columns)
            case["observed"] = observed
            case["numerical"] = reference.evaluate(observed["output"], expected, rows, columns)
            if (observed["rows"] != rows or observed["columns"] != columns or
                    observed["api_width"] != 32 or observed["device_width"] != 32 or
                    observed["padding_sentinel_preserved"] is not True or observed["padded_rows"] != ((rows + 7) // 8) * 8 or
                    observed["block"] != [32, 4, 1] or observed["grid"] != (rows + 7) // 8 or
                    observed["api_calls"] != 1 or observed["softmax_dispatch_launch_count"] != 1):
                report["status"] = "runtime_evidence_mismatch"
                return
            if case["numerical"]["status"] != "passed":
                report["status"] = "numerical_failed"
                return
        report["status"] = "finite_numeric_cases_passed"
    finally:
        report["inputs_unchanged"] = all(p.exists() and sha256(p) == digest for p, digest in
                                         ((Path(p), digest) for p, digest in before.items()))
        report["adapted_inputs_unchanged"] = all((output / name).is_file() and sha256(output / name) == digest
            for name, digest in report.get("adapted_input_hashes", {}).items())
        if "binary_sha256" in report:
            report["binary_unchanged"] = binary.is_file() and sha256(binary) == report["binary_sha256"]
        if not report["inputs_unchanged"]:
            report["status"] = "inputs_changed"
        elif not report["adapted_inputs_unchanged"] or report.get("binary_unchanged") is False:
            report["status"] = "artifacts_changed"
        (output / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        print(json.dumps({"status": report["status"], "cases": len(report["cases"]),
                          "report": str(output / "report.json")}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--hipcc", type=Path, default=Path("/opt/rocm/bin/hipcc"))
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args()
    run(args.source, args.output, args.hipcc, args.run)
    status = json.loads((args.output / "report.json").read_text())["status"]
    raise SystemExit(0 if status in {"compiled_not_executed", "finite_numeric_cases_passed"} else 1)
