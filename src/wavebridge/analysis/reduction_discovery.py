"""Reachability-bounded discovery of structural reduction candidates."""

from __future__ import annotations

from typing import Any

from wavebridge.analysis.block_reduction import recover as recover_block
from wavebridge.analysis.xor_reduction import recover as recover_xor

MAX_REACHABLE_FUNCTIONS = 64
MAX_CANDIDATE_ATTEMPTS = 512
DIRECT_CALL_KINDS = {"CallExpr", "CXXMemberCallExpr"}
SPECIAL_CALL_KINDS = {"CXXOperatorCallExpr", "CUDAKernelCallExpr"}
CALLEE_WRAPPERS = {"ParenExpr", "ImplicitCastExpr"}
ALLOWED_CALLEE_CASTS = {"FunctionToPointerDecay", "NoOp", "BuiltinFnToFnPtr"}


def _children(node: dict[str, Any]) -> list[dict[str, Any]]:
    inner = node.get("inner", [])
    return [child for child in inner if isinstance(child, dict) and child] if isinstance(inner, list) else []


def _walk(node: dict[str, Any]):
    yield node
    for child in _children(node):
        yield from _walk(child)


def _walk_function_body(node: dict[str, Any]):
    """Walk executable syntax without entering nested callable definitions."""
    yield node
    for child in _children(node):
        if child.get("kind") in {"FunctionDecl", "CXXMethodDecl", "LambdaExpr"}:
            yield child
            continue
        yield from _walk_function_body(child)


def _body(node: dict[str, Any]) -> dict[str, Any] | None:
    bodies = [child for child in _children(node) if child.get("kind") == "CompoundStmt"]
    return bodies[0] if len(bodies) == 1 else None


def _callee(call: dict[str, Any], declarations: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    result: dict[str, Any] = {"callee_id": None, "reason": None, "receiver_ast": None,
                              "receiver_semantics": "not_applicable",
                              "dispatch": "not_established", "callee_casts": []}
    children = _children(call)
    if not children:
        result["reason"] = "callee_missing"
        return result
    current = children[0]
    while current.get("kind") in CALLEE_WRAPPERS:
        wrapped = _children(current)
        if len(wrapped) != 1:
            result["reason"] = "ambiguous_callee_wrapper"
            return result
        if (current.get("kind") == "ImplicitCastExpr" and
                current.get("castKind") not in ALLOWED_CALLEE_CASTS):
            result["reason"] = "unsupported_callee_cast"
            return result
        if current.get("kind") == "ImplicitCastExpr":
            result["callee_casts"].append({
                "cast_kind": current.get("castKind"),
                "source_type": wrapped[0].get("type"),
                "destination_type": current.get("type"),
                "range": current.get("range"),
                "semantic_obligation": "not_discharged",
            })
        current = wrapped[0]
    if current.get("kind") == "DeclRefExpr":
        referenced = current.get("referencedDecl")
        if (isinstance(referenced, dict) and referenced.get("kind") == "FunctionDecl" and
                isinstance(referenced.get("id"), str)):
            result.update(callee_id=referenced["id"], dispatch="direct_free_function")
            return result
        result["reason"] = "indirect_or_unresolved_callee"
        return result
    if current.get("kind") == "MemberExpr":
        referenced = current.get("referencedMemberDecl")
        if isinstance(referenced, dict):
            member_id = referenced.get("id")
            referenced_kind = referenced.get("kind")
        else:
            member_id, referenced_kind = referenced, None
        result["receiver_ast"] = _children(current)
        result["receiver_semantics"] = "not_established"
        if not isinstance(member_id, str):
            result["reason"] = "member_callee_id_missing"
            return result
        matching = declarations.get(member_id, [])
        methods = [node for node in matching if node.get("kind") == "CXXMethodDecl"]
        if referenced_kind not in {None, "CXXMethodDecl"} or not methods:
            result["reason"] = "member_callee_declaration_missing"
            return result
        if any(method.get("virtual") is True for method in methods):
            result["reason"] = "dynamic_virtual_member_call"
            return result
        if not all(method.get("storageClass") == "static" for method in methods):
            result["reason"] = "member_dispatch_not_proven_static"
            return result
        result.update(callee_id=member_id, dispatch="static_member_exact_declref")
        return result
    result["reason"] = "indirect_or_unresolved_callee"
    return result


def discover(root: object, entry_id: str, int_bits: int) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema_version": "reduction-discovery/v1", "status": "unknown", "reason": None,
        "entry_function_id": entry_id, "int_bits": int_bits,
        "reachable_function_ids": [], "call_edges": [], "unresolved_calls": [],
        "xor_candidates": [], "block_candidates": [], "candidate_attempts": 0,
        "analysis_complete": False,
        "traversal_budget_complete": False,
        "budget": {"max_reachable_functions": MAX_REACHABLE_FUNCTIONS,
                   "max_candidate_attempts": MAX_CANDIDATE_ATTEMPTS,
                   "reachable_function_budget_exhausted": False,
                   "candidate_budget_exhausted": False},
        "direct_call_semantics": "syntactic_exact_declref_only",
        "external_call_semantics": "not_established", "checked": False,
        "deployable": False, "relation_recovery": "incomplete",
    }
    if not isinstance(root, dict):
        result["reason"] = "root_not_object"
        return result
    if type(int_bits) is not int or not 2 <= int_bits <= 128:
        result["reason"] = "invalid_int_bits"
        return result

    declarations: dict[str, list[dict[str, Any]]] = {}
    for node in _walk(root):
        if node.get("kind") in {"FunctionDecl", "CXXMethodDecl"} and isinstance(node.get("id"), str):
            declarations.setdefault(node["id"], []).append(node)
    definitions: dict[str, dict[str, Any]] = {}
    for identifier, nodes in declarations.items():
        with_body = [node for node in nodes if _body(node) is not None]
        if len(with_body) == 1:
            definitions[identifier] = with_body[0]
    if entry_id not in definitions:
        result["reason"] = "entry_unique_definition_not_found"
        return result

    queue = [entry_id]
    visited: set[str] = set()
    visit_order: list[str] = []
    targets_by_function: dict[str, list[str]] = {}
    while queue:
        function_id = queue.pop(0)
        if function_id in visited:
            continue
        if len(visited) >= MAX_REACHABLE_FUNCTIONS:
            result["budget"]["reachable_function_budget_exhausted"] = True
            break
        visited.add(function_id)
        visit_order.append(function_id)
        function = definitions[function_id]
        body = _body(function)
        targets: list[str] = []
        seen_targets: set[str] = set()
        body_nodes = list(_walk_function_body(body))
        for nested in (node for node in body_nodes
                       if node.get("kind") in {"FunctionDecl", "CXXMethodDecl", "LambdaExpr"}):
            result["unresolved_calls"].append({"caller_id": function_id,
                "call_kind": nested.get("kind"), "call_range": nested.get("range"),
                "reason": "unsupported_nested_callable"})
        for call in (node for node in body_nodes if node.get("kind") in DIRECT_CALL_KINDS | SPECIAL_CALL_KINDS):
            if call.get("kind") in SPECIAL_CALL_KINDS:
                result["unresolved_calls"].append({"caller_id": function_id,
                    "call_kind": call.get("kind"), "call_range": call.get("range"),
                    "reason": "unsupported_call_kind"})
                continue
            callee = _callee(call, declarations)
            target_id, reason = callee["callee_id"], callee["reason"]
            if target_id is None:
                result["unresolved_calls"].append({"caller_id": function_id,
                    "call_kind": call.get("kind"), "call_range": call.get("range"), "reason": reason,
                    "receiver_ast": callee["receiver_ast"],
                    "callee_casts": callee["callee_casts"],
                    "receiver_semantics": callee["receiver_semantics"]})
                continue
            result["call_edges"].append({"caller_id": function_id, "callee_id": target_id,
                                          "call_range": call.get("range"),
                                          "dispatch": callee["dispatch"],
                                          "callee_casts": callee["callee_casts"],
                                          "receiver_ast": callee["receiver_ast"],
                                          "receiver_semantics": callee["receiver_semantics"]})
            if target_id not in seen_targets:
                seen_targets.add(target_id)
                targets.append(target_id)
            if target_id in definitions and target_id not in visited:
                queue.append(target_id)
            elif target_id not in definitions:
                result["unresolved_calls"].append({"caller_id": function_id,
                    "callee_id": target_id, "call_range": call.get("range"),
                    "reason": "callee_unique_definition_not_found"})
        targets_by_function[function_id] = targets

    result["reachable_function_ids"] = visit_order
    recovered_keys: set[tuple[str, ...]] = set()
    budget_exhausted = False
    for function_id in result["reachable_function_ids"]:
        targets = targets_by_function.get(function_id, [])
        definition = definitions[function_id]
        statement_count = len(_children(_body(definition)))
        parameters = [child for child in _children(definition) if child.get("kind") == "ParmVarDecl"]
        # Structural prefilters avoid repeatedly scanning a large full TU for functions
        # which cannot satisfy the strict recovery schemas. They do not use names.
        xor_targets = targets if statement_count == 2 and len(parameters) == 1 else []
        block_targets = targets if statement_count == 7 and len(parameters) == 2 else []
        for shuffle_id in xor_targets:
            if result["candidate_attempts"] >= MAX_CANDIDATE_ATTEMPTS:
                budget_exhausted = True
                break
            result["candidate_attempts"] += 1
            candidate = recover_xor(root, function_id, shuffle_id, int_bits)
            if candidate.get("status") == "recovered":
                key = ("xor", function_id, shuffle_id)
                if key not in recovered_keys:
                    recovered_keys.add(key)
                    candidate = dict(candidate)
                    candidate.setdefault("function_id", function_id)
                    candidate.setdefault("shuffle_declaration_id", shuffle_id)
                    candidate["shuffle_declaration_selection"] = "direct_call_candidate_not_semantic_identification"
                    candidate["discovery_basis"] = "reachable_direct_call_exact_declref"
                    result["xor_candidates"].append(candidate)
        if budget_exhausted:
            break
        for reduce_id in block_targets:
            for barrier_id in block_targets:
                if reduce_id == barrier_id:
                    continue
                if result["candidate_attempts"] >= MAX_CANDIDATE_ATTEMPTS:
                    budget_exhausted = True
                    break
                result["candidate_attempts"] += 1
                candidate = recover_block(root, function_id, reduce_id, barrier_id, int_bits)
                if candidate.get("status") == "recovered":
                    key = ("block", function_id, reduce_id, barrier_id)
                    if key not in recovered_keys:
                        recovered_keys.add(key)
                        candidate = dict(candidate)
                        candidate.setdefault("function_id", function_id)
                        candidate.setdefault("reduce_declaration_id", reduce_id)
                        candidate.setdefault("barrier_declaration_id", barrier_id)
                        candidate["discovery_basis"] = "reachable_direct_call_pair_exact_declref"
                        result["block_candidates"].append(candidate)
            if budget_exhausted:
                break
        if budget_exhausted:
            break
    result["budget"]["candidate_budget_exhausted"] = budget_exhausted
    result["traversal_budget_complete"] = not (budget_exhausted or
        result["budget"]["reachable_function_budget_exhausted"])
    result["analysis_complete"] = (result["traversal_budget_complete"] and
                                   not result["unresolved_calls"])
    result["status"] = "analyzed"
    return result
