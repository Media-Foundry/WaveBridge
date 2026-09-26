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


def _local_squares(terms, magnitude, mode):
    upper = allowance = Fraction(0)
    square = magnitude * magnitude
    product_upper = (1 + U) * square + ETA if mode == "separate" else square
    if terms and product_upper > MAX_FINITE:
        raise ValueError("finite_local_product_bound_not_established")
    for _ in range(terms):
        upper = (1 + U) * (upper + product_upper) + ETA
        allowance = (1 + U) * (allowance + (ETA if mode == "separate" else 0)) + ETA
        if upper > MAX_FINITE:
            raise ValueError("finite_local_accumulator_bound_not_established")
    depth = terms + (1 if mode == "separate" and terms else 0)
    return (1 + U) ** depth - 1, allowance, upper


def compare_sum_squares(source, target, *, ncols, input_abs_bound,
                        source_accumulation, target_accumulation):
    """Compose cyclic-column local square accumulation with each route's error.

    Common row inputs are assumed, but computed local leaves need NOT be equal.
    Accumulation mode is explicit ('fma' or 'separate'), not inferred from AST.
    Only zero-seeded columns t+k*block are modeled. No normalization suffix.
    """
    result = {
        "schema_version": "block-sum-squares-roundoff/v1", "status": "unknown", "reason": None,
        "scope": "conditional_cyclic_columns_local_squares_and_block_reduction",
        "source_program_checked": False, "deployable": False,
        "external_fp_model_verified": False, "numeric_contract_checked": False,
        "source_to_model_correspondence_established": False, "sides": {},
        "u": _ratio(U), "eta": _ratio(ETA), "max_local_iterations": 64,
        "assumptions": [
            "both sides read the same immutable row x with abs(x[j]) <= input_abs_bound",
            "thread t traverses exactly columns t+k*block < ncols with zero accumulator",
            "explicit accumulation modes follow the local error laws in PROOF_PACKAGE.md",
            "all computed square, accumulator and route values are nonnegative",
            "each operation obeys its local error law when the finite bound is established",
            "all route participation, snapshot and shared-memory premises hold",
        ],
        "remaining_obligations": ["actual_source_index_and_value_correspondence",
                                  "actual_compiler_accumulation_and_FP_semantics",
                                  "division_epsilon_rsqrt_output_multiply_and_frozen_tolerance"],
    }
    if (type(ncols) is not int or ncols < 1 or type(input_abs_bound) is not Fraction or
            input_abs_bound < 0 or input_abs_bound > MAX_FINITE or
            max(input_abs_bound.numerator.bit_length(), input_abs_bound.denominator.bit_length()) > 4096 or
            source_accumulation not in ("fma", "separate") or target_accumulation not in ("fma", "separate")):
        result["reason"] = "unsupported_explicit_domain_or_accumulation_mode"
        return result
    routes = block_routes.compare(source, target)
    # Retain only the independently rechecked per-side route premises, not the
    # comparison's unused common-computed-leaf assumption or ordered DAG claim.
    result["route_checks"] = routes.get("checks", {})
    result["route_structure_status"] = routes["status"]
    result["route_structure_reason"] = routes["reason"]
    result["common_computed_leaf_values_assumed"] = False
    if routes["status"] != "evidence":
        result.update(status=routes["status"], reason="route_comparison_not_established")
        return result
    block = source["block_threads"]
    maximum_terms = (ncols + block - 1) // block
    if maximum_terms > 64:
        result["reason"] = "local_iteration_budget_exceeded"
        return result
    counts = [max(0, (ncols - 1 - t) // block + 1) for t in range(block)]
    result["domain"] = {"ncols": ncols, "block_threads": block,
                        "column_stride": block, "input_abs_bound": _ratio(input_abs_bound),
                        "iteration_counts": counts}
    q_upper = ncols * input_abs_bound * input_abs_bound
    total_coefficient = total_allowance = Fraction(0)
    try:
        for side, route, mode in (("source", source, source_accumulation),
                                  ("target", target, target_accumulation)):
            states = {k: _local_squares(k, input_abs_bound, mode) for k in set(counts)}
            local_r = max(states[k][0] for k in counts)
            local_a = sum((states[k][1] for k in counts), Fraction(0))
            leaf_upper = max(states[k][2] for k in counts)
            routing, route_r, route_a = _bounds(route, leaf_upper)
            coefficient = local_r + route_r * (1 + local_r)
            allowance = (1 + route_r) * local_a + route_a
            result["sides"][side] = {
                "accumulation": mode, "max_local_iterations": maximum_terms,
                "local_relative_coefficient": _ratio(local_r),
                "local_sum_absolute_allowance": _ratio(local_a),
                "computed_leaf_upper_bound": _ratio(leaf_upper), "route_bound": routing,
                "relative_coefficient": _ratio(coefficient), "absolute_allowance": _ratio(allowance),
                "absolute_error_upper_bound": _ratio(coefficient * q_upper + allowance),
            }
            total_coefficient += coefficient
            total_allowance += allowance
    except ValueError as error:
        result["reason"] = str(error)
        return result
    result["difference_bound"] = {
        "formula": "abs(source_total-target_total) <= relative_coefficient*Q + absolute_allowance",
        "Q": "exact_sum_of_squares_of_common_row_inputs",
        "Q_upper_bound": _ratio(q_upper), "relative_coefficient": _ratio(total_coefficient),
        "absolute_allowance": _ratio(total_allowance),
        "absolute_upper_bound": _ratio(total_coefficient * q_upper + total_allowance),
    }
    result.update(status="checked", reason="conditional_local_and_route_error_composed")
    return result
