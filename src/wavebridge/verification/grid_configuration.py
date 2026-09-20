"""Conditionally interpret launch grid fields under explicit axis identities."""

from __future__ import annotations

from typing import Any

from wavebridge.verification.constructor_values import check as check_fields
from wavebridge.verification.getter_returns import _hash


def check(site: object, integer_types: object, axis_binding: object,
          declaration_intervals: object) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema_version": "grid-configuration-check/v1", "status": "unknown",
        "reason": None, "field_check": None, "dimensions": None,
        "counterexample": None, "source_program_checked": False, "deployable": False,
        "scope": "conditional_one_dimensional_grid_domains_from_explicit_axis_field_ids",
        "premises": [
            "the supplied launch and constructor reports faithfully describe the same source AST",
            "the explicit field IDs denote the launch API x, y and z grid axes",
            "configuration argument 0 is the grid-dimensions constructor",
            "the supplied declaration intervals are external necessary-condition overapproximations",
            "the explicit integer ABI matches the source compilation target",
        ],
        "limitations": [
            "interval values are not claimed to be reachable",
            "no hardware grid limit or block-index execution semantics is inferred",
            "runtime launch execution and complete source validity are not checked",
        ],
    }

    def unknown(reason: str) -> dict[str, Any]:
        result["reason"] = reason
        return result

    if (not isinstance(site, dict) or not isinstance(integer_types, dict) or
            not isinstance(axis_binding, dict) or not isinstance(declaration_intervals, list)):
        return unknown("inputs_not_expected_objects")
    try:
        result["input_sha256"] = {
            "site": _hash(site), "integer_types": _hash(integer_types),
            "axis_binding": _hash(axis_binding),
            "declaration_intervals": _hash(declaration_intervals),
        }
    except (TypeError, ValueError, RecursionError):
        return unknown("input_hash_unsupported")
    if axis_binding.get("schema_version") != "launch-axis-assumptions/v1":
        return unknown("axis_binding_schema_missing")
    launch_id = site.get("launch_id")
    if not isinstance(launch_id, str) or not launch_id:
        return unknown("launch_id_missing")
    if axis_binding.get("launch_id") != launch_id:
        return unknown("axis_launch_binding_mismatch")
    axes = axis_binding.get("fields")
    if (not isinstance(axes, dict) or set(axes) != {"x", "y", "z"} or
            any(not isinstance(value, str) or not value for value in axes.values()) or
            len(set(axes.values())) != 3):
        return unknown("axis_field_binding_invalid")
    constructors = site.get("configuration_constructor_arguments")
    if (not isinstance(constructors, list) or len(constructors) != 2 or
            not isinstance(constructors[0], dict)):
        return unknown("grid_constructor_missing")
    constructor = constructors[0]
    constructor_id = constructor.get("constructor_declaration_id")
    if (not isinstance(constructor_id, str) or not constructor_id or
            axis_binding.get("constructor_declaration_id") != constructor_id):
        return unknown("axis_constructor_binding_mismatch")
    field_check = check_fields(constructor, constructor.get("field_initialization"),
                               integer_types, declaration_intervals)
    result["field_check"] = field_check
    if field_check.get("status") != "checked":
        return unknown("grid_field_values_not_checked")
    fields = field_check.get("fields")
    if not isinstance(fields, list):
        return unknown("grid_fields_missing")
    by_id: dict[str, dict[str, int]] = {}
    for field in fields:
        if not isinstance(field, dict):
            return unknown("grid_field_entry_invalid")
        field_id = field.get("field_id")
        if not isinstance(field_id, str) or not field_id or field_id in by_id:
            return unknown("grid_field_ids_missing_or_repeated")
        if field.get("value_kind") == "constant":
            value = field.get("value")
            if type(value) is not int:
                return unknown("grid_constant_value_invalid")
            interval = {"lower": value, "upper": value}
        elif field.get("value_kind") == "interval":
            raw = field.get("interval")
            if (not isinstance(raw, dict) or type(raw.get("lower")) is not int or
                    type(raw.get("upper")) is not int or raw["lower"] > raw["upper"]):
                return unknown("grid_interval_value_invalid")
            interval = {"lower": raw["lower"], "upper": raw["upper"]}
        else:
            return unknown("grid_field_value_kind_unsupported")
        by_id[field_id] = interval
    if set(by_id) != set(axes.values()):
        return unknown("axis_fields_do_not_cover_record")
    dimensions = {axis: by_id[field_id] for axis, field_id in axes.items()}
    result["dimensions"] = dimensions
    x, y, z = dimensions["x"], dimensions["y"], dimensions["z"]
    if x["lower"] < 1:
        result.update(status="rejected", reason="grid_x_domain_contains_nonpositive_value",
                      counterexample={"axis": "x", "value": x["lower"],
                                      "conditional_domain_counterexample": True})
        return result
    for axis, interval in (("y", y), ("z", z)):
        if interval != {"lower": 1, "upper": 1}:
            value = interval["lower"] if interval["lower"] != 1 else interval["upper"]
            result.update(status="rejected", reason="grid_domain_not_one_dimensional",
                          counterexample={"axis": axis, "value": value,
                                          "conditional_domain_counterexample": True})
            return result
    result["status"] = "checked"
    return result
