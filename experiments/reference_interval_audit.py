"""Audit stored RMSNorm reference bytes, not a re-execution of Python/libm or GPU.

Connects exact ideal-output intervals to fresh conditional route-model bounds on
the specific stored inputs. Never changes the frozen reference or tolerances.
"""
import argparse
from fractions import Fraction as F
import hashlib
import json
import math
from pathlib import Path
import struct

from experiments.reduction_rounding_witness import model
from wavebridge.verification.rmsnorm_roundoff import compare, ideal_intervals

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "benchmarks/cases/llama-rmsnorm/protocol.json"


def ratio(value):
    return {"numerator": str(value.numerator), "denominator": str(value.denominator)}


def fraction(value):
    return F(int(value["numerator"]), int(value["denominator"]))


def margin(interval, reference, coefficient, allowance, atol, rtol):
    """Exact triangle bound, not evidence that a GPU satisfies coefficient/allowance."""
    lo, hi = interval
    ref_error = max(abs(reference-lo), abs(reference-hi))
    ideal_abs = max(abs(lo), abs(hi))
    bound = coefficient*ideal_abs+allowance+ref_error
    tolerance = atol+rtol*abs(reference)
    return tolerance-bound, ref_error


def audit(directory):
    directory = Path(directory)
    raw_report = (directory / "report.json").read_bytes()
    stored = json.loads(raw_report)
    snapshots = {}
    hashes = {}
    for name, key in (("input.f32", "input_sha256"), ("expected.f32", "expected_sha256"),
                      ("protocol.json", "protocol_sha256"), ("reference.py", "reference_sha256")):
        raw = (directory/name).read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if digest != stored.get(key):
            raise ValueError("stored artifact hash mismatch: " + name)
        snapshots[name], hashes[name] = raw, digest
    if snapshots["protocol.json"] != PROTOCOL.read_bytes():
        raise ValueError("not the repository frozen numeric protocol")
    nrows, ncols, epsilon = stored.get("nrows"), stored.get("ncols"), stored.get("epsilon")
    if (type(nrows) is not int or not 1 <= nrows <= 8 or type(ncols) is not int or
            not 1 <= ncols <= 1023 or type(epsilon) is not float or epsilon != 1.0e-5):
        raise ValueError("unsupported stored shape or fixed baseline epsilon")
    count = nrows*ncols
    arrays = []
    for name in ("input.f32", "expected.f32"):
        if len(snapshots[name]) != count*4:
            raise ValueError("stored array shape mismatch: " + name)
        values = struct.unpack(f"<{count}f", snapshots[name])
        if not all(math.isfinite(v) for v in values):
            raise ValueError("nonfinite stored array: " + name)
        arrays.append([F.from_float(v) for v in values])
    inputs, expected = arrays
    if any(abs(v) > 2 for v in inputs):
        raise ValueError("input outside frozen magnitude domain")
    limits = json.loads(snapshots["protocol.json"])["comparison"]
    atol, rtol = (F.from_float(limits[key]) for key in ("absolute_tolerance", "relative_tolerance"))
    ideal_epsilon = F.from_float(epsilon)
    device_epsilon = F.from_float(struct.unpack("<f", struct.pack("<f", epsilon))[0])
    bounds = {}
    for mode in ("fma", "separate"):
        bounds[mode] = compare(model(32), model(64), ncols=ncols, input_abs_bound=F(2),
                               source_accumulation=mode, target_accumulation=mode,
                               ideal_epsilon=ideal_epsilon, source_epsilon=device_epsilon,
                               target_epsilon=device_epsilon,
                               source_rsqrt_relative_error=F(1, 1 << 22),
                               target_rsqrt_relative_error=F(1, 1 << 22))
        if bounds[mode]["status"] != "checked":
            raise ValueError("conditional output bound unavailable")
    rows, all_fit = [], True
    for r in range(nrows):
        values, refs = inputs[r*ncols:(r+1)*ncols], expected[r*ncols:(r+1)*ncols]
        oracle = ideal_intervals(values, epsilon=ideal_epsilon)
        sides = {}
        max_error = F(0)
        for mode, result in bounds.items():
            for side, width in (("source", 32), ("target", 64)):
                coeff = fraction(result["sides"][side]["relative_coefficient"])
                allowance = fraction(result["sides"][side]["absolute_allowance"])
                margins = []
                for interval, ref in zip(oracle["outputs"], refs):
                    gap, ref_error = margin(interval, ref, coeff, allowance, atol, rtol)
                    margins.append(gap)
                    max_error = max(max_error, ref_error)
                worst = min(range(ncols), key=margins.__getitem__)
                passed = margins[worst] >= 0
                all_fit = all_fit and passed
                sides[f"{mode}_width{width}"] = {
                    "all_pointwise_bounds_fit": passed, "minimum_margin": ratio(margins[worst]),
                    "worst_column": worst, "points_checked": ncols}
        rows.append({"row": r, "ideal_denominator": ratio(oracle["denominator"]),
                     "ideal_scale_interval": [ratio(v) for v in oracle["scale_interval"]],
                     "stored_reference_max_absolute_error_upper_bound": ratio(max_error),
                     "conditional_model_tolerance": sides})
    return {
        "schema_version": "rmsnorm-stored-reference-interval-audit/v1",
        "status": "checked" if all_fit else "unknown",
        "reason": "all_conditional_pointwise_bounds_fit" if all_fit else "bound_not_sufficient",
        "scope": "stored_input_points_conditional_model_exact_arithmetic_tolerance",
        "stored_report_sha256": hashlib.sha256(raw_report).hexdigest(),
        "artifacts": hashes, "implementation_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "shape": [nrows, ncols], "stored_points": count, "interval_precision_bits": 192,
        "ideal_epsilon": ratio(ideal_epsilon), "device_epsilon_assumption": ratio(device_epsilon),
        "tolerance": {"atol": ratio(atol), "rtol": ratio(rtol)},
        "conditional_output_bounds": bounds, "rows": rows,
        "reference_algorithm_reexecuted": False, "reference_algorithm_domain_wide_verified": False,
        "host_comparator_rounding_verified": False, "actual_fp_laws_verified": False,
        "source_program_checked": False, "numeric_contract_checked": False,
        "GPU_executed": False, "deployable": False,
        "remaining_obligations": ["all_actual_source_compiler_runtime_and_FP_model_premises",
                                  "other_inputs_and_reference_algorithm_domain_wide_error",
                                  "actual_host_comparator_rounding_semantics"],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_directory", type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.run_directory), indent=2))
