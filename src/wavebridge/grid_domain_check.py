"""Recover selected launch grid fields under explicit host-guard assumptions."""

from wavebridge.analysis.launch_facts import inspect as inspect_launch
from wavebridge.analysis.constructor_arguments import inspect as inspect_constructor
from wavebridge.analysis.constructor_fields import recover as recover_fields
from wavebridge.analysis.launch_guards import recover as recover_guards
from wavebridge.verification.grid_configuration import check as check_grid
from wavebridge.verification.getter_returns import _hash


def check(root, kernel_id, launch_id, integer_types, binding, *, int_bits=32,
          use_host_guard_assumptions=False):
    result = {
        "schema_version": "conditional-grid-domain-check/v1", "status": "unknown", "reason": None,
        "source_program_checked": False, "deployable": False,
        "scope": "one_selected_launch_grid_field_domains_under_explicit_axis_and_guard_assumptions",
        "premises": ["frontend and original AST are faithful",
                     "host guard intervals are necessary conditions for reaching this launch",
                     "explicit field axes and configuration position match the runtime launch API",
                     "runtime executes the reported configuration with the declared integer ABI"],
        "limitations": ["does not prove all values in the interval are reachable",
                        "does not assign block-id semantics or prove hardware launch limits"],
    }

    def unknown(reason):
        result["reason"] = reason
        return result

    if type(use_host_guard_assumptions) is not bool or not use_host_guard_assumptions:
        return unknown("host_guard_assumptions_must_be_enabled")
    if (not all(isinstance(obj, dict) for obj in (root, integer_types, binding)) or
            any(not isinstance(value, str) or not value for value in (kernel_id, launch_id))):
        return unknown("invalid_inputs")
    try:
        result["input_sha256"] = {"root": _hash(root), "integer_types": _hash(integer_types),
                                  "binding": _hash(binding), "int_bits": _hash(int_bits)}
    except (TypeError, ValueError, RecursionError):
        return unknown("input_hash_unsupported")
    if (binding.get("schema_version") != "grid-domain-assumptions/v1" or
            binding.get("ast_root_sha256") != result["input_sha256"]["root"] or
            binding.get("kernel_declaration_id") != kernel_id or binding.get("launch_id") != launch_id or
            type(binding.get("configuration_position")) is not int or binding["configuration_position"] != 0):
        return unknown("grid_binding_mismatch")
    ty = integer_types.get("int")
    if (type(int_bits) is not int or not 2 <= int_bits <= 128 or not isinstance(ty, dict) or
            type(ty.get("bits")) is not int or ty["bits"] != int_bits or ty.get("signed") is not True):
        return unknown("analysis_integer_abi_mismatch")
    launches = inspect_launch(root, kernel_id)
    sites = [site for site in launches.get("sites", []) if site.get("launch_id") == launch_id]
    if len(sites) != 1 or sites[0].get("kernel_declaration_id") != kernel_id:
        return unknown("selected_launch_not_uniquely_bound")
    site = sites[0]
    arguments = site.get("configuration_arguments")
    if not isinstance(arguments, list) or len(arguments) != 4:
        return unknown("configuration_arguments_missing")
    constructor = inspect_constructor(root, arguments[0], int_bits)
    identifier = constructor.get("constructor_declaration_id")
    if not isinstance(identifier, str) or not identifier:
        return unknown("grid_constructor_missing")
    constructor = {**constructor, "field_initialization": recover_fields(root, identifier)}
    guards = recover_guards(root, launch_id, int_bits)
    result["guard_recovery"] = guards
    if (guards.get("schema_version") != "launch-guards/v1" or guards.get("status") != "recovered" or
            guards.get("launch_id") != launch_id or guards.get("int_bits") != int_bits or
            guards.get("interpretation") != "necessary_conditions_to_pass_supported_early_returns_only"):
        return unknown("guard_domain_not_recovered")
    site = {**site, "configuration_constructor_arguments": [constructor, None]}
    grid = check_grid(site, integer_types, binding.get("axis_binding"), guards.get("intervals"))
    result["grid"] = grid
    result.update(status=grid["status"], reason=grid.get("reason"), kernel_declaration_id=kernel_id,
                  launch_id=launch_id)
    if grid["status"] == "checked":
        result["dimensions"] = grid["dimensions"]
    return result
