"""Fresh selected-launch integer evidence bundle, not a kernel safety verdict.

No child report is an input. In particular the thread report consumed by the
shared-memory branch must come from this invocation's row/column branch.
"""

from wavebridge.row_offset_check import check as check_offsets
from wavebridge.shared_storage_check import check as check_shared
from wavebridge.verification.getter_returns import _hash
from wavebridge.verification.launch_binding import check as check_launch
from wavebridge.analysis.normalization_output import recover as recover_output
from wavebridge.verification.xor_routes import check as check_xor_routes
from wavebridge.verification.block_routes import check as check_block_routes


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


def collect_rmsnorm(root, protocol, *, max_ast_nodes=1_000_000):
    """Connect fresh integer evidence, conditional route counts and output syntax.

    This deliberately preserves collect() and its v1 report unchanged. Neither
    route success nor output recovery establishes FP, participation or visibility.
    """
    integers = collect(root, protocol, max_ast_nodes=max_ast_nodes)
    result = {
        "schema_version": "rmsnorm-structural-evidence/v1", "status": "unknown", "reason": None,
        "scope": "same_launch_integer_relations_conditional_route_counts_and_output_structure",
        "source_program_checked": False, "deployable": False,
        "checks": {"integers": integers},
        "remaining_obligations": list(integers["remaining_obligations"]),
        "input_sha256": integers.get("input_sha256"),
        "all_selected_relations_connected": False,
    }

    def stop(reason, child=None):
        result["reason"] = reason
        if isinstance(child, dict) and child.get("status") == "rejected":
            result["status"] = "rejected"
        return result

    if integers.get("status") != "evidence" or integers.get("all_selected_integer_checks_passed") is not True:
        return stop("integer_evidence_incomplete", integers)
    kernel, launch = integers["kernel_declaration_id"], integers["launch_id"]
    bits = protocol["int_bits"]
    offsets = integers["checks"]["row_offsets"]
    thread = offsets["checks"]["thread"]
    shared = integers["checks"]["shared_storage"]
    chain = shared.get("chain_recovery", {})
    helper = shared.get("indexing", {}).get("coordinates", {}).get("helper_recovery", {})
    indexing = shared.get("indexing", {}).get("indexing", {})
    capacity = shared.get("capacity", {})
    if (chain.get("status") != "recovered" or chain.get("function_id") != kernel or
            chain.get("int_bits") != bits or
            chain != thread.get("recovery", {}).get("chain")):
        return stop("same_invocation_reduction_chains_disagree")
    width, block = chain.get("width"), chain.get("block_threads")
    if (type(width) is not int or not 2 <= width <= 64 or width & (width - 1) or
            type(block) is not int or not 1 <= block <= 1024 or block % width):
        return stop("unsupported_route_shape")
    groups = block // width
    helper_id = shared.get("helper_declaration_id")
    links = chain.get("links")
    if (not isinstance(helper_id, str) or not helper_id or not isinstance(links, list) or len(links) != 3 or
            any(not isinstance(link, dict) for link in links) or
            links[0].get("caller_id") != kernel or links[0].get("callee_id") != helper_id or
            helper.get("status") != "recovered" or helper.get("function_id") != helper_id or
            links[0].get("parameter_id") != helper.get("bindings", {}).get("value_parameter_id") or
            links[1].get("caller_id") != helper_id or
            links[1].get("callee_id") != helper.get("reduce_declaration_id") or
            links[2].get("caller_id") != helper.get("reduce_declaration_id")):
        return stop("reduction_helper_edges_not_bound")
    sequence = ["local_reduce", "group_index", "lane_index", "shared_write",
                "barrier", "shared_gather", "final_reduce"]
    calls = helper.get("call_bindings", {})
    barrier = helper.get("barrier_declaration_id")
    if (helper.get("stage_sequence") != sequence or
            not isinstance(barrier, str) or not barrier or calls.get("barrier") != barrier or
            any(calls.get(key) != helper.get("reduce_declaration_id") for key in ("first_reduce", "final_reduce"))):
        return stop("two_stage_call_sequence_not_bound")
    if (any(report.get("width") != width or report.get("block_threads") != block
            for report in (helper, indexing)) or indexing.get("status") != "checked" or
            indexing.get("schema_version") != "shared-indexing-check/v1" or
            indexing.get("groups") != groups or type(helper.get("writer_lane")) is not int or
            helper["writer_lane"] != 0 or capacity.get("status") != "checked" or
            capacity.get("required_elements") != groups):
        return stop("route_indices_or_capacity_disagree")
    element_bytes = protocol["sizeof_bytes"].get("float")
    available = capacity.get("available_bytes")
    if (type(element_bytes) is not int or element_bytes <= 0 or type(available) is not int or
            available < 0 or available % element_bytes or
            capacity.get("required_bytes") != groups * element_bytes or
            chain.get("shared_storage", {}).get("parameter_id") != helper.get("bindings", {}).get("shared_parameter_id")):
        return stop("route_capacity_or_shared_parameter_not_bound")
    output = recover_output(root, kernel, bits)
    result["checks"]["output_structure"] = output
    if output.get("status") != "recovered" or output.get("function_id") != kernel or output.get("int_bits") != bits:
        return stop("output_structure_not_recovered")
    local = output.get("local_contribution", {})
    consumer = local.get("consumer", {})
    if (not isinstance(chain.get("accumulator_declaration_id"), str) or not chain["accumulator_declaration_id"] or
            local.get("accumulator_declaration_id") != chain["accumulator_declaration_id"] or
            output.get("consumer_declaration_id") != helper_id or
            local.get("consumer_declaration_id") != helper_id or
            consumer.get("callee_declaration_id") != helper_id or
            consumer.get("argument_index") != links[0].get("argument_index") or
            consumer.get("call_range") != links[0].get("call_range")):
        return stop("output_consumer_or_accumulator_not_bound")
    array = shared.get("array_declaration_id")
    operation = output.get("operation", {})
    if (not isinstance(array, str) or not array or
            chain.get("shared_storage", {}).get("array_declaration_id") != array or
            operation != {"local": "sum_of_squares", "output": "scale_times_input",
                          "scale_argument": "total_div_count_plus_epsilon", "shared_argument_id": array}):
        return stop("output_operation_or_shared_array_not_bound")
    prefix = offsets["checks"]["row"]["prefix_recovery"]
    for key in ("source_parameter_id", "output_parameter_id", "count_parameter_id"):
        if not isinstance(output.get(key), str) or not output[key] or output[key] != prefix.get(key):
            return stop("output_parameter_not_bound_to_integer_prefix")
    if output["count_parameter_id"] != offsets.get("count_parameter_id"):
        return stop("output_count_not_bound_to_checked_domain")
    if any(local.get(key) != output["source_parameter_id"] for key in ("input_parameter_id", "input_declaration_id")):
        return stop("local_input_not_bound_to_output_source")
    if output.get("local_loop", {}).get("range") == output.get("output_loop", {}).get("range"):
        return stop("local_and_output_loop_locations_not_distinct")
    for key in ("local_loop", "output_loop"):
        loop = output.get(key, {})
        matches = [item for item in offsets["checks"]["columns"].get("loops", [])
                   if item.get("loop_range") == loop.get("range")]
        if (not loop.get("range") or len(matches) != 1 or loop.get("step") != block or
                loop.get("start", {}).get("declaration_id") != thread.get("start_declaration_id") or
                loop.get("bound", {}).get("declaration_id") != output["count_parameter_id"] or
                matches[0].get("parameter_declaration_id") != output["count_parameter_id"]):
            return stop("output_loop_not_bound_to_checked_columns")
    route_inputs = {"block_threads": block, "width": width, "offsets": chain.get("offsets"),
                    "second_offsets": chain.get("offsets"), "writer_lane": helper["writer_lane"],
                    "shared_slots": available // element_bytes, "barrier": True, "load_offset": 0}
    result["route_binding"] = {
        "inputs": route_inputs, "helper_declaration_id": helper_id, "array_declaration_id": array,
        "chain_sha256": _hash(chain), "helper_sha256": _hash(helper), "indexing_sha256": _hash(indexing),
        "barrier_basis": "conditional_all_threads_arrive_and_stores_visible_not_proven_by_bound_call",
        "load_offset_basis": "checked_shared_indexing_v1_establishes_gather_index_equals_lane",
        "shared_slots_basis": "checked_available_bytes_divided_by_explicit_float_size",
    }
    xor = check_xor_routes(width, chain.get("offsets"))
    result["checks"]["xor_routes"] = xor
    if xor.get("status") != "checked":
        return stop("xor_routes_not_checked", xor)
    block_routes = check_block_routes(**route_inputs)
    result["checks"]["block_routes"] = block_routes
    if block_routes.get("status") != "checked":
        return stop("block_routes_not_checked", block_routes)
    result.update(status="evidence", all_selected_relations_connected=True,
                  kernel_declaration_id=kernel, launch_id=launch)
    return result
