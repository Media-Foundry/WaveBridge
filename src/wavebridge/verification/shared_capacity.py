"""Conditional capacity comparison, not a source or memory-safety proof."""
from wavebridge.verification.shared_bytes import check as check_bytes


def check(chain, site, integer_types, sizeof_bytes):
    result = {"schema_version": "shared-capacity-check/v1", "status": "unknown",
              "reason": None, "required_bytes": None, "available_bytes": None,
              "byte_expression_check": None, "source_program_checked": False,
              "deployable": False,
              "premises": ["source_reports_faithfully_describe_same_ast",
                  "explicit_integer_and_element_size_abi_matches_target",
                  "launch_configuration_argument_2_is_dynamic_shared_bytes",
                  "actual_block_and_coordinates_match_recovered_block_model",
                  "one_shared_array_at_offset_zero_without_other_dynamic_allocations",
                  "source_validity_aliasing_and_collective_participation"]}

    def unknown(reason):
        result["reason"] = reason
        return result

    if not isinstance(chain, dict) or chain.get("status") != "recovered":
        return unknown("reduction_chain_not_recovered")
    if not isinstance(site, dict) or not isinstance(site.get("launch_id"), str) or not site["launch_id"]:
        return unknown("launch_id_missing")
    if not isinstance(site, dict) or not isinstance(chain.get("function_id"), str) or not chain["function_id"] or site.get("kernel_declaration_id") != chain["function_id"]:
        return unknown("launch_kernel_mismatch")
    storage = chain.get("shared_storage")
    if not isinstance(storage, dict) or storage.get("status") != "recovered":
        return unknown("array_binding_not_recovered")
    if storage.get("schema_version") != "source-array-binding/v1" or storage.get("shared_attribute_present") is not True:
        return unknown("shared_storage_evidence_missing")
    if not isinstance(integer_types, dict) or not isinstance(sizeof_bytes, dict):
        return unknown("abi_missing")
    int_type = integer_types.get("int", {})
    if (not isinstance(int_type, dict) or type(chain.get("int_bits")) is not int or not 2 <= chain["int_bits"] <= 128 or
            type(int_type.get("bits")) is not int or int_type.get("bits") != chain["int_bits"] or
            int_type.get("signed") is not True):
        return unknown("analysis_integer_abi_mismatch")
    block, width = chain.get("block_threads"), chain.get("width")
    if (type(block) is not int or type(width) is not int or not 1 <= block <= 1024 or
            not 2 <= width <= 64 or width & (width - 1) or block % width or block // width > width):
        return unknown("unsupported_block_model")
    size = sizeof_bytes.get("float")
    if type(size) is not int or not 1 <= size <= 1048576:
        return unknown("float_size_assumption_missing_or_invalid")
    required = block // width * size
    kind = storage.get("storage_kind")
    if kind == "shared_static":
        if storage.get("capacity_status") != "declared_static_extent":
            return unknown("static_storage_evidence_inconsistent")
        extent = storage.get("extent_elements")
        if storage.get("storage_class") == "extern" or type(extent) is not int or extent <= 0:
            return unknown("static_extent_not_established")
        available = extent * size
    elif kind == "shared_dynamic":
        if storage.get("capacity_status") != "launch_bytes_required" or storage.get("storage_class") != "extern":
            return unknown("dynamic_storage_evidence_inconsistent")
        arguments = site.get("configuration_arguments")
        if not isinstance(arguments, list) or len(arguments) != 4:
            return unknown("launch_configuration_missing")
        byte_check = check_bytes(arguments[2], integer_types, sizeof_bytes)
        result["byte_expression_check"] = byte_check
        if byte_check.get("status") != "checked":
            return unknown("launch_bytes_not_established")
        available = byte_check["value_bytes"]
    else:
        return unknown("storage_not_proven_shared")
    result.update(status="checked" if available >= required else "rejected",
                  reason=None if available >= required else "insufficient_shared_capacity",
                  required_bytes=required, available_bytes=available,
                  required_elements=block // width)
    return result
