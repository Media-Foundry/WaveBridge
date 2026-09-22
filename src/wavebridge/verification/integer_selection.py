"""Check one exact two-operand integer minimum selection and its immediate read.

The checker assigns no semantics to function names.  It accepts only a faithful
single-TU AST containing the exact declaration body and call expression, plus
explicit declaration intervals and an integer ABI.
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any

from wavebridge.verification.integer_conversion import check_interval
from wavebridge.verification.kernel_arguments import _Unknown, _abi_type

MAX_AST_NODES = 1_000_000
HARD_MAX_AST_NODES = 10_000_000
MAX_EXPRESSION_DEPTH = 32
BUILTIN_INTEGER_TYPES = {
    "bool", "char", "signed char", "unsigned char", "wchar_t", "char8_t",
    "char16_t", "char32_t", "short", "short int", "signed short",
    "signed short int", "unsigned short", "unsigned short int", "int",
    "signed", "signed int", "unsigned", "unsigned int", "long", "long int",
    "signed long", "signed long int", "unsigned long", "unsigned long int",
    "long long", "long long int", "signed long long", "signed long long int",
    "unsigned long long", "unsigned long long int", "__int128",
    "signed __int128", "unsigned __int128",
}


class _Rejected(Exception):
    def __init__(self, reason: str, detail: object = None):
        self.reason, self.detail = reason, detail


def _hash(value: object) -> str:
    """Hash identical canonical bytes with an explicit memory/cost tradeoff.

    One-shot allocates the full serialized string and UTF-8 buffer.  It is
    opt-in and allocation failures are never silently retried in another mode.
    """
    mode = os.environ.get("WAVEBRIDGE_JSON_HASH_MODE", "streaming")
    if mode == "one-shot":
        return hashlib.sha256(json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False,
        ).encode()).hexdigest()
    if mode != "streaming":
        raise ValueError("WAVEBRIDGE_JSON_HASH_MODE must be streaming or one-shot")
    digest = hashlib.sha256()
    encoder = json.JSONEncoder(sort_keys=True, separators=(",", ":"), allow_nan=False)
    for chunk in encoder.iterencode(value):
        digest.update(chunk.encode())
    return digest.hexdigest()


def _children(node: object) -> list[dict[str, Any]]:
    if not isinstance(node, dict):
        raise _Unknown("ast_node_not_object")
    children = node.get("inner", [])
    if (not isinstance(children, list) or
            any(not isinstance(child, dict) or not child for child in children)):
        raise _Unknown("malformed_ast_children")
    return children


def _raw_type(node: dict[str, Any]) -> str:
    info = node.get("type")
    if not isinstance(info, dict):
        raise _Unknown("type_evidence_missing")
    value = info.get("desugaredQualType") or info.get("qualType")
    if not isinstance(value, str) or not value:
        raise _Unknown("type_evidence_missing")
    return value


def _reference_type(node: dict[str, Any], integer_types: dict[str, Any]):
    raw = _raw_type(node)
    if not raw.endswith("&") or raw.endswith("&&") or "volatile" in raw.split() or "*" in raw:
        raise _Unknown("expected_const_integer_lvalue_reference_type")
    referred = raw[:-1].strip()
    if "const" not in referred.split():
        raise _Unknown("expected_const_integer_lvalue_reference_type")
    abi = _abi_type({"qualType": referred}, integer_types)
    return raw, referred, abi


def _value_type(node: dict[str, Any], integer_types: dict[str, Any], *, const: bool | None = None):
    raw = _raw_type(node)
    words = raw.split()
    if "volatile" in words or "*" in raw or "&" in raw:
        raise _Unknown("expected_nonreference_integer_type")
    if const is True and "const" not in words:
        raise _Unknown("expected_const_integer_glvalue_type")
    if const is False and "const" in words:
        raise _Unknown("unexpected_const_integer_value_type")
    return raw, _abi_type(node.get("type"), integer_types)


def _declref(node: dict[str, Any], parameter_id: str, expected_reference_type: str,
             expected_abi,
             integer_types: dict[str, Any]) -> None:
    referenced = node.get("referencedDecl")
    if (node.get("kind") != "DeclRefExpr" or node.get("valueCategory") != "lvalue" or
            not isinstance(referenced, dict) or referenced.get("kind") != "ParmVarDecl" or
            referenced.get("id") != parameter_id):
        raise _Unknown("selection_parameter_reference_mismatch")
    if _raw_type(referenced) != expected_reference_type:
        raise _Unknown("selection_parameter_declaration_type_mismatch")
    _, actual = _value_type(node, integer_types, const=True)
    if actual != expected_abi:
        raise _Unknown("selection_parameter_reference_type_mismatch")


def check(root: object, expression_id: object, declaration_intervals: object,
          integer_types: object, *, max_ast_nodes: int | None = None) -> dict[str, Any]:
    node_budget = MAX_AST_NODES if max_ast_nodes is None else max_ast_nodes
    result: dict[str, Any] = {
        "schema_version": "integer-selection-check/v1", "status": "unknown", "reason": None,
        "expression_id": expression_id, "callee_declaration_id": None,
        "operation": "minimum", "operand_intervals": [], "return_interval": None,
        "conversion_checks": [],
        "scope": "exact_two_const_integer_reference_minimum_and_immediate_value_read",
        "source_program_checked": False, "deployable": False,
        "reference_identity_established": False,
        "assumptions": [
            "the AST is a faithful complete single translation unit",
            "the explicit ABI matches the compilation target",
            "each bound declaration value lies in its supplied interval",
            "the referenced objects and any materialized temporary remain alive through the call and immediate read",
            "the source program is valid and the selected function returns normally",
        ],
        "budget": {"max_ast_nodes": node_budget,
                   "max_expression_depth": MAX_EXPRESSION_DEPTH},
    }
    if type(node_budget) is not int or not 1 <= node_budget <= HARD_MAX_AST_NODES:
        result["reason"] = "invalid_ast_node_budget"
        return result
    if (not isinstance(root, dict) or not isinstance(expression_id, str) or not expression_id or
            not isinstance(declaration_intervals, list) or not isinstance(integer_types, dict)):
        result["reason"] = "invalid_inputs"
        return result
    try:
        result["input_sha256"] = {
            "root": _hash(root), "expression_id": _hash(expression_id),
            "declaration_intervals": _hash(declaration_intervals),
            "integer_types": _hash(integer_types),
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
            if len(nodes) > node_budget:
                raise _Unknown("ast_node_budget_exceeded")
            children = node.get("inner", [])
            if not isinstance(children, list) or any(not isinstance(child, dict) for child in children):
                raise _Unknown("malformed_ast_children")
            pending.extend(child for child in children if child)

        expressions = [node for node in nodes if node.get("id") == expression_id]
        if len(expressions) != 1:
            raise _Unknown("expression_id_not_unique")
        expression = expressions[0]

        intervals: dict[str, tuple[int, int, tuple[str, int, bool]]] = {}
        for item in declaration_intervals:
            if not isinstance(item, dict):
                raise _Unknown("declaration_interval_not_object")
            identifier, lower, upper = item.get("declaration_id"), item.get("lower"), item.get("upper")
            if (not isinstance(identifier, str) or not identifier or identifier in intervals or
                    type(lower) is not int or type(upper) is not int or lower > upper):
                raise _Unknown("invalid_or_duplicate_declaration_interval")
            abi = _abi_type(item.get("type"), integer_types)
            represented = check_interval(lower, upper, abi[1], abi[2], abi[1], abi[2])
            if represented["status"] != "checked":
                raise _Unknown("declaration_interval_not_representable")
            intervals[identifier] = (lower, upper, abi)

        outer_casts: list[dict[str, Any]] = []
        current = expression
        depth = 0
        while current.get("kind") == "ImplicitCastExpr" and current.get("castKind") == "IntegralCast":
            depth += 1
            children = _children(current)
            if depth > MAX_EXPRESSION_DEPTH or len(children) != 1 or current.get("valueCategory") != "prvalue":
                raise _Unknown("outer_integer_cast_shape_unsupported")
            outer_casts.append(current)
            current = children[0]
        children = _children(current)
        if (current.get("kind") != "ImplicitCastExpr" or
                current.get("castKind") != "LValueToRValue" or
                current.get("valueCategory") != "prvalue" or len(children) != 1):
            raise _Unknown("selection_result_not_immediately_read")
        read = current
        call = children[0]
        call_children = _children(call)
        if (call.get("kind") != "CallExpr" or call.get("valueCategory") != "lvalue" or
                len(call_children) != 3):
            raise _Unknown("selection_call_shape_unsupported")

        callee_cast, call_args = call_children[0], call_children[1:]
        callee_children = _children(callee_cast)
        if (callee_cast.get("kind") != "ImplicitCastExpr" or
                callee_cast.get("castKind") != "FunctionToPointerDecay" or
                callee_cast.get("valueCategory") != "prvalue" or len(callee_children) != 1):
            raise _Unknown("selection_callee_not_direct_function_decay")
        callee_ref = callee_children[0]
        referenced = callee_ref.get("referencedDecl")
        if (callee_ref.get("kind") != "DeclRefExpr" or callee_ref.get("valueCategory") != "lvalue" or
                not isinstance(referenced, dict) or referenced.get("kind") != "FunctionDecl" or
                not isinstance(referenced.get("id"), str) or not referenced["id"]):
            raise _Unknown("selection_callee_reference_missing")
        callee_id = referenced["id"]
        result["callee_declaration_id"] = callee_id
        declarations = [node for node in nodes
                        if node.get("kind") == "FunctionDecl" and node.get("id") == callee_id]
        if len(declarations) != 1:
            raise _Unknown("selection_function_declaration_not_unique")
        declaration = declarations[0]
        if declaration.get("previousDecl") is not None or declaration.get("variadic") is True:
            raise _Unknown("selection_function_redeclaration_or_variadic_unsupported")
        if any(node.get("kind") == "FunctionDecl" and node.get("previousDecl") == callee_id
               for node in nodes):
            raise _Unknown("selection_function_redeclaration_or_variadic_unsupported")

        declaration_children = _children(declaration)
        parameters = [node for node in declaration_children if node.get("kind") == "ParmVarDecl"]
        bodies = [node for node in declaration_children if node.get("kind") == "CompoundStmt"]
        template_arguments = [node for node in declaration_children if node.get("kind") == "TemplateArgument"]
        allowed = {"ParmVarDecl", "CompoundStmt", "TemplateArgument"}
        if (len(parameters) != 2 or len(bodies) != 1 or len(template_arguments) > 1 or
                any(not (child.get("kind") in allowed or
                        str(child.get("kind", "")).endswith("Attr"))
                    for child in declaration_children)):
            raise _Unknown("selection_function_shape_unsupported")
        parameter_ids = [parameter.get("id") for parameter in parameters]
        if any(not isinstance(identifier, str) or not identifier for identifier in parameter_ids) or len(set(parameter_ids)) != 2:
            raise _Unknown("selection_parameter_ids_invalid")
        if any(sum(node.get("id") == identifier for node in nodes) != 1
               for identifier in parameter_ids):
            raise _Unknown("selection_parameter_declaration_not_unique")
        p0_raw, referred0, p0_abi = _reference_type(parameters[0], integer_types)
        p1_raw, _, p1_abi = _reference_type(parameters[1], integer_types)
        if p0_raw != p1_raw or p0_abi != p1_abi or p0_abi[0] not in BUILTIN_INTEGER_TYPES:
            raise _Unknown("selection_parameter_types_mismatch")
        if template_arguments:
            template_argument = template_arguments[0]
            template_children = _children(template_argument)
            if (len(template_children) != 1 or template_children[0].get("kind") != "BuiltinType" or
                    _abi_type(template_argument.get("type"), integer_types) != p0_abi or
                    _abi_type(template_children[0].get("type"), integer_types) != p0_abi):
                raise _Unknown("selection_template_argument_unsupported")
        expected_function_type = f"{p0_raw}({p0_raw}, {p0_raw})"
        expected_pointer = f"{p0_raw[:-1].rstrip()} &(*)({p0_raw}, {p0_raw})"
        if (_raw_type(declaration) != expected_function_type or
                _raw_type(referenced) != expected_function_type or
                _raw_type(callee_ref) != expected_function_type or
                _raw_type(callee_cast) != expected_pointer):
            raise _Unknown("selection_function_signature_mismatch")

        body_children = _children(bodies[0])
        if len(body_children) != 1 or body_children[0].get("kind") != "ReturnStmt":
            raise _Unknown("selection_function_body_not_single_return")
        returned = _children(body_children[0])
        if len(returned) != 1 or returned[0].get("kind") != "ConditionalOperator":
            raise _Unknown("selection_return_not_conditional")
        conditional = returned[0]
        conditional_children = _children(conditional)
        if (len(conditional_children) != 3 or conditional.get("valueCategory") != "lvalue" or
                _raw_type(conditional) != referred0 or
                _abi_type(conditional.get("type"), integer_types) != p0_abi):
            raise _Unknown("selection_conditional_shape_or_type_mismatch")
        condition, true_value, false_value = conditional_children
        compared = _children(condition)
        if (condition.get("kind") != "BinaryOperator" or condition.get("opcode") != "<" or
                condition.get("valueCategory") != "prvalue" or _raw_type(condition) != "bool" or
                len(compared) != 2):
            raise _Unknown("selection_condition_not_strict_less_than")
        comparison_parameter_ids: list[str] = []
        for operand in compared:
            operand_children = _children(operand)
            if (operand.get("kind") != "ImplicitCastExpr" or
                    operand.get("castKind") != "LValueToRValue" or
                    operand.get("valueCategory") != "prvalue" or len(operand_children) != 1 or
                    _abi_type(operand.get("type"), integer_types) != p0_abi):
                raise _Unknown("selection_comparison_operand_unsupported")
            reference = operand_children[0].get("referencedDecl")
            parameter_id = reference.get("id") if isinstance(reference, dict) else None
            if parameter_id not in parameter_ids or parameter_id in comparison_parameter_ids:
                raise _Unknown("selection_comparison_parameter_mismatch")
            _declref(operand_children[0], parameter_id, p0_raw, p0_abi, integer_types)
            comparison_parameter_ids.append(parameter_id)
        _declref(true_value, comparison_parameter_ids[0], p0_raw, p0_abi, integer_types)
        _declref(false_value, comparison_parameter_ids[1], p0_raw, p0_abi, integer_types)

        call_raw, call_abi = _value_type(call, integer_types, const=True)
        read_raw, read_abi = _value_type(read, integer_types, const=False)
        if call_raw != referred0 or call_abi != p0_abi or read_abi != p0_abi:
            raise _Unknown("selection_call_or_read_type_mismatch")

        used_intervals: set[str] = set()
        operand_domains: list[tuple[int, int]] = []
        for argument in call_args:
            argument_children = _children(argument)
            if argument.get("kind") == "ImplicitCastExpr" and argument.get("castKind") == "NoOp":
                if argument.get("valueCategory") != "lvalue" or len(argument_children) != 1:
                    raise _Unknown("selection_declaration_argument_shape_unsupported")
                _, argument_abi = _value_type(argument, integer_types, const=True)
                leaf = argument_children[0]
                referenced_var = leaf.get("referencedDecl")
                if (leaf.get("kind") != "DeclRefExpr" or leaf.get("valueCategory") != "lvalue" or
                        not isinstance(referenced_var, dict) or
                        referenced_var.get("kind") not in {"VarDecl", "ParmVarDecl"} or
                        not isinstance(referenced_var.get("id"), str)):
                    raise _Unknown("selection_declaration_argument_shape_unsupported")
                var_id = referenced_var["id"]
                variable_matches = [node for node in nodes
                                    if node.get("kind") == referenced_var.get("kind") and
                                    node.get("id") == var_id]
                if len(variable_matches) != 1:
                    raise _Unknown("selection_argument_declaration_not_unique")
                _, variable_abi = _value_type(variable_matches[0], integer_types, const=False)
                referenced_raw, referenced_abi = _value_type(
                    referenced_var, integer_types, const=False)
                _, leaf_abi = _value_type(leaf, integer_types, const=False)
                interval = intervals.get(var_id)
                if interval is None:
                    raise _Unknown("selection_declaration_interval_missing")
                if (_raw_type(variable_matches[0]) != referenced_raw or
                        argument_abi != p0_abi or leaf_abi != p0_abi or
                        referenced_abi != p0_abi or variable_abi != p0_abi or
                        interval[2] != p0_abi):
                    raise _Unknown("selection_declaration_argument_type_mismatch")
                used_intervals.add(var_id)
                operand_domains.append((interval[0], interval[1]))
            elif argument.get("kind") == "MaterializeTemporaryExpr":
                if (argument.get("valueCategory") != "lvalue" or
                        argument.get("boundToLValueRef") is not True or
                        argument.get("storageDuration") != "full expression" or
                        len(argument_children) != 1):
                    raise _Unknown("selection_literal_temporary_shape_unsupported")
                _, temporary_abi = _value_type(argument, integer_types, const=True)
                converted = argument_children[0]
                converted_children = _children(converted)
                if (converted.get("kind") != "ImplicitCastExpr" or
                        converted.get("castKind") != "NoOp" or
                        converted.get("valueCategory") != "prvalue" or len(converted_children) != 1):
                    raise _Unknown("selection_literal_temporary_shape_unsupported")
                _, converted_abi = _value_type(converted, integer_types, const=True)
                literal = converted_children[0]
                value_text = literal.get("value")
                if (literal.get("kind") != "IntegerLiteral" or literal.get("valueCategory") != "prvalue" or
                        _children(literal) or not isinstance(value_text, str)):
                    raise _Unknown("selection_literal_argument_unsupported")
                try:
                    value = int(value_text, 0)
                except ValueError:
                    raise _Unknown("selection_literal_argument_unsupported")
                _, literal_abi = _value_type(literal, integer_types, const=False)
                if temporary_abi != p0_abi or converted_abi != p0_abi or literal_abi != p0_abi:
                    raise _Unknown("selection_literal_argument_type_mismatch")
                represented = check_interval(value, value, p0_abi[1], p0_abi[2], p0_abi[1], p0_abi[2])
                if represented["status"] != "checked":
                    raise _Unknown("selection_literal_not_representable")
                operand_domains.append((value, value))
            else:
                raise _Unknown("selection_argument_expression_unsupported")
        if used_intervals != set(intervals):
            raise _Unknown("declaration_intervals_not_exactly_consumed")

        lower = min(operand_domains[0][0], operand_domains[1][0])
        upper = min(operand_domains[0][1], operand_domains[1][1])
        current_abi = read_abi
        for cast in reversed(outer_casts):
            _, target_abi = _value_type(cast, integer_types, const=False)
            if target_abi[0] not in BUILTIN_INTEGER_TYPES:
                raise _Unknown("selection_result_not_builtin_integer")
            conversion = check_interval(lower, upper, current_abi[1], current_abi[2],
                                        target_abi[1], target_abi[2])
            check_record = {"cast_kind": "IntegralCast", "source_type": current_abi[0],
                            "target_type": target_abi[0], "range": cast.get("range"),
                            "conversion": conversion}
            result["conversion_checks"].append(check_record)
            if conversion["status"] == "rejected":
                raise _Rejected("selection_result_conversion_not_value_preserving", check_record)
            if conversion["status"] != "checked":
                raise _Unknown("selection_result_conversion_unknown")
            current_abi = target_abi
        true_position, false_position = [parameter_ids.index(identifier)
                                         for identifier in comparison_parameter_ids]
        result.update(status="checked", operand_intervals=[
            {"position": index, "lower": interval[0], "upper": interval[1]}
            for index, interval in enumerate(operand_domains)],
            return_interval={"lower": lower, "upper": upper},
            result_type={"qualType": current_abi[0]},
            selection_expression={"condition": f"parameter_{true_position} < parameter_{false_position}",
                                  "true_parameter": true_position, "false_parameter": false_position,
                                  "tie_parameter": false_position},
            immediate_read={"call_type": call_raw, "result_type": read_raw})
    except _Rejected as error:
        result.update(status="rejected", reason=error.reason)
        if error.detail is not None:
            result["diagnostic"] = error.detail
    except _Unknown as error:
        result["reason"] = error.reason
    return result
