"""Replay the exact argument of the previously selected softmax call."""
import argparse
import json
from pathlib import Path

from experiments.pytorch_softmax_intake import implementation_hashes, sha
from experiments.softmax_scalar_forwarding import NATIVE_SHA
from wavebridge.verification.scalar_expression_effects import check_no_memory_write

FORWARDING_SHA = "409b27d15538871fe849ffe981d716b4132586eed5e4eb34fe6347cdb397f7c2"


def run(native, forwarding, output):
    if sha(native) != NATIVE_SHA or sha(forwarding) != FORWARDING_SHA:
        raise ValueError("fixed_input_mismatch")
    if output.exists():
        raise ValueError("output_exists")
    before = implementation_hashes()
    helpers = {str(path): sha(path) for path in
               (Path(__file__), Path(__file__).with_name("pytorch_softmax_intake.py"),
                Path(__file__).with_name("softmax_scalar_forwarding.py"))}
    frontend = json.loads(native.read_text())
    prior = json.loads(forwarding.read_text())
    if frontend.get("status") != "collected" or prior.get("native_sha256") != NATIVE_SHA:
        raise ValueError("input_binding_mismatch")
    call = prior["selected_call_ast"]
    if call.get("kind") != "CallExpr" or len(call.get("inner", [])) != 2:
        raise ValueError("not_unary_call")
    argument = call["inner"][1]
    checked = check_no_memory_write(frontend["payload"]["ast"], argument["id"])
    after = implementation_hashes()
    report = {"schema_version": "softmax-scalar-expression-development/v1",
              "native_sha256": NATIVE_SHA, "forwarding_sha256": FORWARDING_SHA,
              "argument_id": argument["id"], "check": checked,
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
