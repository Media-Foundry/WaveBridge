"""Conservative exact-ID tracing of no-argument getter return-call chains."""

from __future__ import annotations

from typing import Any

FUNCTION_KINDS = {"FunctionDecl", "CXXMethodDecl"}
BODY_KINDS = {"CompoundStmt"}
UNSUPPORTED_BODY_KINDS = {"CXXTryStmt", "CoroutineBodyStmt"}
WRAPPERS = {"ParenExpr", "ImplicitCastExpr"}
CALL_KINDS = {"CallExpr", "CXXMemberCallExpr"}


class _Unknown(Exception):
    def __init__(self, reason: str, range_value: object = None):
        self.reason, self.range = reason, range_value


def _children(node: dict[str, Any]) -> list[dict[str, Any]]:
    inner = node.get("inner", [])
    return [child for child in inner if isinstance(child, dict)] if isinstance(inner, list) else []


def _walk(node: dict[str, Any]):
    yield node
    for child in _children(node):
        yield from _walk(child)


def _type(node: dict[str, Any]) -> str | None:
    type_info = node.get("type")
    return type_info.get("qualType") if isinstance(type_info, dict) else None


def _unwrap(node: dict[str, Any], casts: list[dict[str, Any]]) -> dict[str, Any]:
    current = node
    while current.get("kind") in WRAPPERS:
        children = _children(current)
        if len(children) != 1:
            raise _Unknown("ambiguous_return_wrapper", current.get("range"))
        if current.get("kind") == "ImplicitCastExpr":
            casts.append({"kind": "ImplicitCastExpr", "cast_kind": current.get("castKind"),
                          "type": _type(current), "range": current.get("range"),
                          "semantic_obligation": "not_discharged"})
        current = children[0]
    return current


def _single_return(function: dict[str, Any]) -> dict[str, Any] | None:
    unsupported = [child for child in _children(function)
                   if child.get("kind") in UNSUPPORTED_BODY_KINDS]
    if unsupported:
        raise _Unknown("unsupported_body", unsupported[0].get("range"))
    bodies = [child for child in _children(function) if child.get("kind") in BODY_KINDS]
    if not bodies:
        return None
    if len(bodies) != 1:
        raise _Unknown("multiple_bodies", function.get("range"))
    statements = _children(bodies[0])
    if len(statements) != 1 or statements[0].get("kind") != "ReturnStmt":
        raise _Unknown("body_not_single_return", bodies[0].get("range"))
    return statements[0]


def _parameter_count(function: dict[str, Any]) -> int:
    return sum(child.get("kind") == "ParmVarDecl" for child in _children(function))


def trace(root: object, declaration_id: str, max_depth: int = 16) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema_version": "return-call-trace/v1", "status": "unknown",
        "start_declaration_id": declaration_id, "max_depth": max_depth,
        "steps": [], "leaf": None, "reason": None,
        "semantic_interpretation": "not_established", "checked": False,
        "relation_recovery": "incomplete", "deployable": False,
    }
    if not isinstance(root, dict):
        result["reason"] = "root_not_object"
        return result
    if type(max_depth) is not int or not 1 <= max_depth <= 128:
        result["reason"] = "invalid_max_depth"
        return result
    declarations = {node["id"]: node for node in _walk(root)
                    if node.get("kind") in FUNCTION_KINDS and isinstance(node.get("id"), str)}
    active: set[str] = set()

    def follow(clang_id: str, depth: int) -> None:
        if depth >= max_depth:
            raise _Unknown("max_depth_exceeded")
        if clang_id in active:
            raise _Unknown("call_cycle")
        function = declarations.get(clang_id)
        if function is None:
            raise _Unknown("callee_definition_missing")
        return_stmt = _single_return(function)
        if return_stmt is None:
            if depth == 0:
                raise _Unknown("start_definition_has_no_body", function.get("range"))
            result["leaf"] = {
                "kind": "external_leaf", "declaration_id": clang_id,
                "name": function.get("name"), "signature": _type(function),
                "range": function.get("range"), "arguments": [],
            }
            return
        if _parameter_count(function) > 0:
            raise _Unknown("defined_callee_has_parameters", function.get("range"))
        expressions = _children(return_stmt)
        if len(expressions) != 1:
            raise _Unknown("return_expression_missing_or_ambiguous", return_stmt.get("range"))
        casts: list[dict[str, Any]] = []
        call = _unwrap(expressions[0], casts)
        if call.get("kind") not in CALL_KINDS:
            raise _Unknown("return_expression_not_call", call.get("range"))
        call_children = _children(call)
        if not call_children:
            raise _Unknown("call_callee_missing", call.get("range"))
        callee_casts: list[dict[str, Any]] = []
        callee_expr = _unwrap(call_children[0], callee_casts)
        target_id = None
        target_name = None
        member_call = callee_expr.get("kind") == "MemberExpr"
        if callee_expr.get("kind") == "DeclRefExpr":
            referenced = callee_expr.get("referencedDecl")
            if isinstance(referenced, dict) and referenced.get("kind") == "FunctionDecl":
                target_id, target_name = referenced.get("id"), referenced.get("name")
        elif member_call:
            referenced = callee_expr.get("referencedMemberDecl")
            if isinstance(referenced, dict):
                target_id, target_name = referenced.get("id"), referenced.get("name")
            else:
                target_id = referenced
        if not isinstance(target_id, str):
            raise _Unknown("call_target_not_exact_function_declaration", call.get("range"))
        arguments = call_children[1:]
        step = {
            "declaration_id": clang_id, "name": function.get("name"),
            "declaration_range": function.get("range"), "return_range": return_stmt.get("range"),
            "return_casts": casts, "callee_casts": callee_casts,
            "call_kind": call.get("kind"), "call_range": call.get("range"),
            "callee_declaration_id": target_id, "callee_name": target_name,
            "arguments_ast": arguments,
            "member_call": member_call,
            "receiver_purity": "not_established" if member_call else "not_applicable",
        }
        result["steps"].append(step)
        target = declarations.get(target_id)
        if target is None:
            raise _Unknown("callee_definition_missing", call.get("range"))
        target_body = _single_return(target)
        if target_body is None:
            result["leaf"] = {
                "kind": "external_leaf", "declaration_id": target_id,
                "name": target.get("name") or target_name, "signature": _type(target),
                "range": target.get("range"), "call_range": call.get("range"),
                "arguments": arguments,
                "member_receiver_ast": _children(callee_expr) if member_call else None,
                "receiver_purity": "not_established" if member_call else "not_applicable",
            }
            return
        if arguments:
            raise _Unknown("defined_callee_call_has_arguments", call.get("range"))
        if _parameter_count(target) > 0:
            raise _Unknown("defined_callee_has_parameters", target.get("range"))
        active.add(clang_id)
        try:
            follow(target_id, depth + 1)
        finally:
            active.remove(clang_id)

    try:
        follow(declaration_id, 0)
    except _Unknown as error:
        result["reason"] = error.reason
        result["unknown_range"] = error.range
        return result
    result["status"] = "external_leaf"
    return result
