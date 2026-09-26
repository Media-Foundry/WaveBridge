"""Fresh selected-launch integer evidence bundle, not a kernel safety verdict.

No child report is an input. In particular the thread report consumed by the
shared-memory branch must come from this invocation's row/column branch.
"""

from wavebridge.row_offset_check import check as check_offsets
from wavebridge.shared_storage_check import check as check_shared
from wavebridge.verification.getter_returns import _hash
from wavebridge.verification.getter_returns import check_property_no_memory_write
from wavebridge.verification.launch_binding import check as check_launch
from wavebridge.analysis.normalization_output import recover as recover_output
from wavebridge.verification.xor_routes import check as check_xor_routes
from wavebridge.verification.block_routes import check as check_block_routes
from wavebridge.verification.block_routes import compare as compare_block_routes
from wavebridge.verification.local_structure import compare as compare_local_structure


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


def _local_entry_signature(root, protocol, side, snapshot):
    """Join only fresh children from compare_rmsnorm_routes, never a report API.

    A common signature describes conditional index relations, not equal runtime
    arguments, pointer contents, getter effects or floating-point values.
    """
    kernel = side["kernel_declaration_id"]
    integers = side["checks"]["integers"]
    offsets = integers["checks"]["row_offsets"]
    row, thread = offsets["checks"]["row"], offsets["checks"]["thread"]
    prefix = row["prefix_recovery"]
    local = snapshot["local_recovery"]
    roles = snapshot["role_bindings"]
    automatic = "automatic_on_each_passage_through_declaration"
    if (snapshot["input_sha256"] != _hash({"root": root, "kernel": kernel,
                                           "int_bits": protocol["int_bits"]})
            or prefix["function_id"] != kernel
            or prefix["status"] != "recovered"
            or any(item["status"] != "checked" for item in (offsets, row, thread))
            or prefix.get("declaration_evaluation") != automatic
            or thread.get("declaration_evaluation") != automatic
            or local != prefix["normalization_output"]["local_contribution"]):
        raise ValueError("fresh_prefix_local_or_coordinate_evidence_not_bound")
    expected = {"input": prefix["source_parameter_id"],
                "start": prefix["start_declaration_id"],
                "bound": prefix["count_parameter_id"],
                "accumulator": thread["recovery"]["chain"]["accumulator_declaration_id"]}
    if (any(roles[role]["declaration_id"] != identifier for role, identifier in expected.items())
            or expected["start"] != thread["start_declaration_id"]
            or expected["bound"] != offsets["count_parameter_id"]
            or prefix["row_declaration_id"] != offsets["row_declaration_id"]):
        raise ValueError("local_roles_do_not_match_fresh_entry_relations")
    # Exact local recovery equality above also binds the selected loop, its
    # induction and loaded-value declarations to the checked prefix/output path.
    def coordinate(name):
        value = protocol[name]["coordinate"]
        return {key: value[key] for key in ("semantics", "axis", "return_type")}

    return {
        "parameter_roles": {role: {key: roles[role][key] for key in
                                    ("kind", "type", "parameter_position")}
                            for role in ("input", "bound")},
        "integer_types": protocol["integer_types"],
        "row_coordinate": coordinate("row_binding"),
        "thread_coordinate": coordinate("thread_binding"),
        "row_interval": offsets["row_interval"], "count_interval": offsets["count_interval"],
        "start_interval": thread["start_interval"],
        "source_offset": {key: offsets["checks"]["source_offset"][key]
                          for key in ("symbolic_relation", "result_type")},
    }


def _coordinate_effects(root, protocol, side, *, max_ast_nodes):
    """Freshly check the two exact property expressions, retaining all premises."""
    result = {"status": "unknown", "reason": None, "checks": {},
              "scope": "row_and_start_property_evaluation_under_external_effect_receiver_premises",
              "external_premises_verified": False,
              "source_program_checked": False, "deployable": False}
    try:
        offsets = side["checks"]["integers"]["checks"]["row_offsets"]
        coordinates = offsets["checks"]
        row, thread = coordinates["row"], coordinates["thread"]
        links = {"row": row["prefix_recovery"]["row_initializer_evidence"]["value_link"],
                 "start": thread["recovery"]["initializer"]["value_link"]}
        protocols = protocol["coordinate_effects"]
        if not isinstance(protocols, dict) or set(protocols) != {"row", "start"}:
            raise ValueError("exact_row_start_effect_protocols_required")
        for name, coordinate in (("row", row), ("start", thread)):
            link = links[name]
            if coordinate["status"] != "checked" or link["status"] != "recovered":
                raise ValueError(name + "_coordinate_or_initializer_not_checked")
            expression = link["pseudo_object"]["expression_id"]
            assumptions = protocols[name]
            child = check_property_no_memory_write(
                root, expression, coordinate["derived_leaf_domain"], protocol["integer_types"],
                assumptions["effect_protocol"], assumptions["receiver_protocol"],
                max_ast_nodes=max_ast_nodes)
            result["checks"][name] = child
            if child["status"] != "checked":
                raise ValueError(name + "_property_effect_not_checked")
            fresh_link = child["value_link"]
            if any(fresh_link[key] != link[key] for key in ("call_id", "callee_declaration_id")):
                raise ValueError(name + "_property_call_binding_mismatch")
        result["status"] = "checked"
    except (KeyError, TypeError, ValueError, RecursionError) as error:
        result["reason"] = str(error)
    return result


def _load_index_relation(comparison):
    """Compare element-index recurrences under common abstract r, n, t.

    Private fresh-child composition, not a report-consuming public checker.
    This does not assert that any two actual invocations share those values.
    """
    result = {"status": "unknown", "reason": None, "sides": {},
              "scope": "ordered_logical_element_indices_relative_to_each_input_parameter",
              "hypothesis": "paired_executions_have_common_row_r_count_n_and_local_x_t_in_both_domains",
              "runtime_pairing_verified": False, "input_contents_correspondence": "not_established",
              "source_program_checked": False, "deployable": False}
    try:
        for name in ("source", "target"):
            snapshot = comparison["checks"]["local_structure"]["checks"][name]
            local, roles = snapshot["local_recovery"], snapshot["role_bindings"]
            loop = local["loop"]
            signature = comparison["checks"]["local_entry_binding"]["signatures"][name]
            step = loop["step"]
            integer_checks = comparison["checks"][name]["checks"]["integers"]["checks"]["row_offsets"]["checks"]
            columns, thread, row = (integer_checks[key] for key in ("columns", "thread", "row"))
            recovered = [item for item in columns["column_recovery"]["loops"] if item["range"] == loop["range"]]
            covered = [item for item in columns["loops"] if item["loop_range"] == loop["range"]]
            if (columns["status"] != "checked" or recovered != [loop] or len(covered) != 1
                    or covered[0]["coverage"]["status"] != "checked"
                    or covered[0]["parameter_declaration_id"] != roles["bound"]["declaration_id"]
                    or integer_checks["source_offset"]["status"] != "checked"
                    or thread["recovery"]["chain"]["block_threads"] != step
                    or thread["checks"]["block"]["dimensions"] != {"x": step, "y": 1, "z": 1}
                    or row["conclusion"] != "row_initializer_equals_workgroup_x_under_explicit_protocol"
                    or thread["coordinate_conclusion"] !=
                    "column_start_equals_local_x_under_explicit_API_and_launch_premises"
                    or comparison["checks"]["coordinate_effects"][name]["status"] != "checked"):
                raise ValueError(name + "_integer_or_effect_premises_not_connected")
            if (local["status"] != "recovered" or local["operation"] != "sum_of_squares"
                    or loop["status"] != "recovered" or type(step) is not int or step <= 0
                    or loop["header_recurrence_observed"] is not True
                    or any(loop[key] != "established_in_supported_effect_subset"
                           for key in ("body_preserves_induction", "body_preserves_bound"))
                    or local["input_parameter_id"] != roles["input"]["declaration_id"]
                    or loop["start"]["declaration_id"] != roles["start"]["declaration_id"]
                    or loop["bound"]["declaration_id"] != roles["bound"]["declaration_id"]
                    or loop["induction"]["declaration_id"] != roles["induction"]["declaration_id"]
                    or signature["source_offset"]["symbolic_relation"] !=
                    {"coefficient": 1, "row_power": 1, "count_power": 1}):
                raise ValueError(name + "_unsupported_load_recurrence")
            domains = {symbol: signature[key] for symbol, key in
                       (("r", "row_interval"), ("n", "count_interval"), ("t", "start_interval"))}
            for domain in domains.values():
                if (set(domain) != {"lower", "upper"}
                        or any(type(value) is not int for value in domain.values())
                        or not 0 <= domain["lower"] <= domain["upper"]):
                    raise ValueError(name + "_unsupported_index_domain")
            result["sides"][name] = {
                "bindings": {symbol: roles[role]["declaration_id"] for symbol, role in
                             (("input", "input"), ("n", "bound"), ("t", "start"), ("j", "induction"))},
                "domains": domains,
                "normal_form": {"element_index": {"r*n": 1, "t": 1, "k": step},
                                "column": {"t": 1, "k": step},
                                "iteration": "k_integer_ge_0_and_column_lt_n"},
            }
        source, target = (result["sides"][name] for name in ("source", "target"))
        if source["normal_form"] != target["normal_form"] or source["domains"] != target["domains"]:
            raise ValueError("different_ordered_index_relations_not_supported")
        result.update(status="checked", conclusion="same_ordered_element_indices_under_common_r_n_t")
    except (KeyError, TypeError, ValueError) as error:
        result["reason"] = str(error)
    return result


def compare_rmsnorm_routes(source_root, source_protocol, target_root, target_protocol,
                           *, max_ast_nodes=1_000_000):
    """Fresh two-sided route evidence; leaves are NOT proven equivalent values."""
    result = {
        "schema_version": "rmsnorm-route-comparison/v5", "status": "unknown", "reason": None,
        "scope": "fresh_two_sided_routes_local_templates_entry_effects_and_conditional_load_indices",
        "source_program_checked": False, "deployable": False,
        "leaf_value_correspondence": "not_established",
        "floating_point_equivalence": "not_checked", "checks": {},
        "remaining_obligations": {},
    }
    for side, root, protocol in (("source", source_root, source_protocol),
                                 ("target", target_root, target_protocol)):
        evidence = collect_rmsnorm(root, protocol, max_ast_nodes=max_ast_nodes)
        result["checks"][side] = evidence
        result["remaining_obligations"][side] = list(evidence["remaining_obligations"])
        if evidence.get("status") != "evidence" or evidence.get("all_selected_relations_connected") is not True:
            result.update(status="rejected" if evidence.get("status") == "rejected" else "unknown",
                          reason=side + "_structural_evidence_incomplete")
            return result
    comparison = compare_block_routes(*(result["checks"][side]["route_binding"]["inputs"]
                                         for side in ("source", "target")))
    result["checks"]["route_relation"] = comparison
    result.update(status=comparison["status"], reason=comparison["reason"])
    if comparison["status"] != "evidence":
        return result
    if source_protocol["int_bits"] != target_protocol["int_bits"]:
        result.update(status="unknown", reason="different_integer_ABI_not_supported")
        return result
    local = compare_local_structure(
        source_root, result["checks"]["source"]["kernel_declaration_id"],
        target_root, result["checks"]["target"]["kernel_declaration_id"],
        source_protocol["int_bits"], max_ast_nodes=max_ast_nodes)
    result["checks"]["local_structure"] = local
    result["remaining_obligations"]["local_structure"] = local["remaining_obligations"]
    if local["status"] != "evidence":
        result.update(status=local["status"], reason="local_structure_not_matched")
        return result
    entry = {"status": "unknown", "signatures": {}, "relation_signatures_equal": None,
             "premise_scope": "both_sides_nested_premises_required_not_proven_equal",
             "host_guard_assumption_modes": {
                 "source": source_protocol.get("use_host_guard_assumptions"),
                 "target": target_protocol.get("use_host_guard_assumptions")},
             "runtime_argument_correspondence": "not_established",
             "pointer_contents_correspondence": "not_established"}
    result["checks"]["local_entry_binding"] = entry
    try:
        for name, root, protocol in (("source", source_root, source_protocol),
                                      ("target", target_root, target_protocol)):
            entry["signatures"][name] = _local_entry_signature(
                root, protocol, result["checks"][name], local["checks"][name])
    except (KeyError, TypeError, ValueError, RecursionError) as error:
        result.update(status="unknown", reason="local_entry_not_bound:" + str(error))
        return result
    equal = entry["signatures"]["source"] == entry["signatures"]["target"]
    entry.update(status="evidence" if equal else "unknown", relation_signatures_equal=equal)
    if not equal:
        result.update(status="unknown", reason="different_entry_relation_signatures_not_supported")
        return result
    effects = {}
    result["checks"]["coordinate_effects"] = effects
    result["remaining_obligations"]["coordinate_effects"] = [
        "external_leaf_no_write_and_normal_return_assumptions_unverified",
        "receiver_readiness_and_extension_semantics_assumptions_unverified"]
    for name, root, protocol in (("source", source_root, source_protocol),
                                  ("target", target_root, target_protocol)):
        child = _coordinate_effects(root, protocol, result["checks"][name],
                                    max_ast_nodes=max_ast_nodes)
        effects[name] = child
        if child["status"] != "checked":
            result.update(status="unknown", reason=name + "_coordinate_effects_not_checked")
            return result
    indices = _load_index_relation(result)
    result["checks"]["load_index_relation"] = indices
    if indices["status"] != "checked":
        result.update(status="unknown", reason="load_index_relation_not_checked")
    return result


def _conditional_local_values(comparison, assumptions):
    """Induction in an explicitly common abstract interpretation, NOT GPU FP."""
    result = {"status": "unknown", "reason": None,
              "scope": "local_accumulator_in_common_abstract_typed_AST_interpretation",
              "external_premises_verified": False, "actual_FP_semantics_verified": False,
              "source_program_checked": False, "deployable": False}
    try:
        keys = {"schema_version", "source", "target", "common_count_and_coordinates_assumed",
                "coordinate_domain", "input_origin", "same_immutable_logical_input_array_assumed",
                "valid_complete_local_executions_assumed", "evaluation_model", "evidence_reference"}
        if (not isinstance(assumptions, dict)
                or set(assumptions) != keys
                or assumptions.get("schema_version") != "paired-local-input-assumptions/v1"
                or assumptions.get("common_count_and_coordinates_assumed") is not True
                or assumptions.get("coordinate_domain") != "common_tuple_in_both_checked_domains"
                or assumptions.get("input_origin") != "kernel_entry_parameter_before_row_offset"
                or assumptions.get("same_immutable_logical_input_array_assumed") is not True
                or assumptions.get("valid_complete_local_executions_assumed") is not True
                or assumptions.get("evaluation_model") != "common_total_deterministic_order_preserving_typed_AST_interpretation"
                or not isinstance(assumptions.get("evidence_reference"), str)
                or not assumptions["evidence_reference"].strip()):
            raise ValueError("explicit_paired_input_and_interpretation_assumptions_required")
        result["assumptions_sha256"] = _hash(assumptions)
        result["assumptions"] = assumptions
        checks = comparison["checks"]
        local = checks["local_structure"]
        if (comparison["status"] != "evidence" or local["status"] != "evidence"
                or local["local_structure_equal"] is not True
                or checks["load_index_relation"]["status"] != "checked"):
            raise ValueError("fresh_structure_and_index_relations_required")
        for name in ("source", "target"):
            side, snapshot = checks[name], local["checks"][name]
            expected = {"root_sha256": side["input_sha256"]["root"],
                        "protocol_sha256": side["input_sha256"]["protocol"],
                        "kernel_declaration_id": side["kernel_declaration_id"],
                        "launch_id": side["launch_id"],
                        "input_parameter_id": snapshot["role_bindings"]["input"]["declaration_id"],
                        "count_parameter_id": snapshot["role_bindings"]["bound"]["declaration_id"]}
            if assumptions.get(name) != expected:
                raise ValueError(name + "_paired_input_binding_mismatch")
        source, target = (local["checks"][name]["template"] for name in ("source", "target"))
        if source != target:
            raise ValueError("typed_templates_not_identical")
        result.update(status="checked", conclusion={
            "status": "conditional",
            "property": "equal_loop_exit_accumulators_in_the_common_abstract_interpretation",
            "rule": "induction_over_equal_ordered_local_iterations",
            "base": "identical_typed_seed_in_the_same_interpretation",
            "step": "equal_logical_input_values_and_identical_deterministic_typed_update",
            "termination": "equal_checked_iteration_sequences_under_common_count_and_coordinates",
        }, derivation_bindings={"seed_sha256": _hash(source["accumulator"]),
                                "loop_sha256": _hash(source["loop"]),
                                "indices_sha256": _hash(checks["load_index_relation"])})
    except (KeyError, TypeError, ValueError, RecursionError) as error:
        result["reason"] = str(error)
    return result


def compare_rmsnorm_local_values(source_root, source_protocol, target_root, target_protocol,
                                 assumptions, *, max_ast_nodes=1_000_000):
    """Fresh source comparison plus conditional abstract local-value congruence.

    No numerical tolerance or compiler FP mode is inferred. The original route
    comparison remains available unchanged, without these extra assumptions.
    """
    result = compare_rmsnorm_routes(source_root, source_protocol, target_root, target_protocol,
                                    max_ast_nodes=max_ast_nodes)
    result["schema_version"] = "rmsnorm-local-value-comparison/v1"
    result["scope"] = "fresh_relations_plus_conditional_abstract_local_accumulator_correspondence"
    if result["status"] != "evidence":
        return result
    local = _conditional_local_values(result, assumptions)
    result["checks"]["conditional_local_values"] = local
    result["remaining_obligations"]["conditional_local_values"] = [
        "paired_input_values_immutability_and_runtime_coordinates_not_verified",
        "common_abstract_interpretation_not_verified_against_compiler_or_device_FP",
        "reduction_FP_and_whole_kernel_equivalence_not_established"]
    if local["status"] != "checked":
        result.update(status="unknown", reason="conditional_local_value_relation_not_checked")
    return result
