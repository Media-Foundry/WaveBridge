"""Compare launch block fields under explicit axis identities, never infer axes by name."""
import hashlib
import json

from wavebridge.verification.constructor_values import check as check_fields


def check(chain, site, integer_types, axis_binding):
    result = {"schema_version": "block-configuration-check/v1", "status": "unknown",
              "reason": None, "field_check": None, "dimensions": None,
              "source_program_checked": False, "deployable": False,
              "premises": ["reports_faithfully_describe_same_ast",
                  "explicit_axis_field_binding_matches_launch_API",
                  "configuration_argument_1_is_block_dimensions",
                  "integer_ABI_and_declaration_constants_match_source_target",
                  "kernel_uses_x_coordinate_for_recovered_column_start",
                  "runtime_executes_reported_launch_without_other_configuration_changes"]}

    def unknown(reason):
        result["reason"] = reason
        return result

    if not all(isinstance(value, dict) for value in (chain, site, integer_types, axis_binding)):
        return unknown("inputs_not_objects")
    try:
        result["input_sha256"] = hashlib.sha256(json.dumps([chain, site, integer_types, axis_binding],
            sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    except (TypeError, ValueError, RecursionError):
        return unknown("input_hash_unsupported")
    if axis_binding.get("schema_version") != "launch-axis-assumptions/v1":
        return unknown("axis_binding_schema_missing")
    if chain.get("status") != "recovered" or not isinstance(chain.get("function_id"), str) or not chain["function_id"] or chain["function_id"] != site.get("kernel_declaration_id"):
        return unknown("chain_or_kernel_binding_missing")
    if not isinstance(site.get("launch_id"), str) or not site["launch_id"]:
        return unknown("launch_id_missing")
    if axis_binding.get("launch_id") != site["launch_id"]:
        return unknown("axis_launch_binding_mismatch")
    block = chain.get("block_threads")
    if type(block) is not int or not 1 <= block <= 1024:
        return unknown("block_model_unsupported")
    bits = chain.get("int_bits")
    integer = integer_types.get("int")
    if (type(bits) is not int or not 2 <= bits <= 128 or not isinstance(integer, dict)
            or type(integer.get("bits")) is not int or integer["bits"] != bits
            or integer.get("signed") is not True):
        return unknown("analysis_integer_abi_mismatch")
    constructors = site.get("configuration_constructor_arguments")
    if not isinstance(constructors, list) or len(constructors) != 2 or not isinstance(constructors[1], dict):
        return unknown("block_constructor_missing")
    constructor = constructors[1]
    identifier = constructor.get("constructor_declaration_id")
    if not isinstance(identifier, str) or not identifier or axis_binding.get("constructor_declaration_id") != identifier:
        return unknown("axis_constructor_binding_mismatch")
    axes = axis_binding.get("fields")
    if not isinstance(axes, dict) or set(axes) != {"x", "y", "z"} or any(not isinstance(v, str) or not v for v in axes.values()) or len(set(axes.values())) != 3:
        return unknown("axis_field_binding_invalid")
    fields = check_fields(constructor, constructor.get("field_initialization"), integer_types)
    result["field_check"] = fields
    if fields["status"] != "checked":
        result["status"] = fields["status"]
        result["reason"] = "block_field_values_not_checked"
        return result
    values = {item["field_id"]: item["value"] for item in fields["fields"]}
    if set(values) != set(axes.values()):
        return unknown("axis_fields_do_not_cover_record")
    dimensions = {axis: values[field] for axis, field in axes.items()}
    result.update(dimensions=dimensions, expected_dimensions={"x": block, "y": 1, "z": 1})
    if dimensions != result["expected_dimensions"]:
        result.update(status="rejected", reason="block_dimensions_disagree_with_one_dimensional_model")
    else:
        result["status"] = "checked"
    return result
