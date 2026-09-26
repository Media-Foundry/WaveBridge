"""Inventory explicit uses of the width selected by a recovered reduction chain.

This is deliberately an evidence extractor, not a transformation-safety check.  It
classifies only the five exact ``DeclRefExpr`` positions already accepted by the
block/XOR recovery schemas; every other explicit reference remains unsupported.
"""

from __future__ import annotations

from typing import Any

from wavebridge.analysis.reduction_chain import recover as recover_chain
from wavebridge.analysis.reduction_discovery import discover


MAX_AST_NODES = 1_000_000
HARD_MAX_AST_NODES = 10_000_000
FUNCTION_KINDS = {"FunctionDecl", "CXXMethodDecl"}
EXPECTED_ROLES = {
    "xor_initial_offset",
    "xor_intrinsic_width",
    "block_group_divisor",
    "block_lane_modulus",
    "block_group_count_divisor",
}


class _Unknown(Exception):
    def __init__(self, reason: str):
        self.reason = reason


def _children(node: dict[str, Any]) -> list[dict[str, Any]]:
    inner = node.get("inner", [])
    if not isinstance(inner, list):
        raise _Unknown("ast_inner_not_list")
    result = []
    for child in inner:
        if not isinstance(child, dict):
            raise _Unknown("ast_child_not_object")
        if child:
            result.append(child)
    return result


def _summary(node: dict[str, Any]) -> dict[str, Any]:
    return {key: node[key] for key in ("kind", "id", "range") if key in node}


def _type(node: dict[str, Any]) -> str | None:
    value = node.get("type")
    if not isinstance(value, dict):
        return None
    desugared = value.get("desugaredQualType")
    if "typeAliasDeclId" in value and not isinstance(desugared, str):
        return None
    return desugared if isinstance(desugared, str) else value.get("qualType")


def _same_range(left: object, right: object) -> bool:
    return isinstance(left, dict) and isinstance(right, dict) and left == right


def _refs(node: dict[str, Any], declaration_id: str) -> list[dict[str, Any]]:
    found, stack = [], [node]
    while stack:
        current = stack.pop()
        referenced = current.get("referencedDecl")
        if (current.get("kind") == "DeclRefExpr" and isinstance(referenced, dict)
                and referenced.get("id") == declaration_id):
            found.append(current)
        stack.extend(reversed(_children(current)))
    return found


def _direct_operand_ancestor(
        reference: dict[str, Any], ancestors: list[dict[str, Any]], kind: str,
        *, opcode: str | None = None) -> tuple[dict[str, Any], int] | None:
    child = reference
    for index in range(len(ancestors) - 1, -1, -1):
        parent = ancestors[index]
        if parent.get("kind") in {"ParenExpr", "ImplicitCastExpr"}:
            children = _children(parent)
            if len(children) != 1 or children[0] is not child:
                return None
            if (parent.get("kind") == "ImplicitCastExpr" and
                    parent.get("castKind") not in {"LValueToRValue", "NoOp", "IntegralCast"}):
                return None
            child = parent
            continue
        if parent.get("kind") != kind or (opcode is not None and parent.get("opcode") != opcode):
            return None
        children = _children(parent)
        positions = [position for position, item in enumerate(children) if item is child]
        return (parent, positions[0]) if len(positions) == 1 else None
    return None


def inspect(root: object, kernel_id: str, int_bits: int, *,
            max_ast_nodes: int = MAX_AST_NODES) -> dict[str, Any]:
    """Classify all explicit references to the freshly recovered width declaration."""
    result: dict[str, Any] = {
        "schema_version": "width-use-evidence/v1", "status": "unknown", "reason": None,
        "kernel_id": kernel_id, "int_bits": int_bits, "width_declaration_id": None,
        "width": None, "uses": [], "role_counts": {}, "explicit_reference_count": 0,
        "all_explicit_declref_uses_classified": False,
        "implicit_or_constant_folded_uses_covered": False,
        "conversion_semantics": "not_established_beyond_supported_syntactic_cast_kinds",
        "checked": False, "source_program_checked": False, "deployable": False,
        "scope": "explicit_DeclRefExpr_uses_of_one_fresh_recovered_width_declaration_only",
        "limitations": [
            "absence_of_DeclRefExpr_does_not_establish_absence_of_a_semantic_width_use",
            "classified_evidence_does_not_establish_source_target_equivalence_or_edit_safety",
            "external_or_diagnostic_uses_are_not_treated_as_safe",
        ],
        "budget": {"max_ast_nodes": max_ast_nodes, "visited_ast_nodes": 0},
    }

    def unknown(reason: str) -> dict[str, Any]:
        result["reason"] = reason
        return result

    if not isinstance(root, dict):
        return unknown("root_not_object")
    if root.get("kind") != "TranslationUnitDecl":
        return unknown("root_not_translation_unit")
    if not isinstance(kernel_id, str) or not kernel_id:
        return unknown("kernel_id_invalid")
    if type(int_bits) is not int or not 2 <= int_bits <= 128:
        return unknown("invalid_int_bits")
    if (type(max_ast_nodes) is not int or max_ast_nodes <= 0 or
            max_ast_nodes > HARD_MAX_AST_NODES):
        return unknown("invalid_max_ast_nodes")

    nodes: list[tuple[dict[str, Any], list[dict[str, Any]], str | None]] = []
    identifiers: dict[str, list[dict[str, Any]]] = {}
    active: set[int] = set()

    def walk(node: dict[str, Any], ancestors: list[dict[str, Any]], owner: str | None) -> None:
        identity = id(node)
        if identity in active:
            raise _Unknown("ast_cycle")
        if len(nodes) >= max_ast_nodes:
            raise _Unknown("ast_node_budget_exceeded")
        active.add(identity)
        current_owner = node.get("id") if (node.get("kind") in FUNCTION_KINDS and
                                             isinstance(node.get("id"), str)) else owner
        nodes.append((node, ancestors, current_owner))
        identifier = node.get("id")
        if isinstance(identifier, str) and identifier:
            identifiers.setdefault(identifier, []).append(node)
        for child in _children(node):
            walk(child, [*ancestors, node], current_owner)
        active.remove(identity)

    try:
        walk(root, [], None)
    except (_Unknown, RecursionError) as error:
        result["budget"]["visited_ast_nodes"] = len(nodes)
        return unknown(error.reason if isinstance(error, _Unknown) else "ast_recursion_limit_exceeded")
    result["budget"]["visited_ast_nodes"] = len(nodes)

    try:
        chain = recover_chain(root, kernel_id, int_bits)
        discovery = discover(root, kernel_id, int_bits)
    except RecursionError:
        return unknown("recovery_recursion_limit_exceeded")
    result["chain_recovery"] = chain
    result["discovery"] = discovery
    if chain.get("status") != "recovered":
        return unknown("reduction_chain_not_recovered")
    if not discovery.get("traversal_budget_complete"):
        return unknown("reduction_discovery_incomplete")
    links = chain.get("links")
    if not isinstance(links, list) or len(links) < 2:
        return unknown("reduction_chain_links_incomplete")
    block_id, xor_id = links[0].get("callee_id"), links[1].get("callee_id")
    blocks = [item for item in discovery.get("block_candidates", [])
              if isinstance(item, dict) and item.get("function_id") == block_id]
    xors = [item for item in discovery.get("xor_candidates", [])
            if isinstance(item, dict) and item.get("function_id") == xor_id]
    if len(blocks) != 1 or len(xors) != 1:
        return unknown("chain_reduction_candidates_not_unique")
    block, xor = blocks[0], xors[0]
    block_bindings, xor_bindings = block.get("bindings"), xor.get("bindings")
    if not isinstance(block_bindings, dict) or not isinstance(xor_bindings, dict):
        return unknown("width_bindings_missing")
    width_id = block_bindings.get("width_declaration_id")
    if (not isinstance(width_id, str) or not width_id or
            xor_bindings.get("width_declaration_id") != width_id):
        return unknown("block_xor_width_declaration_mismatch")
    result["width_declaration_id"] = width_id
    result["width"] = chain.get("width")

    declarations = identifiers.get(width_id, [])
    if len(declarations) != 1 or declarations[0].get("kind") != "VarDecl":
        return unknown("width_declaration_not_globally_unique")
    declaration = declarations[0]
    declaration_type = _type(declaration)
    if not isinstance(declaration_type, str):
        return unknown("width_declaration_type_missing")
    result["width_declaration"] = _summary(declaration) | {"type": declaration.get("type")}

    expected_by_identity: dict[int, str] = {}
    sources = [
        (block.get("index_initializers", {}).get("group"), "block_group_divisor"),
        (block.get("index_initializers", {}).get("lane"), "block_lane_modulus"),
        (block.get("shared_access_asts", {}).get("gather_predicate"),
         "block_group_count_divisor"),
    ]
    try:
        for subtree, role in sources:
            if not isinstance(subtree, dict):
                return unknown("block_width_role_ast_missing")
            matches = _refs(subtree, width_id)
            if len(matches) != 1:
                return unknown("block_width_role_not_unique")
            expected_by_identity[id(matches[0])] = role
    except _Unknown as error:
        return unknown(error.reason)

    uses = [(node, ancestors, owner) for node, ancestors, owner in nodes
            if node.get("kind") == "DeclRefExpr" and
            isinstance(node.get("referencedDecl"), dict) and
            node["referencedDecl"].get("id") == width_id]
    result["explicit_reference_count"] = len(uses)
    role_counts: dict[str, int] = {}
    for reference, ancestors, owner in uses:
        role = expected_by_identity.get(id(reference))
        if role is None and owner == xor_id:
            division = _direct_operand_ancestor(reference, ancestors, "BinaryOperator", opcode="/")
            call = _direct_operand_ancestor(reference, ancestors, "CallExpr")
            ranges = xor.get("ranges", {})
            if (division is not None and division[1] == 0 and
                    _same_range(division[0].get("range"), ranges.get("initializer"))):
                role = "xor_initial_offset"
            elif (call is not None and
                  _same_range(call[0].get("range"), ranges.get("call")) and
                  call[1] == len(_children(call[0])) - 1):
                role = "xor_intrinsic_width"
        if role is None:
            role = "external_other"

        expression_id = reference.get("id")
        if not isinstance(expression_id, str) or not expression_id:
            return unknown("width_reference_id_missing")
        if len(identifiers.get(expression_id, [])) != 1:
            return unknown("width_reference_id_not_unique")
        referenced = reference.get("referencedDecl")
        referenced_type = _type(referenced)
        if (referenced.get("kind") != "VarDecl" or referenced_type != declaration_type or
                _children(reference) or
                reference.get("valueCategory") not in {None, "lvalue"} or
                _type(reference) != declaration_type):
            return unknown("width_reference_shape_or_type_mismatch")
        role_counts[role] = role_counts.get(role, 0) + 1
        result["uses"].append({
            "expression_id": expression_id, "role": role,
            "owning_function_id": owner, "type": reference.get("type"),
            "value_category": reference.get("valueCategory"), "range": reference.get("range"),
            "ancestors_outer_to_inner": [_summary(item) for item in ancestors],
        })

    result["role_counts"] = role_counts
    if any(role_counts.get(role) != 1 for role in EXPECTED_ROLES):
        return unknown("required_width_role_use_missing_or_duplicated")
    if role_counts.get("external_other", 0):
        return unknown("explicit_width_uses_not_fully_classified")
    result.update(status="evidence", all_explicit_declref_uses_classified=True)
    return result
