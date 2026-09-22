"""Exact coverage of same-stride arithmetic progressions, without column expansion."""

import hashlib
import json

from wavebridge.verification.integer_conversion import check_interval as check_conversion


def check(columns, starts, stride, *, int_bits=32):
    report = {
        "schema_version": "column-coverage/v1", "status": "unknown", "reason": None,
        "checker": "residue-intervals/v1", "columns": columns, "starts": starts,
        "stride": stride, "int_bits": int_bits, "max_threads": 1024,
        "scope": "same_positive_stride_signed_integer_column_coverage",
        "source_program_checked": False, "deployable": False,
        "assumptions": ["each participating thread uses the supplied start value",
                        "all threads evaluate i < columns and update i += stride",
                        "each iteration contributes exactly once to its column"],
        "floating_point_equivalence": "not_checked",
    }
    if (type(int_bits) is not int or not 2 <= int_bits <= 128 or
            type(columns) is not int or type(stride) is not int or
            not isinstance(starts, list) or not 1 <= len(starts) <= 1024 or
            any(type(start) is not int for start in starts)):
        report["reason"] = "unsupported_input"
        return report
    maximum = (1 << (int_bits - 1)) - 1
    if not 0 <= columns <= maximum or not 1 <= stride <= maximum or any(
            not 0 <= start <= maximum for start in starts):
        report["reason"] = "unsupported_signed_domain"
        return report
    report["input_sha256"] = hashlib.sha256(json.dumps(
        {"columns": columns, "starts": starts, "stride": stride, "int_bits": int_bits},
        sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    # The last loop-body iteration is followed by an increment, even when the
    # next condition is false. Check it rather than assuming no overflow.
    for thread, start in enumerate(starts):
        if start < columns:
            last = start + ((columns - 1 - start) // stride) * stride
            if last + stride > maximum:
                report.update(reason="signed_increment_overflow",
                              counterexample={"thread": thread, "last_column": last})
                return report
    residues = {}
    for thread, start in enumerate(starts):
        if start >= columns:
            continue
        residue = start % stride
        if residue in residues:
            previous = residues[residue]
            report.update(status="rejected", reason="duplicate_column",
                          counterexample={"column": max(start, previous[1]),
                                          "threads": [previous[0], thread]})
            return report
        residues[residue] = (thread, start)
    # Every required residue must begin at the first nonnegative representative.
    # At most len(starts) keys are sorted: cost is independent of columns/stride.
    expected_residue = 0
    for residue in sorted(residues):
        if residue != expected_residue:
            report.update(status="rejected", reason="missing_column",
                          counterexample={"column": expected_residue})
            return report
        if residues[residue][1] != residue:
            report.update(status="rejected", reason="missing_column",
                          counterexample={"column": residue})
            return report
        expected_residue += 1
    if expected_residue != min(stride, columns):
        report.update(status="rejected", reason="missing_column",
                      counterexample={"column": expected_residue})
        return report
    report.update(status="checked", columns_checked=columns, threads_checked=len(starts))
    return report


def check_interval(lower, upper, starts, stride, *, int_bits=32):
    """Lift fixed-column coverage to one closed column-count interval.

    With fixed starts and stride, every thread's contributions for a smaller
    column count are a prefix of those for ``upper``.  Consequently exact
    coverage at the upper endpoint establishes exact coverage throughout the
    interval; the fixed checker also checks the post-body increment at that
    endpoint, which bounds every smaller execution.
    """
    report = {
        "schema_version": "column-coverage-interval/v1", "status": "unknown",
        "reason": None, "lower": lower, "upper": upper, "starts": starts,
        "stride": stride, "int_bits": int_bits, "upper_check": None,
        "scope": "all_column_counts_in_declared_closed_interval",
        "source_program_checked": False, "deployable": False,
        "assumptions": [
            "starts and stride are fixed for every column count in the interval",
            "each participating thread uses the supplied start value",
            "all threads evaluate i < columns and update i += stride",
            "each iteration contributes exactly once to its column",
            "signed integer behavior and the post-body increment follow the fixed-column checker",
        ],
        "method": "check_upper_endpoint_once_using_prefix_monotonicity",
    }
    if (type(lower) is not int or type(upper) is not int or
            type(int_bits) is not int or not 2 <= int_bits <= 128 or
            type(stride) is not int or not isinstance(starts, list) or
            not 1 <= len(starts) <= 1024 or any(type(start) is not int for start in starts)):
        report["reason"] = "unsupported_input"
        return report
    maximum = (1 << (int_bits - 1)) - 1
    if (not 0 <= lower <= upper <= maximum or not 1 <= stride <= maximum or
            any(not 0 <= start <= maximum for start in starts)):
        report["reason"] = "unsupported_signed_domain"
        return report
    report["input_sha256"] = hashlib.sha256(json.dumps(
        {"lower": lower, "upper": upper, "starts": starts,
         "stride": stride, "int_bits": int_bits},
        sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    upper_check = check(upper, starts, stride, int_bits=int_bits)
    report["upper_check"] = upper_check
    report["status"] = upper_check.get("status", "unknown")
    report["reason"] = upper_check.get("reason")
    if report["status"] == "checked":
        iterations = [max(0, (upper - 1 - start) // stride + 1) for start in starts]
        report["interval_checked"] = {"lower": lower, "upper": upper}
        report["threads_checked"] = upper_check.get("threads_checked")
        report["max_iterations_per_thread"] = iterations
        report["max_iterations"] = max(iterations)
    elif report["status"] == "rejected":
        report["counterexample"] = {
            "columns": upper, "upper_counterexample": upper_check.get("counterexample")}
    return report


def check_unsigned_compound_interval(lower, upper, block_threads, *,
                                     int_bits=32, unsigned_bits=32):
    """Conditionally check ``int i`` advanced by unsigned ``i += blockDim.x``.

    The caller supplies the already-bound model: starts are exactly
    ``0..block_threads-1``, the positive step and block dimension are both
    ``block_threads``, and Clang selected unsigned computation followed by an
    assignment to signed int.  This function checks that the resulting machine
    operations preserve the corresponding mathematical recurrence.  It does
    not recover those facts from source.
    """
    report = {
        "schema_version": "unsigned-compound-column-coverage/v1",
        "status": "unknown", "reason": None,
        "lower": lower, "upper": upper, "block_threads": block_threads,
        "int_bits": int_bits, "unsigned_bits": unsigned_bits,
        "starts": None, "stride": block_threads,
        "conversion_checks": [], "coverage": None,
        "scope": "conditional_column_coverage_for_unsigned_compound_assignment_model",
        "source_program_checked": False, "deployable": False,
        "assumptions": [
            "the signed int and unsigned int widths supplied here match the compilation ABI",
            "the start values are exactly local IDs 0 through block_threads minus one",
            "the positive step and runtime block x dimension both equal block_threads",
            "the loop condition is signed int induction less than the supplied signed column count",
            "the compound assignment computes in unsigned int and assigns its result back to signed int",
            "the loop body does not modify induction, column bound, or the fixed coordinate and dimension values",
            "every reached loop body and increment completes normally",
        ],
        "limitations": [
            "does not recover coordinate, launch, ABI or compute-type facts from source",
            "does not establish source equivalence, reachability, body effects or deployment safety",
            "unknown overflow evidence is not asserted to be a reachable runtime counterexample",
        ],
    }
    if (any(type(value) is not int for value in
            (lower, upper, block_threads, int_bits, unsigned_bits)) or
            not 2 <= int_bits <= 128 or not 2 <= unsigned_bits <= 128 or
            int_bits != unsigned_bits or not 1 <= block_threads <= 1024):
        report["reason"] = "unsupported_input_or_integer_abi"
        return report
    signed_maximum = (1 << (int_bits - 1)) - 1
    if not 0 <= lower <= upper <= signed_maximum:
        report["reason"] = "column_interval_not_signed_int_domain"
        return report
    starts = list(range(block_threads))
    report["starts"] = starts
    inputs = {"lower": lower, "upper": upper, "block_threads": block_threads,
              "int_bits": int_bits, "unsigned_bits": unsigned_bits}
    report["input_sha256"] = hashlib.sha256(json.dumps(
        inputs, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def conversion(stage, low, high, source_signed, target_signed):
        evidence = {"stage": stage, "value_interval": {"lower": low, "upper": high},
                    "conversion": check_conversion(low, high, int_bits, source_signed,
                                                   unsigned_bits, target_signed)}
        report["conversion_checks"].append(evidence)
        return evidence["conversion"].get("status") == "checked"

    if not conversion("initial_unsigned_local_id_to_signed_int", 0, block_threads - 1,
                      False, True):
        report["reason"] = "initial_conversion_not_value_preserving"
        return report
    if not conversion("unsigned_step_representability", block_threads, block_threads,
                      False, False):
        report["reason"] = "step_not_representable_in_unsigned_int"
        return report

    if upper > 0:
        # With starts covering every residue 0..B-1, body induction values over
        # all C <= upper are contained in [0, upper-1].  Every executed body is
        # followed by an increment, including the final one after its body.
        if not conversion("signed_induction_to_unsigned_compute_lhs", 0, upper - 1,
                          True, False):
            report["reason"] = "compute_lhs_conversion_not_value_preserving"
            return report
        post_lower, post_upper = block_threads, upper - 1 + block_threads
        # check_interval here checks representability of the mathematical sum;
        # it does not itself model or execute unsigned addition.
        if not conversion("mathematical_unsigned_sum_no_wrap", post_lower, post_upper,
                          False, False):
            report["reason"] = "unsigned_increment_may_wrap"
            return report
        if not conversion("unsigned_compound_result_to_signed_int", post_lower, post_upper,
                          False, True):
            report["reason"] = "final_assignment_not_value_preserving"
            return report

    if upper == 0:
        coverage = {
            "schema_version": "column-coverage-interval/v1",
            "status": "checked", "reason": None,
            "interval_checked": {"lower": 0, "upper": 0},
            "max_iterations_per_thread": [0] * block_threads,
            "max_iterations": 0,
            "method": "zero_column_interval_is_vacuous_after_initialization",
            "source_program_checked": False, "deployable": False,
        }
    else:
        coverage = check_interval(lower, upper, starts, block_threads, int_bits=int_bits)
    report["coverage"] = coverage
    if coverage.get("status") != "checked":
        report["reason"] = "conditional_mathematical_coverage_not_checked"
        return report
    report.update(
        status="checked", reason=None,
        interval_checked={"lower": lower, "upper": upper},
        max_iterations_per_thread=coverage["max_iterations_per_thread"],
        max_iterations=coverage["max_iterations"],
        conclusion="mathematical_recurrence_is_preserved_under_supplied_compound_assignment_model",
    )
    return report
