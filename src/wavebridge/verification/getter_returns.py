"""Independently check integer getter bodies under an explicit external leaf domain.

No function names carry semantics. The result is conditional value preservation,
not proof that the external leaf denotes a thread coordinate or that a launch
supplies the stated interval.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from wavebridge.verification.integer_conversion import check_interval
from wavebridge.verification.kernel_arguments import _abi_type, _Unknown

MAX_AST_NODES = 1_000_000
HARD_MAX_AST_NODES = 10_000_000
MAX_CALL_DEPTH = 32
MAX_EXPRESSION_DEPTH = 32


class _Rejected(Exception):
    pass


def _hash(value):
    digest = hashlib.sha256()
    for chunk in json.JSONEncoder(sort_keys=True, separators=(",", ":"),
                                  allow_nan=False).iterencode(value):
        digest.update(chunk.encode())
    return digest.hexdigest()


def _children(node):
    children = node.get("inner", [])
    if not isinstance(children, list) or any(not isinstance(c, dict) or not c for c in children):
        raise _Unknown("malformed_expression_children")
    return children


def check(root: object, start_declaration_id: object, leaf_contract: object,
          integer_types: object, *, max_ast_nodes: int | None = None) -> dict[str, Any]:
    node_budget = MAX_AST_NODES if max_ast_nodes is None else max_ast_nodes
    result: dict[str, Any] = {
        "schema_version": "getter-return-domain-check/v1", "status": "unknown", "reason": None,
        "start_declaration_id": start_declaration_id, "conversion_checks": [],
        "call_edges": [], "leaf_arguments": [], "return_interval": None,
        "scope": "integer_getter_return_value_preservation_under_explicit_leaf_domain_and_abi",
        "source_program_checked": False, "deployable": False,
        "coordinate_semantics": "not_established",
        "assumptions": ["AST is a faithful well-formed single translation unit",
                        "explicit ABI matches the compilation target",
                        "the exact external leaf with the stated arguments returns in the supplied interval",
                        "source calls are valid and the external leaf returns normally"],
        "budget": {"max_ast_nodes": node_budget, "max_call_depth": MAX_CALL_DEPTH,
                   "max_expression_depth": MAX_EXPRESSION_DEPTH},
    }
    if type(node_budget) is not int or not 1 <= node_budget <= HARD_MAX_AST_NODES:
        result["reason"] = "invalid_ast_node_budget"
        return result
    if (not isinstance(root, dict) or not isinstance(leaf_contract, dict) or
            not isinstance(integer_types, dict) or not isinstance(start_declaration_id, str) or
            not start_declaration_id):
        result["reason"] = "invalid_inputs"
        return result
    try:
        result["input_sha256"] = {
            "root": _hash(root), "start_declaration_id": _hash(start_declaration_id),
            "leaf_contract": _hash(leaf_contract), "integer_types": _hash(integer_types)}
    except (TypeError, ValueError, RecursionError):
        result["reason"] = "input_hash_unsupported"
        return result
    try:
        leaf_id = leaf_contract.get("declaration_id")
        expected_args = leaf_contract.get("arguments")
        lower, upper = leaf_contract.get("lower"), leaf_contract.get("upper")
        if (leaf_contract.get("schema_version") != "getter-leaf-domain/v1" or
                not isinstance(leaf_id, str) or not leaf_id or
                not isinstance(expected_args, list) or len(expected_args) > 4 or
                any(type(v) is not int or not 0 <= v < (1 << 128) for v in expected_args) or
                type(lower) is not int or type(upper) is not int or lower > upper):
            raise _Unknown("invalid_leaf_contract")
        leaf_type = _abi_type(leaf_contract.get("return_type"), integer_types)
        initial = check_interval(lower, upper, leaf_type[1], leaf_type[2], leaf_type[1], leaf_type[2])
        if initial["status"] != "checked":
            raise _Unknown("leaf_domain_not_representable")

        declarations: dict[str, list[dict[str, Any]]] = {}
        pending = [root]
        nodes = 0
        while pending:
            node = pending.pop()
            nodes += 1
            if nodes > node_budget:
                raise _Unknown("ast_node_budget_exceeded")
            if not isinstance(node, dict):
                raise _Unknown("ast_node_not_object")
            if node.get("kind") in {"FunctionDecl", "CXXMethodDecl"}:
                key = node.get("id")
                if isinstance(key, str) and key:
                    declarations.setdefault(key, []).append(node)
            # Clang contains empty placeholders outside the expression being checked.
            children = node.get("inner", [])
            if not isinstance(children, list):
                raise _Unknown("ast_children_not_list")
            pending.extend(children)

        def unique(declaration_id):
            matches = declarations.get(declaration_id, [])
            if len(matches) != 1:
                raise _Unknown("function_declaration_not_unique")
            return matches[0]

        def scalar_type(node):
            return _abi_type(node.get("type"), integer_types)

        def wrappers(node, depth, evaluate, domain_lower, domain_upper, argument=False):
            if depth > MAX_EXPRESSION_DEPTH:
                raise _Unknown("expression_depth_budget_exceeded")
            kind = node.get("kind")
            if kind not in {"ParenExpr", "ImplicitCastExpr"}:
                return None
            children = _children(node)
            if len(children) != 1 or node.get("valueCategory") != "prvalue":
                raise _Unknown("unsupported_expression_wrapper")
            if kind == "ImplicitCastExpr" and node.get("castKind") != "IntegralCast":
                raise _Unknown("unsupported_integer_cast")
            child_type = evaluate(children[0], depth + 1)
            target_type = scalar_type(node)
            if kind == "ParenExpr":
                if target_type != child_type:
                    raise _Unknown("parenthesis_changes_type")
                return target_type
            conversion = check_interval(domain_lower, domain_upper, child_type[1], child_type[2],
                                        target_type[1], target_type[2])
            result["conversion_checks"].append({
                "scope": "leaf_argument" if argument else "getter_return",
                "source_type": child_type[0], "target_type": target_type[0],
                "range": node.get("range"), "conversion": conversion})
            if conversion["status"] == "rejected" and not argument:
                raise _Rejected("return_conversion_not_value_preserving")
            if conversion["status"] != "checked":
                raise _Unknown("integer_conversion_not_value_preserving")
            return target_type

        def argument(node):
            # Establish the literal first; evaluate each surrounding conversion on
            # that singleton. Arithmetic, default arguments and calls stay unknown.
            current = node
            depth = 0
            while current.get("kind") in {"ParenExpr", "ImplicitCastExpr"}:
                depth += 1
                if depth > MAX_EXPRESSION_DEPTH or len(_children(current)) != 1:
                    raise _Unknown("argument_wrapper_budget_or_shape")
                current = _children(current)[0]
            value_text = current.get("value")
            if (current.get("kind") != "IntegerLiteral" or _children(current) or
                    not isinstance(value_text, str) or not value_text.isdecimal() or len(value_text) > 39):
                raise _Unknown("leaf_argument_not_nonnegative_literal")
            value = int(value_text)

            def evaluate(expr, level):
                found = wrappers(expr, level, evaluate, value, value, argument=True)
                if found is not None:
                    return found
                if expr is not current or expr.get("valueCategory") != "prvalue":
                    raise _Unknown("unsupported_leaf_argument")
                ty = scalar_type(expr)
                if check_interval(value, value, ty[1], ty[2], ty[1], ty[2])["status"] != "checked":
                    raise _Unknown("literal_not_representable")
                return ty

            return value, evaluate(node, 0)

        active = set()

        def follow(declaration_id, call_depth):
            if call_depth >= MAX_CALL_DEPTH or declaration_id in active:
                raise _Unknown("getter_cycle_or_depth_budget")
            function = unique(declaration_id)
            if function.get("kind") == "CXXMethodDecl" and function.get("storageClass") != "static":
                raise _Unknown("nonstatic_getter_unsupported")
            children = _children(function)
            if function.get("variadic") or any(c.get("kind") == "ParmVarDecl" for c in children):
                raise _Unknown("getter_parameters_unsupported")
            bodies = [c for c in children if c.get("kind") == "CompoundStmt"]
            if (len(bodies) != 1 or any(c.get("kind") in {"CXXTryStmt", "CoroutineBodyStmt"} for c in children) or
                    len(_children(bodies[0])) != 1):
                raise _Unknown("getter_not_single_return_body")
            statement = _children(bodies[0])[0]
            if statement.get("kind") != "ReturnStmt" or len(_children(statement)) != 1:
                raise _Unknown("getter_not_single_return_body")

            def evaluate(expr, level):
                found = wrappers(expr, level, evaluate, lower, upper)
                if found is not None:
                    return found
                if expr.get("kind") != "CallExpr" or expr.get("valueCategory") != "prvalue":
                    raise _Unknown("return_not_direct_integer_call")
                parts = _children(expr)
                if not parts:
                    raise _Unknown("callee_missing")
                callee = parts[0]
                callee_cast_kind = None
                if callee.get("kind") == "ImplicitCastExpr":
                    callee_cast_kind = callee.get("castKind")
                    if (callee_cast_kind not in {"FunctionToPointerDecay", "BuiltinFnToFnPtr"} or
                            len(_children(callee)) != 1):
                        raise _Unknown("unsupported_callee_cast")
                    callee = _children(callee)[0]
                ref = callee.get("referencedDecl")
                if (callee.get("kind") != "DeclRefExpr" or _children(callee) or
                        not isinstance(ref, dict) or ref.get("kind") != "FunctionDecl" or
                        not isinstance(ref.get("id"), str) or not ref["id"]):
                    raise _Unknown("callee_not_exact_free_function")
                target_id = ref["id"]
                target = unique(target_id)
                if target.get("kind") != "FunctionDecl":
                    raise _Unknown("callee_declaration_kind_mismatch")
                if callee_cast_kind == "BuiltinFnToFnPtr":
                    # Clang uses this representation only for a builtin at the
                    # direct call site. Keep this deliberately narrower than
                    # ordinary function decay: the real coordinate leaves are
                    # zero-argument functions with one of these exact forms.
                    target_type = target.get("type")
                    referenced_type = ref.get("type")
                    signature = target_type.get("qualType") if isinstance(target_type, dict) else None
                    if signature == f"{leaf_type[0]} ()":
                        pointer_signature = f"{leaf_type[0]} (*)()"
                    elif signature == f"{leaf_type[0]} () noexcept":
                        pointer_signature = f"{leaf_type[0]} (*)() noexcept"
                    else:
                        raise _Unknown("builtin_leaf_signature_unsupported")
                    if (target_id != leaf_id or expected_args != [] or parts[1:] or
                            parts[0].get("valueCategory") != "prvalue" or
                            callee.get("type") != {"qualType": "<builtin fn type>"} or
                            callee.get("valueCategory") != "prvalue" or
                            referenced_type != target_type or
                            parts[0].get("type") != {"qualType": pointer_signature} or
                            not any(child.get("kind") == "BuiltinAttr"
                                    for child in _children(target))):
                        raise _Unknown("builtin_leaf_evidence_mismatch")
                result["call_edges"].append({"caller": declaration_id, "callee": target_id,
                                             "range": expr.get("range"),
                                             "cast_kind": callee_cast_kind})
                if target_id == leaf_id:
                    target_children = _children(target)
                    parameters = [c for c in target_children if c.get("kind") == "ParmVarDecl"]
                    if (target.get("variadic") or any(c.get("kind") in {"CompoundStmt", "CXXTryStmt", "CoroutineBodyStmt"}
                                                      for c in target_children)):
                        raise _Unknown("contract_leaf_not_external_nonvariadic_function")
                    if len(parts) - 1 != len(expected_args) or len(parameters) != len(expected_args):
                        raise _Unknown("external_argument_arity_mismatch")
                    for position, (arg, parameter, expected) in enumerate(zip(parts[1:], parameters, expected_args)):
                        value, ty = argument(arg)
                        if ty != scalar_type(parameter) or value != expected:
                            raise _Unknown("external_argument_contract_mismatch")
                        result["leaf_arguments"].append({"position": position, "value": value, "type": ty[0]})
                    returned = leaf_type
                else:
                    if len(parts) != 1:
                        raise _Unknown("internal_getter_arguments_unsupported")
                    returned = follow(target_id, call_depth + 1)
                if scalar_type(expr) != returned:
                    raise _Unknown("call_return_type_mismatch")
                return returned

            active.add(declaration_id)
            try:
                return evaluate(_children(statement)[0], 0)
            finally:
                active.remove(declaration_id)

        returned = follow(start_declaration_id, 0)
        result.update(status="checked", return_type=returned[0],
                      return_interval={"lower": lower, "upper": upper},
                      completion={
                          "status": "conditional",
                          "external_leaf_declaration_id": leaf_id,
                          "external_arguments": list(expected_args),
                          "maximum_call_edges": len(result["call_edges"]),
                          "premise": "valid calls and the exact external leaf returns normally",
                      })
    except _Unknown as error:
        result["reason"] = error.reason
    except _Rejected as error:
        result.update(status="rejected", reason=str(error))
    return result


def check_no_memory_write(root: object, start_declaration_id: object,
                          leaf_contract: object, integer_types: object,
                          effect_protocol: object, *,
                          max_ast_nodes: int | None = None) -> dict[str, Any]:
    """Conditionally check that the restricted getter wrappers do not write memory.

    The external leaf effect and normal completion are explicit, unverified
    premises.  In particular, declaration names and Clang attributes are not
    interpreted as effect evidence.

    This deliberately narrower sufficient check also requires the existing
    value-domain check. Callers must supply an independently justified domain;
    they must not invent one merely to obtain a memory-effect conclusion.
    """
    value_report = check(root, start_declaration_id, leaf_contract, integer_types,
                         max_ast_nodes=max_ast_nodes)
    result: dict[str, Any] = {
        "schema_version": "getter-no-memory-write-check/v1",
        "status": "unknown",
        "reason": None,
        "start_declaration_id": start_declaration_id,
        "getter_return_check": value_report,
        "scope": "restricted_getter_wrapper_chain_no_memory_write_under_explicit_external_leaf_effect",
        "source_program_checked": False,
        "deployable": False,
        "external_leaf_effect_verified": False,
        "assumptions": [
            "AST is a faithful well-formed single translation unit",
            "the fresh getter return check exactly describes the wrapper call chain",
            "the exact external leaf performs no memory writes",
            "source calls are valid and the exact external leaf returns normally",
        ],
        "limitations": [
            "requires the supplied leaf domain and ABI; not a standalone effect analysis",
            "the external evidence reference is recorded but not verified",
            "declaration names and attributes do not establish memory effects",
            "coordinate meaning, receiver and call-site effects are not established",
            "compiled-code identity and whole-program memory behavior are not established",
        ],
    }
    if not isinstance(effect_protocol, dict):
        result["reason"] = "invalid_effect_protocol"
        return result
    if not isinstance(value_report.get("input_sha256"), dict):
        result["reason"] = "getter_return_check_not_checked"
        return result
    try:
        # Reuse only the fresh in-process check above, never a caller's report.
        root_sha256 = value_report["input_sha256"]["root"]
        result["input_sha256"] = {
            "root": root_sha256,
            "start_declaration_id": _hash(start_declaration_id),
            "leaf_contract": _hash(leaf_contract),
            "integer_types": _hash(integer_types),
            "effect_protocol": _hash(effect_protocol),
        }
    except (TypeError, ValueError, RecursionError):
        result["reason"] = "input_hash_unsupported"
        return result

    if value_report.get("status") != "checked":
        result["reason"] = "getter_return_check_not_checked"
        return result
    completion = value_report.get("completion")
    leaf_id = leaf_contract.get("declaration_id") if isinstance(leaf_contract, dict) else None
    if (not isinstance(completion, dict) or completion.get("status") != "conditional" or
            completion.get("external_leaf_declaration_id") != leaf_id):
        result["reason"] = "getter_completion_not_established"
        return result

    evidence_reference = effect_protocol.get("evidence_reference")
    if (effect_protocol.get("schema_version") != "getter-leaf-effect-assumption/v1" or
            effect_protocol.get("root_sha256") != root_sha256 or
            effect_protocol.get("start_declaration_id") != start_declaration_id or
            effect_protocol.get("external_leaf_declaration_id") != leaf_id or
            effect_protocol.get("external_leaf_no_memory_write_assumed") is not True or
            effect_protocol.get("valid_calls_and_external_leaf_returns_normally_assumed") is not True or
            not isinstance(evidence_reference, str) or not evidence_reference.strip()):
        result["reason"] = "effect_protocol_not_applicable"
        return result

    result.update(
        status="checked",
        external_leaf_declaration_id=leaf_id,
        effect_evidence={
            "reference": evidence_reference,
            "verification_status": "unverified",
        },
        conclusion={
            "status": "conditional",
            "property": "no_memory_write",
            "subject": "restricted_getter_wrapper_chain",
            "premise": "the exact external leaf performs no memory writes and returns normally from valid calls",
        },
    )
    return result
