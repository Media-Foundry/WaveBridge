"""Replay conditional loop recovery with pinned builtin and scalar leaf premises."""
import argparse
from collections import Counter
import json
from pathlib import Path

from experiments.pytorch_softmax_intake import implementation_hashes, sha, walk
from wavebridge.analysis.column_loops import recover_with_call_effects

NATIVE_SHA = "317b1a438bc13845cf76b5aa7461db4db2081b402c457a85c4160fdd7257c027"
BUILTIN_SHA = "4b209cf805ca46d40293a595b9d3c65a891a394e3a5111467c70f0e56b777ce7"
SCALAR_SHA = "3a4dd37815d11bccca809a006f964526c16c4a1a25c219a8b60565aaf9167b42"


def run(native, builtin, scalar, output, *, all_same_wrapper=False):
    inputs = {str(native): NATIVE_SHA, str(builtin): BUILTIN_SHA, str(scalar): SCALAR_SHA}
    if any(sha(path) != digest for path, digest in inputs.items()):
        raise ValueError("fixed_input_mismatch")
    if output.exists():
        raise ValueError("output_exists")
    before = implementation_hashes()
    helpers = {str(path): sha(path) for path in
               (Path(__file__), Path(__file__).with_name("pytorch_softmax_intake.py"))}
    frontend = json.loads(native.read_text())
    old = json.loads(builtin.read_text())
    selected = json.loads(scalar.read_text())
    if (frontend.get("status") != "collected" or old.get("native_sha256") != NATIVE_SHA or
            selected.get("native_sha256") != NATIVE_SHA):
        raise ValueError("input_binding_mismatch")
    # Reuse fixed selections and explicitly unverified premises, NOT old checks.
    protocols = dict(old["call_protocols"])
    identifier = selected["call_expression_id"]
    if identifier in protocols:
        raise ValueError("duplicate_protocol")
    protocols[identifier] = selected["effect_protocol"]
    if all_same_wrapper:
        # Selection is exact declaration identity, not a math function name.
        # Every added call is independently checked by the recovery entry.
        target_id = selected["check"]["forwarding_check"]["wrapper_declaration_ids"][0]
        entries = [node for node in walk(frontend["payload"]["ast"]) if node.get("id") == old["entry_id"]]
        if len(entries) != 1:
            raise ValueError("entry_not_unique")
        for call in walk(entries[0]):
            parts = call.get("inner", [])
            if call.get("kind") != "CallExpr" or len(parts) != 2:
                continue
            decay = parts[0]
            refs = decay.get("inner", [])
            if (decay.get("kind") != "ImplicitCastExpr" or decay.get("castKind") != "FunctionToPointerDecay"
                    or len(refs) != 1 or refs[0].get("kind") != "DeclRefExpr"
                    or refs[0].get("referencedDecl", {}).get("id") != target_id):
                continue
            call_id = call["id"]
            if call_id in protocols and call_id != identifier:
                raise ValueError("duplicate_protocol")
            protocols[call_id] = dict(selected["effect_protocol"], call_expression_id=call_id)
    checked = recover_with_call_effects(frontend["payload"], old["entry_id"], 32, protocols)
    after = implementation_hashes()
    loops = checked.get("recovery", {}).get("loops", [])
    report = {"schema_version": "softmax-call-effects-development/v1", "inputs": inputs,
              "entry_id": old["entry_id"], "integer_abi": "explicit_external_int32_assumption",
              "call_protocols": protocols, "conditional": checked,
              "assumption_scope": "all_same_wrapper_calls" if all_same_wrapper else "one_scalar_call",
              "loop_counts": dict(Counter(loop["status"] for loop in loops)),
              "historical_builtin_only_loop_counts": old["conditional_loop_counts"],
              "source_program_checked": False, "deployable": False, "GPU_executed": False,
              "implementation_before": before, "implementation_after": after,
              "driver_dependencies": helpers,
              "inputs_unchanged": before == after
              and all(sha(path) == digest for path, digest in (inputs | helpers).items())}
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": checked["status"], "loop_counts": report["loop_counts"],
                      "sha256": sha(output), "inputs_unchanged": report["inputs_unchanged"]}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native", type=Path, required=True)
    parser.add_argument("--builtin", type=Path, required=True)
    parser.add_argument("--scalar", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--all-same-wrapper", action="store_true")
    args = parser.parse_args()
    run(args.native, args.builtin, args.scalar, args.output, all_same_wrapper=args.all_same_wrapper)
