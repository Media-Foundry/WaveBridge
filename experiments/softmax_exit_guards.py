"""Inspect the exact remaining loop exits in the pinned softmax native AST."""
import argparse
import json
from pathlib import Path

from experiments.pytorch_softmax_intake import implementation_hashes, sha, walk
from wavebridge.verification.loop_exit_guards import (
    inspect_structure, check_prefix_values, check_header_connection, check_work_preservation)

NATIVE_SHA = "317b1a438bc13845cf76b5aa7461db4db2081b402c457a85c4160fdd7257c027"
RECOVERY_SHA = "31a6570762225ea247f24b799be28ebd51f3dab13e562e32cccb8e305d764f67"


def run(native, recovery, output, *, prefix_values=False, header_connection=False, work_preservation=False,
        int_bits=32, static_branches=False):
    if static_branches and not work_preservation:
        raise ValueError("static_branches_requires_work_preservation")
    if sha(native) != NATIVE_SHA or sha(recovery) != RECOVERY_SHA:
        raise ValueError("fixed_input_mismatch")
    if output.exists():
        raise ValueError("output_exists")
    before = implementation_hashes()
    helpers = {str(path): sha(path) for path in
               (Path(__file__), Path(__file__).with_name("pytorch_softmax_intake.py"))}
    frontend = json.loads(native.read_text())
    old = json.loads(recovery.read_text())
    if frontend.get("status") != "collected" or NATIVE_SHA not in old.get("inputs", {}).values():
        raise ValueError("input_binding_mismatch")
    root = frontend["payload"]["ast"]
    entries = [node for node in walk(root) if node.get("id") == old["entry_id"]]
    if len(entries) != 1:
        raise ValueError("entry_not_unique")
    loops = [node for node in walk(entries[0]) if node.get("kind") == "ForStmt"]
    checks = []
    for previous in old["conditional"]["recovery"]["loops"]:
        if previous.get("reason") != "unsupported_control_flow_in_body":
            continue
        matches = [node for node in loops if node.get("range") == previous["range"]]
        if len(matches) != 1:
            raise ValueError("loop_selection_not_unique")
        if work_preservation:
            # Select only explicit old premises whose call IDs occur in this
            # original loop. The checker reruns all applicable call checks.
            call_ids = {node.get("id") for node in walk(matches[0]) if node.get("kind") == "CallExpr"}
            protocols = {key: value for key, value in old["call_protocols"].items() if key in call_ids}
            checked = check_work_preservation(frontend["payload"], matches[0]["id"], int_bits, protocols,
                                               use_static_branches=static_branches)
        elif header_connection:
            checked = check_header_connection(root, matches[0]["id"], int_bits)
        else:
            checker = check_prefix_values if prefix_values else inspect_structure
            checked = checker(root, matches[0]["id"])
        checks.append({"loop_range": previous["range"], "check": checked})
    if not checks:
        raise ValueError("no_remaining_exit_loops")
    after = implementation_hashes()
    report = {"schema_version": "softmax-exit-guard-development/v1",
              "native_sha256": NATIVE_SHA, "recovery_sha256": RECOVERY_SHA, "checks": checks,
              "source_program_checked": False, "deployable": False, "GPU_executed": False,
              "iteration_domains_established": False, "previous_recovery_upgraded": False,
              "implementation_before": before, "implementation_after": after,
              "driver_dependencies": helpers,
              "inputs_unchanged": before == after and sha(native) == NATIVE_SHA and sha(recovery) == RECOVERY_SHA
              and all(sha(path) == digest for path, digest in helpers.items())}
    if prefix_values:
        report["schema_version"] = "softmax-exit-prefix-development/v1"
    if header_connection:
        report["schema_version"] = "softmax-exit-header-development/v1"
        report["integer_abi"] = {"int_bits": int_bits, "status": "explicit_external_assumption"}
    if work_preservation:
        report["schema_version"] = "softmax-exit-work-development/v1"
        report["integer_abi"] = {"int_bits": int_bits, "status": "explicit_external_assumption"}
        report["static_branches_enabled"] = static_branches
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"checks": [{"status": item["check"]["status"], "reason": item["check"]["reason"],
                                  "scope": item["check"]["scope"]}
                                 for item in checks],
                      "sha256": sha(output), "inputs_unchanged": report["inputs_unchanged"]}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native", type=Path, required=True)
    parser.add_argument("--recovery", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--prefix-values", action="store_true")
    mode.add_argument("--header-connection", action="store_true")
    mode.add_argument("--work-preservation", action="store_true")
    parser.add_argument("--int-bits", type=int, default=32)
    parser.add_argument("--static-branches", action="store_true")
    args = parser.parse_args()
    run(args.native, args.recovery, args.output, prefix_values=args.prefix_values,
        header_connection=args.header_connection, work_preservation=args.work_preservation,
        int_bits=args.int_bits, static_branches=args.static_branches)
