"""Compose fresh source recovery with conditional thread-start checks for one launch.

This orchestration layer trusts the documented frontend recovery subset, not a
candidate generator. Independent getter/conversion/configuration checkers retain
their own evidence. It never authorizes deployment.
"""

from wavebridge.analysis.column_loops import recover as recover_columns
from wavebridge.analysis.reduction_chain import recover as recover_chain
from wavebridge.analysis.initializer_evidence import inspect as inspect_initializer
from wavebridge.analysis.launch_facts import inspect as inspect_launch
from wavebridge.analysis.constructor_arguments import inspect as inspect_constructor
from wavebridge.analysis.constructor_fields import recover as recover_fields
from wavebridge.verification.block_configuration import check as check_block
from wavebridge.verification.getter_returns import check as check_getter, _hash
from wavebridge.verification.initializer_domain import check as check_initializer


def check(root, kernel_id, launch_id, integer_types, binding, *, int_bits=32):
    result = {
        "schema_version": "conditional-thread-start-check/v1", "status": "unknown", "reason": None,
        "kernel_declaration_id": kernel_id, "launch_id": launch_id,
        "int_bits": int_bits,
        "scope": "recovered_column_start_for_one_explicit_launch_under_external_coordinate_API",
        "source_program_checked": False, "deployable": False,
        "checks": {}, "recovery": {},
        "premises": ["faithful well-formed single-TU Clang AST and supported frontend recovery",
                     "explicit integer ABI matches source compilation",
                     "explicit field axes and configuration position match the launch API",
                     "explicit external leaf(axis=0) denotes workgroup local x coordinate",
                     "runtime executes this launch with the checked dimensions",
                     "source and receiver evaluation are valid; purity is not established"],
    }

    def unknown(reason):
        result["reason"] = reason
        return result

    if not all(isinstance(obj, dict) for obj in (root, integer_types, binding)):
        return unknown("inputs_not_objects")
    if any(not isinstance(v, str) or not v for v in (kernel_id, launch_id)):
        return unknown("kernel_or_launch_id_missing")
    if type(int_bits) is not int or not 2 <= int_bits <= 128:
        return unknown("unsupported_int_bits")
    try:
        root_hash = _hash(root)
        result["input_sha256"] = {"root": root_hash, "integer_types": _hash(integer_types),
                                  "binding": _hash(binding)}
    except (TypeError, ValueError, RecursionError):
        return unknown("input_hash_unsupported")
    if (binding.get("schema_version") != "thread-start-assumptions/v1" or
            binding.get("ast_root_sha256") != root_hash or
            binding.get("kernel_declaration_id") != kernel_id or
            binding.get("launch_id") != launch_id):
        return unknown("external_binding_does_not_match_ast_kernel_launch")
    positions = binding.get("configuration_positions")
    if (not isinstance(positions, dict) or set(positions) != {"grid", "block"} or
            any(type(value) is not int for value in positions.values()) or
            positions != {"grid": 0, "block": 1}):
        return unknown("unsupported_launch_configuration_positions")
    coordinate = binding.get("coordinate")
    if (not isinstance(coordinate, dict) or coordinate.get("semantics") != "workgroup_local_id" or
            type(coordinate.get("axis")) is not int or coordinate["axis"] != 0 or
            not isinstance(coordinate.get("declaration_id"), str) or not coordinate["declaration_id"] or
            not isinstance(coordinate.get("return_type"), dict)):
        return unknown("unsupported_coordinate_protocol")
    # Recovery is repeated from the same root, not copied from a prior report.
    columns = recover_columns(root, kernel_id, int_bits)
    chain = recover_chain(root, kernel_id, int_bits)
    launches = inspect_launch(root, kernel_id)
    result["recovery"].update(columns=columns, chain=chain, launches=launches)
    if columns.get("status") != "recovered" or chain.get("status") != "recovered":
        return unknown("column_or_reduction_recovery_incomplete")
    if columns.get("function_id") != kernel_id or chain.get("function_id") != kernel_id:
        return unknown("recovery_kernel_mismatch")
    loops = columns.get("loops")
    if not isinstance(loops, list) or not loops:
        return unknown("column_loops_missing")
    starts = []
    for loop in loops:
        if (not isinstance(loop, dict) or loop.get("status") != "recovered" or
                loop.get("step") != chain.get("block_threads")):
            return unknown("loop_not_recovered_or_step_mismatch")
        start = loop.get("start")
        if (not isinstance(start, dict) or start.get("kind") != "declaration_reference" or
                not isinstance(start.get("declaration_id"), str) or not start["declaration_id"]):
            return unknown("column_start_not_declaration")
        starts.append(start["declaration_id"])
    if len(set(starts)) != 1:
        return unknown("column_loops_have_different_starts")
    sites = launches.get("sites")
    if not isinstance(sites, list):
        return unknown("launch_sites_missing")
    matches = [site for site in sites if isinstance(site, dict) and site.get("launch_id") == launch_id]
    if len(matches) != 1:
        return unknown("selected_launch_not_unique")
    site = matches[0]
    arguments = site.get("configuration_arguments")
    if not isinstance(arguments, list) or len(arguments) != 4:
        return unknown("launch_configuration_incomplete")
    constructors = [inspect_constructor(root, expression, int_bits) for expression in arguments[:2]]
    for constructor in constructors:
        identifier = constructor.get("constructor_declaration_id")
        if identifier is not None:
            constructor["field_initialization"] = recover_fields(root, identifier)
    site = {**site, "configuration_constructor_arguments": constructors}
    block = check_block(chain, site, integer_types, binding.get("axis_binding"))
    result["checks"]["block"] = block
    if block["status"] != "checked":
        result.update(status=block["status"], reason="block_configuration_not_checked")
        return result
    dimensions = block.get("dimensions")
    if (not isinstance(dimensions, dict) or set(dimensions) != {"x", "y", "z"} or
            any(type(value) is not int for value in dimensions.values()) or
            not 1 <= dimensions["x"] <= 1024 or dimensions["y"] != 1 or dimensions["z"] != 1 or
            dimensions["x"] != chain.get("block_threads")):
        return unknown("checked_block_dimensions_invalid")
    origin = inspect_initializer(root, starts[0])
    result["recovery"]["initializer"] = origin
    link = origin.get("value_link")
    if (origin.get("status") != "evidence" or not isinstance(link, dict) or
            link.get("status") != "recovered"):
        return unknown("initializer_value_link_missing")
    leaf_domain = {
        "schema_version": "getter-leaf-domain/v1", "declaration_id": coordinate["declaration_id"],
        "arguments": [coordinate["axis"]], "return_type": coordinate["return_type"],
        "lower": 0, "upper": block["dimensions"]["x"] - 1,
    }
    result["derived_leaf_domain"] = leaf_domain
    getter = check_getter(root, link.get("callee_declaration_id"), leaf_domain, integer_types)
    result["checks"]["getter"] = getter
    if getter["status"] != "checked":
        result.update(status=getter["status"], reason="getter_return_domain_not_checked")
        return result
    if getter.get("input_sha256", {}).get("root") != root_hash:
        return unknown("getter_ast_binding_mismatch")
    initializer = check_initializer(link, getter, integer_types)
    result["checks"]["initializer"] = initializer
    if initializer["status"] != "checked":
        result.update(status=initializer["status"], reason="initializer_domain_not_checked")
        return result
    if initializer.get("result_type") != "int" or initializer.get("result_interval") != {"lower": 0, "upper": block["dimensions"]["x"] - 1}:
        return unknown("initializer_does_not_match_signed_column_start")
    result.update(status="checked", start_declaration_id=starts[0],
                  start_interval=initializer["result_interval"],
                  coordinate_conclusion="column_start_equals_local_x_under_explicit_API_and_launch_premises")
    return result
