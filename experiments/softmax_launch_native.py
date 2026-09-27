"""Rebuild exact softmax launch binding, without inferring configuration values."""

import argparse
import json
from pathlib import Path

from experiments.pytorch_softmax_intake import implementation_hashes, select_entry, sha
from wavebridge.analysis.launch_facts import inspect
from wavebridge.verification.getter_returns import _hash
from wavebridge.verification.launch_binding import check


NATIVE_SHA = "a59c12247f796fe2034ba03ecc43782f77ac3942496b18a140ceacbb24c7ff45"
KERNEL_ID = "0x30d762e0"


def run(native, output, *, threads_object=False, host_minimum_update=False, host_minimum_history=False,
        host_minimum_quotient=False):
    if sha(native) != NATIVE_SHA or output.exists():
        raise ValueError("native_mismatch_or_output_exists")
    before = implementation_hashes()
    dependencies = {str(path): sha(path) for path in
                    (Path(__file__), Path(__file__).with_name("pytorch_softmax_intake.py"))}
    capture = json.loads(native.read_text())
    if capture.get("status") != "collected":
        raise ValueError("native_not_collected")
    root = capture["payload"]["ast"]
    kernel = select_entry(root)
    if kernel["id"] != KERNEL_ID:
        raise ValueError("fixed_kernel_identity_mismatch")
    facts = inspect(root, KERNEL_ID)
    sites = facts["sites"]
    print(json.dumps({"phase": "launch_discovery", "selected_kernel_sites": len(sites),
                      "unresolved_sites": len(facts["unresolved_sites"])}), flush=True)
    selection = None
    checked = {"status": "unknown", "reason": "selected_kernel_launch_not_unique"}
    if len(sites) == 1:
        site = sites[0]
        selection = {"schema_version": "launch-selection/v1", "ast_root_sha256": _hash(root),
                     "kernel_declaration_id": KERNEL_ID, "launch_id": site["launch_id"],
                     "configuration_declaration_id": site["configuration_declaration_id"],
                     "configuration_expression_ids": [arg["id"] for arg in site["configuration_arguments"]]}
        checked = check(root, selection)
    object_report = None
    if threads_object and checked.get("status") == "checked":
        from wavebridge.verification.object_use_closure import inspect_structure

        # Exact development-input selection, not a constructor-value oracle.
        selected_variable = "0x30d69b78"
        owners = []
        pending = [(root, None)]
        while pending:
            node, owner = pending.pop()
            if node.get("kind") == "FunctionDecl":
                owner = node
            if node.get("id") == selected_variable:
                owners.append(owner)
            pending.extend((child, owner) for child in node.get("inner", []))
        if len(owners) != 1 or owners[0] is None:
            raise ValueError("threads_owner_not_unique")
        abi = {"int": {"bits": 32, "signed": True},
               "unsigned int": {"bits": 32, "signed": False}}
        object_report = inspect_structure(capture["payload"], selected_variable, abi, {},
                                         instantiated_function_id=owners[0]["id"],
                                         max_ast_nodes=10_000_000)
    minimum_report = None
    if host_minimum_update and checked.get("status") == "checked":
        from wavebridge.verification.integer_selection import check_local_minimum_update

        minimum_report = check_local_minimum_update(
            root, "0x30d69470", {"int": {"bits": 32, "signed": True}},
            max_ast_nodes=10_000_000)
    history_report = None
    if host_minimum_history and checked.get("status") == "checked":
        from wavebridge.verification.integer_selection import check_minimum_to_statement

        statements, pending = [], [(root, None)]
        while pending:
            node, parent = pending.pop()
            if node.get("id") == "0x30d69b78":
                statements.append(parent)
            pending.extend((child, node) for child in node.get("inner", []))
        if len(statements) != 1 or statements[0].get("kind") != "DeclStmt":
            raise ValueError("threads_statement_not_unique")
        history_report = check_minimum_to_statement(
            root, "0x30d69470", statements[0]["id"], {"int": {"bits": 32, "signed": True}},
            max_ast_nodes=10_000_000)
    quotient_report = None
    if host_minimum_quotient and checked.get("status") == "checked":
        from wavebridge.verification.integer_selection import check_minimum_quotient

        candidates, pending = [], [(root, None)]
        while pending:
            node, owner = pending.pop()
            if node.get("kind") == "FunctionDecl":
                owner = node.get("id")
            if (owner == "0x30a41828" and node.get("kind") == "VarDecl" and
                    node.get("name") == "warps_per_block"):
                candidates.append(node)
            pending.extend((child, owner) for child in node.get("inner", []))
        if len(candidates) != 1:
            raise ValueError("quotient_declaration_not_unique")
        quotient_report = check_minimum_quotient(
            root, "0x30d69470", candidates[0]["id"], {"int": {"bits": 32, "signed": True}},
            max_ast_nodes=10_000_000)
    after = implementation_hashes()
    report = {"schema_version": "softmax-native-launch-observation/v1", "check": checked,
              "selection": selection, "launch_discovery": facts, "native_sha256": NATIVE_SHA,
              "threads_object_check": object_report,
              "host_minimum_update_check": minimum_report,
              "host_minimum_history_check": history_report,
              "host_minimum_quotient_check": quotient_report,
              "implementation_before": before, "implementation_after": after,
              "driver_dependencies": dependencies,
              "inputs_unchanged": before == after and sha(native) == NATIVE_SHA and
                  all(sha(path) == digest for path, digest in dependencies.items()),
              "configuration_values_established": False, "lane_family_established": False,
              "GPU_executed": False, "source_program_checked": False, "deployable": False}
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": checked["status"], "reason": checked.get("reason"),
                      "inputs_unchanged": report["inputs_unchanged"], "sha256": sha(output)}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--threads-object", action="store_true")
    parser.add_argument("--host-minimum-update", action="store_true")
    parser.add_argument("--host-minimum-history", action="store_true")
    parser.add_argument("--host-minimum-quotient", action="store_true")
    args = parser.parse_args()
    run(args.native, args.output, threads_object=args.threads_object,
        host_minimum_update=args.host_minimum_update, host_minimum_history=args.host_minimum_history,
        host_minimum_quotient=args.host_minimum_quotient)
