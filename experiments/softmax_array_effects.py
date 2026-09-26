"""Replay the pinned softmax array helper's write footprint; no GPU execution."""
import argparse
import json
from pathlib import Path

from experiments.pytorch_softmax_intake import implementation_hashes, sha
from wavebridge.verification.array_call_effects import check

NATIVE_SHA = "317b1a438bc13845cf76b5aa7461db4db2081b402c457a85c4160fdd7257c027"


def run(native, output):
    if sha(native) != NATIVE_SHA or output.exists():
        raise ValueError("fixed_native_mismatch_or_output_exists")
    helpers = {str(path): sha(path) for path in
               (Path(__file__), Path(__file__).with_name("pytorch_softmax_intake.py"))}
    before = implementation_hashes()
    frontend = json.loads(native.read_text())
    if frontend.get("status") != "collected":
        raise ValueError("native_not_collected")
    checked = check(frontend["payload"]["ast"], "0x1954ab18", "0x19546950")
    after = implementation_hashes()
    report = {"schema_version": "softmax-array-effects-development/v1", "check": checked,
              "native_sha256": NATIVE_SHA, "implementation_before": before,
              "implementation_after": after, "driver_dependencies": helpers,
              "GPU_executed": False, "source_program_checked": False, "deployable": False,
              "inputs_unchanged": before == after and sha(native) == NATIVE_SHA
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
    args = parser.parse_args()
    run(args.native, args.output)
