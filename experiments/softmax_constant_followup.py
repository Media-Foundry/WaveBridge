"""Development replay on a sealed real AST; never rewrites its frozen first result."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys

from experiments.pytorch_softmax_intake import implementation_hashes, select_entry, sha, walk
from wavebridge.analysis.integer_constants import evaluate
from wavebridge.analysis.column_loops import recover
from wavebridge.analysis.reduction_discovery import discover

AST_SHA = "7da820c6358895e322b73e7f942c046ae9114dc65d5092666a348397b7e05a86"
PREVIOUS_REPORT_SHA = "3a39162609eddcdd6a144749bc59b1e3fa895d7fe144cef7f7ef8d3db728d5cc"


def run(ast_path, previous_report, output_dir):
    ast_path, previous_report = Path(ast_path).resolve(), Path(previous_report).resolve()
    if sha(ast_path) != AST_SHA or sha(previous_report) != PREVIOUS_REPORT_SHA:
        raise ValueError("frozen_ast_or_report_hash_mismatch")
    previous = json.loads(previous_report.read_text())
    if previous.get("ast_report_sha256") != AST_SHA:
        raise ValueError("previous_report_ast_binding_mismatch")
    directory = Path(output_dir).resolve()
    directory.mkdir(parents=True, exist_ok=False)
    implementation = implementation_hashes()
    driver_sha = sha(__file__)
    report = {
        "schema_version": "softmax-constant-followup/v1", "status": "not_started",
        "evaluation_role": "development_replay_on_previously_analyzed_real_ast_not_holdout",
        "previous_report": str(previous_report), "previous_report_sha256": PREVIOUS_REPORT_SHA,
        "ast": str(ast_path), "ast_sha256": AST_SHA,
        "source_program_checked": False, "deployable": False, "GPU_executed": False,
        "frontend_reexecuted": False, "driver_sha256": driver_sha,
        "command": sys.argv, "implementation_before": implementation,
        "constants": [], "int_bits": 32, "int_bits_origin": "explicit_external_assumption",
    }
    (directory / "pre-analysis.json").write_text(json.dumps(report, indent=2) + "\n")
    frontend = json.loads(ast_path.read_text())
    if frontend.get("status") != "collected" or len(frontend.get("ast_roots", [])) != 1:
        raise ValueError("saved_frontend_not_unique_collected_root")
    root = frontend["ast_roots"][0]
    entry = select_entry(root)
    # Enumerate all concrete constexpr locals, not a name -> expected-value map.
    for node in walk(entry):
        if node.get("kind") == "VarDecl" and node.get("constexpr") is True:
            report["constants"].append({"name": node.get("name"), "id": node["id"],
                                        "evaluation": evaluate(root, node["id"], 32)})
    columns = recover(root, entry["id"], 32)
    reduction = discover(root, entry["id"], 32)
    report["columns"] = columns
    report["reduction_discovery"] = reduction
    report["loop_counts"] = dict(Counter(loop["status"] for loop in columns["loops"]))
    report["loop_reasons"] = dict(Counter(loop["reason"] for loop in columns["loops"] if loop.get("reason")))
    report["previous_loop_counts"] = previous["loop_counts"]
    report["previous_loop_reasons"] = previous["loop_reasons"]
    report["implementation_after"] = implementation_hashes()
    report["inputs_unchanged"] = (sha(ast_path) == AST_SHA and sha(previous_report) == PREVIOUS_REPORT_SHA
                                  and driver_sha == sha(__file__)
                                  and implementation == report["implementation_after"])
    report["status"] = "analyzed" if report["inputs_unchanged"] else "inputs_changed"
    path = directory / "report.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n")
    print(json.dumps({"status": report["status"], "report": str(path), "sha256": sha(path)}))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ast", type=Path, required=True)
    parser.add_argument("--previous-report", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    report = run(args.ast, args.previous_report, args.output_dir)
    return 0 if report["status"] == "analyzed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
