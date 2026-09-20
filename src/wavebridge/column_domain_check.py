"""Bind recovered host column bounds to conditional per-launch loop coverage."""

from wavebridge.analysis.column_loops import recover as recover_columns
from wavebridge.analysis.launch_facts import inspect as inspect_launch
from wavebridge.analysis.launch_guards import recover as recover_guards
from wavebridge.verification.getter_returns import _hash
from wavebridge.verification.kernel_arguments import check as check_argument, _abi_type, _Unknown
from wavebridge.verification.column_coverage import check_interval as check_coverage


def _walk(node, parent=None):
    yield node, parent
    for child in node.get("inner", []):
        if isinstance(child, dict) and child:
            yield from _walk(child, node)


def _loop_context(root, kernel, bounds, loops):
    """Do not infer an unchanged loop bound merely from a launch argument."""
    functions = [node for node, _ in _walk(root)
                 if node.get("kind") == "FunctionDecl" and node.get("id") == kernel]
    if len(functions) != 1:
        return "kernel_definition_not_unique"
    bodies = [child for child in functions[0].get("inner", []) if child.get("kind") == "CompoundStmt"]
    if len(bodies) != 1:
        return "kernel_body_not_unique"
    top_loops = [child for child in bodies[0].get("inner", []) if child.get("kind") == "ForStmt"]
    if (len(top_loops) != len(loops) or
            [node.get("range") for node in top_loops] != [loop.get("range") for loop in loops]):
        return "column_loops_not_direct_kernel_statements"
    for node, parent in _walk(bodies[0]):
        if node.get("kind") in {"ReturnStmt", "GotoStmt", "IndirectGotoStmt", "CXXThrowExpr",
                                "WhileStmt", "DoStmt", "CXXForRangeStmt", "BreakStmt", "ContinueStmt"}:
            return "kernel_control_flow_outside_supported_context"
        ref = node.get("referencedDecl")
        if node.get("kind") == "DeclRefExpr" and isinstance(ref, dict) and ref.get("id") in bounds:
            if (not isinstance(parent, dict) or parent.get("kind") != "ImplicitCastExpr" or
                    parent.get("castKind") != "LValueToRValue" or parent.get("inner") != [node]):
                return "column_parameter_has_write_or_escape_use"
    return None


def check(root, thread_report, integer_types, binding, *, use_host_guard_assumptions=False):
    result = {
        "schema_version": "conditional-column-domain-check/v1", "status": "unknown", "reason": None,
        "source_program_checked": False, "deployable": False, "loops": [],
        "host_guard_assumptions_enabled": use_host_guard_assumptions,
        "scope": "all_column_counts_in_recovered_guard_domains_for_one_selected_launch",
        "limitations": ["coverage describes induction indices, not loop-body data accesses or contributions",
                        "guard intervals are necessary-condition overapproximations, not proven reachable domains"],
        "premises": ["thread_report is genuine checker evidence for the same AST and external protocol",
                     "frontend loop, positional argument and host-guard recovery are faithful",
                     "host guards describe necessary conditions when this launch is reached",
                     "all modeled threads reach the supported loops and execution is otherwise valid",
                     "explicit coordinate API, ABI and runtime launch configuration remain valid"],
    }

    def unknown(reason):
        result["reason"] = reason
        return result

    if type(use_host_guard_assumptions) is not bool or not use_host_guard_assumptions:
        return unknown("host_guard_assumptions_must_be_explicitly_enabled")
    if not all(isinstance(obj, dict) for obj in (root, thread_report, integer_types, binding)):
        return unknown("inputs_not_objects")
    try:
        hashes = {"root": _hash(root), "integer_types": _hash(integer_types), "binding": _hash(binding)}
        result["input_sha256"] = {**hashes, "thread_report": _hash(thread_report)}
    except (TypeError, ValueError, RecursionError):
        return unknown("input_hash_unsupported")
    if (thread_report.get("schema_version") != "conditional-thread-start-check/v1" or
            thread_report.get("status") != "checked" or thread_report.get("input_sha256") != hashes):
        return unknown("thread_report_not_checked_or_same_inputs")
    kernel, launch = thread_report.get("kernel_declaration_id"), thread_report.get("launch_id")
    if (not isinstance(kernel, str) or not kernel or not isinstance(launch, str) or not launch or
            binding.get("schema_version") != "thread-start-assumptions/v1" or
            binding.get("kernel_declaration_id") != kernel or binding.get("launch_id") != launch or
            binding.get("ast_root_sha256") != hashes["root"]):
        return unknown("kernel_launch_binding_mismatch")
    bits = thread_report.get("int_bits")
    try:
        ty = _abi_type({"qualType": "int"}, integer_types)
    except _Unknown:
        return unknown("integer_abi_missing")
    if type(bits) is not int or ty[1:] != (bits, True):
        return unknown("analysis_integer_abi_mismatch")
    start_domain = thread_report.get("start_interval")
    if (not isinstance(start_domain, dict) or type(start_domain.get("lower")) is not int or
            start_domain["lower"] != 0 or type(start_domain.get("upper")) is not int or
            not 0 <= start_domain["upper"] < 1024):
        return unknown("thread_start_domain_unsupported")
    starts = list(range(start_domain["upper"] + 1))
    columns = recover_columns(root, kernel, bits)
    launches = inspect_launch(root, kernel)
    result["column_recovery"] = columns
    loops = columns.get("loops")
    if (columns.get("status") != "recovered" or columns.get("function_id") != kernel or
            not isinstance(loops, list) or not loops):
        return unknown("column_recovery_incomplete")
    bounds = set()
    for loop in loops:
        bound, start = loop.get("bound"), loop.get("start")
        if (loop.get("status") != "recovered" or not isinstance(bound, dict) or
                loop.get("header_recurrence_observed") is not True or
                loop.get("body_preserves_induction") != "established_in_supported_effect_subset" or
                loop.get("body_preserves_bound") != "established_in_supported_effect_subset" or
                bound.get("kind") != "parameter" or not isinstance(bound.get("declaration_id"), str) or
                not bound["declaration_id"] or not isinstance(start, dict) or
                start.get("kind") != "declaration_reference" or
                start.get("declaration_id") != thread_report.get("start_declaration_id") or
                type(loop.get("step")) is not int or loop["step"] != len(starts)):
            return unknown("loop_parameter_start_or_stride_mismatch")
        bounds.add(bound["declaration_id"])
    context_reason = _loop_context(root, kernel, bounds, loops)
    if context_reason:
        return unknown(context_reason)
    sites = [site for site in launches.get("sites", []) if site.get("launch_id") == launch]
    if len(sites) != 1 or sites[0].get("parameter_binding_status") != "bound_by_position":
        return unknown("selected_launch_arguments_not_uniquely_bound")
    site = sites[0]
    if site.get("kernel_declaration_id") != kernel:
        return unknown("selected_launch_kernel_mismatch")
    guards = recover_guards(root, launch, bits)
    result["host_guard_recovery"] = guards
    if (guards.get("schema_version") != "launch-guards/v1" or guards.get("status") != "recovered" or
            guards.get("launch_id") != launch or guards.get("int_bits") != bits or
            guards.get("interpretation") != "necessary_conditions_to_pass_supported_early_returns_only"):
        return unknown("host_guard_domain_not_recovered")
    for loop in loops:
        parameter = loop["bound"]["declaration_id"]
        matches = [item for item in site.get("parameter_bindings", [])
                   if item.get("parameter_declaration_id") == parameter]
        if len(matches) != 1:
            return unknown("column_parameter_argument_not_unique")
        domain = check_argument(matches[0], guards.get("intervals"), integer_types)
        entry = {"loop_range": loop.get("range"), "parameter_declaration_id": parameter, "argument_domain": domain}
        result["loops"].append(entry)
        if domain["status"] != "checked":
            result.update(status=domain["status"], reason="column_argument_domain_not_checked")
            return result
        interval = domain.get("interval") if domain.get("value_kind") == "interval" else {
            "lower": domain.get("value"), "upper": domain.get("value")}
        if not isinstance(interval, dict):
            return unknown("column_argument_interval_missing")
        coverage = check_coverage(interval.get("lower"), interval.get("upper"), starts, loop["step"], int_bits=bits)
        entry["coverage"] = coverage
        if coverage["status"] != "checked":
            result.update(status=coverage["status"], reason="column_domain_coverage_not_checked")
            return result
    result.update(status="checked", kernel_declaration_id=kernel, launch_id=launch,
                  coverage_conclusion="each_column_index_is_generated_once_across_modeled_threads_per_loop")
    return result
