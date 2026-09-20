"""Exact coverage of same-stride arithmetic progressions, without column expansion."""

import hashlib
import json


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
        report["interval_checked"] = {"lower": lower, "upper": upper}
        report["threads_checked"] = upper_check.get("threads_checked")
    elif report["status"] == "rejected":
        report["counterexample"] = {
            "columns": upper, "upper_counterexample": upper_check.get("counterexample")}
    return report
