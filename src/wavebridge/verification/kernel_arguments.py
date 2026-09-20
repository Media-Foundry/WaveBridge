"""Conditionally verify one positional kernel integer argument binding."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from wavebridge.verification.integer_conversion import check_interval

MAX_INTERVALS = 64
MAX_CASTS = 64
CAST_KINDS = ("LValueToRValue", "NoOp", "IntegralCast")


class _Unknown(Exception):
    def __init__(self, reason: str):
        self.reason = reason


class _Rejected(Exception):
    def __init__(self, reason: str, detail: object = None):
        self.reason, self.detail = reason, detail


def _hash(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False).encode()).hexdigest()


def _raw_type(value: object) -> str:
    if not isinstance(value, dict):
        raise _Unknown("type_evidence_missing")
    spelling = value.get("desugaredQualType") or value.get("qualType")
    if not isinstance(spelling, str) or not spelling:
        raise _Unknown("type_evidence_missing")
    return spelling


def _base_type(value: object) -> str:
    spelling = _raw_type(value)
    words = spelling.split()
    if "volatile" in words or "*" in spelling or "&" in spelling:
        raise _Unknown("non_scalar_integer_type_unsupported")
    while words and words[0] == "const":
        words.pop(0)
    if not words:
        raise _Unknown("empty_integer_type")
    return " ".join(words)


def _abi_type(value: object, abi: dict[str, Any]) -> tuple[str, int, bool]:
    name = _base_type(value)
    specification = abi.get(name)
    if not isinstance(specification, dict):
        raise _Unknown("integer_type_missing_from_abi")
    bits, signed = specification.get("bits"), specification.get("signed")
    if type(bits) is not int or not 2 <= bits <= 128 or type(signed) is not bool:
        raise _Unknown("invalid_abi_type_entry")
    return name, bits, signed


def _children(node: object) -> list[dict[str, Any]]:
    if not isinstance(node, dict) or not isinstance(node.get("inner"), list):
        return []
    return [child for child in node["inner"] if isinstance(child, dict) and child]


def _argument(node: object) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if not isinstance(node, dict):
        raise _Unknown("argument_ast_missing")
    current = node
    casts: list[dict[str, Any]] = []
    while current.get("kind") in ("ParenExpr", "ImplicitCastExpr"):
        children = _children(current)
        if len(children) != 1:
            raise _Unknown("argument_wrapper_ambiguous")
        child = children[0]
        if current.get("kind") == "ImplicitCastExpr":
            cast_kind = current.get("castKind")
            if not isinstance(cast_kind, str) or cast_kind not in CAST_KINDS:
                raise _Unknown("unsupported_argument_cast")
            casts.append({"cast_kind": cast_kind, "source_type": child.get("type"),
                          "destination_type": current.get("type"),
                          "range": current.get("range")})
        current = child
    return current, casts


def _apply(lower: int, upper: int, initial_type: object, casts: list[dict[str, Any]],
           parameter_type: object, abi: dict[str, Any]) -> list[dict[str, Any]]:
    current_name, current_bits, current_signed = _abi_type(initial_type, abi)
    checks: list[dict[str, Any]] = []
    initial = check_interval(lower, upper, current_bits, current_signed,
                             current_bits, current_signed)
    checks.append({"stage": "initial_type", "source_type": current_name,
                   "target_type": current_name, "conversion": initial})
    if (initial.get("status") == "rejected" or
            initial.get("reason") == "interval_not_representable_in_source_type"):
        raise _Rejected("argument_domain_not_representable_in_initial_type", checks[-1])
    if initial.get("status") != "checked":
        raise _Unknown("initial_type_domain_check_unknown")
    for cast in reversed(casts):
        source_name, source_bits, source_signed = _abi_type(cast.get("source_type"), abi)
        target_name, target_bits, target_signed = _abi_type(cast.get("destination_type"), abi)
        if source_name != current_name:
            raise _Rejected("cast_type_chain_discontinuity")
        if cast["cast_kind"] in ("LValueToRValue", "NoOp") and source_name != target_name:
            raise _Rejected("nonconverting_cast_changes_base_type")
        conversion = check_interval(lower, upper, source_bits, source_signed,
                                    target_bits, target_signed)
        evidence = {**cast, "source_type": source_name, "destination_type": target_name,
                    "conversion": conversion}
        checks.append(evidence)
        if conversion.get("status") == "rejected":
            raise _Rejected("integer_conversion_not_value_preserving", evidence)
        if conversion.get("status") != "checked":
            raise _Unknown("integer_conversion_check_unknown")
        current_name, current_bits, current_signed = target_name, target_bits, target_signed
    expected_name, _, _ = _abi_type(parameter_type, abi)
    if current_name != expected_name:
        raise _Rejected("parameter_type_chain_mismatch")
    return checks


def check(binding: object, declaration_intervals: object, abi: object) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema_version": "kernel-argument-domain-check/v1", "status": "unknown",
        "reason": None, "parameter_declaration_id": None, "position": None,
        "declaration_id": None, "value_kind": None, "casts": [], "conversion_checks": [],
        "scope": "one_positional_scalar_integer_kernel_argument_under_explicit_domain_and_abi",
        "binding_scope": "supplied_position_binding_only_not_complete_kernel_signature",
        "source_program_checked": False, "deployable": False,
        "budget": {"max_intervals": MAX_INTERVALS, "max_casts": MAX_CASTS,
                   "intervals_used": 0, "casts_used": 0},
        "assumptions": ["the supplied binding was obtained from a trusted positional binding step",
                        "each referenced declaration runtime value lies within its supplied interval",
                        "the interval source and the explicit ABI match this compilation target"],
    }
    if not isinstance(binding, dict) or not isinstance(declaration_intervals, list) or not isinstance(abi, dict):
        result["reason"] = "inputs_not_expected_objects"
        return result
    result["input_sha256"] = {"binding": _hash(binding),
                              "declaration_intervals": _hash(declaration_intervals),
                              "abi": _hash(abi)}
    try:
        parameter_id, position = binding.get("parameter_declaration_id"), binding.get("position")
        if not isinstance(parameter_id, str) or not parameter_id:
            raise _Unknown("parameter_declaration_id_missing")
        if type(position) is not int or position < 0:
            raise _Unknown("parameter_position_invalid")
        result.update(parameter_declaration_id=parameter_id, position=position)
        if len(declaration_intervals) > MAX_INTERVALS:
            raise _Unknown("declaration_interval_budget_exceeded")
        intervals: dict[str, dict[str, Any]] = {}
        for interval in declaration_intervals:
            if not isinstance(interval, dict):
                raise _Unknown("declaration_interval_not_object")
            declaration_id = interval.get("declaration_id")
            lower, upper = interval.get("lower"), interval.get("upper")
            if not isinstance(declaration_id, str) or not declaration_id:
                raise _Unknown("declaration_interval_id_missing")
            if declaration_id in intervals:
                raise _Rejected("declaration_interval_ids_not_unique")
            if type(lower) is not int or type(upper) is not int or lower > upper:
                raise _Unknown("declaration_interval_bounds_invalid")
            _raw_type(interval.get("type"))
            intervals[declaration_id] = interval
        result["budget"]["intervals_used"] = len(intervals)
        leaf, casts = _argument(binding.get("argument_ast"))
        result["casts"] = casts
        result["budget"]["casts_used"] = len(casts)
        if len(casts) > MAX_CASTS:
            raise _Unknown("argument_cast_budget_exceeded")
        if leaf.get("kind") == "IntegerLiteral":
            try:
                value = int(str(leaf["value"]), 0)
            except (KeyError, TypeError, ValueError):
                raise _Unknown("integer_literal_invalid")
            lower = upper = value
            result.update(value_kind="constant", value=value)
        elif leaf.get("kind") == "DeclRefExpr":
            referenced = leaf.get("referencedDecl")
            if (not isinstance(referenced, dict) or
                    referenced.get("kind") not in ("VarDecl", "ParmVarDecl") or
                    not isinstance(referenced.get("id"), str) or not referenced["id"]):
                raise _Unknown("argument_declref_unresolved")
            declaration_id = referenced["id"]
            interval = intervals.get(declaration_id)
            if interval is None:
                raise _Unknown("argument_declaration_interval_missing")
            if _raw_type(interval.get("type")) != _raw_type(leaf.get("type")):
                raise _Rejected("declaration_interval_leaf_type_mismatch")
            lower, upper = interval["lower"], interval["upper"]
            result.update(declaration_id=declaration_id, value_kind="interval",
                          interval={"lower": lower, "upper": upper})
        else:
            raise _Unknown("argument_leaf_not_supported_scalar_integer")
        checks = _apply(lower, upper, leaf.get("type"), casts,
                        binding.get("parameter_type"), abi)
        result.update(status="checked", conversion_checks=checks)
    except _Rejected as error:
        result.update(status="rejected", reason=error.reason)
        if error.detail is not None:
            result["diagnostic"] = error.detail
    except _Unknown as error:
        result["reason"] = error.reason
    return result
