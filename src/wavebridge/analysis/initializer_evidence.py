"""Collect call evidence from one exact VarDecl initializer without equating values."""

from __future__ import annotations

from typing import Any

from wavebridge.analysis.return_trace import trace
from wavebridge.analysis.initializer_value import link

CALL_KINDS = {"CallExpr", "CXXMemberCallExpr", "CXXOperatorCallExpr", "CUDAKernelCallExpr"}
SUPPORTED_CALL_KINDS = {"CallExpr", "CXXMemberCallExpr"}
CALLEE_WRAPPERS = {"ParenExpr", "ImplicitCastExpr"}


def _children(node: dict[str, Any]) -> list[dict[str, Any]]:
    inner = node.get("inner", [])
    return [child for child in inner if isinstance(child, dict) and child] if isinstance(inner, list) else []


def _walk(node: dict[str, Any]):
    yield node
    for child in _children(node):
        yield from _walk(child)


def _type(node: dict[str, Any]) -> str | None:
    info = node.get("type")
    return info.get("qualType") if isinstance(info, dict) else None


def _initializer(node: dict[str, Any]) -> dict[str, Any] | None:
    candidates = [child for child in _children(node)
                  if not str(child.get("kind", "")).endswith("Attr")]
    if node.get("init") is None or len(candidates) != 1:
        return None
    return candidates[0]


def _callee(call: dict[str, Any]) -> dict[str, Any]:
    children = _children(call)
    item: dict[str, Any] = {
        "status": "unknown", "reason": None, "call_id": call.get("id"),
        "call_kind": call.get("kind"), "call_range": call.get("range"),
        "callee_declaration_id": None, "callee_name": None, "callee_casts": [],
        "arguments": children[1:] if children else [], "receiver_ast": None,
        "receiver_purity": "not_applicable", "trace": None,
    }
    if call.get("kind") not in SUPPORTED_CALL_KINDS:
        item["reason"] = "unsupported_call_kind"
        return item
    if not children:
        item["reason"] = "callee_missing"
        return item
    current = children[0]
    while current.get("kind") in CALLEE_WRAPPERS:
        wrapper_children = _children(current)
        if len(wrapper_children) != 1:
            item["reason"] = "ambiguous_callee_wrapper"
            return item
        if current.get("kind") == "ImplicitCastExpr":
            item["callee_casts"].append({
                "kind": current.get("kind"), "cast_kind": current.get("castKind"),
                "type": _type(current), "range": current.get("range"),
                "semantic_obligation": "not_discharged",
            })
        current = wrapper_children[0]
    target_id = target_name = None
    if current.get("kind") == "DeclRefExpr":
        referenced = current.get("referencedDecl")
        if isinstance(referenced, dict) and referenced.get("kind") == "FunctionDecl":
            target_id, target_name = referenced.get("id"), referenced.get("name")
    elif current.get("kind") == "MemberExpr":
        referenced = current.get("referencedMemberDecl")
        if isinstance(referenced, dict):
            target_id, target_name = referenced.get("id"), referenced.get("name")
        elif isinstance(referenced, str):
            target_id = referenced
        item["receiver_ast"] = _children(current)
        item["receiver_purity"] = "not_established"
    if not isinstance(target_id, str):
        item["reason"] = "callee_not_exact_function_or_member_declaration"
        return item
    item["callee_declaration_id"], item["callee_name"] = target_id, target_name
    if item["arguments"]:
        item["reason"] = "call_has_arguments"
        return item
    item["status"] = "evidence"
    return item


def inspect(root: object, declaration_id: str) -> dict[str, Any]:
    """Inspect initializer calls; never claim that a call supplies the variable value."""
    result: dict[str, Any] = {
        "schema_version": "initializer-call-evidence/v1", "status": "unknown",
        "declaration_id": declaration_id, "declaration_range": None,
        "initializer_range": None, "initializer_ast": None, "calls": [],
        "reason": None, "origin_candidate": False,
        "value_equivalence": "not_established", "start_semantics": "unknown",
        "checked": False, "deployable": False, "relation_recovery": "incomplete",
        "value_link": None,
    }
    if not isinstance(root, dict):
        result["reason"] = "root_not_object"
        return result
    matches = [node for node in _walk(root)
               if node.get("kind") == "VarDecl" and node.get("id") == declaration_id]
    complete = [(node, _initializer(node)) for node in matches]
    complete = [(node, initializer) for node, initializer in complete if initializer is not None]
    if len(complete) != 1:
        result["reason"] = "unique_initialized_variable_not_found"
        return result
    declaration, initializer = complete[0]
    result["declaration_range"] = declaration.get("range")
    result["initializer_range"] = initializer.get("range")
    result["initializer_ast"] = initializer

    seen_ids: set[str] = set()
    calls: list[dict[str, Any]] = []
    for call in (node for node in _walk(initializer) if node.get("kind") in CALL_KINDS):
        call_id = call.get("id")
        if isinstance(call_id, str):
            if call_id in seen_ids:
                continue
            seen_ids.add(call_id)
        evidence = _callee(call)
        if evidence["status"] == "evidence":
            evidence["trace"] = trace(root, evidence["callee_declaration_id"])
        calls.append(evidence)
    result["calls"] = calls

    qual_type = _type(declaration)
    words = qual_type.split() if isinstance(qual_type, str) else []
    if "const" not in words or "volatile" in words:
        result["reason"] = "variable_not_const_nonvolatile"
        return result
    result["origin_candidate"] = True
    if not calls:
        result["reason"] = "initializer_contains_no_calls"
    elif len(calls) > 1:
        result["reason"] = "initializer_contains_multiple_calls"
    elif calls[0]["status"] != "evidence":
        result["reason"] = "initializer_call_unresolved"
    else:
        result["status"] = "evidence"
        result["value_link"] = link(root, initializer)
    return result
