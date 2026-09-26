"""Conditional normal-input audit for the frozen RMSNorm domain, no GPU.

Explicit route models, not machine-code validation. The interval construction
does not assume any rsqrt accuracy, so it can qualify the ISA accuracy premise
without circularly using that premise to establish its own input domain.
"""
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import sys

from experiments.reduction_rounding_witness import model
from wavebridge.verification.block_roundoff import compare_sum_squares, U, ETA

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "benchmarks/cases/llama-rmsnorm/protocol.json"
MIN_NORMAL = F(1, 1 << 126)


def ratio(value):
    return {"numerator": str(value.numerator), "denominator": str(value.denominator)}


def fraction(value):
    return F(int(value["numerator"]), int(value["denominator"]))


def argument_interval(ncols, mode, magnitude, epsilon_min, epsilon_max):
    """Bounds conditional on nonnegative arithmetic and the declared local laws."""
    if not (type(epsilon_min) is F and type(epsilon_max) is F and
            0 < epsilon_min <= epsilon_max):
        raise ValueError("ordered positive exact epsilon limits required")
    sums = compare_sum_squares(model(32), model(64), ncols=ncols,
                              input_abs_bound=magnitude,
                              source_accumulation=mode, target_accumulation=mode)
    if sums["status"] != "checked":
        raise ValueError("sum-squares model bound unavailable: " + str(sums["reason"]))
    # Treat epsilon conversion as a separate explicit RNE32-like local law.
    stored_min = (1-U)*epsilon_min-ETA
    stored_max = (1+U)*epsilon_max+ETA
    lower = (1-U)*stored_min-ETA
    result = {}
    for side, width in (("source", 32), ("target", 64)):
        total = sums["sides"][side]
        qmax = ncols*magnitude*magnitude
        total_max = qmax + fraction(total["absolute_error_upper_bound"])
        upper = (1+U)*((1+U)*total_max/ncols+ETA+stored_max)+ETA
        result[width] = (lower, upper)
    return result


def audit():
    raw = PROTOCOL.read_bytes()
    protocol = json.loads(raw)
    limits = protocol["input"]
    # Bind the actual Python JSON boundary values used by reference.validate.
    emin = F.from_float(limits["epsilon"]["minimum"])
    emax = F.from_float(limits["epsilon"]["maximum"])
    magnitude = F.from_float(limits["absolute_value_maximum"])
    domain = range(limits["ncols"]["minimum"], limits["ncols"]["maximum_exclusive"])
    lower = upper = None
    count = 0
    for n in domain:
        for mode in ("fma", "separate"):
            for width, (lo, hi) in argument_interval(n, mode, magnitude, emin, emax).items():
                count += 1
                lower = lo if lower is None else min(lower, lo)
                if upper is None or hi > upper:
                    upper, witness = hi, {"ncols": n, "mode": mode, "width": width}
        if n % 128 == 0:
            print(f"audited ncols through {n}", file=sys.stderr, flush=True)
    if lower is None:
        raise ValueError("empty ncols domain")
    # Strong simple interval also places exact rsqrt in [1/4, 1024].
    normal = lower >= MIN_NORMAL and upper <= 16 and lower >= F(1, 1 << 20)
    return {
        "schema_version": "rmsnorm-rsqrt-domain-audit/v1",
        "status": "checked" if normal else "unknown",
        "scope": "conditional_explicit_models_normal_rsqrt_input_and_result_range",
        "protocol_sha256": hashlib.sha256(raw).hexdigest(),
        "implementation_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "ncols": {"minimum": domain.start, "maximum_exclusive": domain.stop},
        "model_configurations_checked": count,
        "modes": ["fma", "separate"], "logical_widths": [32, 64],
        "epsilon_before_conversion": {"lower": ratio(emin), "upper": ratio(emax)},
        "rsqrt_argument_interval": {"lower": ratio(lower), "upper": ratio(upper)},
        "upper_bound_attained_in_audit_at": witness,
        "exact_rsqrt_enclosure_if_checked": ["1/4", "1024"],
        "rsqrt_accuracy_used_to_establish_interval": False,
        "rsqrt_contract_verified": False, "source_program_checked": False,
        "numeric_contract_checked": False, "GPU_executed": False, "deployable": False,
        "assumptions": ["explicit cyclic allocation and route model correspondence",
                        "all fresh sum-squares model local arithmetic laws",
                        "nonnegative division/addition obey u=2^-24, eta=2^-150 local law",
                        "positive ncols is exactly converted",
                        "epsilon conversion obeys same local law and uses protocol limits"],
        "remaining_obligations": ["actual_binary_and_runtime_correspondence",
                                  "documented_ISA_error_contract_applies_to_executing_device",
                                  "actual_division_and_other_arithmetic_error_laws",
                                  "frozen_reference_rounding_and_tolerance"],
    }


if __name__ == "__main__":
    print(json.dumps(audit(), indent=2))
