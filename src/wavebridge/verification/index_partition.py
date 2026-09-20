"""Check a restricted source expression against one index-partition relation."""

from __future__ import annotations

from typing import Any

from wavebridge.verification.getter_returns import _hash
from wavebridge.verification.integer_conversion import check_interval
from wavebridge.verification.kernel_arguments import _abi_type, _Unknown


MAX_DEPTH = 32
MAX_NODES = 128


class _Rejected(Exception):
    def __init__(self, reason: str, detail: object = None):
        self.reason, self.detail = reason, detail


def _children(node: dict[str, Any]) -> list[dict[str, Any]]:
    children = node.get("inner", [])
    if not isinstance(children, list) or any(not isinstance(child, dict) or not child
                                             for child in children):
        raise _Unknown("malformed_expression_children")
    return children


def check(expression: object, coordinate_expression: object,
          width_declaration_id: object, width: object, block_threads: object,
          integer_types: object, *, operation: object) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema_version": "index-partition-check/v1", "status": "unknown", "reason": None,
        "operator": operation, "width": width, "block_threads": block_threads,
        "output_range": None, "counterexample": None, "conversion_checks": [],
        "source_program_checked": False, "deployable": False,
        "scope": "pointwise_index_partition_for_one_explicit_block_domain",
        "assumptions": [
            "coordinate_expression is trusted evidence for workgroup local x=t for every thread",
            "width_declaration_id denotes the supplied true width constant",
            "the explicit integer ABI matches the source compilation target",
            "the source expression is valid and evaluated for every modeled thread",
        ],
        "budget": {"max_depth": MAX_DEPTH, "max_nodes": MAX_NODES,
                   "nodes_used": 0, "coordinate_anchors": 0},
    }
    if (not isinstance(expression, dict) or not isinstance(coordinate_expression, dict) or
            not isinstance(integer_types, dict) or
            not isinstance(width_declaration_id, str) or not width_declaration_id or
            type(width) is not int or type(block_threads) is not int or
            not isinstance(operation, str) or operation not in {"/", "%"}):
        result["reason"] = "invalid_inputs"
        return result
    try:
        result["input_sha256"] = {
            "expression": _hash(expression), "coordinate_expression": _hash(coordinate_expression),
            "width_declaration_id": _hash(width_declaration_id), "width": _hash(width),
            "block_threads": _hash(block_threads), "integer_types": _hash(integer_types),
            "operation": _hash(operation),
        }
    except (TypeError, ValueError, RecursionError):
        result["reason"] = "input_hash_unsupported"
        return result

    try:
        if not 1 <= block_threads <= 1024:
            raise _Unknown("block_threads_unsupported")
        if width <= 0:
            raise _Unknown("width_not_positive")
        coordinate_id = coordinate_expression.get("id")
        if (not isinstance(coordinate_id, str) or not coordinate_id or
                coordinate_expression.get("kind") == "BinaryOperator"):
            raise _Unknown("coordinate_anchor_unsupported")
        coordinate_reference = coordinate_expression.get("referencedDecl")
        if (coordinate_expression.get("kind") == "DeclRefExpr" and
                isinstance(coordinate_reference, dict) and
                coordinate_reference.get("id") == width_declaration_id):
            raise _Unknown("coordinate_anchor_is_width_reference")

        nodes = 0
        anchors = 0

        def validate_tree(node: dict[str, Any], depth: int, inside_anchor: bool = False) -> None:
            nonlocal nodes, anchors
            if not isinstance(node.get("kind"), str):
                raise _Unknown("expression_kind_missing")
            if depth > MAX_DEPTH:
                raise _Unknown("expression_depth_budget_exceeded")
            nodes += 1
            if nodes > MAX_NODES:
                raise _Unknown("expression_node_budget_exceeded")
            is_anchor = not inside_anchor and node == coordinate_expression
            if is_anchor:
                anchors += 1
            for child in _children(node):
                validate_tree(child, depth + 1, inside_anchor or is_anchor)

        validate_tree(expression, 0)
        result["budget"].update(nodes_used=nodes, coordinate_anchors=anchors)
        if anchors != 1 or expression == coordinate_expression:
            raise _Unknown("coordinate_anchor_count_not_one")

        def scalar(node: dict[str, Any]) -> tuple[str, int, bool]:
            return _abi_type(node.get("type"), integer_types)

        def represented(value: int, ty: tuple[str, int, bool]) -> bool:
            return check_interval(value, value, ty[1], ty[2], ty[1], ty[2]).get("status") == "checked"

        def evaluate(node: dict[str, Any], thread: int, depth: int) -> tuple[int, tuple[str, int, bool]]:
            if depth > MAX_DEPTH:
                raise _Unknown("expression_depth_budget_exceeded")
            if node == coordinate_expression:
                ty = scalar(node)
                if not represented(thread, ty):
                    raise _Unknown("coordinate_not_representable")
                return thread, ty
            kind = node.get("kind")
            children = _children(node)
            if kind in {"ParenExpr", "ImplicitCastExpr"}:
                if len(children) != 1 or node.get("valueCategory") != "prvalue":
                    raise _Unknown("unsupported_expression_wrapper")
                cast_kind = node.get("castKind")
                if kind == "ImplicitCastExpr" and cast_kind not in ("IntegralCast", "LValueToRValue", "NoOp"):
                    raise _Unknown("unsupported_expression_cast")
                value, source = evaluate(children[0], thread, depth + 1)
                target = scalar(node)
                if kind == "ParenExpr":
                    if source != target:
                        raise _Unknown("parenthesis_type_discontinuity")
                    return value, target
                if cast_kind in {"LValueToRValue", "NoOp"} and source[0] != target[0]:
                    raise _Unknown("nonconverting_cast_type_discontinuity")
                conversion = check_interval(value, value, source[1], source[2], target[1], target[2])
                evidence = {"thread": thread, "cast_kind": cast_kind,
                            "source_type": source[0], "target_type": target[0],
                            "range": node.get("range"), "conversion": conversion}
                result["conversion_checks"].append(evidence)
                if conversion.get("status") == "rejected":
                    raise _Rejected("expression_cast_not_value_preserving", evidence)
                if conversion.get("status") != "checked":
                    raise _Unknown("expression_cast_check_unknown")
                return value, target
            if kind == "IntegerLiteral":
                if children or node.get("valueCategory") != "prvalue":
                    raise _Unknown("integer_literal_malformed")
                text = node.get("value")
                if not isinstance(text, str) or not text.isdecimal() or len(text) > 39:
                    raise _Unknown("nonnegative_integer_literal_required")
                value = int(text)
                ty = scalar(node)
                if not represented(value, ty):
                    raise _Unknown("integer_literal_not_representable")
                return value, ty
            if kind == "DeclRefExpr":
                if children or node.get("valueCategory") != "lvalue":
                    raise _Unknown("width_reference_malformed")
                reference = node.get("referencedDecl")
                if (not isinstance(reference, dict) or reference.get("id") != width_declaration_id or
                        reference.get("kind") not in ("VarDecl", "ParmVarDecl")):
                    raise _Unknown("declaration_reference_not_width")
                ty = scalar(node)
                if not represented(width, ty):
                    raise _Unknown("width_not_representable")
                return width, ty
            if kind == "BinaryOperator":
                if (len(children) != 2 or node.get("opcode") not in ("/", "%") or
                        node.get("valueCategory") != "prvalue"):
                    raise _Unknown("unsupported_binary_expression")
                left, left_type = evaluate(children[0], thread, depth + 1)
                right, right_type = evaluate(children[1], thread, depth + 1)
                target = scalar(node)
                if left_type != target or right_type != target:
                    raise _Unknown("binary_operand_type_discontinuity")
                if right == 0:
                    raise _Unknown("division_by_zero")
                value = left // right if node["opcode"] == "/" else left % right
                if not represented(value, target):
                    raise _Unknown("binary_result_not_representable")
                return value, target
            raise _Unknown("unsupported_expression_node")

        # The requested relation must also be the expression's outer binary operation;
        # this prevents coincidental equality for degenerate one-thread domains.
        core = expression
        while core.get("kind") in {"ParenExpr", "ImplicitCastExpr"}:
            core_children = _children(core)
            if len(core_children) != 1:
                raise _Unknown("unsupported_expression_wrapper")
            core = core_children[0]
        if core.get("kind") != "BinaryOperator":
            raise _Unknown("partition_binary_operator_missing")
        if core.get("opcode") not in ("/", "%"):
            raise _Unknown("unsupported_binary_expression")
        if core.get("opcode") != operation:
            result.update(status="rejected", reason="partition_operator_mismatch")
            return result

        outputs = []
        for thread in range(block_threads):
            actual, _ = evaluate(expression, thread, 0)
            expected = thread // width if operation == "/" else thread % width
            if actual != expected:
                result.update(status="rejected", reason="index_partition_value_mismatch",
                              counterexample={"thread": thread, "actual": actual,
                                              "expected": expected})
                return result
            outputs.append(actual)
        result.update(status="checked", output_range={"lower": min(outputs), "upper": max(outputs)})
    except _Rejected as error:
        result.update(status="rejected", reason=error.reason, counterexample=error.detail)
    except _Unknown as error:
        result["reason"] = error.reason
    return result
