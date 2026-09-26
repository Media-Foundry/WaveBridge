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


def run(native, output):
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
    after = implementation_hashes()
    report = {"schema_version": "softmax-native-launch-observation/v1", "check": checked,
              "selection": selection, "launch_discovery": facts, "native_sha256": NATIVE_SHA,
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
    args = parser.parse_args()
    run(args.native, args.output)
