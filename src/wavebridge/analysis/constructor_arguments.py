"""Inspect constructor argument evidence without assigning field or launch semantics."""

from __future__ import annotations

from typing import Any

from wavebridge.analysis.integer_constants import evaluate

ARG_CASTS = {"LValueToRValue", "IntegralCast", "NoOp"}


class _Unknown(Exception):
    def __init__(self, reason: str, range_value: object = None):
        self.reason, self.range = reason, range_value


def _children(node: dict[str, Any]) -> list[dict[str, Any]]:
    inner = node.get("inner", [])
    return [child for child in inner if isinstance(child, dict) and child] if isinstance(inner, list) else []


def _type(node: dict[str, Any]) -> object:
    return node.get("type") if isinstance(node.get("type"), dict) else None


def _record_cast(node: dict[str, Any], child: dict[str, Any]) -> dict[str, Any]:
    return {"kind": node.get("kind"), "cast_kind": node.get("castKind"),
            "source_type": _type(child), "destination_type": _type(node),
            "range": node.get("range"), "conversion_semantics": "not_established"}


def _unwrap_parens(node: dict[str, Any]) -> dict[str, Any]:
    current = node
    while current.get("kind") == "ParenExpr":
        children = _children(current)
        if len(children) != 1:
            raise _Unknown("ambiguous_parentheses", current.get("range"))
        current = children[0]
    return current


def _argument(root: dict[str, Any], node: dict[str, Any], position: int,
              int_bits: int) -> dict[str, Any]:
    item: dict[str, Any] = {
        "position": position, "status": "unknown", "reason": None,
        "argument_ast": node, "default_argument": False, "default_source_ast": None,
        "leaf_kind": None, "declaration_id": None, "casts": [],
        "pre_conversion_constant": None, "range": node.get("range"),
        "conversion_semantics": "not_established",
    }
    current = node
    if current.get("kind") == "CXXDefaultArgExpr":
        item["default_argument"] = True
        children = _children(current)
        if len(children) != 1:
            item["reason"] = "default_argument_source_missing_or_ambiguous"
            return item
        item["default_source_ast"] = children[0]
        current = children[0]
    current = _unwrap_parens(current)
    while current.get("kind") == "ImplicitCastExpr":
        children = _children(current)
        if len(children) != 1:
            item["reason"] = "ambiguous_argument_cast"
            return item
        if current.get("castKind") not in ARG_CASTS:
            item["reason"] = "unsupported_argument_cast"
            return item
        item["casts"].append(_record_cast(current, children[0]))
        current = _unwrap_parens(children[0])
    item["leaf_kind"] = current.get("kind")
    if current.get("kind") == "IntegerLiteral":
        try:
            value = int(str(current.get("value")), 0)
        except (TypeError, ValueError):
            item["reason"] = "invalid_integer_literal"
            return item
        if not -(1 << (int_bits - 1)) <= value <= (1 << (int_bits - 1)) - 1:
            item["reason"] = "pre_conversion_signed_integer_out_of_range"
            return item
        item["pre_conversion_constant"] = {"status": "evaluated", "value": value,
                                            "source": "integer_literal",
                                            "range": current.get("range")}
        item["status"] = "evidence"
        return item
    if current.get("kind") == "DeclRefExpr":
        referenced = current.get("referencedDecl")
        if not isinstance(referenced, dict) or referenced.get("kind") not in {"VarDecl", "ParmVarDecl"}:
            item["reason"] = "argument_reference_not_variable_or_parameter"
            return item
        declaration_id = referenced.get("id")
        if not isinstance(declaration_id, str):
            item["reason"] = "argument_declaration_id_missing"
            return item
        item["declaration_id"] = declaration_id
        if referenced.get("kind") == "VarDecl":
            constant = evaluate(root, declaration_id, int_bits)
            if constant.get("status") == "evaluated":
                item["pre_conversion_constant"] = {"status": "evaluated",
                    "value": constant["value"], "source": "signed_int_declaration",
                    "declaration_id": declaration_id, "evaluation": constant}
                item["status"] = "evidence"
                return item
            item["constant_evaluation"] = constant
        item["status"] = "symbolic"
        return item
    item["reason"] = "unsupported_argument_expression"
    return item


def inspect(root: object, expression: object, int_bits: int) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema_version": "constructor-arguments/v1", "status": "unknown", "reason": None,
        "int_bits": int_bits, "expression_ast": expression if isinstance(expression, dict) else None,
        "expression_type": None, "constructor_declaration_id": None,
        "constructor_reference": None, "constructor_expression_ast": None,
        "constructor_type": None, "casts": [], "arguments": [],
        "constructor_semantics": "not_established", "field_mapping": "not_established",
        "actual_configuration_values": "not_established",
        "conversion_semantics": "not_established", "checked": False,
        "deployable": False, "relation_recovery": "incomplete",
    }
    if not isinstance(root, dict):
        result["reason"] = "root_not_object"
        return result
    if not isinstance(expression, dict):
        result["reason"] = "expression_not_object"
        return result
    if type(int_bits) is not int or not 2 <= int_bits <= 128:
        result["reason"] = "invalid_int_bits"
        return result
    try:
        outer = _unwrap_parens(expression)
        result["expression_type"] = _type(outer)
        if outer.get("kind") != "CXXFunctionalCastExpr" or outer.get("castKind") != "ConstructorConversion":
            raise _Unknown("not_constructor_functional_cast", outer.get("range"))
        conversion = outer.get("conversionFunc")
        if (not isinstance(conversion, dict) or conversion.get("kind") != "CXXConstructorDecl" or
                not isinstance(conversion.get("id"), str)):
            raise _Unknown("constructor_declaration_reference_missing", outer.get("range"))
        constructed = _children(outer)
        if len(constructed) != 1 or constructed[0].get("kind") != "CXXConstructExpr":
            raise _Unknown("constructor_target_missing_or_ambiguous", outer.get("range"))
        constructor = constructed[0]
        arguments = [_argument(root, argument, position, int_bits)
                     for position, argument in enumerate(_children(constructor))]
        result.update(constructor_declaration_id=conversion["id"], constructor_reference=conversion,
                      constructor_expression_ast=constructor,
                      constructor_type=constructor.get("ctorType") or _type(constructor),
                      arguments=arguments,
                      casts=[cast for argument in arguments for cast in argument["casts"]])
        unknown = [argument for argument in arguments if argument["status"] == "unknown"]
        if unknown:
            result["reason"] = "one_or_more_arguments_unknown"
            return result
        result["status"] = "inspected"
    except _Unknown as error:
        result["reason"], result["unknown_range"] = error.reason, error.range
    return result
