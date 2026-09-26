"""Fresh selected-launch integer evidence bundle, not a kernel safety verdict.

No child report is an input. In particular the thread report consumed by the
shared-memory branch must come from this invocation's row/column branch.
"""

from wavebridge.row_offset_check import check as check_offsets
from wavebridge.shared_storage_check import check as check_shared
from wavebridge.verification.getter_returns import _hash
from wavebridge.verification.launch_binding import check as check_launch


def collect(root, protocol, *, max_ast_nodes=1_000_000):
    result = {
        "schema_version": "device-integer-evidence/v1", "status": "unknown", "reason": None,
        "scope": "selected_launch_binding_integer_coordinates_columns_offsets_and_shared_capacity",
        "source_program_checked": False, "deployable": False,
        "checks": {}, "all_selected_integer_checks_passed": False,
        "remaining_obligations": [
            "source_validity_and_external_ABI_API_premises",
            "configuration_object_history_and_runtime_launch_correspondence",
            "pointer_allocation_aliasing_and_access_validity",
            "thread_participation_and_collective_convergence",
            "shared_values_and_barrier_visibility",
            "source_to_intrinsic_and_reduction_value_correspondence",
            "floating_point_output_and_external_numerical_contract",
            "target_source_recovery_and_source_target_relation",
            "actual_device_mode_and_numerical_execution",
        ],
        "premises": "all_nested_checker_premises_remain_required",
    }

    def stop(reason, child=None):
        result["reason"] = reason
        if isinstance(child, dict) and child.get("status") == "rejected":
            result["status"] = "rejected"
        return result

    if not isinstance(root, dict) or not isinstance(protocol, dict):
        return stop("inputs_not_objects")
    if protocol.get("schema_version") != "device-integer-protocol/v1":
        return stop("unsupported_protocol_schema")
    keys = ("selection", "integer_types", "sizeof_bytes", "row_binding", "thread_binding")
    if any(not isinstance(protocol.get(key), dict) for key in keys):
        return stop("required_protocol_objects_missing")
    bits, guards = protocol.get("int_bits"), protocol.get("use_host_guard_assumptions")
    if type(bits) is not int or not 2 <= bits <= 128 or type(guards) is not bool:
        return stop("invalid_integer_or_host_guard_protocol")
    selection, abi = protocol["selection"], protocol["integer_types"]
    row_binding, thread_binding = protocol["row_binding"], protocol["thread_binding"]
    try:
        hashes = {"root": _hash(root), "protocol": _hash(protocol), "integer_types": _hash(abi),
                  "row_binding": _hash(row_binding), "thread_binding": _hash(thread_binding),
                  "sizeof_bytes": _hash(protocol["sizeof_bytes"])}
    except (TypeError, ValueError, RecursionError):
        return stop("input_hash_unsupported")
    result["input_sha256"] = hashes
    kernel, launch = selection.get("kernel_declaration_id"), selection.get("launch_id")
    if any(not isinstance(value, str) or not value for value in (kernel, launch)):
        return stop("kernel_launch_identity_missing")
    for binding in (selection, row_binding, thread_binding):
        if (binding.get("ast_root_sha256") != hashes["root"] or
                binding.get("kernel_declaration_id") != kernel or binding.get("launch_id") != launch):
            return stop("protocol_root_kernel_launch_mismatch")
    result.update(kernel_declaration_id=kernel, launch_id=launch)
    paired = check_launch(root, selection, max_ast_nodes=max_ast_nodes)
    result["checks"]["launch_binding"] = paired
    if paired.get("status") != "checked":
        return stop("launch_binding_not_checked", paired)
    if (paired.get("kernel_declaration_id") != kernel or paired.get("launch_id") != launch or
            paired.get("input_sha256") != {"root": hashes["root"], "selection": _hash(selection)}):
        return stop("fresh_launch_input_binding_mismatch")
    offsets = check_offsets(root, kernel, launch, abi, row_binding, thread_binding,
                            int_bits=bits, use_host_guard_assumptions=guards)
    result["checks"]["row_offsets"] = offsets
    if offsets.get("status") != "checked":
        return stop("row_offsets_not_checked", offsets)
    expected_offsets = {key: hashes[key] for key in ("root", "integer_types", "row_binding", "thread_binding")}
    expected_offsets.update(int_bits=_hash(bits), kernel_id=_hash(kernel), launch_id=_hash(launch),
                            use_host_guard_assumptions=_hash(guards))
    if offsets.get("input_sha256") != expected_offsets:
        return stop("fresh_offset_input_binding_mismatch")
    thread = offsets.get("checks", {}).get("thread")
    if (not isinstance(thread, dict) or thread.get("status") != "checked" or
            thread.get("schema_version") != "conditional-thread-start-check/v1" or
            thread.get("kernel_declaration_id") != kernel or thread.get("launch_id") != launch or
            type(thread.get("int_bits")) is not int or thread["int_bits"] != bits or
            thread.get("input_sha256") != {"root": hashes["root"], "integer_types": hashes["integer_types"],
                                           "binding": hashes["thread_binding"]}):
        return stop("fresh_thread_binding_mismatch")
    shared = check_shared(root, thread, abi, protocol["sizeof_bytes"], thread_binding)
    result["checks"]["shared_storage"] = shared
    if shared.get("status") != "checked":
        return stop("shared_storage_not_checked", shared)
    if (shared.get("kernel_declaration_id") != kernel or shared.get("launch_id") != launch or
            shared.get("sizeof_bytes_sha256") != hashes["sizeof_bytes"] or
            shared.get("input_sha256", {}).get("root") != hashes["root"] or
            shared.get("input_sha256", {}).get("integer_types") != hashes["integer_types"] or
            shared.get("input_sha256", {}).get("binding") != hashes["thread_binding"]):
        return stop("fresh_shared_input_binding_mismatch")
    result.update(status="evidence", all_selected_integer_checks_passed=True)
    return result
