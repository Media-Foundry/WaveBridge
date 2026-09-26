"""Replay the pinned softmax array helper's write footprint; no GPU execution."""
import argparse
import json
from pathlib import Path

from experiments.pytorch_softmax_intake import implementation_hashes, sha, select_entry, walk
from wavebridge.verification.array_call_effects import check

NATIVE_SHA = "317b1a438bc13845cf76b5aa7461db4db2081b402c457a85c4160fdd7257c027"
LIFECYCLE_NATIVE_SHA = "a59c12247f796fe2034ba03ecc43782f77ac3942496b18a140ceacbb24c7ff45"


def run(native, output, *, use_scalar_operators=False, use_native_lifecycle=False):
    expected = LIFECYCLE_NATIVE_SHA if use_native_lifecycle else NATIVE_SHA
    if sha(native) != expected or output.exists():
        raise ValueError("fixed_native_mismatch_or_output_exists")
    helpers = {str(path): sha(path) for path in
               (Path(__file__), Path(__file__).with_name("pytorch_softmax_intake.py"))}
    before = implementation_hashes()
    frontend = json.loads(native.read_text())
    if frontend.get("status") != "collected":
        raise ValueError("native_not_collected")
    root = frontend["payload"]["ast"]
    call_id, protected_id = "0x1954ab18", "0x19546950"
    if use_native_lifecycle:
        entry = select_entry(root)
        declarations = [n for n in walk(entry) if n.get("kind") == "VarDecl" and n.get("name") == "local_idx"]
        if len(declarations) != 1:
            raise ValueError("protected_selection_not_unique")
        call_id, protected_id = "0x30de0078", declarations[0]["id"]
    checked = check(root, call_id, protected_id, use_scalar_operators=use_scalar_operators,
                    native_payload=frontend["payload"] if use_native_lifecycle else None)
    after = implementation_hashes()
    report = {"schema_version": "softmax-array-effects-development/v1", "check": checked,
              "native_sha256": expected, "implementation_before": before,
              "implementation_after": after, "driver_dependencies": helpers,
              "use_scalar_operators": use_scalar_operators,
              "use_native_lifecycle": use_native_lifecycle,
              "GPU_executed": False, "source_program_checked": False, "deployable": False,
              "inputs_unchanged": before == after and sha(native) == expected
              and all(sha(path) == digest for path, digest in helpers.items())}
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": checked["status"], "reason": checked["reason"],
                      "explicit_write_targets_checked": checked["explicit_write_targets_checked"],
                      "writes": len(checked["explicit_writes"]),
                      "pending_effects": checked["pending_effects"], "sha256": sha(output),
                      "inputs_unchanged": report["inputs_unchanged"]}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--use-scalar-operators", action="store_true")
    parser.add_argument("--use-native-lifecycle", action="store_true")
    args = parser.parse_args()
    run(args.native, args.output, use_scalar_operators=args.use_scalar_operators,
        use_native_lifecycle=args.use_native_lifecycle)
