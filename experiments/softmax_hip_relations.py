"""Replay existing relation checks on the executed HIP input without imported premises."""
import argparse
import json
from pathlib import Path

from experiments.pytorch_softmax_intake import implementation_hashes, select_entry, sha, walk
from experiments.softmax_call_audit import inventory
from wavebridge.analysis.column_loops import observe_header
from wavebridge.verification.loop_exit_guards import inspect_structure, check_work_preservation

AST_SHA = "ae7cb74e0b35a40ab14a42a9f5c763be7279f95ef7586e30513e92508b80ad11"
INTAKE_SHA = "e0f3691cd2a4952193770cf251e7414d2be9ea4af11b4776967f7e0da9e091b9"


def validate_intake(frontend, intake):
    if (frontend.get("status") != "collected" or len(frontend.get("ast_roots", [])) != 1
            or intake.get("ast_report_sha256") != AST_SHA
            or intake.get("status") != "analyzed"
            or intake.get("executed_source_files_bound") is not True
            or intake.get("inputs_unchanged") is not True):
        raise ValueError("intake_binding_not_established")
    root = frontend["ast_roots"][0]
    entry = select_entry(root)
    if entry.get("id") != intake.get("selected_entry", {}).get("id"):
        raise ValueError("selected_entry_changed")
    return root, entry


def run(ast, intake, output):
    inputs = {str(ast): AST_SHA, str(intake): INTAKE_SHA}
    if any(sha(p) != digest for p, digest in inputs.items()):
        raise ValueError("sealed_input_mismatch")
    output.mkdir(parents=True, exist_ok=False)
    before = implementation_hashes()
    helpers = {str(Path(__file__).with_name(name)): sha(Path(__file__).with_name(name)) for name in
               ("softmax_hip_relations.py", "pytorch_softmax_intake.py", "softmax_call_audit.py",
                "softmax_constant_followup.py")}
    root, entry = validate_intake(json.loads(ast.read_text()), json.loads(intake.read_text()))
    report = {"schema_version": "softmax-hip-relations/v1", "inputs": inputs,
              "entry_id": entry["id"], "implementation_before": before,
              "driver_dependencies": helpers, "integer_abi": "explicit_external_int32_assumption",
              "external_call_protocols": {}, "native_observations_supplied": False,
              "source_program_checked": False, "deployable": False, "GPU_executed": False,
              "frontend_reexecuted": False, "loops": []}
    (output / "pre-analysis.json").write_text(json.dumps(report, indent=2) + "\n")
    for loop in (node for node in walk(entry) if node.get("kind") == "ForStmt"):
        structure = inspect_structure(root, loop["id"])
        item = {"id": loop["id"], "range": loop.get("range"),
                "header": observe_header(root, loop["id"], 32), "exit_structure": structure}
        # This checker requires a direct exit partition; a missing partition
        # is not a claim that the loop is invalid or that no other checker applies.
        if structure["status"] == "checked":
            item["guarded_work"] = check_work_preservation(
                {"ast": root}, loop["id"], 32, {}, use_static_branches=True, use_nested_loops=True)
        report["loops"].append(item)
        print(json.dumps({"loop": loop["id"], "header": item["header"]["status"],
                          "exit_structure": structure["status"]}), flush=True)
    report["call_inventory"] = inventory(root, entry["id"])
    report["implementation_after"] = implementation_hashes()
    report["inputs_unchanged"] = (before == report["implementation_after"] and
        all(sha(p) == digest for p, digest in (inputs | helpers).items()))
    report["status"] = "observed" if report["inputs_unchanged"] else "inputs_changed"
    path = output / "report.json"
    path.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "sha256": sha(path)}), flush=True)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ast", type=Path, required=True)
    parser.add_argument("--intake", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(0 if run(args.ast, args.intake, args.output)["inputs_unchanged"] else 2)
