"""Freshly connect direct constructor arguments to field value intervals.

This composition checks only evaluation-time integer values for one exact
direct construction expression.  It does not establish launch, copy/move, or
deployment semantics, and it never rewrites frontend report status.
"""

from __future__ import annotations

from typing import Any

from wavebridge.analysis.constructor_arguments import inspect as inspect_constructor
from wavebridge.analysis.constructor_fields import recover as recover_fields
from wavebridge.verification.constructor_effects import check as check_constructor_effects
from wavebridge.verification.constructor_values import (
    _Rejected,
    _Unknown,
    _abi_type,
    _apply_casts,
    _argument_leaf,
)
from wavebridge.verification.integer_selection import _hash, check as check_selection

MAX_AST_NODES = 1_000_000
HARD_MAX_AST_NODES = 10_000_000
MAX_FIELDS = 64
MAX_WRAPPERS = 256


def _children(node: object, *, strict: bool = True) -> list[dict[str, Any]]:
    if not isinstance(node, dict):
        raise _Unknown("ast_node_not_object")
    children = node.get("inner", [])
    if not isinstance(children, list) or any(not isinstance(child, dict) for child in children):
        raise _Unknown("ast_children_not_list_of_objects")
    if strict and any(not child for child in children):
        raise _Unknown("selected_ast_contains_empty_placeholder")
    return [child for child in children if child]


def _literal_casts(argument: dict[str, Any], leaf: dict[str, Any],
                   integer_types: dict[str, Any]) -> None:
    """Match reported casts to the complete raw/default-source wrapper chain."""
    raw = argument.get("argument_ast")
    current = (argument.get("default_source_ast")
               if argument.get("default_argument") is True else raw)
    if not isinstance(current, dict):
        raise _Unknown("literal_source_ast_missing")
    if argument.get("default_argument") is True:
        if not isinstance(raw, dict) or raw.get("kind") != "CXXDefaultArgExpr":
            raise _Rejected("literal_default_callpoint_mismatch")
        raw_children = _children(raw)
        if argument.get("default_source_binding") is None:
            if len(raw_children) != 1 or current != raw_children[0]:
                raise _Rejected("literal_default_source_child_mismatch")
        elif raw_children:
            raise _Rejected("literal_bound_default_unexpected_callpoint_child")
    casts: list[dict[str, Any]] = []
    wrappers = 0
    while current.get("kind") in {"ParenExpr", "ImplicitCastExpr"}:
        wrappers += 1
        children = _children(current)
        if (wrappers > MAX_WRAPPERS or len(children) != 1 or
                current.get("valueCategory") != "prvalue"):
            raise _Unknown("literal_wrapper_shape_or_budget")
        child = children[0]
        parent_abi = _abi_type(current.get("type"), integer_types)
        child_abi = _abi_type(child.get("type"), integer_types)
        if current.get("kind") == "ParenExpr":
            if parent_abi != child_abi:
                raise _Rejected("literal_parenthesis_type_discontinuity")
        else:
            if current.get("castKind") not in {"IntegralCast", "NoOp"}:
                raise _Unknown("literal_cast_unsupported")
            if current.get("castKind") == "NoOp" and parent_abi != child_abi:
                raise _Rejected("literal_nonconverting_cast_type_discontinuity")
            casts.append({
                "kind": "ImplicitCastExpr", "cast_kind": current.get("castKind"),
                "source_type": child.get("type"),
                "destination_type": current.get("type"), "range": current.get("range"),
            })
        current = child
    if (current != leaf or leaf.get("kind") != "IntegerLiteral" or
            leaf.get("valueCategory") != "prvalue" or _children(leaf)):
        raise _Rejected("literal_leaf_not_from_recorded_source")
    _abi_type(leaf.get("type"), integer_types)
    reported = argument.get("casts")
    if (not isinstance(reported, list) or len(reported) != len(casts) or
            any(not isinstance(item, dict) or
                any(item.get(key) != value for key, value in expected.items())
                for item, expected in zip(reported, casts))):
        raise _Rejected("literal_cast_evidence_mismatch")


def check(root: object, expression_id: object, integer_types: object,
          selection_domains: object, *, max_ast_nodes: int | None = None) -> dict[str, Any]:
    budget = MAX_AST_NODES if max_ast_nodes is None else max_ast_nodes
    result: dict[str, Any] = {
        "schema_version": "source-constructor-values-check/v1",
        "status": "unknown", "reason": None, "expression_id": expression_id,
        "constructor_arguments": None, "constructor_fields": None,
        "constructor_effects": None,
        "selection_checks": [], "fields": [], "conversion_checks": [],
        "scope": "direct_constructor_evaluation_time_integer_field_domains",
        "source_program_checked": False, "deployable": False,
        "copy_or_move_semantics": "not_established", "launch_semantics": "not_established",
        "call_argument_effects": "not_established",
        "post_construction_escape": "not_established",
        "assumptions": [
            "the AST is a faithful complete single translation unit",
            "the explicit integer ABI matches the compilation target",
            "each supplied selection declaration interval contains its runtime value",
            "selection references and materialized temporaries remain alive through each call and immediate read",
            "source expressions are valid and checked calls return normally",
        ],
        "budget": {"max_ast_nodes": budget, "max_fields": MAX_FIELDS,
                   "max_literal_wrappers": MAX_WRAPPERS},
    }
    if type(budget) is not int or not 1 <= budget <= HARD_MAX_AST_NODES:
        result["reason"] = "invalid_ast_node_budget"
        return result
    if (not isinstance(root, dict) or not isinstance(expression_id, str) or not expression_id or
            not isinstance(integer_types, dict) or not isinstance(selection_domains, dict) or
            any(not isinstance(key, str) or not key or not isinstance(value, list)
                for key, value in selection_domains.items())):
        result["reason"] = "invalid_inputs"
        return result
    try:
        result["input_sha256"] = {
            "root": _hash(root), "expression_id": _hash(expression_id),
            "integer_types": _hash(integer_types),
            "selection_domains": _hash(selection_domains),
        }
    except (TypeError, ValueError, RecursionError):
        result["reason"] = "input_hash_unsupported"
        return result

    try:
        nodes: list[dict[str, Any]] = []
        pending = [root]
        while pending:
            node = pending.pop()
            if not isinstance(node, dict):
                raise _Unknown("ast_node_not_object")
            nodes.append(node)
            if len(nodes) > budget:
                raise _Unknown("ast_node_budget_exceeded")
            pending.extend(_children(node, strict=False))
        matches = [node for node in nodes if node.get("id") == expression_id]
        if len(matches) != 1:
            raise _Unknown("constructor_expression_id_not_unique")
        expression = matches[0]
        if expression.get("kind") != "CXXConstructExpr":
            raise _Unknown("expression_not_direct_constructor")

        int_abi = _abi_type({"qualType": "int"}, integer_types)
        arguments = inspect_constructor(root, expression, int_abi[1], max_ast_nodes=budget)
        result["constructor_arguments"] = arguments
        if (arguments.get("status") != "inspected" and not
                (arguments.get("status") == "unknown" and
                 arguments.get("reason") == "one_or_more_arguments_unknown")):
            raise _Unknown("constructor_argument_recovery_unsupported")
        identity = arguments.get("constructor_identity", {})
        if (identity.get("mode") !=
                "exact_alias_record_and_unique_selected_constructor_type"):
            raise _Unknown("constructor_not_exact_direct_identity")
        constructor_id = arguments.get("constructor_declaration_id")
        record_id = identity.get("record_declaration_id")
        if (not isinstance(constructor_id, str) or not constructor_id or
                not isinstance(record_id, str) or not record_id):
            raise _Unknown("constructor_declaration_id_missing")
        effects = check_constructor_effects(root, constructor_id, integer_types,
                                            max_ast_nodes=budget)
        result["constructor_effects"] = effects
        if (effects.get("status") != "checked" or
                effects.get("constructor_declaration_id") != constructor_id or
                effects.get("record_declaration_id") != record_id):
            raise _Unknown("constructor_effects_not_checked")
        fields = recover_fields(root, constructor_id)
        result["constructor_fields"] = fields
        if fields.get("status") != "recovered":
            raise _Unknown("constructor_field_recovery_unsupported")
        if (fields.get("constructor_declaration_id") != constructor_id or
                fields.get("record_declaration_id") != record_id or
                fields.get("record_completeness") != "all_direct_record_fields_initialized"):
            raise _Unknown("constructor_fields_not_complete_direct_record")

        argument_items = arguments.get("arguments")
        mappings = fields.get("field_mappings")
        declaration = arguments.get("default_constructor_declaration_ast")
        if (not isinstance(argument_items, list) or not isinstance(mappings, list) or
                not isinstance(declaration, dict) or declaration.get("kind") != "CXXConstructorDecl" or
                declaration.get("id") != constructor_id or not argument_items or
                len(argument_items) > MAX_FIELDS or len(argument_items) != len(mappings)):
            raise _Unknown("constructor_arguments_or_fields_shape_unsupported")
        expression_arguments = _children(expression)
        parameters = [child for child in _children(declaration)
                      if child.get("kind") == "ParmVarDecl"]
        if len(expression_arguments) != len(argument_items) or len(parameters) != len(argument_items):
            raise _Rejected("constructor_argument_parameter_count_mismatch")
        parameter_ids = [parameter.get("id") for parameter in parameters]
        if (any(not isinstance(identifier, str) or not identifier for identifier in parameter_ids) or
                len(set(parameter_ids)) != len(parameter_ids)):
            raise _Unknown("constructor_parameter_ids_invalid")
        for parameter, identifier in zip(parameters, parameter_ids):
            occurrences = [node for node in nodes if node.get("id") == identifier]
            if len(occurrences) != 1 or occurrences[0] is not parameter:
                raise _Unknown("constructor_parameter_declaration_not_unique")

        mapping_by_position: dict[int, dict[str, Any]] = {}
        field_ids: set[str] = set()
        mapped_parameter_ids: set[str] = set()
        for mapping in mappings:
            if not isinstance(mapping, dict):
                raise _Unknown("field_mapping_not_object")
            position, field_id, parameter_id = (mapping.get("parameter_position"),
                                                mapping.get("field_id"),
                                                mapping.get("parameter_id"))
            if (type(position) is not int or not 0 <= position < len(parameters) or
                    position in mapping_by_position or not isinstance(field_id, str) or not field_id or
                    field_id in field_ids or not isinstance(parameter_id, str) or
                    parameter_id in mapped_parameter_ids):
                raise _Rejected("field_mapping_identity_or_position_mismatch")
            parameter = parameters[position]
            if (parameter_id != parameter.get("id") or
                    mapping.get("parameter_type") != parameter.get("type")):
                raise _Rejected("field_mapping_parameter_binding_mismatch")
            mapping_by_position[position] = mapping
            field_ids.add(field_id)
            mapped_parameter_ids.add(parameter_id)
        if set(mapping_by_position) != set(range(len(parameters))):
            raise _Rejected("field_mapping_positions_not_complete")

        required_selection_keys: set[str] = set()
        checked_fields: list[dict[str, Any]] = []
        all_conversions: list[dict[str, Any]] = []
        for position, (argument, original_ast, parameter) in enumerate(
                zip(argument_items, expression_arguments, parameters)):
            if (not isinstance(argument, dict) or argument.get("position") != position or
                    argument.get("argument_ast") != original_ast):
                raise _Rejected("constructor_argument_ast_or_position_mismatch")
            mapping = mapping_by_position[position]
            if (_abi_type(original_ast.get("type"), integer_types) !=
                    _abi_type(parameter.get("type"), integer_types)):
                raise _Rejected("constructor_argument_parameter_type_mismatch")
            leaf = _argument_leaf(argument, arguments, mapping, integer_types)
            argument_id = original_ast.get("id")
            if leaf.get("kind") == "IntegerLiteral":
                _literal_casts(argument, leaf, integer_types)
                try:
                    value = int(str(leaf.get("value")), 0)
                except (TypeError, ValueError):
                    raise _Unknown("literal_value_invalid")
                argument_checks: list[dict[str, Any]] = []
                _apply_casts(value, value, leaf.get("type"), argument.get("casts"),
                             parameter.get("type"), integer_types, argument_checks, "constant")
                lower = upper = value
                value_evidence = {"value_kind": "constant", "value": value}
            else:
                if not isinstance(argument_id, str) or not argument_id:
                    raise _Unknown("selection_argument_expression_id_missing")
                required_selection_keys.add(argument_id)
                domain = selection_domains.get(argument_id)
                if domain is None:
                    raise _Unknown("selection_domain_missing")
                selection = check_selection(root, argument_id, domain, integer_types,
                                            max_ast_nodes=budget)
                result["selection_checks"].append({"position": position, "report": selection})
                if selection.get("status") == "rejected":
                    raise _Rejected("selection_argument_rejected", selection)
                if selection.get("status") != "checked":
                    raise _Unknown("selection_argument_unknown")
                interval = selection.get("return_interval")
                if (not isinstance(interval, dict) or type(interval.get("lower")) is not int or
                        type(interval.get("upper")) is not int or interval["lower"] > interval["upper"]):
                    raise _Unknown("selection_result_interval_invalid")
                selection_type = selection.get("result_type")
                expected_abi = _abi_type(parameter.get("type"), integer_types)
                if (_abi_type(original_ast.get("type"), integer_types) != expected_abi or
                        _abi_type(selection_type, integer_types) != expected_abi or
                        _abi_type(mapping.get("parameter_type"), integer_types) != expected_abi):
                    raise _Rejected("selection_result_type_or_parameter_mismatch")
                lower, upper = interval["lower"], interval["upper"]
                argument_checks = []
                value_evidence = {"value_kind": "interval",
                                  "interval": {"lower": lower, "upper": upper},
                                  "selection_expression_id": argument_id}

            field_checks: list[dict[str, Any]] = []
            _apply_casts(lower, upper, parameter.get("type"), mapping.get("casts"),
                         mapping.get("field_type"), integer_types, field_checks,
                         value_evidence["value_kind"])
            all_conversions.append({"field_id": mapping.get("field_id"),
                                    "parameter_position": position,
                                    "argument_casts": argument_checks,
                                    "field_initializer_casts": field_checks})
            checked_fields.append({"field_id": mapping.get("field_id"),
                                   "field_name": mapping.get("field_name"),
                                   "parameter_position": position, **value_evidence})

        if required_selection_keys != set(selection_domains):
            raise _Unknown("selection_domains_not_exactly_consumed")
        result.update(status="checked", fields=checked_fields,
                      conversion_checks=all_conversions)
    except _Rejected as error:
        result.update(status="rejected", reason=error.reason)
        if error.detail is not None:
            result["diagnostic"] = error.detail
    except _Unknown as error:
        result["reason"] = error.reason
    return result
