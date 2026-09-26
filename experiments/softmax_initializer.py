"""Recheck the pinned mutable local_idx initializer, not its later value history."""
import argparse
import json
from pathlib import Path

from experiments.pytorch_softmax_intake import implementation_hashes, sha
from wavebridge.verification.initializer_domain import check_source, check_to_statement

NATIVE_SHA = "317b1a438bc13845cf76b5aa7461db4db2081b402c457a85c4160fdd7257c027"


def run(native, protocol, output, *, target_statement=None, call_protocols=None):
    if sha(native) != NATIVE_SHA or output.exists():
        raise ValueError("fixed_native_mismatch_or_output_exists")
    bound = json.loads(protocol.read_text())
    if bound.get("native_sha256") != NATIVE_SHA:
        raise ValueError("protocol_native_mismatch")
    protocol_hash = sha(protocol)
    helpers = {str(path): sha(path) for path in
               (Path(__file__), Path(__file__).with_name("pytorch_softmax_intake.py"))}
    effects = {}
    if call_protocols is not None:
        if target_statement is None:
            raise ValueError("call_protocols_require_target_statement")
        helpers[str(call_protocols)] = sha(call_protocols)
        if helpers[str(call_protocols)] != "31a6570762225ea247f24b799be28ebd51f3dab13e562e32cccb8e305d764f67":
            raise ValueError("fixed_call_protocol_artifact_mismatch")
        previous = json.loads(call_protocols.read_text())
        if NATIVE_SHA not in previous.get("inputs", {}).values():
            raise ValueError("call_protocol_native_mismatch")
        effects = previous["call_protocols"]
    before = implementation_hashes()
    frontend = json.loads(native.read_text())
    if frontend.get("status") != "collected":
        raise ValueError("native_not_collected")
    if target_statement is None:
        checked = check_source(frontend["payload"]["ast"], bound["declaration_id"],
                               bound["leaf_contract"], bound["integer_types"])
    else:
        checked = check_to_statement(frontend["payload"], bound["declaration_id"], target_statement,
                                     bound["leaf_contract"], bound["integer_types"], effects,
                                     use_static_branches=True)
    after = implementation_hashes()
    report = {"schema_version": "softmax-initializer-development/v1", "check": checked,
              "native_sha256": NATIVE_SHA, "protocol_sha256": protocol_hash,
              "protocol": bound, "implementation_before": before, "implementation_after": after,
              "driver_dependencies": helpers, "GPU_executed": False,
              "source_program_checked": False, "deployable": False,
              "loop_entry_domain_established": False,
              "inputs_unchanged": before == after and sha(native) == NATIVE_SHA and sha(protocol) == protocol_hash
              and all(sha(path) == digest for path, digest in helpers.items())}
    if target_statement is not None:
        report["schema_version"] = "softmax-initializer-history-development/v1"
        report["target_statement_id"] = target_statement
        report["call_protocols"] = effects
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": checked["status"], "reason": checked["reason"],
                      "result_interval": checked.get("result_interval"), "sha256": sha(output),
                      "inputs_unchanged": report["inputs_unchanged"]}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--target-statement")
    parser.add_argument("--call-protocols", type=Path)
    args = parser.parse_args()
    run(args.native, args.protocol, args.output, target_statement=args.target_statement,
        call_protocols=args.call_protocols)
