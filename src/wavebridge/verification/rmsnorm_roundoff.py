"""Conditional RMSNorm output error relative to an ideal real-valued reference.

Requires explicit rsqrt error bounds. Never infers SDK guarantees or validates
the frozen numerical reference implementation. All decisions use Fraction.
"""
from fractions import Fraction
from math import isqrt

from wavebridge.verification import block_roundoff

U, ETA, MAX_FINITE = block_roundoff.U, block_roundoff.ETA, block_roundoff.MAX_FINITE


def _binary32(value):
    if type(value) is not Fraction or abs(value) > MAX_FINITE:
        return False
    units = abs(value) * (1 << 149)
    if units.denominator != 1:
        return False
    shift = max(0, units.numerator.bit_length() - 24)
    return units.numerator % (1 << shift) == 0


def ideal_intervals(values, *, epsilon, precision_bits=192):
    """Enclose ideal real outputs for one concrete finite binary32 input row.

    Uses exact rationals and integer sqrt only, not the stored FP reference or
    any GPU model. Returned Fractions are bounds, not rounded output predictions.
    Signs of zero are intentionally not modeled. Unsupported inputs raise.
    """
    if (not isinstance(values, (list, tuple)) or not 1 <= len(values) <= 4096 or
            not all(_binary32(value) for value in values) or
            not _supported(epsilon, positive=True) or type(precision_bits) is not int or
            not 16 <= precision_bits <= 1024):
        raise ValueError("finite binary32 row, positive exact epsilon and bounded precision required")
    denominator = sum((value * value for value in values), Fraction(0)) / len(values) + epsilon
    grid = 1 << precision_bits
    numerator = denominator.denominator * grid * grid
    root = isqrt(numerator // denominator.numerator)
    lo = Fraction(root, grid)
    hi = lo if root * root * denominator.numerator == numerator else Fraction(root + 1, grid)
    outputs = [(min(value * lo, value * hi), max(value * lo, value * hi)) for value in values]
    return {"denominator": denominator, "scale_interval": (lo, hi), "outputs": outputs}


def _ratio(value):
    return {"numerator": str(value.numerator), "denominator": str(value.denominator)}


def _value(ratio):
    return Fraction(int(ratio["numerator"]), int(ratio["denominator"]))


def _supported(value, positive=False):
    return (type(value) is Fraction and (value > 0 if positive else value >= 0) and
            value <= MAX_FINITE and
            max(value.numerator.bit_length(), value.denominator.bit_length()) <= 4096)


def compare(source, target, *, ncols, input_abs_bound, source_accumulation,
            target_accumulation, ideal_epsilon, source_epsilon, target_epsilon,
            source_rsqrt_relative_error, target_rsqrt_relative_error):
    """Fresh local+route bounds, then division, epsilon, rsqrt and final multiply.

    The reference is x/sqrt(sum(x*x)/ncols+ideal_epsilon) over exact reals.
    Integer-to-divisor conversion is assumed exact; the modeled suffix is a
    rounded division followed by a rounded addition, not reassociated code.
    """
    report = {
        "schema_version": "rmsnorm-ideal-output-roundoff/v1", "status": "unknown", "reason": None,
        "scope": "conditional_error_to_ideal_real_RMSNorm_output", "sides": {},
        "source_program_checked": False, "deployable": False,
        "external_fp_model_verified": False, "rsqrt_contract_verified": False,
        "frozen_reference_implementation_checked": False, "numeric_contract_checked": False,
        "assumptions": [
            "all fresh sum-squares model premises hold",
            "ncols converts exactly to the positive divisor on both sides",
            "suffix is rounded total/ncols then rounded +epsilon then rsqrt then rounded x*scale",
            "division/addition obey abs(fl(z)-z)<=u*abs(z)+eta and return nonnegative values",
            "supplied epsilon values are the actual exact stored values",
            "on each reported positive input interval rsqrt has supplied relative error rho",
            "final signed multiplication obeys abs(fl(z)-z)<=u*abs(z)+eta",
            "operation error laws apply within the established finite bounds",
        ],
        "remaining_obligations": ["actual_source_and_compiler_suffix_correspondence",
                                  "actual_division_rsqrt_and_multiply_error_guarantees",
                                  "frozen_reference_rounding_error_and_tolerance_acceptance",
                                  "runtime_and_target_execution_validation"],
    }
    if (not all(_supported(v, positive=True) for v in
                (ideal_epsilon, source_epsilon, target_epsilon)) or
            not all(_supported(v) and v < 1 for v in
                    (source_rsqrt_relative_error, target_rsqrt_relative_error))):
        report["reason"] = "explicit_positive_epsilons_and_rsqrt_error_fractions_required"
        return report
    sums = block_roundoff.compare_sum_squares(
        source, target, ncols=ncols, input_abs_bound=input_abs_bound,
        source_accumulation=source_accumulation, target_accumulation=target_accumulation)
    report["sum_squares_check"] = sums
    if sums["status"] != "checked":
        report.update(status=sums["status"], reason="sum_squares_bound_not_established")
        return report
    report["ideal_epsilon"] = _ratio(ideal_epsilon)
    ideal_scale_upper = max(Fraction(1), 1 / ideal_epsilon)
    coefficient_sum = Fraction(0)
    for side, epsilon, rho in (("source", source_epsilon, source_rsqrt_relative_error),
                               ("target", target_epsilon, target_rsqrt_relative_error)):
        total = sums["sides"][side]
        a, b = _value(total["relative_coefficient"]), _value(total["absolute_allowance"])
        total_upper = _value(total["route_bound"]["computed_output_upper_bound"])
        division_upper = (1 + U) * total_upper / ncols + ETA
        argument_upper = (1 + U) * (division_upper + epsilon) + ETA
        if max(division_upper, argument_upper) > MAX_FINITE:
            report["reason"] = side + "_finite_division_or_addition_bound_not_established"
            return report
        a_argument = (1 + U) ** 2 * (1 + a) - 1
        b_argument = ((1 + U) ** 2 * b / ncols + (2 + U) * ETA +
                      U * epsilon + abs(epsilon - ideal_epsilon))
        delta = max(a_argument, b_argument / ideal_epsilon)
        if delta >= 1:
            report["reason"] = side + "_positive_rsqrt_argument_not_established"
            return report
        h = delta / (2 * (1 - delta))
        scale_upper = (1 + rho) * (1 + h) * ideal_scale_upper
        output_upper = (1 + U) * input_abs_bound * scale_upper + ETA
        if max(scale_upper, output_upper) > MAX_FINITE:
            report["reason"] = side + "_finite_scale_or_output_bound_not_established"
            return report
        coefficient = (1 + U) * (1 + h) * (1 + rho) - 1
        report["sides"][side] = {
            "stored_epsilon": _ratio(epsilon), "rsqrt_relative_error_assumption": _ratio(rho),
            "argument_relative_error_bound": _ratio(delta),
            "rsqrt_input_interval": {"lower": _ratio((1 - delta) * ideal_epsilon),
                                     "upper": _ratio(argument_upper)},
            "ideal_rsqrt_perturbation_bound": _ratio(h),
            "computed_scale_upper_bound": _ratio(scale_upper),
            "computed_output_abs_upper_bound": _ratio(output_upper),
            "relative_coefficient": _ratio(coefficient), "absolute_allowance": _ratio(ETA),
        }
        coefficient_sum += coefficient
    report["difference_bound"] = {
        "formula": "abs(source_output-target_output) <= relative_coefficient*abs(y_ideal) + absolute_allowance",
        "ideal_reference": "x/sqrt(exact_sum_of_squares/ncols+ideal_epsilon)",
        "relative_coefficient": _ratio(coefficient_sum), "absolute_allowance": _ratio(2 * ETA),
    }
    report.update(status="checked", reason="conditional_error_to_ideal_real_output")
    return report
