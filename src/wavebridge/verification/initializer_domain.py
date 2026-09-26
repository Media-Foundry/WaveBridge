"""Compose trusted initializer and getter evidence under one explicit integer ABI.

This checker does not parse source AST or reinterpret a pseudo-object receiver.  It
only checks report bindings and value preservation through the recorded outer
initializer conversions.
"""

from __future__ import annotations

from typing import Any

from wavebridge.verification.getter_returns import _hash
from wavebridge.verification.integer_conversion import check_interval
from wavebridge.verification.kernel_arguments import _abi_type, _Unknown


MAX_CASTS = 32


def check_source(root, declaration_id, leaf_contract, integer_types, *, max_ast_nodes=None):
    """Freshly bind a local scalar initializer; no post-initialization history claim."""
    from wavebridge.analysis.initializer_value import link
    from wavebridge.verification.getter_returns import check as check_getter
    from wavebridge.verification.scalar_expression_effects import _type

    budget = 1_000_000 if max_ast_nodes is None else max_ast_nodes
    result = {"schema_version": "source-initializer-domain-check/v1", "status": "unknown", "reason": None,
              "scope": "selected_local_scalar_value_at_initialization_only",
              "source_program_checked": False, "deployable": False, "value_preserved_to_use": False,
              "coordinate_semantics": "not_established", "receiver_purity": "not_established",
              "checks": {}, "budget": {"max_ast_nodes": budget},
              "assumptions": ["AST faithfully represents a valid translation unit and initialization is reached",
                              "external leaf domain and integer ABI are valid; initialization completes normally"],
              "limitations": ["no value history, reaching definition, loop-entry or launch-domain guarantee",
                              "no thread-coordinate semantics or complete initializer effect guarantee"]}
    try:
        if (not isinstance(root, dict) or root.get("kind") != "TranslationUnitDecl" or
                not isinstance(declaration_id, str) or not declaration_id or
                type(budget) is not int or not 1 <= budget <= 10_000_000):
            raise _Unknown("invalid_inputs_or_budget")
        index, selected, pending, count = {}, [], [(root, ())], 0
        while pending:
            node, parents = pending.pop()
            count += 1
            if count > budget:
                raise _Unknown("ast_node_budget_exceeded")
            if not isinstance(node, dict) or not isinstance(node.get("inner", []), list):
                raise _Unknown("malformed_ast")
            if isinstance(node.get("id"), str):
                index.setdefault(node["id"], []).append(node)
            if node.get("id") == declaration_id:
                selected.append((node, parents))
            pending.extend((child, (parents + (node.get("kind"),))[-2:]) for child in node.get("inner", []))
        if len(selected) != 1:
            raise _Unknown("initializer_declaration_not_unique")
        declaration, parents = selected[0]
        if (declaration.get("kind") != "VarDecl" or parents != ("CompoundStmt", "DeclStmt") or
                _type(declaration) not in {"int", "const int"} or
                declaration.get("storageClass") not in (None, "auto", "register") or
                any(declaration.get(key) is not None for key in ("tls", "tlsKind", "thread_local", "threadLocal")) or
                declaration.get("init") is None or len(declaration.get("inner", [])) != 1):
            raise _Unknown("unsupported_local_scalar_declaration")
        initializer = declaration["inner"][0]
        if len(index.get(initializer.get("id"), [])) != 1:
            raise _Unknown("initializer_expression_not_unique")
        result.update(declaration_id=declaration_id, initializer_id=initializer.get("id"),
                      declaration_range=declaration.get("range"), initializer_ast=initializer)
        origin = link(root, initializer)
        result["checks"]["value_link"] = origin
        if origin["status"] != "recovered":
            raise _Unknown("initializer_value_link_not_recovered")
        getter = check_getter(root, origin["callee_declaration_id"], leaf_contract, integer_types,
                              max_ast_nodes=budget)
        result["checks"]["getter"] = getter
        if getter["status"] != "checked":
            result.update(status=getter["status"], reason="initializer_getter_not_checked")
            return result
        domain = check(origin, getter, integer_types)
        result["checks"]["conversion"] = domain
        if domain["status"] != "checked":
            result.update(status=domain["status"], reason="initializer_conversion_not_checked")
            return result
        if domain["result_type"] != "int":
            raise _Unknown("initializer_result_declaration_type_mismatch")
        result.update(status="checked", result_type="int", result_interval=domain["result_interval"],
                      input_sha256={"root": _hash(root), "declaration_id": _hash(declaration_id),
                                    "leaf_contract": _hash(leaf_contract), "integer_types": _hash(integer_types)})
        result["assumptions"].extend(origin["assumptions"] + getter["assumptions"])
    except _Unknown as error:
        result["reason"] = str(error)
    except (TypeError, ValueError, KeyError, IndexError, RecursionError):
        result["reason"] = "unsupported_input_representation"
    return result


def check(value_link: object, getter_report: object,
          integer_types: object) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema_version": "initializer-domain-check/v1",
        "status": "unknown",
        "reason": None,
        "result_type": None,
        "result_interval": None,
        "conversion_checks": [],
        "source_program_checked": False,
        "deployable": False,
        "receiver_purity": "not_established",
        "coordinate_semantics": "not_established",
        "scope": "trusted_initializer_value_link_and_getter_domain_composition",
        "assumptions": [
            "value_link is trusted frontend initializer-value-link/v1 evidence from the source AST",
            "getter_report is genuine getter-return-domain-check/v1 checker evidence for the same source",
            "the explicit integer ABI matches both evidence reports and the compilation target",
            "receiver purity and coordinate meaning are not established by this composition",
        ],
        "budget": {"max_casts": MAX_CASTS, "casts_used": 0},
    }
    if (not isinstance(value_link, dict) or not isinstance(getter_report, dict) or
            not isinstance(integer_types, dict)):
        result["reason"] = "inputs_not_expected_objects"
        return result
    try:
        result["input_sha256"] = {
            "value_link": _hash(value_link),
            "getter_report": _hash(getter_report),
            "integer_types": _hash(integer_types),
        }
    except (TypeError, ValueError, RecursionError):
        result["reason"] = "input_hash_unsupported"
        return result

    try:
        if (value_link.get("schema_version") != "initializer-value-link/v1" or
                value_link.get("status") != "recovered"):
            raise _Unknown("initializer_value_link_not_recovered")
        if (getter_report.get("schema_version") != "getter-return-domain-check/v1" or
                getter_report.get("status") != "checked"):
            raise _Unknown("getter_domain_not_checked")
        call_id = value_link.get("call_id")
        callee_id = value_link.get("callee_declaration_id")
        if not isinstance(call_id, str) or not call_id or not isinstance(callee_id, str) or not callee_id:
            raise _Unknown("initializer_call_binding_missing")
        if getter_report.get("start_declaration_id") != callee_id:
            raise _Unknown("getter_start_does_not_match_initializer_callee")

        getter_hashes = getter_report.get("input_sha256")
        if (not isinstance(getter_hashes, dict) or
                getter_hashes.get("integer_types") != _hash(integer_types)):
            raise _Unknown("getter_integer_abi_not_bound")

        interval = getter_report.get("return_interval")
        if not isinstance(interval, dict):
            raise _Unknown("getter_return_interval_missing")
        lower, upper = interval.get("lower"), interval.get("upper")
        if type(lower) is not int or type(upper) is not int or lower > upper:
            raise _Unknown("getter_return_interval_invalid")
        getter_type = getter_report.get("return_type")
        current_name, current_bits, current_signed = _abi_type(
            {"qualType": getter_type}, integer_types)
        initial = check_interval(lower, upper, current_bits, current_signed,
                                 current_bits, current_signed)
        if initial.get("status") != "checked":
            raise _Unknown("getter_interval_not_representable")
        call_name, _, _ = _abi_type({"qualType": value_link.get("call_type")}, integer_types)
        if call_name != current_name:
            raise _Unknown("initializer_call_type_mismatch")

        conversions = value_link.get("conversions_outer_to_inner")
        if not isinstance(conversions, list):
            raise _Unknown("initializer_conversion_chain_missing")
        result["budget"]["casts_used"] = len(conversions)
        if len(conversions) > MAX_CASTS:
            raise _Unknown("initializer_conversion_budget_exceeded")
        for conversion in reversed(conversions):
            if not isinstance(conversion, dict) or conversion.get("cast_kind") != "IntegralCast":
                raise _Unknown("unsupported_initializer_conversion")
            source_name, source_bits, source_signed = _abi_type(
                {"qualType": conversion.get("source_type")}, integer_types)
            target_name, target_bits, target_signed = _abi_type(
                {"qualType": conversion.get("target_type")}, integer_types)
            if source_name != current_name:
                raise _Unknown("initializer_conversion_chain_discontinuous")
            interval_check = check_interval(lower, upper, source_bits, source_signed,
                                            target_bits, target_signed)
            evidence = {
                "cast_kind": "IntegralCast",
                "source_type": source_name,
                "target_type": target_name,
                "range": conversion.get("range"),
                "conversion": interval_check,
            }
            result["conversion_checks"].append(evidence)
            if interval_check.get("status") == "rejected":
                result.update(status="rejected", reason="initializer_conversion_not_value_preserving",
                              result_type=target_name)
                return result
            if interval_check.get("status") != "checked":
                raise _Unknown("initializer_conversion_check_unknown")
            current_name, current_bits, current_signed = target_name, target_bits, target_signed

        result.update(status="checked", result_type=current_name,
                      result_interval={"lower": lower, "upper": upper})
    except _Unknown as error:
        result["reason"] = error.reason
    return result
