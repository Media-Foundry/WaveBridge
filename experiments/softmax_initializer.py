"""Recheck the pinned mutable local_idx initializer, not its later value history."""
import argparse
import json
from pathlib import Path

from experiments.pytorch_softmax_intake import implementation_hashes, sha
from wavebridge.verification.initializer_domain import check_source

NATIVE_SHA = "317b1a438bc13845cf76b5aa7461db4db2081b402c457a85c4160fdd7257c027"


def run(native, protocol, output):
    if sha(native) != NATIVE_SHA or output.exists():
        raise ValueError("fixed_native_mismatch_or_output_exists")
    bound = json.loads(protocol.read_text())
    if bound.get("native_sha256") != NATIVE_SHA:
        raise ValueError("protocol_native_mismatch")
    protocol_hash = sha(protocol)
    helpers = {str(path): sha(path) for path in
               (Path(__file__), Path(__file__).with_name("pytorch_softmax_intake.py"))}
    before = implementation_hashes()
    frontend = json.loads(native.read_text())
    if frontend.get("status") != "collected":
        raise ValueError("native_not_collected")
    checked = check_source(frontend["payload"]["ast"], bound["declaration_id"],
                           bound["leaf_contract"], bound["integer_types"])
    after = implementation_hashes()
    report = {"schema_version": "softmax-initializer-development/v1", "check": checked,
              "native_sha256": NATIVE_SHA, "protocol_sha256": protocol_hash,
              "protocol": bound, "implementation_before": before, "implementation_after": after,
              "driver_dependencies": helpers, "GPU_executed": False,
              "source_program_checked": False, "deployable": False,
              "loop_entry_domain_established": False,
              "inputs_unchanged": before == after and sha(native) == NATIVE_SHA and sha(protocol) == protocol_hash
              and all(sha(path) == digest for path, digest in helpers.items())}
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": checked["status"], "reason": checked["reason"],
                      "result_interval": checked.get("result_interval"), "sha256": sha(output),
                      "inputs_unchanged": report["inputs_unchanged"]}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.native, args.protocol, args.output)
