"""Conditionally check prefix getter bodies, never external-call termination."""

from wavebridge.analysis.reduction_chain import recover as recover_chain
from wavebridge.verification.getter_returns import check as check_getter, _hash


def check(root, kernel_id, int_bits, integer_types, protocol):
    result = {
        "schema_version": "conditional-entry-call-check/v1", "status": "unknown", "reason": None,
        "checks": [], "source_program_checked": False, "deployable": False,
        "participation": "not_established",
        "scope": "prefix_getter_body_completion_under_external_normal_return_and_domain_assumptions",
        "premises": ["source AST and recovery are faithful; calls are valid",
                     "each explicitly bound external leaf returns normally in its declared domain",
                     "explicit integer ABI matches the target"],
        "limitations": ["does not prove external leaf termination or its supplied value domain",
                        "does not prove call-site receiver/argument evaluation, loop completion or helper reachability"],
    }

    def unknown(reason):
        result["reason"] = reason
        return result

    if (not isinstance(root, dict) or not isinstance(integer_types, dict) or not isinstance(protocol, dict) or
            not isinstance(kernel_id, str) or not kernel_id or type(int_bits) is not int):
        return unknown("invalid_inputs")
    try:
        result["input_sha256"] = {"root": _hash(root), "kernel_id": _hash(kernel_id),
                                  "int_bits": _hash(int_bits), "integer_types": _hash(integer_types),
                                  "protocol": _hash(protocol)}
    except (TypeError, ValueError, RecursionError):
        return unknown("input_hash_unsupported")
    if (protocol.get("schema_version") != "getter-completion-assumptions/v1" or
            protocol.get("ast_root_sha256") != result["input_sha256"]["root"] or
            protocol.get("kernel_declaration_id") != kernel_id or
            protocol.get("external_normal_return_assumed") is not True or
            not isinstance(protocol.get("getters"), dict)):
        return unknown("external_protocol_not_bound_or_enabled")
    chain = recover_chain(root, kernel_id, int_bits)
    result["chain_recovery"] = chain
    entry = chain.get("entry_control")
    if (chain.get("status") != "recovered" or chain.get("function_id") != kernel_id or
            not isinstance(entry, dict) or entry.get("status") != "recovered" or
            entry.get("function_id") != kernel_id):
        return unknown("entry_control_not_recovered")
    obligations = entry.get("call_obligations")
    if not isinstance(obligations, list) or not obligations:
        return unknown("no_prefix_call_obligations")
    incomplete = False
    for obligation in obligations:
        identifier = obligation.get("declaration_id") if isinstance(obligation, dict) else None
        if not isinstance(identifier, str) or not identifier:
            return unknown("prefix_call_declaration_missing")
        evidence = {"obligation": obligation, "status": "unknown"}
        result["checks"].append(evidence)
        contract = protocol["getters"].get(identifier)
        if not isinstance(contract, dict):
            evidence["reason"] = "external_getter_contract_missing"
            incomplete = True
            continue
        getter = check_getter(root, identifier, contract, integer_types)
        evidence["getter"] = getter
        completion = getter.get("completion")
        if (getter.get("status") != "checked" or not isinstance(completion, dict) or
                completion.get("status") != "conditional"):
            # Failed value preservation is not evidence of nontermination.
            evidence["reason"] = "getter_completion_not_established"
            incomplete = True
            continue
        evidence.update(status="checked", conclusion="body_returns_under_bound_external_assumptions")
    if incomplete:
        return unknown("one_or_more_prefix_calls_unestablished")
    result.update(status="checked", conclusion="prefix_getter_bodies_return_under_stated_external_assumptions")
    return result
