"""Verify constructor field constants under an explicit integer ABI model."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from wavebridge.verification.integer_conversion import check_interval

MAX_FIELDS = 64
MAX_CASTS = 256
ALLOWED_CASTS = {"LValueToRValue", "NoOp", "IntegralCast"}


class _Unknown(Exception):
    def __init__(self, reason: str):
        self.reason = reason


class _Rejected(Exception):
    def __init__(self, reason: str, detail: object = None):
        self.reason, self.detail = reason, detail


def _hash(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def _raw_type(type_value: object) -> str:
    if not isinstance(type_value, dict):
        raise _Unknown("type_evidence_missing")
    value = type_value.get("desugaredQualType") or type_value.get("qualType")
    if not isinstance(value, str):
        raise _Unknown("type_evidence_missing")
    return value


def _base_type(type_value: object) -> str:
    value = _raw_type(type_value)
    words = value.split()
    if "volatile" in words or "*" in value or "&" in value:
        raise _Unknown("volatile_pointer_or_reference_type_unsupported")
    while words and words[0] == "const":
        words.pop(0)
    normalized = " ".join(words)
    if not normalized:
        raise _Unknown("empty_integer_type")
    return normalized


def _abi_type(type_value: object, abi: dict[str, Any]) -> tuple[str, int, bool]:
    name = _base_type(type_value)
    specification = abi.get(name)
    if not isinstance(specification, dict):
        raise _Unknown("integer_type_missing_from_abi")
    bits, signed = specification.get("bits"), specification.get("signed")
    if type(bits) is not int or not 2 <= bits <= 128 or type(signed) is not bool:
        raise _Unknown("invalid_abi_type_entry")
    return name, bits, signed


def _children(node: object) -> list[dict[str, Any]]:
    if not isinstance(node, dict) or not isinstance(node.get("inner"), list):
        return []
    return [child for child in node["inner"] if isinstance(child, dict) and child]


def _leaf(node: object) -> dict[str, Any]:
    if not isinstance(node, dict):
        raise _Unknown("raw_argument_ast_missing")
    current = node
    if current.get("kind") == "CXXDefaultArgExpr":
        children = _children(current)
        if len(children) != 1:
            raise _Unknown("raw_default_argument_source_missing")
        current = children[0]
    while isinstance(current.get("kind"), str) and current.get("kind") in ("ParenExpr", "ImplicitCastExpr"):
        children = _children(current)
        if len(children) != 1:
            raise _Unknown("raw_argument_wrapper_ambiguous")
        current = children[0]
    return current


def _argument_leaf(argument, constructor_report, mapping, abi):
    """Recheck separately recorded parameter defaults without inventing AST children.

    Same-TU provenance/redeclaration exclusion is a frontend premise, as for
    existing field recovery. Parameter ownership, source and casts are checked
    here independently of the reported constant value.
    """
    raw = argument.get("argument_ast")
    binding = argument.get("default_source_binding")
    if binding is None:
        return _leaf(raw)
    declaration = constructor_report.get("default_constructor_declaration_ast")
    constructor_id = constructor_report.get("constructor_declaration_id")
    if (not isinstance(raw, dict) or raw.get("kind") != "CXXDefaultArgExpr" or
            raw.get("inner", []) != [] or argument.get("default_argument") is not True or
            not isinstance(binding, dict) or
            binding.get("schema_version") != "constructor-default-source/v1" or
            binding.get("constructor_declaration_id") != constructor_id or
            not isinstance(declaration, dict) or declaration.get("kind") != "CXXConstructorDecl" or
            declaration.get("id") != constructor_id or declaration.get("previousDecl") is not None):
        raise _Unknown("default_parameter_source_binding_missing_or_unsupported")
    position = binding.get("parameter_position")
    parameters = [node for node in _children(declaration) if node.get("kind") == "ParmVarDecl"]
    ids = [node.get("id") for node in parameters]
    if (type(position) is not int or position != argument.get("position") or
            position != mapping.get("parameter_position") or
            len(parameters) != len(constructor_report["arguments"]) or
            not 0 <= position < len(parameters) or
            any(not isinstance(identifier, str) or not identifier for identifier in ids) or
            len(set(ids)) != len(ids)):
        raise _Rejected("default_parameter_position_mismatch")
    parameter = parameters[position]
    if parameter["id"] != binding.get("parameter_id") or parameter["id"] != mapping.get("parameter_id"):
        raise _Rejected("default_parameter_identity_mismatch")
    expressions = [node for node in _children(parameter) if not str(node.get("kind", "")).endswith("Attr")]
    source = argument.get("default_source_ast")
    if parameter.get("init") != "c" or len(expressions) != 1 or source != expressions[0]:
        raise _Rejected("default_parameter_initializer_mismatch")
    expected_type = _abi_type(parameter.get("type"), abi)
    if any(_abi_type(info, abi) != expected_type for info in
           (raw.get("type"), source.get("type"), mapping.get("parameter_type"))):
        raise _Rejected("default_parameter_type_mismatch")
    current, casts, wrappers = source, [], 0
    while current.get("kind") in {"ParenExpr", "ImplicitCastExpr"}:
        wrappers += 1
        children = _children(current)
        if len(children) != 1 or wrappers > MAX_CASTS:
            raise _Unknown("default_source_wrapper_unsupported")
        child = children[0]
        if (current.get("kind") == "ParenExpr" and
                _abi_type(current.get("type"), abi) != _abi_type(child.get("type"), abi)):
            raise _Rejected("default_source_parenthesis_type_mismatch")
        if current.get("kind") == "ImplicitCastExpr":
            if current.get("castKind") not in {"NoOp", "IntegralCast"}:
                raise _Unknown("default_source_cast_unsupported")
            casts.append({"kind": current["kind"], "cast_kind": current["castKind"],
                          "source_type": child.get("type"), "destination_type": current.get("type"),
                          "range": current.get("range")})
        current = child
    if current.get("kind") != "IntegerLiteral" or _children(current):
        raise _Unknown("default_source_not_literal")
    reported = argument.get("casts")
    if (not isinstance(reported, list) or len(reported) != len(casts) or
            any(not isinstance(item, dict) or any(item.get(key) != value for key, value in expected.items())
                for item, expected in zip(reported, casts))):
        raise _Rejected("default_source_cast_evidence_mismatch")
    return current


def _apply_casts(lower: int, upper: int, initial_type: object, casts: object, final_type: object,
                 abi: dict[str, Any], checks: list[dict[str, Any]], value_kind: str) -> None:
    if not isinstance(casts, list):
        raise _Unknown("cast_evidence_not_list")
    current_name, current_bits, current_signed = _abi_type(initial_type, abi)
    initial_check = check_interval(lower, upper, current_bits, current_signed,
                                   current_bits, current_signed)
    checks.append({"cast_kind": "initial_type_representability", "source_type": current_name,
                   "target_type": current_name, "range": None, "conversion": initial_check})
    if initial_check["status"] != "checked":
        reason = ("constant_not_representable_in_initial_type" if value_kind == "constant" else
                  "interval_not_representable_in_initial_type")
        raise _Rejected(reason, checks[-1])
    for cast in reversed(casts):
        if not isinstance(cast, dict):
            raise _Unknown("unsupported_or_missing_cast_evidence")
        cast_kind = cast.get("cast_kind")
        if not isinstance(cast_kind, str) or cast_kind not in ALLOWED_CASTS:
            raise _Unknown("unsupported_or_missing_cast_evidence")
        source_name, source_bits, source_signed = _abi_type(cast.get("source_type"), abi)
        target_name, target_bits, target_signed = _abi_type(cast.get("destination_type"), abi)
        if source_name != current_name:
            raise _Rejected("cast_type_chain_discontinuity", {"expected": current_name,
                                                               "reported": source_name})
        if cast_kind in {"LValueToRValue", "NoOp"} and target_name != source_name:
            raise _Rejected("nonconverting_cast_changes_base_type")
        conversion = check_interval(lower, upper, source_bits, source_signed,
                                    target_bits, target_signed)
        check = {"cast_kind": cast_kind, "source_type": source_name,
                 "target_type": target_name, "range": cast.get("range"),
                 "conversion": conversion}
        checks.append(check)
        if conversion["status"] == "rejected":
            raise _Rejected("integer_conversion_not_value_preserving", check)
        if conversion["status"] != "checked":
            raise _Unknown("integer_conversion_check_unknown")
        current_name, current_bits, current_signed = target_name, target_bits, target_signed
    expected_name, _, _ = _abi_type(final_type, abi)
    if current_name != expected_name:
        raise _Rejected("final_type_chain_mismatch", {"actual": current_name,
                                                       "expected": expected_name})


def check(constructor_report: object, field_report: object, abi: object,
          declaration_intervals: object = None) -> dict[str, Any]:
    interval_mode = declaration_intervals is not None
    result: dict[str, Any] = {
        "schema_version": ("constructor-values-check/v2" if interval_mode else
                           "constructor-values-check/v1"),
        "status": "unknown", "reason": None,
        "fields": [], "conversion_checks": [], "source_program_checked": False,
        "checked_scope": ("explicit_constructor_constants_intervals_and_integer_abi_conditional"
                          if interval_mode else
                          "explicit_constructor_constants_and_integer_abi_only"),
        "deployable": False,
        "budget": {"max_fields": MAX_FIELDS, "max_casts": MAX_CASTS,
                   "fields_used": 0, "casts_used": 0},
        "assumptions": ["reports faithfully preserve the source AST evidence",
                        "declaration-derived constants are accepted as explicit report premises",
                        "the explicit ABI table matches the compilation target"],
    }
    if interval_mode:
        result["budget"]["max_intervals"] = MAX_FIELDS
        result["assumptions"].extend([
            "each symbolic declaration runtime value lies within its supplied closed interval",
            "the source guard producing each supplied interval is not verified by this checker",
        ])
    if not isinstance(constructor_report, dict) or not isinstance(field_report, dict) or not isinstance(abi, dict):
        result["reason"] = "inputs_not_objects"
        return result
    result["input_sha256"] = {
        "constructor_report": _hash(constructor_report), "field_report": _hash(field_report),
        "abi": _hash(abi)}
    default_arguments = constructor_report.get("arguments")
    if isinstance(default_arguments, list) and any(
            isinstance(argument, dict) and argument.get("default_source_binding") is not None
            for argument in default_arguments):
        result["assumptions"].append(
            "frontend establishes same-TU default declaration/source uniqueness and excludes redeclared, inherited or templated defaults")
    if interval_mode:
        result["input_sha256"]["declaration_intervals"] = _hash(declaration_intervals)
    try:
        interval_by_id: dict[str, dict[str, Any]] = {}
        if interval_mode:
            if not isinstance(declaration_intervals, list):
                raise _Unknown("declaration_intervals_not_list")
            if len(declaration_intervals) > MAX_FIELDS:
                raise _Unknown("declaration_interval_budget_exceeded")
            for interval in declaration_intervals:
                if not isinstance(interval, dict):
                    raise _Unknown("declaration_interval_not_object")
                declaration_id = interval.get("declaration_id")
                lower, upper = interval.get("lower"), interval.get("upper")
                if not isinstance(declaration_id, str) or not declaration_id:
                    raise _Unknown("declaration_interval_id_missing")
                if declaration_id in interval_by_id:
                    raise _Rejected("declaration_interval_ids_not_unique")
                if type(lower) is not int or type(upper) is not int or lower > upper:
                    raise _Unknown("declaration_interval_bounds_invalid")
                _raw_type(interval.get("type"))
                interval_by_id[declaration_id] = interval
            result["budget"]["intervals_used"] = len(interval_by_id)
        if (constructor_report.get("schema_version") != "constructor-arguments/v1" or
                constructor_report.get("status") != "inspected"):
            raise _Unknown("constructor_report_not_inspected")
        if (field_report.get("schema_version") != "constructor-fields/v1" or
                field_report.get("status") != "recovered"):
            raise _Unknown("field_report_not_recovered")
        constructor_id = constructor_report.get("constructor_declaration_id")
        if (not isinstance(constructor_id, str) or not constructor_id or
                constructor_id != field_report.get("constructor_declaration_id")):
            raise _Rejected("constructor_declaration_id_mismatch")
        if field_report.get("record_completeness") != "all_direct_record_fields_initialized":
            raise _Unknown("record_field_completeness_not_established")
        arguments, mappings = constructor_report.get("arguments"), field_report.get("field_mappings")
        if not isinstance(arguments, list) or not isinstance(mappings, list):
            raise _Unknown("arguments_or_mappings_missing")
        if not arguments or not mappings:
            raise _Unknown("arguments_or_mappings_empty")
        if len(arguments) > MAX_FIELDS or len(mappings) > MAX_FIELDS:
            raise _Unknown("field_budget_exceeded")
        result["budget"]["fields_used"] = len(mappings)
        if len(arguments) != len(mappings):
            raise _Rejected("argument_mapping_count_mismatch")
        for index, argument in enumerate(arguments):
            if not isinstance(argument, dict):
                raise _Unknown("argument_entry_not_object")
            if type(argument.get("position")) is not int or argument["position"] != index:
                raise _Rejected("argument_positions_not_exact_and_ordered")
            argument_status = argument.get("status")
            if (not isinstance(argument_status, str) or
                    argument_status not in ("evidence", "symbolic", "unknown")):
                raise _Unknown("argument_status_invalid")
            if not isinstance(argument.get("casts"), list):
                raise _Unknown("argument_casts_not_list")
        field_ids: list[str] = []
        parameter_ids: list[str] = []
        positions: list[int] = []
        for mapping in mappings:
            if not isinstance(mapping, dict):
                raise _Unknown("field_mapping_entry_not_object")
            field_id, parameter_id, position = (mapping.get("field_id"), mapping.get("parameter_id"),
                                                mapping.get("parameter_position"))
            if not isinstance(field_id, str) or not field_id:
                raise _Unknown("field_id_missing")
            if not isinstance(parameter_id, str) or not parameter_id:
                raise _Unknown("parameter_id_missing")
            if type(position) is not int:
                raise _Unknown("parameter_position_not_integer")
            if not isinstance(mapping.get("casts"), list):
                raise _Unknown("field_mapping_casts_not_list")
            field_ids.append(field_id)
            parameter_ids.append(parameter_id)
            positions.append(position)
        if len(set(field_ids)) != len(field_ids):
            raise _Rejected("field_ids_not_unique")
        if len(set(parameter_ids)) != len(parameter_ids):
            raise _Rejected("parameter_ids_not_unique")
        if sorted(positions) != list(range(len(arguments))):
            raise _Rejected("parameter_positions_not_one_to_one")
        total_casts = sum(len(argument["casts"]) for argument in arguments)
        total_casts += sum(len(mapping["casts"]) for mapping in mappings)
        result["budget"]["casts_used"] = total_casts
        if total_casts > MAX_CASTS:
            raise _Unknown("cast_budget_exceeded")

        fields: list[dict[str, Any]] = []
        checks: list[dict[str, Any]] = []
        declaration_premises: list[str] = []
        interval_premises: list[str] = []
        for mapping in mappings:
            position = mapping["parameter_position"]
            argument = arguments[position]
            constant = argument.get("pre_conversion_constant") if isinstance(argument, dict) else None
            leaf = _argument_leaf(argument, constructor_report, mapping, abi)
            value_kind = "constant"
            lower: int
            upper: int
            field_value: dict[str, Any]
            if argument.get("status") == "symbolic":
                if not interval_mode:
                    raise _Unknown("constructor_argument_not_constant")
                if constant is not None:
                    raise _Rejected("symbolic_argument_has_constant_evidence")
                referenced = leaf.get("referencedDecl")
                declaration_id = argument.get("declaration_id")
                if (leaf.get("kind") != "DeclRefExpr" or not isinstance(referenced, dict) or
                        referenced.get("kind") not in ("VarDecl", "ParmVarDecl") or
                        not isinstance(declaration_id, str) or not declaration_id or
                        referenced.get("id") != declaration_id):
                    raise _Rejected("symbolic_argument_raw_declref_mismatch")
                interval = interval_by_id.get(declaration_id)
                if interval is None:
                    raise _Unknown("symbolic_declaration_interval_missing")
                if _raw_type(interval.get("type")) != _raw_type(_type_from_leaf(leaf)):
                    raise _Rejected("symbolic_interval_leaf_type_mismatch")
                lower, upper = interval["lower"], interval["upper"]
                value_kind = "interval"
                if declaration_id not in interval_premises:
                    interval_premises.append(declaration_id)
                field_value = {"value_kind": "interval",
                               "interval": {"lower": lower, "upper": upper},
                               "declaration_id": declaration_id}
            elif argument.get("status") != "evidence" or not isinstance(constant, dict):
                raise _Unknown("constructor_argument_not_constant")
            elif constant.get("status") != "evaluated":
                raise _Unknown("constructor_constant_not_evaluated")
            elif type(constant.get("value")) is not int:
                raise _Unknown("constructor_constant_not_integer")
            else:
                value = constant["value"]
                lower = upper = value
                field_value = {"value_kind": "constant", "value": value}
            if value_kind == "constant" and constant.get("source") == "integer_literal":
                if leaf.get("kind") != "IntegerLiteral":
                    raise _Rejected("literal_constant_raw_ast_mismatch")
                try:
                    raw_value = int(str(leaf.get("value")), 0)
                except (TypeError, ValueError):
                    raise _Rejected("literal_constant_raw_ast_invalid")
                if raw_value != lower:
                    raise _Rejected("literal_constant_value_mismatch")
            elif value_kind == "constant" and constant.get("source") == "signed_int_declaration":
                referenced = leaf.get("referencedDecl")
                if (leaf.get("kind") != "DeclRefExpr" or not isinstance(referenced, dict) or
                        not isinstance(referenced.get("id"), str) or not referenced["id"] or
                        referenced["id"] != constant.get("declaration_id")):
                    raise _Rejected("declaration_constant_raw_ast_mismatch")
                declaration_premises.append(constant["declaration_id"])
            elif value_kind == "constant":
                raise _Unknown("constant_source_unsupported")
            initial_type = _type_from_leaf(leaf)
            argument_checks: list[dict[str, Any]] = []
            _apply_casts(lower, upper, initial_type, argument.get("casts"),
                         mapping.get("parameter_type"), abi, argument_checks, value_kind)
            field_checks: list[dict[str, Any]] = []
            _apply_casts(lower, upper, mapping.get("parameter_type"), mapping.get("casts"),
                         mapping.get("field_type"), abi, field_checks, value_kind)
            checks.append({"field_id": mapping.get("field_id"), "parameter_position": position,
                           "argument_casts": argument_checks, "field_initializer_casts": field_checks})
            fields.append({"field_id": mapping.get("field_id"), "field_name": mapping.get("field_name"),
                           "parameter_position": position, **field_value})
        result.update(status="checked", fields=fields, conversion_checks=checks,
                      declaration_constant_premises=declaration_premises)
        if interval_mode:
            result["interval_declaration_premises"] = interval_premises
    except _Rejected as error:
        result.update(status="rejected", reason=error.reason)
        if error.detail is not None:
            result["diagnostic"] = error.detail
    except _Unknown as error:
        result["reason"] = error.reason
    return result


def _type_from_leaf(leaf: dict[str, Any]) -> object:
    type_value = leaf.get("type")
    if isinstance(type_value, dict):
        return type_value
    referenced = leaf.get("referencedDecl")
    if isinstance(referenced, dict) and isinstance(referenced.get("type"), dict):
        return referenced["type"]
    raise _Unknown("leaf_type_missing")
