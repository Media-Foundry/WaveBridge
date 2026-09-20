"""Conditionally evaluate a restricted dynamic-shared byte expression."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from wavebridge.verification.integer_conversion import check_interval
from wavebridge.verification.kernel_arguments import _abi_type, _raw_type, _Unknown


MAX_DEPTH = 32
MAX_NODES = 128


def _hash(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False).encode()).hexdigest()


def _children(node: object) -> list[dict[str, Any]]:
    if not isinstance(node, dict):
        raise _Unknown("expression_node_not_object")
    if "inner" not in node:
        return []
    raw = node["inner"]
    if not isinstance(raw, list) or any(not isinstance(child, dict) or not child
                                        for child in raw):
        raise _Unknown("expression_children_malformed")
    return raw


def _canonical_size_type(value: object) -> str:
    spelling = _raw_type(value)
    words = spelling.split()
    if "volatile" in words:
        raise _Unknown("sizeof_volatile_type_unsupported")
    while words and words[0] == "const":
        words.pop(0)
    if not words:
        raise _Unknown("sizeof_type_missing")
    return " ".join(words)


def _limits(bits: int, signed: bool) -> tuple[int, int]:
    if signed:
        return -(1 << (bits - 1)), (1 << (bits - 1)) - 1
    return 0, (1 << bits) - 1


def check(expression: object, integer_types: object, sizeof_bytes: object) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema_version": "shared-byte-expression-check/v1", "status": "unknown",
        "reason": None, "value_bytes": None, "expression_range": None,
        "checked": False, "source_program_checked": False, "deployable": False,
        "scope": "restricted_nonnegative_integer_byte_expression_under_explicit_abi",
        "conversion_checks": [], "sizeof_evidence": [],
        "budget": {"max_depth": MAX_DEPTH, "max_nodes": MAX_NODES,
                   "nodes_used": 0, "maximum_depth_used": 0},
        "assumptions": ["integer type widths and signedness match the compilation target",
                        "sizeof entries match the compilation target ABI",
                        "the supplied AST is the expression executed at the launch site"],
    }
    if not isinstance(expression, dict) or not isinstance(integer_types, dict) or not isinstance(sizeof_bytes, dict):
        result["reason"] = "inputs_not_expected_objects"
        return result
    try:
        result["input_sha256"] = {"expression": _hash(expression),
                                  "integer_types": _hash(integer_types),
                                  "sizeof_bytes": _hash(sizeof_bytes)}
    except (RecursionError, TypeError, ValueError):
        result["reason"] = "input_hash_unsupported"
        return result
    result["expression_range"] = expression.get("range")
    try:
        for name, specification in integer_types.items():
            if (not isinstance(name, str) or not name or not isinstance(specification, dict) or
                    type(specification.get("bits")) is not int or
                    not 2 <= specification["bits"] <= 128 or
                    type(specification.get("signed")) is not bool):
                raise _Unknown("invalid_integer_type_table")
        sizes: dict[str, int] = {}
        for name, size in sizeof_bytes.items():
            if not isinstance(name, str) or not name or type(size) is not int or size <= 0:
                raise _Unknown("invalid_sizeof_table")
            sizes[name] = size

        nodes = 0
        maximum_depth = 0

        def evaluate(node: object, depth: int) -> tuple[int, str, int, bool]:
            nonlocal nodes, maximum_depth
            if not isinstance(node, dict):
                raise _Unknown("expression_node_not_object")
            nodes += 1
            maximum_depth = max(maximum_depth, depth)
            if nodes > MAX_NODES:
                raise _Unknown("expression_node_budget_exceeded")
            if depth > MAX_DEPTH:
                raise _Unknown("expression_depth_budget_exceeded")
            kind = node.get("kind")
            if not isinstance(kind, str):
                raise _Unknown("expression_kind_missing")

            if kind == "IntegerLiteral":
                if _children(node):
                    raise _Unknown("integer_literal_has_children")
                try:
                    value = int(str(node["value"]), 0)
                except (KeyError, TypeError, ValueError):
                    raise _Unknown("integer_literal_invalid")
                if value < 0:
                    raise _Unknown("negative_integer_literal_unsupported")
                name, bits, signed = _abi_type(node.get("type"), integer_types)
            elif kind == "UnaryExprOrTypeTraitExpr":
                if node.get("name") != "sizeof" or _children(node):
                    raise _Unknown("unsupported_unary_or_dynamic_sizeof")
                argument_type = node.get("argType")
                size_name = _canonical_size_type(argument_type)
                value = sizes.get(size_name)
                if value is None:
                    raise _Unknown("sizeof_type_missing_from_table")
                name, bits, signed = _abi_type(node.get("type"), integer_types)
                result["sizeof_evidence"].append({"type": size_name, "bytes": value,
                                                  "range": node.get("range")})
            elif kind == "ParenExpr":
                children = _children(node)
                if len(children) != 1:
                    raise _Unknown("paren_expression_ambiguous")
                value, child_name, _, _ = evaluate(children[0], depth + 1)
                name, bits, signed = _abi_type(node.get("type"), integer_types)
                if name != child_name:
                    raise _Unknown("paren_expression_changes_type")
            elif kind == "ImplicitCastExpr":
                children = _children(node)
                cast_kind = node.get("castKind")
                if len(children) != 1 or cast_kind not in ("IntegralCast", "NoOp"):
                    raise _Unknown("unsupported_integer_cast")
                value, source_name, source_bits, source_signed = evaluate(children[0], depth + 1)
                name, bits, signed = _abi_type(node.get("type"), integer_types)
                if cast_kind == "NoOp" and source_name != name:
                    raise _Unknown("noop_cast_changes_type")
                conversion = check_interval(value, value, source_bits, source_signed, bits, signed)
                evidence = {"cast_kind": cast_kind, "source_type": source_name,
                            "destination_type": name, "value": value,
                            "range": node.get("range"), "conversion": conversion}
                result["conversion_checks"].append(evidence)
                if conversion.get("status") != "checked":
                    raise _Unknown("integer_cast_not_value_preserving")
            elif kind == "BinaryOperator":
                children = _children(node)
                if node.get("opcode") != "*" or len(children) != 2:
                    raise _Unknown("unsupported_binary_expression")
                left, left_name, _, _ = evaluate(children[0], depth + 1)
                right, right_name, _, _ = evaluate(children[1], depth + 1)
                name, bits, signed = _abi_type(node.get("type"), integer_types)
                if left_name != name or right_name != name:
                    raise _Unknown("multiplication_operand_type_mismatch")
                value = left * right
            else:
                raise _Unknown("unsupported_expression_kind")

            lower, upper = _limits(bits, signed)
            if value < 0:
                raise _Unknown("negative_byte_expression_unsupported")
            if value < lower or value > upper:
                raise _Unknown("integer_expression_overflow")
            return value, name, bits, signed

        value, _, _, _ = evaluate(expression, 1)
        result.update(status="checked", checked=True, value_bytes=value)
    except _Unknown as error:
        result["reason"] = error.reason
    finally:
        if "nodes" in locals():
            result["budget"]["nodes_used"] = nodes
            result["budget"]["maximum_depth_used"] = maximum_depth
    return result
