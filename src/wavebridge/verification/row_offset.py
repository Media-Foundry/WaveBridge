"""Check a restricted integer expression is exactly ``row * count``."""

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


def check(expression: object, row_declaration_id: object, count_declaration_id: object,
          row_interval: object, count_interval: object,
          integer_types: object) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema_version": "row-offset-check/v1", "status": "unknown", "reason": None,
        "symbolic_relation": None, "value_interval": None, "result_type": None,
        "conversion_checks": [], "counterexample": None,
        "counterexample_scope": "abstract_relation_or_domain_diagnostic_not_proven_runtime_reachable",
        "source_program_checked": False, "deployable": False,
        "scope": "restricted_nonnegative_integer_row_times_count_expression",
        "assumptions": [
            "the row and count declarations have values within the supplied intervals",
            "the supplied expression and declaration IDs come from one faithful source AST",
            "the explicit integer ABI matches the source compilation target",
        ],
        "limitations": [
            "does not prove pointer arithmetic, allocation bounds or alias safety",
            "does not prove floating-point behavior, source validity or interval reachability",
        ],
        "budget": {"max_depth": MAX_DEPTH, "max_nodes": MAX_NODES,
                   "nodes_used": 0, "maximum_depth_used": 0},
    }
    if (not isinstance(expression, dict) or not isinstance(integer_types, dict) or
            not isinstance(row_declaration_id, str) or not row_declaration_id or
            not isinstance(count_declaration_id, str) or not count_declaration_id or
            row_declaration_id == count_declaration_id or
            not isinstance(row_interval, dict) or not isinstance(count_interval, dict)):
        result["reason"] = "invalid_inputs"
        return result
    try:
        result["input_sha256"] = {
            "expression": _hash(expression), "row_declaration_id": _hash(row_declaration_id),
            "count_declaration_id": _hash(count_declaration_id),
            "row_interval": _hash(row_interval), "count_interval": _hash(count_interval),
            "integer_types": _hash(integer_types),
        }
    except (TypeError, ValueError, RecursionError):
        result["reason"] = "input_hash_unsupported"
        return result
    try:
        domains: dict[str, tuple[int, int, tuple[int, int]]] = {}
        for name, declaration_id, interval, powers in (
                ("row", row_declaration_id, row_interval, (1, 0)),
                ("count", count_declaration_id, count_interval, (0, 1))):
            lower, upper = interval.get("lower"), interval.get("upper")
            if (type(lower) is not int or type(upper) is not int or
                    lower < 0 or lower > upper):
                raise _Unknown("declaration_interval_invalid")
            domains[declaration_id] = (lower, upper, powers)

        nodes = 0
        maximum_depth = 0

        def represented(lower: int, upper: int, ty: tuple[str, int, bool]) -> bool:
            return check_interval(lower, upper, ty[1], ty[2], ty[1], ty[2]).get("status") == "checked"

        # value is (coefficient, row_power, count_power, lower, upper, ABI type)
        def evaluate(node: dict[str, Any], depth: int):
            nonlocal nodes, maximum_depth
            nodes += 1
            maximum_depth = max(maximum_depth, depth)
            result["budget"].update(nodes_used=nodes, maximum_depth_used=maximum_depth)
            if nodes > MAX_NODES:
                raise _Unknown("expression_node_budget_exceeded")
            if depth > MAX_DEPTH:
                raise _Unknown("expression_depth_budget_exceeded")
            kind = node.get("kind")
            if not isinstance(kind, str):
                raise _Unknown("expression_kind_missing")
            children = _children(node)
            if kind == "DeclRefExpr":
                if children or node.get("valueCategory") != "lvalue":
                    raise _Unknown("declaration_reference_malformed")
                reference = node.get("referencedDecl")
                declaration_id = reference.get("id") if isinstance(reference, dict) else None
                if (not isinstance(reference, dict) or
                        reference.get("kind") not in {"VarDecl", "ParmVarDecl"} or
                        declaration_id not in domains):
                    raise _Unknown("declaration_reference_not_row_or_count")
                lower, upper, powers = domains[declaration_id]
                ty = _abi_type(node.get("type"), integer_types)
                if not represented(lower, upper, ty):
                    raise _Unknown("declaration_interval_not_representable")
                return 1, powers[0], powers[1], lower, upper, ty
            if kind == "IntegerLiteral":
                if children or node.get("valueCategory") != "prvalue":
                    raise _Unknown("integer_literal_malformed")
                text = node.get("value")
                if not isinstance(text, str) or not text.isdecimal() or len(text) > 39:
                    raise _Unknown("nonnegative_integer_literal_required")
                value = int(text)
                ty = _abi_type(node.get("type"), integer_types)
                if not represented(value, value, ty):
                    raise _Unknown("integer_literal_not_representable")
                return value, 0, 0, value, value, ty
            if kind in {"ParenExpr", "ImplicitCastExpr", "CXXStaticCastExpr"}:
                if len(children) != 1 or node.get("valueCategory") != "prvalue":
                    raise _Unknown("expression_wrapper_malformed")
                value = evaluate(children[0], depth + 1)
                coefficient, row_power, count_power, lower, upper, source = value
                target = _abi_type(node.get("type"), integer_types)
                if kind == "ParenExpr":
                    if source != target:
                        raise _Unknown("parenthesis_type_discontinuity")
                    return coefficient, row_power, count_power, lower, upper, target
                cast_kind = node.get("castKind")
                allowed = ({"LValueToRValue", "IntegralCast", "NoOp"}
                           if kind == "ImplicitCastExpr" else {"IntegralCast", "NoOp"})
                if cast_kind not in allowed:
                    raise _Unknown("unsupported_integer_cast")
                if cast_kind in {"LValueToRValue", "NoOp"} and source[0] != target[0]:
                    raise _Unknown("nonconverting_cast_type_discontinuity")
                conversion = check_interval(lower, upper, source[1], source[2],
                                            target[1], target[2])
                evidence = {"cast_kind": cast_kind, "source_type": source[0],
                            "target_type": target[0], "range": node.get("range"),
                            "value_interval": {"lower": lower, "upper": upper},
                            "conversion": conversion}
                result["conversion_checks"].append(evidence)
                if conversion.get("status") == "rejected":
                    raise _Rejected("integer_cast_not_value_preserving", evidence)
                if conversion.get("status") != "checked":
                    raise _Unknown("integer_cast_check_unknown")
                return coefficient, row_power, count_power, lower, upper, target
            if kind == "BinaryOperator":
                if (node.get("opcode") != "*" or len(children) != 2 or
                        node.get("valueCategory") != "prvalue"):
                    raise _Unknown("unsupported_binary_expression")
                left = evaluate(children[0], depth + 1)
                right = evaluate(children[1], depth + 1)
                target = _abi_type(node.get("type"), integer_types)
                if left[5] != target or right[5] != target:
                    raise _Unknown("multiplication_operand_type_discontinuity")
                lower, upper = left[3] * right[3], left[4] * right[4]
                if not represented(lower, upper, target):
                    raise _Unknown("multiplication_may_overflow")
                return (left[0] * right[0], left[1] + right[1], left[2] + right[2],
                        lower, upper, target)
            raise _Unknown("unsupported_expression_node")

        value = evaluate(expression, 0)
        coefficient, row_power, count_power, lower, upper, ty = value
        result.update(symbolic_relation={"coefficient": coefficient,
                                         "row_power": row_power,
                                         "count_power": count_power},
                      value_interval={"lower": lower, "upper": upper}, result_type=ty[0])
        if (coefficient, row_power, count_power) != (1, 1, 1):
            raise _Rejected("expression_not_exact_row_times_count", result["symbolic_relation"])
        result["status"] = "checked"
    except _Rejected as error:
        result.update(status="rejected", reason=error.reason, counterexample=error.detail)
    except _Unknown as error:
        result["reason"] = error.reason
    return result
