"""Conditional replay of a pinned softmax call; leaf effects remain assumed."""
import argparse
import json
from pathlib import Path

from experiments.pytorch_softmax_intake import implementation_hashes, sha
from experiments.softmax_scalar_forwarding import NATIVE_SHA
from experiments.softmax_scalar_expression import FORWARDING_SHA
from wavebridge.verification.getter_returns import _hash
from wavebridge.verification.scalar_call_effects import check_no_memory_write


def run(native, forwarding, output):
    if sha(native) != NATIVE_SHA or sha(forwarding) != FORWARDING_SHA:
        raise ValueError("fixed_input_mismatch")
    if output.exists():
        raise ValueError("output_exists")
    before = implementation_hashes()
    helpers = {str(path): sha(path) for path in
               (Path(__file__), Path(__file__).with_name("pytorch_softmax_intake.py"),
                Path(__file__).with_name("softmax_scalar_forwarding.py"),
                Path(__file__).with_name("softmax_scalar_expression.py"))}
    frontend = json.loads(native.read_text())
    prior = json.loads(forwarding.read_text())
    if frontend.get("status") != "collected" or prior.get("native_sha256") != NATIVE_SHA:
        raise ValueError("input_binding_mismatch")
    root = frontend["payload"]["ast"]
    call_id = prior["selected_call_ast"]["id"]
    # Prior report supplies selection IDs only, never a proof accepted by checker.
    protocol = {"schema_version": "scalar-leaf-effect-assumption/v1", "root_sha256": _hash(root),
                "call_expression_id": call_id, "leaf_declaration_id": prior["selected_path"][-1]["id"],
                "leaf_no_memory_write_assumed": True, "valid_call_and_normal_return_assumed": True,
                "evidence_reference": "UNVERIFIED development sensitivity assumption, not a certificate"}
    checked = check_no_memory_write(root, call_id, protocol)
    after = implementation_hashes()
    report = {"schema_version": "softmax-scalar-call-development/v1",
              "native_sha256": NATIVE_SHA, "forwarding_sha256": FORWARDING_SHA,
              "call_expression_id": call_id, "effect_protocol": protocol, "check": checked,
              "source_program_checked": False, "deployable": False, "GPU_executed": False,
              "implementation_before": before, "implementation_after": after,
              "driver_dependencies": helpers,
              "inputs_unchanged": before == after and sha(native) == NATIVE_SHA
              and sha(forwarding) == FORWARDING_SHA
              and all(sha(path) == digest for path, digest in helpers.items())}
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": checked["status"], "reason": checked["reason"],
                      "sha256": sha(output), "inputs_unchanged": report["inputs_unchanged"]}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native", type=Path, required=True)
    parser.add_argument("--forwarding", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.native, args.forwarding, args.output)
