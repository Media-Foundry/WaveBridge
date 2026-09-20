"""Bind prefix loop obligations to finite recurrence bounds, not reachability."""

from wavebridge.column_domain_check import check as check_columns
from wavebridge.analysis.reduction_chain import recover as recover_chain


def check(root, thread_report, integer_types, binding, *, use_host_guard_assumptions=False):
    result = {
        "schema_version": "conditional-entry-loop-check/v1", "status": "unknown", "reason": None,
        "source_program_checked": False, "deployable": False, "participation": "not_established",
        "scope": "finite_iteration_bounds_for_entry_prefix_column_recurrences_only",
        "loops": [], "remaining_call_obligations": [],
        "premises": ["all premises of the fresh column-domain check remain required",
                     "entry-control and column recovery faithfully describe the same valid AST",
                     "each loop-body execution completes normally"],
        "limitations": ["does not prove loop-body completion, prefix call return or first helper reachability",
                        "does not discharge memory validity, collective convergence or synchronization"],
    }

    def unknown(reason):
        result["reason"] = reason
        return result

    columns = check_columns(root, thread_report, integer_types, binding,
                            use_host_guard_assumptions=use_host_guard_assumptions)
    result["columns"] = columns
    result["input_sha256"] = columns.get("input_sha256")
    if columns.get("status") != "checked":
        result.update(status=columns.get("status", "unknown"), reason="column_domains_not_checked")
        return result
    kernel = thread_report.get("kernel_declaration_id")
    chain = recover_chain(root, kernel, thread_report.get("int_bits"))
    result["chain_recovery"] = chain
    if chain.get("status") != "recovered" or chain.get("function_id") != kernel:
        return unknown("fresh_chain_not_recovered")
    entry, edges = chain.get("entry_control"), chain.get("links")
    if (not isinstance(entry, dict) or entry.get("schema_version") != "entry-control-obligations/v1" or
            entry.get("status") != "recovered" or entry.get("function_id") != kernel or
            not isinstance(edges, list) or not edges or not isinstance(edges[0], dict) or
            edges[0].get("caller_id") != kernel or entry.get("callee_id") != edges[0].get("callee_id") or
            entry.get("call_range") != edges[0].get("call_range")):
        return unknown("entry_control_not_recovered_or_bound")
    obligations = entry.get("loop_obligations")
    if not isinstance(obligations, list) or not obligations:
        return unknown("no_prefix_loop_obligations")
    calls = entry.get("call_obligations")
    if not isinstance(calls, list):
        return unknown("entry_call_obligations_missing")
    result["remaining_call_obligations"] = calls
    seen = []
    for obligation in obligations:
        location = obligation.get("range") if isinstance(obligation, dict) else None
        if not isinstance(location, dict) or not location or location in seen:
            return unknown("prefix_loop_location_missing_or_duplicate")
        seen.append(location)
        matches = [item for item in columns.get("loops", []) if item.get("loop_range") == location]
        if len(matches) != 1:
            return unknown("prefix_loop_domain_not_unique")
        coverage = matches[0].get("coverage")
        if (not isinstance(coverage, dict) or coverage.get("schema_version") != "column-coverage-interval/v1" or
                coverage.get("status") != "checked"):
            return unknown("prefix_loop_coverage_not_checked")
        counts = coverage.get("max_iterations_per_thread")
        maximum = coverage.get("max_iterations")
        if (not isinstance(counts, list) or not counts or
                any(type(count) is not int or count < 0 for count in counts) or
                type(maximum) is not int or maximum != max(counts) or
                len(counts) != coverage.get("threads_checked")):
            return unknown("prefix_loop_iteration_bounds_missing")
        result["loops"].append({"range": location,
                                "column_interval": coverage.get("interval_checked"),
                                "max_iterations_per_thread": counts, "max_iterations": maximum,
                                "overflow_check": "checked_for_final_increment",
                                "body_normal_completion": "not_established"})
    result.update(status="checked", kernel_declaration_id=kernel,
                  helper_declaration_id=entry["callee_id"],
                  conclusion="prefix_recurrences_have_finite_iteration_bounds_under_stated_premises")
    return result
