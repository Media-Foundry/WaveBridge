"""Connect a recovered row initializer to a checked grid and explicit block-ID API."""

from wavebridge.grid_domain_check import check as check_grid
from wavebridge.analysis.row_prefix import recover as recover_prefix
from wavebridge.verification.getter_returns import check as check_getter, _hash
from wavebridge.verification.initializer_domain import check as check_initializer


def check(root, kernel_id, launch_id, integer_types, binding, *, int_bits=32,
          use_host_guard_assumptions=False):
    result = {
        "schema_version": "conditional-row-coordinate-check/v1", "status": "unknown", "reason": None,
        "source_program_checked": False, "deployable": False,
        "scope": "one_selected_launch_row_initializer_under_explicit_workgroup_id_semantics",
        "checks": {},
        "premises": ["fresh grid check premises hold, including actual runtime configuration",
                     "the exact external leaf(axis=0) denotes workgroup x ID in [0, grid.x-1]",
                     "source, receiver evaluation and explicit integer ABI are valid",
                     "frontend initializer and row-prefix recovery are faithful"],
        "limitations": ["row interval is an overapproximation across the grid domain",
                        "does not prove pointer offsets, allocation bounds, participation or numerical results"],
    }

    def unknown(reason):
        result["reason"] = reason
        return result

    if (not all(isinstance(obj, dict) for obj in (root, integer_types, binding)) or
            any(not isinstance(value, str) or not value for value in (kernel_id, launch_id))):
        return unknown("invalid_inputs")
    try:
        root_hash = _hash(root)
        result["input_sha256"] = {"root": root_hash, "binding": _hash(binding),
                                  "integer_types": _hash(integer_types), "int_bits": _hash(int_bits)}
    except (TypeError, ValueError, RecursionError):
        return unknown("input_hash_unsupported")
    if (binding.get("schema_version") != "row-coordinate-assumptions/v1" or
            binding.get("ast_root_sha256") != root_hash or
            binding.get("kernel_declaration_id") != kernel_id or binding.get("launch_id") != launch_id):
        return unknown("row_binding_mismatch")
    coordinate = binding.get("coordinate")
    if (not isinstance(coordinate, dict) or coordinate.get("semantics") != "workgroup_id" or
            type(coordinate.get("axis")) is not int or coordinate["axis"] != 0 or
            not isinstance(coordinate.get("declaration_id"), str) or not coordinate["declaration_id"] or
            not isinstance(coordinate.get("return_type"), dict)):
        return unknown("workgroup_coordinate_protocol_missing")
    grid = check_grid(root, kernel_id, launch_id, integer_types, binding.get("grid_binding"),
                      int_bits=int_bits, use_host_guard_assumptions=use_host_guard_assumptions)
    result["checks"]["grid"] = grid
    if grid.get("status") != "checked":
        result.update(status=grid.get("status", "unknown"), reason="grid_domain_not_checked")
        return result
    dimensions = grid.get("dimensions")
    if not isinstance(dimensions, dict) or set(dimensions) != {"x", "y", "z"}:
        return unknown("grid_dimensions_missing")
    for axis in ("x", "y", "z"):
        interval = dimensions[axis]
        if (not isinstance(interval, dict) or type(interval.get("lower")) is not int or
                type(interval.get("upper")) is not int or not 1 <= interval["lower"] <= interval["upper"] or
                (axis != "x" and interval != {"lower": 1, "upper": 1})):
            return unknown("grid_dimensions_not_positive_one_dimensional")
    prefix = recover_prefix(root, kernel_id, int_bits)
    result["prefix_recovery"] = prefix
    if (prefix.get("status") != "recovered" or prefix.get("function_id") != kernel_id or
            not isinstance(prefix.get("row_declaration_id"), str) or not prefix["row_declaration_id"]):
        return unknown("row_prefix_not_recovered")
    origin = prefix.get("row_initializer_evidence")
    link = origin.get("value_link") if isinstance(origin, dict) else None
    if (not isinstance(origin, dict) or origin.get("status") != "evidence" or
            not isinstance(link, dict) or link.get("status") != "recovered"):
        return unknown("row_initializer_value_link_missing")
    domain = {"schema_version": "getter-leaf-domain/v1", "declaration_id": coordinate["declaration_id"],
              "arguments": [0], "return_type": coordinate["return_type"],
              "lower": 0, "upper": dimensions["x"]["upper"] - 1}
    result["derived_leaf_domain"] = domain
    getter = check_getter(root, link.get("callee_declaration_id"), domain, integer_types)
    result["checks"]["getter"] = getter
    if getter.get("status") != "checked":
        result.update(status=getter.get("status", "unknown"), reason="row_getter_not_checked")
        return result
    if getter.get("input_sha256", {}).get("root") != root_hash:
        return unknown("getter_root_mismatch")
    initializer = check_initializer(link, getter, integer_types)
    result["checks"]["initializer"] = initializer
    if initializer.get("status") != "checked":
        result.update(status=initializer.get("status", "unknown"), reason="row_initializer_not_checked")
        return result
    interval = {"lower": domain["lower"], "upper": domain["upper"]}
    if initializer.get("result_type") != "int" or initializer.get("result_interval") != interval:
        return unknown("row_initializer_not_expected_signed_domain")
    result.update(status="checked", kernel_declaration_id=kernel_id, launch_id=launch_id,
                  row_declaration_id=prefix["row_declaration_id"], row_interval=interval,
                  conclusion="row_initializer_equals_workgroup_x_under_explicit_protocol")
    return result
