"""Exact-integer diagnostic for a nonnegative binary32 reduction witness.

This is an explicit route-model experiment, not source recovery or GPU execution.
Numbers are integers in units of 2**-149. Every add is rounded to binary32,
round-to-nearest ties-to-even, with gradual underflow and finite results only.
"""
from __future__ import annotations

import json

from wavebridge.verification.block_routes import compare


def rounded_add(left: int, right: int) -> int:
    if any(type(value) is not int or value < 0 for value in (left, right)):
        raise ValueError("nonnegative integer units required")
    total = left + right
    shift = max(0, total.bit_length() - 24)
    if shift:
        significand, remainder = divmod(total, 1 << shift)
        halfway = 1 << (shift - 1)
        if remainder > halfway or (remainder == halfway and significand & 1):
            significand += 1
        total = significand << shift
    if total >= 1 << 277:
        raise ValueError("finite binary32 range exceeded")
    return total


def bits(units: int) -> str:
    if type(units) is not int or not 0 <= units < (1 << 277):
        raise ValueError("finite nonnegative units required")
    if rounded_add(units, 0) != units:
        raise ValueError("units not exactly representable as binary32")
    if units < 1 << 23:
        return f"0x{units:08x}"
    exponent = units.bit_length() - 23
    fraction = (units >> (exponent - 1)) - (1 << 23)
    return f"0x{(exponent << 23) | fraction:08x}"


def model(width: int) -> dict:
    if type(width) is not int or width not in (32, 64):
        raise ValueError("this diagnostic is fixed to width32/64")
    offsets = [width >> i for i in range(1, width.bit_length())]
    return {"block_threads": 256, "width": width, "offsets": offsets,
            "second_offsets": offsets.copy(), "writer_lane": 0,
            "shared_slots": 256 // width, "barrier": True, "load_offset": 0}


def evaluate(inputs: list[int], route: dict) -> list[int]:
    if not isinstance(route, dict) or route != model(route.get("width")):
        raise ValueError("only the explicit fixed witness routes are supported")
    if len(inputs) != 256:
        raise ValueError("256 explicit block inputs required")
    for value in inputs:
        bits(value)
    width = route["width"]

    def stages(values, offsets):
        for offset in offsets:
            previous = values
            values = [rounded_add(previous[t], previous[t // width * width + ((t % width) ^ offset)])
                      for t in range(256)]
        return values

    local = stages(inputs, route["offsets"])
    partials = [local[group * width + route["writer_lane"]] for group in range(256 // width)]
    seeds = [partials[t % width] if t % width < len(partials) else 0 for t in range(256)]
    return stages(seeds, route["second_offsets"])


def witness() -> dict:
    source, target = model(32), model(64)
    # ncols=34: every participating thread has at most one input, so each
    # nonzero local square is exact even if zero + x*x uses contraction.
    leaves = [0] * 256
    leaves[0] = 1 << 149                 # 1**2
    leaves[1] = leaves[33] = 1 << 125    # (2**-12)**2
    left, right = evaluate(leaves, source), evaluate(leaves, target)
    return {
        "schema_version": "block-route-rounding-witness/v1",
        "scope": "explicit_models_exact_integer_simulation_of_finite_nonnegative_RNE32_adds",
        "source_model": source, "target_model": target,
        "route_comparison": compare(source, target),
        "input": {"nrows": 1, "ncols": 34, "epsilon": "1e-5",
                  "nonzero_x": {"0": "1", "1": "2^-12", "33": "2^-12"},
                  "other_x": "positive_zero", "stride": 256},
        "nonzero_leaf_bits": {str(t): bits(value) for t, value in enumerate(leaves) if value},
        "source_output_bits": [bits(value) for value in left],
        "target_output_bits": [bits(value) for value in right],
        "different_threads": [t for t in range(256) if left[t] != right[t]],
        "units_scale": "2^-149",
        "source_thread0_units": str(left[0]), "target_thread0_units": str(right[0]),
        "source_program_checked": False, "deployable": False,
        "GPU_executed": False, "numeric_tolerance_violation_established": False,
        "limitations": ["explicit model inputs, not fresh source recovery",
                        "actual shuffle/synchronization/FP semantics remain external",
                        "reduction totals only; no rsqrt or final output evaluated",
                        "one witness is not a domain-wide numerical error bound"],
    }


if __name__ == "__main__":
    print(json.dumps(witness(), indent=2))
