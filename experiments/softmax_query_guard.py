"""Prepare a pinned, isolated runtime-guard candidate; never deploy or certify it."""
import argparse
import hashlib
import json
from pathlib import Path

INPUTS = {
    "pytorch-softmax-hip.hip.cpp": "fcfa6606452f25ce85508267bffff7ba743148ffef0b600e05b9b54f8bac3cc0",
    "wavebridge_softmax_compat.h": "532ef5da3fc38256117702443df6fc354f7b7db07ae9465bd3cb94f98e282489",
    "PersistentSoftmax.hip.cuh": "9579a670b1a0f1871e5dbfa747748efc7649d7e9b319bf85012ffb58d80a9328",
}
ANCHOR = "        int warp_size = at::cuda::warp_size();\n"


def add_guard(source, width):
    if type(width) is not int or not 1 <= width <= 2147483647:
        raise ValueError("positive_int_width_required")
    if source.count(ANCHOR) != 2:
        raise ValueError("pinned_forward_and_backward_context_required")
    # Only the forward host dispatch is changed. No constants, kernel or launch
    # formulas are rewritten, and backward remains byte-for-byte unchanged.
    return source.replace(ANCHOR, ANCHOR + f"        if (warp_size != {width}) std::abort();\n", 1)


def prepare(source, output, width=32):
    source, output = Path(source).resolve(), Path(output).resolve()
    if output.exists():
        raise ValueError("output_must_not_exist")
    contents = {name: (source / name).read_bytes() for name in INPUTS}
    digest = lambda data: hashlib.sha256(data).hexdigest()
    if {name: digest(data) for name, data in contents.items()} != INPUTS:
        raise ValueError("pinned_input_hash_mismatch")
    changed = dict(contents)
    changed["PersistentSoftmax.hip.cuh"] = add_guard(contents["PersistentSoftmax.hip.cuh"].decode(), width).encode()
    output.mkdir(parents=True, exist_ok=False)
    for name, data in changed.items():
        (output / name).write_bytes(data)
    report = {"schema_version": "softmax-query-guard-candidate/v1", "status": "unverified_candidate",
              "source_directory": str(source), "output_directory": str(output),
              "input_hashes": INPUTS, "output_hashes": {name: digest(data) for name, data in changed.items()},
              "expected_query_width": width, "change": "insert fail-stop guard after forward getter initialization",
              "source_equivalence_proved": False, "fallback_provided": False,
              "GPU_executed": False, "deployable": False,
              "limitation": "rejects other queried widths; this is not a native-width adaptation or automatic portability result"}
    (output / "guard-candidate.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--width", type=int, default=32)
    args = parser.parse_args()
    print(json.dumps(prepare(args.source, args.output, args.width), indent=2))
