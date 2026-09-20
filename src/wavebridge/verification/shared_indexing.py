"""Conditionally check shared-partial predicates and indices pointwise."""

from __future__ import annotations

from typing import Any

from wavebridge.verification.getter_returns import _hash
from wavebridge.verification.integer_conversion import check_interval
from wavebridge.verification.kernel_arguments import _abi_type, _Unknown


ACCESS_KEYS = {"writer_predicate", "writer_index", "gather_predicate", "gather_index"}
BINDING_KEYS = {"group_declaration_id", "lane_declaration_id",
                "width_declaration_id", "block_declaration_id"}
MAX_DEPTH = 32
MAX_NODES = 512


class _Rejected(Exception):
    def __init__(self, reason: str, detail: object = None):
        self.reason, self.detail = reason, detail


def _children(node: dict[str, Any]) -> list[dict[str, Any]]:
    children = node.get("inner", [])
    if not isinstance(children, list) or any(not isinstance(child, dict) or not child
                                             for child in children):
        raise _Unknown("malformed_expression_children")
    return children


def _bool_type(node: dict[str, Any]) -> bool:
    info = node.get("type")
    if not isinstance(info, dict):
        return False
    spelling = info.get("desugaredQualType") or info.get("qualType")
    return spelling == "bool"


def check(access_asts: object, bindings: object, width: object, block_threads: object,
          integer_types: object) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema_version": "shared-indexing-check/v1", "status": "unknown", "reason": None,
        "width": width, "block_threads": block_threads, "groups": None,
        "counterexample": None, "conversion_checks": [],
        "source_program_checked": False, "deployable": False,
        "scope": "shared_partial_writer_and_gather_predicates_and_indices_only",
        "assumptions": [
            "group and lane declarations equal t/width and t%width for every modeled thread",
            "width and block declarations equal the supplied constants",
            "the supplied ASTs and declaration bindings come from the same faithful source AST",
            "the explicit integer ABI matches the source compilation target",
        ],
        "limitations": [
            "pointer validity, shared capacity, aliasing and synchronization are not checked",
            "the values stored or gathered and their contribution semantics are not checked",
        ],
        "budget": {"max_threads": 1024, "max_depth": MAX_DEPTH,
                   "max_nodes": MAX_NODES, "nodes_used": 0},
    }
    if (not isinstance(access_asts, dict) or not isinstance(bindings, dict) or
            not isinstance(integer_types, dict) or type(width) is not int or
            type(block_threads) is not int):
        result["reason"] = "invalid_inputs"
        return result
    try:
        result["input_sha256"] = {
            "access_asts": _hash(access_asts), "bindings": _hash(bindings),
            "width": _hash(width), "block_threads": _hash(block_threads),
            "integer_types": _hash(integer_types),
        }
    except (TypeError, ValueError, RecursionError):
        result["reason"] = "input_hash_unsupported"
        return result
    try:
        if set(access_asts) != ACCESS_KEYS or any(not isinstance(access_asts[key], dict) or
                                                  not access_asts[key] for key in ACCESS_KEYS):
            raise _Unknown("access_ast_set_invalid")
        if set(bindings) != BINDING_KEYS:
            raise _Unknown("binding_set_invalid")
        identifiers = list(bindings.values())
        if (any(not isinstance(identifier, str) or not identifier for identifier in identifiers) or
                len(set(identifiers)) != len(identifiers)):
            raise _Unknown("binding_ids_missing_or_repeated")
        if (not 1 <= block_threads <= 1024 or width <= 0 or block_threads % width != 0 or
                block_threads // width > width):
            raise _Unknown("unsupported_block_width_relationship")
        groups = block_threads // width
        result["groups"] = groups

        nodes = 0

        def validate(node: dict[str, Any], depth: int) -> None:
            nonlocal nodes
            if depth > MAX_DEPTH:
                raise _Unknown("expression_depth_budget_exceeded")
            if not isinstance(node.get("kind"), str):
                raise _Unknown("expression_kind_missing")
            nodes += 1
            if nodes > MAX_NODES:
                raise _Unknown("expression_node_budget_exceeded")
            for child in _children(node):
                validate(child, depth + 1)

        for ast in access_asts.values():
            validate(ast, 0)
        result["budget"]["nodes_used"] = nodes

        def scalar(node: dict[str, Any]) -> tuple[str, int, bool]:
            return _abi_type(node.get("type"), integer_types)

        def representable(value: int, ty: tuple[str, int, bool]) -> bool:
            return check_interval(value, value, ty[1], ty[2], ty[1], ty[2]).get("status") == "checked"

        def evaluate(node: dict[str, Any], thread: int, depth: int):
            if depth > MAX_DEPTH:
                raise _Unknown("expression_depth_budget_exceeded")
            kind = node.get("kind")
            children = _children(node)
            if kind == "DeclRefExpr":
                if children or node.get("valueCategory") != "lvalue":
                    raise _Unknown("declaration_reference_malformed")
                reference = node.get("referencedDecl")
                if not isinstance(reference, dict) or reference.get("kind") != "VarDecl":
                    raise _Unknown("declaration_reference_not_bound_variable")
                declaration_id = reference.get("id")
                values = {
                    bindings["group_declaration_id"]: thread // width,
                    bindings["lane_declaration_id"]: thread % width,
                    bindings["width_declaration_id"]: width,
                    bindings["block_declaration_id"]: block_threads,
                }
                if not isinstance(declaration_id, str) or declaration_id not in values:
                    raise _Unknown("declaration_reference_not_bound_variable")
                value, ty = values[declaration_id], scalar(node)
                if not representable(value, ty):
                    raise _Unknown("bound_value_not_representable")
                return value, ty
            if kind == "IntegerLiteral":
                if children or node.get("valueCategory") != "prvalue":
                    raise _Unknown("integer_literal_malformed")
                text = node.get("value")
                if not isinstance(text, str) or not text.isdecimal() or len(text) > 39:
                    raise _Unknown("nonnegative_integer_literal_required")
                value, ty = int(text), scalar(node)
                if not representable(value, ty):
                    raise _Unknown("integer_literal_not_representable")
                return value, ty
            if kind in {"ParenExpr", "ImplicitCastExpr"}:
                if len(children) != 1 or node.get("valueCategory") != "prvalue":
                    raise _Unknown("unsupported_expression_wrapper")
                value, source = evaluate(children[0], thread, depth + 1)
                if kind == "ParenExpr":
                    if source == "bool":
                        if not _bool_type(node):
                            raise _Unknown("parenthesis_type_discontinuity")
                        return value, source
                    target = scalar(node)
                    if source != target:
                        raise _Unknown("parenthesis_type_discontinuity")
                    return value, target
                cast_kind = node.get("castKind")
                if not isinstance(cast_kind, str) or cast_kind not in {"IntegralCast", "LValueToRValue", "NoOp"}:
                    raise _Unknown("unsupported_expression_cast")
                if source == "bool":
                    if cast_kind not in {"LValueToRValue", "NoOp"} or not _bool_type(node):
                        raise _Unknown("boolean_cast_unsupported")
                    return value, source
                target = scalar(node)
                if cast_kind in {"LValueToRValue", "NoOp"} and source[0] != target[0]:
                    raise _Unknown("nonconverting_cast_type_discontinuity")
                conversion = check_interval(value, value, source[1], source[2],
                                            target[1], target[2])
                evidence = {"thread": thread, "cast_kind": cast_kind,
                            "source_type": source[0], "target_type": target[0],
                            "range": node.get("range"), "conversion": conversion}
                result["conversion_checks"].append(evidence)
                if conversion.get("status") == "rejected":
                    raise _Rejected("expression_cast_not_value_preserving", evidence)
                if conversion.get("status") != "checked":
                    raise _Unknown("expression_cast_check_unknown")
                return value, target
            if kind == "BinaryOperator":
                if len(children) != 2 or node.get("valueCategory") != "prvalue":
                    raise _Unknown("binary_expression_malformed")
                opcode = node.get("opcode")
                if not isinstance(opcode, str) or opcode not in {"/", "%", "==", "<"}:
                    raise _Unknown("unsupported_binary_operator")
                left, left_type = evaluate(children[0], thread, depth + 1)
                right, right_type = evaluate(children[1], thread, depth + 1)
                if left_type == "bool" or right_type == "bool" or left_type != right_type:
                    raise _Unknown("binary_operand_type_discontinuity")
                if opcode in {"/", "%"}:
                    target = scalar(node)
                    if target != left_type:
                        raise _Unknown("binary_result_type_discontinuity")
                    if right == 0:
                        raise _Unknown("division_by_zero")
                    value = left // right if opcode == "/" else left % right
                    if not representable(value, target):
                        raise _Unknown("binary_result_not_representable")
                    return value, target
                if not _bool_type(node):
                    raise _Unknown("comparison_result_not_bool")
                return (left == right if opcode == "==" else left < right), "bool"
            raise _Unknown("unsupported_expression_node")

        for thread in range(block_threads):
            lane, group = thread % width, thread // width
            writer, writer_type = evaluate(access_asts["writer_predicate"], thread, 0)
            if writer_type != "bool":
                raise _Unknown("writer_predicate_not_bool")
            expected_writer = lane == 0
            if writer is not expected_writer:
                raise _Rejected("writer_predicate_mismatch", {
                    "thread": thread, "actual": writer, "expected": expected_writer})
            gather, gather_type = evaluate(access_asts["gather_predicate"], thread, 0)
            if gather_type != "bool":
                raise _Unknown("gather_predicate_not_bool")
            expected_gather = lane < groups
            if gather is not expected_gather:
                raise _Rejected("gather_predicate_mismatch", {
                    "thread": thread, "actual": gather, "expected": expected_gather})
            if expected_writer:
                actual, actual_type = evaluate(access_asts["writer_index"], thread, 0)
                if actual_type == "bool":
                    raise _Unknown("writer_index_not_integer")
                if actual != group:
                    raise _Rejected("writer_index_mismatch", {
                        "thread": thread, "actual": actual, "expected": group})
            if expected_gather:
                actual, actual_type = evaluate(access_asts["gather_index"], thread, 0)
                if actual_type == "bool":
                    raise _Unknown("gather_index_not_integer")
                if actual != lane:
                    raise _Rejected("gather_index_mismatch", {
                        "thread": thread, "actual": actual, "expected": lane})
        result["status"] = "checked"
    except _Rejected as error:
        result.update(status="rejected", reason=error.reason, counterexample=error.detail)
    except _Unknown as error:
        result["reason"] = error.reason
    return result
