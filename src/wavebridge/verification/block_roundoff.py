"""Conditional forward-error bounds for explicit nonnegative block-route models.

Exact rational arithmetic; no source/IEEE/runtime equivalence is certified.
See PROOF_PACKAGE.md for the local error law and induction used here.
"""
from fractions import Fraction

from wavebridge.verification import block_routes

U = Fraction(1, 1 << 24)
ETA = Fraction(1, 1 << 150)
MAX_FINITE = Fraction(((1 << 24) - 1) << 104)


def _ratio(value):
    return {"numerator": str(value.numerator), "denominator": str(value.denominator)}


def _bounds(model, leaf_upper):
    # State = (longest addition path, propagated absolute rounding allowance,
    #          upper bound on the computed nonnegative value).
    block, width = model["block_threads"], model["width"]
    additions = 0

    def stages(lanes, offsets):
        nonlocal additions
        for offset in offsets:
            previous = lanes
            lanes = []
            for t in range(block):
                a = previous[t]
                b = previous[t // width * width + ((t % width) ^ offset)]
                upper = (1 + U) * (a[2] + b[2]) + ETA
                # This stronger sufficient condition also bounds the exact
                # sum of already-rounded child values by MAX_FINITE.
                if upper > MAX_FINITE:
                    raise ValueError("finite_intermediate_bound_not_established")
                lanes.append((max(a[0], b[0]) + 1,
                              (1 + U) * (a[1] + b[1]) + ETA, upper))
                additions += 1
        return lanes

    lanes = stages([(0, Fraction(0), leaf_upper)] * block, model["offsets"])
    groups = block // width
    shared = [lanes[g * width + model["writer_lane"]] for g in range(groups)]
    seeds = [shared[t % width + model["load_offset"]] if t % width < groups
             else (0, Fraction(0), Fraction(0)) for t in range(block)]
    outputs = stages(seeds, model["second_offsets"])
    depth = max(item[0] for item in outputs)
    additive = max(item[1] for item in outputs)
    relative = (1 + U) ** depth - 1
    return {"max_addition_depth": depth, "addition_instances": additions,
            "relative_coefficient": _ratio(relative), "absolute_allowance": _ratio(additive),
            "computed_output_upper_bound": _ratio(max(item[2] for item in outputs)),
            "absolute_error_upper_bound": _ratio(relative * block * leaf_upper + additive)}, relative, additive


def compare(source, target, *, leaf_upper_bound):
    """Bound route outputs assuming common exact leaves in [0, leaf_upper_bound].

    The caller must supply a Fraction; its applicability to recovered local
    accumulators is NOT inferred. Local rounding obeys the explicit law in the
    report. This does not evaluate or accept any external atol/rtol protocol.
    """
    result = {
        "schema_version": "block-route-roundoff/v1", "status": "unknown", "reason": None,
        "scope": "conditional_explicit_route_nonnegative_leaf_forward_error",
        "source_program_checked": False, "deployable": False,
        "external_fp_model_verified": False, "numeric_contract_checked": False,
        "leaf_bound_established_from_source": False, "sides": {},
        "assumptions": [
            "same exact nonnegative input value at each block-local thread on both sides",
            "each input value is at most the explicitly supplied leaf_upper_bound",
            "nonnegative computed additions obey abs(fl(a+b)-(a+b)) <= u*(a+b)+eta",
            "the local error law applies whenever the finite bound is established",
            "all route participation, snapshot, shared visibility and zero-seed premises hold",
        ],
        "u": _ratio(U), "eta": _ratio(ETA), "max_finite": _ratio(MAX_FINITE),
        "remaining_obligations": ["actual_local_accumulator_value_and_bound",
                                  "actual_FP_and_intrinsic_semantics",
                                  "source_to_route_correspondence",
                                  "division_rsqrt_final_multiply_and_frozen_output_tolerance"],
    }
    if (type(leaf_upper_bound) is not Fraction or leaf_upper_bound < 0 or
            leaf_upper_bound > MAX_FINITE or
            max(leaf_upper_bound.numerator.bit_length(),
                leaf_upper_bound.denominator.bit_length()) > 4096):
        result["reason"] = "bounded_nonnegative_fraction_leaf_limit_required"
        return result
    result["leaf_upper_bound"] = _ratio(leaf_upper_bound)
    routes = block_routes.compare(source, target)
    result["route_comparison"] = routes
    if routes["status"] != "evidence":
        result.update(status=routes["status"], reason="route_comparison_not_established")
        return result
    try:
        left, ls, la = _bounds(source, leaf_upper_bound)
        right, rs, ra = _bounds(target, leaf_upper_bound)
    except ValueError as error:
        result["reason"] = str(error)
        return result
    result["sides"] = {"source": left, "target": right}
    result["difference_bound"] = {
        "formula": "abs(source_output-target_output) <= relative_coefficient*S + absolute_allowance",
        "S": "sum_of_common_exact_nonnegative_block_input_leaves",
        "relative_coefficient": _ratio(ls + rs), "absolute_allowance": _ratio(la + ra),
        "S_upper_bound": _ratio(source["block_threads"] * leaf_upper_bound),
        "absolute_upper_bound": _ratio((ls + rs) * source["block_threads"] * leaf_upper_bound + la + ra),
    }
    result.update(status="checked", reason="conditional_model_forward_error_bound")
    return result
