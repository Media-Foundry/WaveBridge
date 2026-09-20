"""Compose fresh row/column evidence with integer-only pointer offset checks."""

from wavebridge.row_coordinate_check import check as check_row
from wavebridge.thread_start_check import check as check_thread
from wavebridge.column_domain_check import check as check_columns
from wavebridge.verification.row_offset import check as check_offset
from wavebridge.verification.getter_returns import _hash


def check(root, kernel_id, launch_id, integer_types, row_binding, thread_binding, *,
          int_bits=32, use_host_guard_assumptions=False):
    result = {
        "schema_version": "conditional-row-offset-check/v1", "status": "unknown", "reason": None,
        "source_program_checked": False, "deployable": False, "checks": {},
        "scope": "integer_rhs_of_two_pointer_updates_only",
        "premises": ["all fresh row, thread and column checker premises hold",
                     "frontend AST and prefix recovery faithfully represent the selected kernel",
                     "external coordinate APIs, explicit ABI and runtime configuration are valid"],
        "limitations": ["rectangular row/count domain overapproximates runtime combinations",
                        "does not prove allocation size, pointer addition, aliasing or memory accesses",
                        "does not prove thread participation, floating point results or deployment safety"],
    }

    def unknown(reason):
        result["reason"] = reason
        return result

    if not all(isinstance(item, dict) for item in (root, integer_types, row_binding, thread_binding)):
        return unknown("inputs_not_objects")
    if any(not isinstance(item, str) or not item for item in (kernel_id, launch_id)):
        return unknown("kernel_or_launch_id_invalid")
    try:
        result["input_sha256"] = {
            "root": _hash(root), "integer_types": _hash(integer_types),
            "row_binding": _hash(row_binding), "thread_binding": _hash(thread_binding),
            "int_bits": _hash(int_bits),
            "kernel_id": _hash(kernel_id), "launch_id": _hash(launch_id),
            "use_host_guard_assumptions": _hash(use_host_guard_assumptions),
        }
    except (ValueError, TypeError, RecursionError):
        return unknown("input_hash_unsupported")
    for binding in (row_binding, thread_binding):
        if (binding.get("ast_root_sha256") != result["input_sha256"]["root"] or
                binding.get("kernel_declaration_id") != kernel_id or binding.get("launch_id") != launch_id):
            return unknown("root_kernel_launch_binding_mismatch")
    row = check_row(root, kernel_id, launch_id, integer_types, row_binding,
                    int_bits=int_bits, use_host_guard_assumptions=use_host_guard_assumptions)
    result["checks"]["row"] = row
    if row.get("status") != "checked":
        return unknown("row_coordinate_not_checked")
    thread = check_thread(root, kernel_id, launch_id, integer_types, thread_binding, int_bits=int_bits)
    result["checks"]["thread"] = thread
    if thread.get("status") != "checked":
        return unknown("thread_coordinate_not_checked")
    columns = check_columns(root, thread, integer_types, thread_binding,
                            use_host_guard_assumptions=use_host_guard_assumptions)
    result["checks"]["columns"] = columns
    if columns.get("status") != "checked":
        return unknown("column_domain_not_checked")
    for report in (row, thread, columns):
        if (report.get("kernel_declaration_id") != kernel_id or report.get("launch_id") != launch_id or
                report.get("input_sha256", {}).get("root") != result["input_sha256"]["root"] or
                report.get("input_sha256", {}).get("integer_types") != result["input_sha256"]["integer_types"]):
            return unknown("fresh_evidence_binding_mismatch")
    prefix = row.get("prefix_recovery", {})
    row_id, count_id = prefix.get("row_declaration_id"), prefix.get("count_parameter_id")
    if (prefix.get("status") != "recovered" or prefix.get("function_id") != kernel_id or
            row_id != row.get("row_declaration_id") or
            prefix.get("start_declaration_id") != thread.get("start_declaration_id")):
        return unknown("prefix_coordinate_binding_mismatch")
    loops = columns.get("loops")
    if not isinstance(loops, list) or len(loops) != 2:
        return unknown("expected_two_column_loops")
    intervals = []
    for loop in loops:
        domain = loop.get("argument_domain", {})
        if (loop.get("parameter_declaration_id") != count_id or domain.get("status") != "checked" or
                domain.get("parameter_declaration_id") != count_id):
            return unknown("column_parameter_binding_mismatch")
        intervals.append(domain.get("interval") if domain.get("value_kind") == "interval" else
                         {"lower": domain.get("value"), "upper": domain.get("value")})
    if intervals[0] != intervals[1]:
        return unknown("column_domains_disagree")
    result.update(row_declaration_id=row_id, count_parameter_id=count_id,
                  row_interval=row.get("row_interval"), count_interval=intervals[0])
    for name in ("source_offset", "output_offset"):
        expression = prefix.get(name, {}).get("offset_ast")
        checked = check_offset(expression, row_id, count_id, row.get("row_interval"),
                               intervals[0], integer_types)
        result["checks"][name] = checked
        if checked.get("status") != "checked":
            result.update(status=checked.get("status", "unknown"), reason=name + "_not_checked")
            return result
    result.update(status="checked", kernel_declaration_id=kernel_id, launch_id=launch_id,
                  conclusion="both_integer_offsets_equal_row_times_count_without_overflow_on_supplied_domains")
    return result
