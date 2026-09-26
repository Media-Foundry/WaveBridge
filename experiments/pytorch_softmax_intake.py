"""Frozen-analyzer first observation of a new target, not blind holdout proof."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess

from wavebridge.frontend.clang_ast import collect
from wavebridge.analysis.column_loops import recover
from wavebridge.analysis.reduction_discovery import discover
from wavebridge.analysis.launch_facts import inspect as inspect_launch

ROOT = Path(__file__).resolve().parents[1]
HEADER = "ATen/native/cuda/PersistentSoftmax.cuh"
HEADER_SHA = "12436933cae8c1e4096af342313070ce873eefad3d6a1637675ef780d1fdea1e"
HARNESS = ROOT / "benchmarks/intake/pytorch-softmax-harness.cu"
PROTOCOL = ROOT / "benchmarks/intake/pytorch-softmax-protocol.md"
FREEZE = "ee10c5d6e0c8341e6c24d28521d40068114dfbdd"


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def implementation_hashes():
    return {str(path.relative_to(ROOT)): sha(path)
            for path in sorted((ROOT / "src/wavebridge").rglob("*.py"))}


def require_frozen_implementation(hashes):
    listing = subprocess.check_output(
        ["git", "ls-tree", "-r", "--name-only", FREEZE, "--", "src/wavebridge"], cwd=ROOT,
        text=True).splitlines()
    if set(hashes) != {name for name in listing if name.endswith(".py")}:
        raise ValueError("analysis_implementation_file_set_not_frozen")
    result = subprocess.run(["git", "diff", "--quiet", FREEZE, "--", "src/wavebridge"], cwd=ROOT)
    if result.returncode != 0:
        raise ValueError("analysis_implementation_differs_from_frozen_revision")


def walk(node):
    if not isinstance(node, dict):
        return
    yield node
    for child in node.get("inner", []):
        yield from walk(child)


def select_entry(root):
    """Select only the predeclared specialization, never by recovered success."""
    matches = {}
    for node in walk(root):
        if node.get("kind") != "FunctionDecl" or node.get("name") != "softmax_warp_forward":
            continue
        children = node.get("inner", [])
        if not any(child.get("kind") == "CompoundStmt" for child in children):
            continue
        arguments = [child for child in children if child.get("kind") == "TemplateArgument"]
        if len(arguments) != 6:
            continue
        if [arg.get("type", {}).get("qualType") for arg in arguments[:3]] != ["float"] * 3:
            continue
        # Clang JSON template integral values are numeric, including bool args.
        if [arg.get("value") for arg in arguments[3:]] != [7, 0, 0]:
            continue
        identity = node.get("id")
        if not isinstance(identity, str) or not identity:
            raise ValueError("selected_entry_identity_missing")
        if identity in matches and matches[identity] != node:
            raise ValueError("selected_entry_identity_conflict")
        matches[identity] = node
    if len(matches) != 1:
        raise ValueError("selected_entry_missing_or_ambiguous")
    return next(iter(matches.values()))


def run(config_path, output_dir, *, timeout=180):
    config_path = Path(config_path).resolve()
    config = json.loads(config_path.read_text())
    directory = Path(output_dir).resolve()
    directory.mkdir(parents=True, exist_ok=False)
    include_root = Path(config["torch_include"]).resolve()
    header_path = include_root / HEADER
    if sha(header_path) != HEADER_SHA:
        raise ValueError("upstream_header_hash_mismatch")
    before = implementation_hashes()
    require_frozen_implementation(before)
    report = {
        "schema_version": "pytorch-softmax-intake/v1", "status": "not_started",
        "analyzer_freeze_revision": FREEZE,
        "evaluation_role": "new_target_in_previously_exposed_dependency_not_blind_holdout",
        "compilation_view": "unmodified_upstream_header_with_explicit_instantiation_harness",
        "selected_template_arguments": ["float", "float", "float", 7, False, False],
        "source_header": {"path": str(header_path), "sha256": HEADER_SHA},
        "harness": {"path": str(HARNESS), "sha256": sha(HARNESS)},
        "config": {"path": str(config_path), "sha256": sha(config_path)},
        "protocol": {"path": str(PROTOCOL), "sha256": sha(PROTOCOL)},
        "driver_sha256": sha(__file__), "implementation_before": before,
        "int_bits": 32, "int_bits_origin": "explicit_external_assumption",
        "source_program_checked": False, "deployable": False, "GPU_executed": False,
        "full_production_TU": False, "strict_lineage_holdout_established": False,
        "analysis": None,
    }
    (directory / "pre-analysis.json").write_text(json.dumps(report, indent=2) + "\n")
    frontend = collect(HARNESS, config["compiler"], config["compiler_args"],
                       "softmax_warp_forward", timeout=timeout,
                       full_translation_unit=True, dependency_binding="required",
                       toolchain_trace=True)
    print("frontend:", frontend["status"], flush=True)
    ast_path = directory / "ast.json"
    with ast_path.open("x") as stream:
        json.dump(frontend, stream, separators=(",", ":"), allow_nan=False)
    report.update(ast_report=str(ast_path), ast_report_sha256=sha(ast_path),
                  frontend_status=frontend["status"],
                  dependency_status=frontend["dependency_binding"]["status"],
                  toolchain_trace_status=frontend["toolchain_trace"]["status"])
    # The configured include root must be the one Clang actually observed, not
    # merely a separately hashed copy while another -I path supplies the header.
    matching_headers = [item for item in frontend["dependency_binding"].get("files", [])
                        if item.get("resolved_path") == str(header_path.resolve())]
    report["selected_header_dependency_bound"] = (
        len(matching_headers) == 1 and matching_headers[0].get("sha256") == HEADER_SHA)
    if frontend["status"] != "collected":
        report.update(status="frontend_unavailable", reason=frontend.get("reason"))
    elif report["dependency_status"] != "observed":
        report.update(status="dependency_evidence_unavailable")
    elif not report["selected_header_dependency_bound"]:
        report.update(status="selected_header_not_bound_to_compilation")
    elif len(frontend["ast_roots"]) != 1:
        report.update(status="ambiguous_compilation_view")
    else:
        root = frontend["ast_roots"][0]
        try:
            entry = select_entry(root)
        except ValueError as error:
            report.update(status="entry_selection_unknown", reason=str(error))
        else:
            identity = entry["id"]
            report["selected_entry"] = {key: entry.get(key) for key in
                                        ("id", "name", "mangledName", "loc", "range")}
            columns = recover(root, identity, 32)
            report["analysis"] = {"columns": columns,
                                  "reduction_discovery": discover(root, identity, 32),
                                  "launch": inspect_launch(root, identity)}
            report["loop_counts"] = dict(Counter(loop["status"] for loop in columns["loops"]))
            report["loop_reasons"] = dict(Counter(loop.get("reason") for loop in columns["loops"]
                                                  if loop.get("reason") is not None))
            report["status"] = "analyzed"
    report["implementation_after"] = implementation_hashes()
    report["implementation_hashes_stable"] = before == report["implementation_after"]
    report["header_unchanged"] = sha(header_path) == HEADER_SHA
    report["harness_unchanged"] = sha(HARNESS) == report["harness"]["sha256"]
    report["driver_unchanged"] = sha(__file__) == report["driver_sha256"]
    report["config_unchanged"] = sha(config_path) == report["config"]["sha256"]
    report["protocol_unchanged"] = sha(PROTOCOL) == report["protocol"]["sha256"]
    if not all(report[key] for key in ("implementation_hashes_stable", "header_unchanged",
                                      "harness_unchanged", "driver_unchanged",
                                      "config_unchanged", "protocol_unchanged")):
        report["status"] = "inputs_changed"
    path = directory / "report.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n")
    print(json.dumps({"status": report["status"], "report": str(path), "sha256": sha(path)}), flush=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--timeout", type=float, default=180)
    args = parser.parse_args()
    report = run(args.config, args.output_dir, timeout=args.timeout)
    return 0 if report["status"] == "analyzed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
