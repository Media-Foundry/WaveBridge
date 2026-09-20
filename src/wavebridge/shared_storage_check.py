"""Connect checked shared indices to same-AST array and allocation evidence."""

from wavebridge.shared_index_check import check as check_indices
from wavebridge.analysis.reduction_chain import recover as recover_chain
from wavebridge.analysis.launch_facts import inspect as inspect_launch
from wavebridge.verification.shared_capacity import check as check_capacity
from wavebridge.verification.getter_returns import _hash


def check(root, thread_report, integer_types, sizeof_bytes, binding):
    result = {
        "schema_version": "conditional-shared-storage-check/v1", "status": "unknown", "reason": None,
        "source_program_checked": False, "deployable": False,
        "scope": "selected_launch_shared_integer_indices_and_bound_array_capacity_only",
        "premises": ["all premises of the index and capacity checks remain required",
                     "one shared array at offset zero without other dynamic allocations",
                     "configuration argument 2 denotes dynamic shared bytes",
                     "external sizeof and integer ABI assumptions match the target"],
        "limitations": ["does not establish pointer aliasing, synchronization, participation or stored values",
                        "does not establish complete source or compiled-code memory safety"],
    }

    def unknown(reason):
        result["reason"] = reason
        return result

    if not all(isinstance(value, dict) for value in (root, thread_report, integer_types, sizeof_bytes, binding)):
        return unknown("inputs_not_objects")
    try:
        result["sizeof_bytes_sha256"] = _hash(sizeof_bytes)
    except (TypeError, ValueError, RecursionError):
        return unknown("sizeof_hash_unsupported")
    indexing = check_indices(root, thread_report, integer_types, binding)
    result["indexing"] = indexing
    result["input_sha256"] = indexing.get("input_sha256")
    if indexing.get("status") != "checked":
        result.update(status=indexing.get("status", "unknown"), reason="shared_indices_not_checked")
        return result
    coordinates = indexing.get("coordinates")
    helper = coordinates.get("helper_recovery") if isinstance(coordinates, dict) else None
    if (not isinstance(helper, dict) or not isinstance(helper.get("function_id"), str) or
            not helper["function_id"] or helper["function_id"] != indexing.get("helper_declaration_id")):
        return unknown("checked_helper_binding_missing")
    kernel, launch = thread_report.get("kernel_declaration_id"), thread_report.get("launch_id")
    if not isinstance(kernel, str) or not kernel or not isinstance(launch, str) or not launch:
        return unknown("kernel_launch_ids_missing")
    chain = recover_chain(root, kernel, thread_report.get("int_bits"))
    result["chain_recovery"] = chain
    if chain.get("status") != "recovered" or chain.get("function_id") != kernel:
        return unknown("fresh_reduction_chain_missing")
    edges = chain.get("links")
    if (not isinstance(edges, list) or not edges or not isinstance(edges[0], dict) or
            edges[0].get("caller_id") != kernel or edges[0].get("callee_id") != helper["function_id"]):
        return unknown("fresh_chain_helper_mismatch")
    if any(type(chain.get(key)) is not int or chain[key] != helper.get(key)
           for key in ("width", "block_threads")):
        return unknown("index_capacity_model_mismatch")
    storage, declarations = chain.get("shared_storage"), helper.get("bindings")
    if (not isinstance(storage, dict) or storage.get("status") != "recovered" or
            not isinstance(declarations, dict) or
            not isinstance(declarations.get("shared_parameter_id"), str) or
            not declarations["shared_parameter_id"] or
            storage.get("parameter_id") != declarations["shared_parameter_id"] or
            not isinstance(storage.get("array_declaration_id"), str) or not storage["array_declaration_id"]):
        return unknown("shared_array_parameter_binding_missing")
    launches = inspect_launch(root, kernel)
    sites = [site for site in launches.get("sites", []) if site.get("launch_id") == launch]
    if len(sites) != 1:
        return unknown("selected_launch_not_unique")
    capacity = check_capacity(chain, sites[0], integer_types, sizeof_bytes)
    result["capacity"] = capacity
    result.update(status=capacity["status"], reason=capacity.get("reason"),
                  kernel_declaration_id=kernel, launch_id=launch,
                  helper_declaration_id=helper["function_id"],
                  array_declaration_id=storage["array_declaration_id"])
    return result
