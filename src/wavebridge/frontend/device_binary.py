"""Observe embedded AMDGPU code from a saved executable, never execute it.

LLVM --offloading writes extraction products beside its input. Always inspect a
private snapshot in a fresh directory, never the historical executable path.
"""
import argparse
import json
import math
from pathlib import Path
import shutil
import tempfile

from wavebridge.frontend import clang_ast
from wavebridge.frontend.device_compile import _command_hash, _sha


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field: " + key)
        result[key] = value
    return result


def collect(binary: Path, execution_report: Path, objdump: Path, readelf: Path,
            output_parent: Path, *, timeout=60):
    if isinstance(timeout, bool) or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("positive finite timeout required")
    paths = {name: path.resolve(strict=True) for name, path in
             (("binary", binary), ("execution_report", execution_report),
              ("objdump", objdump), ("readelf", readelf))}
    if any(not p.is_file() for p in paths.values()):
        raise ValueError("binary, report and observation tools must be files")
    before = {name: {"path": str(p), "sha256": _sha(p)} for name, p in paths.items()}
    recorded = json.loads(paths["execution_report"].read_text(), object_pairs_hook=_unique_object)
    container = recorded
    for name in ("build_binding", "files", "binary"):
        if not isinstance(container, dict) or not isinstance(container.get(name), dict):
            raise ValueError("saved report requires object binding field: " + name)
        container = container[name]
    bound = container.get("sha256")
    run = Path(tempfile.mkdtemp(prefix="binary-observation-", dir=output_parent.resolve(strict=True)))
    report = {
        "schema_version": "saved-device-binary-observation/v1", "status": "unknown",
        "run_directory": str(run), "inputs": before, "jobs": [], "device_objects": [],
        "collector_sha256": _sha(Path(__file__)),
        "invoke_implementation_sha256": _sha(Path(clang_ast.__file__)),
        "scope": "embedded_code_observation_bound_to_saved_run_binary_hash",
        "saved_binary_hash_matched": False, "source_program_checked": False,
        "metadata_semantically_validated": False, "actual_fp_laws_verified": False,
        "dynamic_loader_selection_verified": False, "GPU_executed": False,
        "numeric_contract_checked": False, "deployable": False,
        "limitations": ["saved report is a provenance anchor, not a trusted execution attestation",
                        "tool output and metadata are retained, not parsed into semantic guarantees",
                        "no new compile, GPU execution, or complete machine-code equivalence check",
                        "before/after hashes do not rule out transient file changes",
                        "tool shared libraries and extraction process identity are not frozen"],
    }

    def finish(status):
        after = {}
        for name, path in paths.items():
            try:
                after[name] = _sha(path)
            except OSError:
                after[name] = None
        report["input_hashes_after"] = after
        report["direct_inputs_unchanged"] = all(after[n] == v["sha256"] for n, v in before.items())
        report["status"] = status if report["direct_inputs_unchanged"] else "input_changed"
        (run/"report.json").write_text(json.dumps(report, indent=2)+"\n")
        return report

    def invoke(kind, tool, arguments):
        command = [str(paths[tool]), *arguments]
        result = clang_ast.invoke(command, timeout, run)
        result["command_sha256"] = _command_hash(command)
        report["jobs"].append({"kind": kind, "execution": result})
        (run/(kind+".stdout.txt")).write_text(result["stdout"])
        (run/(kind+".stderr.txt")).write_text(result["stderr"])
        return result["status"] == "completed" and result["returncode"] == 0

    if recorded.get("binary_sha256") != before["binary"]["sha256"] or bound != before["binary"]["sha256"]:
        return finish("saved_binary_hash_mismatch")
    report["saved_binary_hash_matched"] = True
    snapshot = run/"snapshot"
    shutil.copyfile(paths["binary"], snapshot)
    if _sha(snapshot) != before["binary"]["sha256"]:
        return finish("snapshot_hash_mismatch")
    for tool in ("objdump", "readelf"):
        if not invoke(tool+"-version", tool, ["--version"]):
            return finish("tool_version_unavailable")
    if not invoke("extract", "objdump", ["--offloading", str(snapshot)]):
        return finish("extraction_failed")
    # Only recognize AMDGPU HIP bundle names, no guesses from host ELF bytes.
    objects = sorted(p for p in run.glob("snapshot.*") if p.is_file() and
                     (".hip-" in p.name or ".hipv4-" in p.name) and
                     "amdgcn-amd-amdhsa" in p.name)
    if not objects:
        return finish("no_supported_device_objects")
    for i, path in enumerate(objects):
        item = {"path": str(path), "sha256": _sha(path), "size": path.stat().st_size}
        report["device_objects"].append(item)
        if not item["size"]:
            return finish("empty_device_object")
        for kind, tool, flags in (("disassembly", "objdump", ["-d"]),
                                  ("notes", "readelf", ["-n"])):
            label = f"device-{i}-{kind}"
            if not invoke(label, tool, [*flags, str(path)]):
                return finish("device_observation_failed")
            output = run/(label+".stdout.txt")
            if not output.stat().st_size:
                return finish("empty_device_observation")
            item[kind] = {"path": str(output), "sha256": _sha(output)}
        if _sha(path) != item["sha256"]:
            return finish("extracted_object_changed")
    if _sha(snapshot) != before["binary"]["sha256"]:
        return finish("snapshot_changed")
    report["snapshot"] = {"path": str(snapshot), "sha256": _sha(snapshot)}
    return finish("observed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("binary", "execution-report", "objdump", "readelf", "output-parent"):
        parser.add_argument("--"+name, required=True, type=Path)
    parser.add_argument("--timeout", type=float, default=60)
    args = parser.parse_args()
    try:
        report = collect(args.binary, args.execution_report, args.objdump, args.readelf,
                         args.output_parent, timeout=args.timeout)
    except (OSError, ValueError) as error:
        parser.exit(3, str(error)+"\n")
    print(json.dumps({"status": report["status"], "report": str(Path(report["run_directory"])/"report.json")}))
    return 0 if report["status"] == "observed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
