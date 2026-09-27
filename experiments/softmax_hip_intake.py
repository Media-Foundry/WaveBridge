"""Fresh AST intake of the executed manual HIP pilot, not CUDA-report reuse."""
import argparse
import json
from pathlib import Path

from experiments.pytorch_softmax_intake import implementation_hashes, select_entry, sha
from wavebridge.frontend.clang_ast import collect
from wavebridge.analysis.column_loops import recover
from wavebridge.analysis.reduction_discovery import discover
from wavebridge.analysis.launch_facts import inspect as inspect_launch

PILOT_SHA = "f53b5800c54e8ef5ec459b7734e3c4edf0a6064e8e519357881926e28b78cab2"


def verify_pilot(report, directory):
    if (report.get("status") != "finite_numeric_cases_passed" or len(report.get("cases", [])) != 18 or
            any(report.get(k) is not True for k in
                ("inputs_unchanged", "adapted_inputs_unchanged", "binary_unchanged"))):
        raise ValueError("pilot_not_complete_stable_numeric_evidence")
    for path, digest in report["input_hashes"].items():
        if sha(path) != digest:
            raise ValueError("pilot_input_changed")
    for name, digest in report["adapted_input_hashes"].items():
        if Path(name).name != name or sha(directory / name) != digest:
            raise ValueError("adapted_input_changed")
    if sha(directory / "softmax-hip") != report["binary_sha256"]:
        raise ValueError("pilot_binary_changed")
    compiler = Path(report["compile"]["command"][0])
    if sha(compiler.resolve()) != report["compiler_wrapper_sha256"]:
        raise ValueError("compiler_wrapper_changed")
    for item in report["sdk_view_observation"]["inputs"]:
        if sha(item["path"]) != item["observed_sha256"]:
            raise ValueError("observed_sdk_file_changed")
    return compiler


def run(pilot_path, output):
    pilot_path, output = pilot_path.resolve(), output.resolve()
    if sha(pilot_path) != PILOT_SHA or output.exists():
        raise ValueError("pilot_report_mismatch_or_output_exists")
    pilot = json.loads(pilot_path.read_text())
    directory = pilot_path.parent
    compiler = verify_pilot(pilot, directory)
    output.mkdir(parents=True)
    before = implementation_hashes()
    dependencies = {str(p): sha(p) for p in
                    (Path(__file__), Path(__file__).with_name("pytorch_softmax_intake.py"))}
    source = directory / "pytorch-softmax-hip.hip.cpp"
    # Preserve the numerical build's language/optimization/architecture/macro/include
    # settings. Save-temps, linking and output options do not belong to AST capture.
    arguments = ["-std=c++17", "-O2", "--offload-arch=gfx1100", "-DWB_COMPILED_COOP_WIDTH=32",
                 "-I", str(directory), "--offload-device-only"]
    expected_compile = [str(compiler), "-std=c++17", "-O2", "--offload-arch=gfx1100", "--save-temps",
                        "-DWB_COMPILED_COOP_WIDTH=32", str(source), "-I", str(directory),
                        "-ldl", "-o", str(directory / "softmax-hip")]
    if pilot["compile"]["command"] != expected_compile:
        raise ValueError("pilot_compile_options_not_expected")
    report = {"schema_version": "softmax-executed-hip-intake/v1", "status": "not_started",
              "pilot_report_sha256": PILOT_SHA, "binary_sha256": pilot["binary_sha256"],
              "compilation_view": "manual_hip_pilot_full_tu_device_only_gfx1100",
              "implementation_before": before, "driver_dependencies": dependencies,
              "prior_cuda_ast_reused": False, "GPU_executed_this_run": False,
              "binary_build_dependency_closure_established": False,
              "source_program_checked": False, "deployable": False}
    (output / "pre-analysis.json").write_text(json.dumps(report, indent=2) + "\n")
    frontend = collect(source, str(compiler), arguments, "softmax_warp_forward", timeout=180,
                       cwd=output, full_translation_unit=True, dependency_binding="required", toolchain_trace=True)
    print(json.dumps({"phase": "frontend", "status": frontend["status"], "reason": frontend.get("reason")}), flush=True)
    ast_path = output / "ast.json"
    with ast_path.open("x") as stream:
        json.dump(frontend, stream, separators=(",", ":"))
    report.update(frontend_status=frontend["status"], frontend_reason=frontend.get("reason"),
                  ast_report=str(ast_path), ast_report_sha256=sha(ast_path),
                  dependency_binding=frontend["dependency_binding"], toolchain_trace=frontend["toolchain_trace"])
    required = {str((directory / name).resolve()): digest for name, digest in pilot["adapted_input_hashes"].items()
                if name.endswith((".cpp", ".h", ".cuh"))}
    observed = {item["resolved_path"]: item["sha256"] for item in frontend["dependency_binding"].get("files", [])}
    report["executed_source_files_bound"] = bool(required) and all(observed.get(p) == h for p, h in required.items())
    if frontend["status"] != "collected":
        report["status"] = "frontend_unavailable"
    elif not report["executed_source_files_bound"] or len(frontend["ast_roots"]) != 1:
        report["status"] = "input_binding_unestablished"
    else:
        root = frontend["ast_roots"][0]
        entry = select_entry(root)
        report["selected_entry"] = {key: entry.get(key) for key in ("id", "name", "mangledName", "loc")}
        report["analysis"] = {"columns": recover(root, entry["id"], 32),
                              "reductions": discover(root, entry["id"], 32),
                              "launch": inspect_launch(root, entry["id"])}
        report["status"] = "analyzed"
    verify_pilot(pilot, directory)
    report["implementation_after"] = implementation_hashes()
    report["inputs_unchanged"] = (before == report["implementation_after"] and sha(pilot_path) == PILOT_SHA and
                                   all(sha(p) == h for p, h in dependencies.items()))
    if not report["inputs_unchanged"]:
        report["status"] = "inputs_changed"
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "source_files_bound": report["executed_source_files_bound"],
                      "inputs_unchanged": report["inputs_unchanged"], "sha256": sha(output / "report.json")}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pilot-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.pilot_report, args.output)
