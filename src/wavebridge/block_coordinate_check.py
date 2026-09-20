"""Conditionally connect block helper partition expressions to checked local x.

The prior thread-start report must be genuine checker output; hashes bind its
root, ABI and external protocol, not its authenticity. Frontend recovery remains
part of the trusted base. Only group/lane initializers are checked here.
"""

from wavebridge.analysis.reduction_discovery import discover
from wavebridge.analysis.initializer_value import link
from wavebridge.verification.getter_returns import check as check_getter, _hash
from wavebridge.verification.initializer_domain import check as check_domain
from wavebridge.verification.index_partition import check as check_partition


def check(root, thread_report, integer_types, binding):
    result = {
        "schema_version": "conditional-block-coordinate-check/v1", "status": "unknown", "reason": None,
        "source_program_checked": False, "deployable": False, "checks": {},
        "scope": "selected_block_helper_group_and_lane_initializers_only",
        "premises": ["thread_report is genuine conditional-thread-start checker output",
                     "frontend recovery and Clang AST are faithful",
                     "bound local-id API semantics hold throughout this helper in the same workgroup",
                     "runtime launch dimensions, ABI and source validity match the explicit protocol"],
    }

    def unknown(reason):
        result["reason"] = reason
        return result

    if not all(isinstance(value, dict) for value in (root, thread_report, integer_types, binding)):
        return unknown("inputs_not_objects")
    try:
        hashes = {"root": _hash(root), "integer_types": _hash(integer_types), "binding": _hash(binding)}
        result["input_sha256"] = {**hashes, "thread_report": _hash(thread_report)}
    except (TypeError, ValueError, RecursionError):
        return unknown("input_hash_unsupported")
    if (binding.get("schema_version") != "thread-start-assumptions/v1" or
            thread_report.get("schema_version") != "conditional-thread-start-check/v1" or
            thread_report.get("status") != "checked" or thread_report.get("input_sha256") != hashes):
        return unknown("thread_evidence_not_checked_or_same_inputs")
    kernel = thread_report.get("kernel_declaration_id")
    if (not isinstance(kernel, str) or not kernel or binding.get("kernel_declaration_id") != kernel or
            thread_report.get("launch_id") != binding.get("launch_id") or
            binding.get("ast_root_sha256") != hashes["root"]):
        return unknown("kernel_launch_or_ast_binding_mismatch")
    recovery = thread_report.get("recovery")
    chain = recovery.get("chain") if isinstance(recovery, dict) else None
    if not isinstance(chain, dict) or chain.get("status") != "recovered":
        return unknown("connected_reduction_chain_missing")
    edges = chain.get("links")
    if (not isinstance(edges, list) or not edges or not isinstance(edges[0], dict) or
            edges[0].get("caller_id") != kernel):
        return unknown("kernel_to_helper_binding_missing")
    helper = edges[0].get("callee_id")
    if not isinstance(helper, str) or not helper:
        return unknown("helper_id_missing")
    discovered = discover(root, kernel, thread_report.get("int_bits"))
    if not discovered.get("traversal_budget_complete"):
        return unknown("discovery_budget_incomplete")
    blocks = [block for block in discovered.get("block_candidates", [])
              if block.get("function_id") == helper]
    if len(blocks) != 1:
        return unknown("connected_helper_not_unique")
    block = blocks[0]
    result["helper_recovery"] = block
    if (block.get("status") != "recovered" or block.get("block_threads") != chain.get("block_threads") or
            block.get("width") != chain.get("width")):
        return unknown("helper_model_mismatch")
    domain = thread_report.get("derived_leaf_domain")
    if (not isinstance(domain, dict) or domain.get("schema_version") != "getter-leaf-domain/v1" or
            type(domain.get("lower")) is not int or type(domain.get("upper")) is not int or domain.get("lower") != 0 or
            domain.get("upper") != block["block_threads"] - 1):
        return unknown("thread_domain_mismatch")
    coordinate = binding.get("coordinate")
    if (not isinstance(coordinate, dict) or coordinate.get("semantics") != "workgroup_local_id" or
            type(coordinate.get("axis")) is not int or
            domain.get("declaration_id") != coordinate.get("declaration_id") or
            domain.get("return_type") != coordinate.get("return_type") or
            domain.get("arguments") != [0] or coordinate.get("axis") != 0):
        return unknown("coordinate_protocol_mismatch")
    for name, operation in (("group", "/"), ("lane", "%")):
        expression = block.get("index_initializers", {}).get(name)
        coordinate_ast = block.get("coordinate_asts", {}).get(name + "_coordinate")
        origin = link(root, coordinate_ast)
        evidence = {"value_link": origin}
        result["checks"][name] = evidence
        if origin.get("status") != "recovered":
            return unknown("helper_coordinate_value_link_missing")
        getter = check_getter(root, origin.get("callee_declaration_id"), domain, integer_types)
        evidence["getter"] = getter
        if getter["status"] != "checked":
            result.update(status=getter["status"], reason="helper_getter_not_checked")
            return result
        scalar = check_domain(origin, getter, integer_types)
        evidence["domain"] = scalar
        if scalar["status"] != "checked":
            result.update(status=scalar["status"], reason="helper_coordinate_conversion_not_checked")
            return result
        if scalar.get("result_interval") != {"lower": domain["lower"], "upper": domain["upper"]}:
            return unknown("helper_coordinate_domain_mismatch")
        partition = check_partition(expression, coordinate_ast, block["bindings"]["width_declaration_id"],
                                    block["width"], block["block_threads"], integer_types, operation=operation)
        evidence["partition"] = partition
        if partition["status"] != "checked":
            result.update(status=partition["status"], reason="helper_partition_not_checked")
            return result
    result.update(status="checked", helper_declaration_id=helper,
                  coordinate_conclusion="group_equals_local_x_div_width_and_lane_equals_local_x_mod_width_under_protocol")
    return result
