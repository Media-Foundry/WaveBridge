"""Bind narrow builtin call shapes to trusted same-context native observations.

`checked` is structural only. No builtin return value or effect is assumed.
"""
from __future__ import annotations

from wavebridge.verification.getter_returns import _hash

MAX_AST_NODES = 1_000_000
HARD_MAX_AST_NODES = 10_000_000


class _Unknown(Exception):
    pass


def _children(node):
    children = node.get("inner", [])
    if not isinstance(children, list) or any(not isinstance(c, dict) or not c for c in children):
        raise _Unknown("malformed_selected_children")
    return children


def _typed(node, kind, spelling, category):
    if (node.get("kind") != kind or node.get("type") != {"qualType": spelling} or
            node.get("valueCategory") != category):
        raise _Unknown("selected_expression_shape_mismatch")


def inspect_structure(payload, call_expression_id, *, max_ast_nodes=None):
    budget = MAX_AST_NODES if max_ast_nodes is None else max_ast_nodes
    report = {
        "schema_version": "builtin-call-structure/v1", "status": "unknown", "reason": None,
        "scope": "same_context_native_builtin_identity_and_restricted_argument_structure",
        "source_program_checked": False, "deployable": False,
        "value_semantics": "not_established", "effect_semantics": "not_established",
        "assumptions": ["native envelope and embedded AST faithfully describe one compiler ASTContext",
                        "compiler and native plugin are trusted frontend components"],
        "remaining_obligations": ["builtin value and effect semantics under the actual compilation protocol",
                                  "source validity and normal return", "enclosing expression effects"],
        "budget": {"max_ast_nodes": budget},
    }
    try:
        if type(budget) is not int or not 1 <= budget <= HARD_MAX_AST_NODES:
            raise _Unknown("invalid_ast_budget")
        if (not isinstance(payload, dict) or not isinstance(call_expression_id, str) or
                not call_expression_id):
            raise _Unknown("invalid_inputs")
        if (payload.get("schema_version") != "clang-native-captures/v1" or
                payload.get("builtin_call_coverage") != "visited_direct_builtin_calls_not_exhaustive" or
                payload.get("builtin_call_semantics") != "compiler_identity_not_value_or_effect_proof" or
                any(not isinstance(payload.get(k), str) or not payload[k]
                    for k in ("plugin_build_clang_version", "ast_target_triple"))):
            raise _Unknown("native_envelope_evidence_missing")
        root = payload.get("ast")
        records = payload.get("builtin_calls")
        if (not isinstance(root, dict) or root.get("kind") != "TranslationUnitDecl" or
                not isinstance(records, list) or len(records) > budget or
                any(not isinstance(r, dict) for r in records)):
            raise _Unknown("native_payload_malformed")
        selected = [r for r in records if r.get("call_expression_id") == call_expression_id]
        if len(selected) != 1:
            raise _Unknown("native_call_observation_not_unique")
        observed = selected[0]
        if type(observed.get("builtin_id")) is not int or observed["builtin_id"] <= 0:
            raise _Unknown("native_builtin_id_invalid")
        name = observed.get("builtin_name")
        if name not in {"__builtin_huge_valf", "__builtin_nanf"}:
            raise _Unknown("builtin_structure_not_supported")
        declaration_id = observed.get("callee_declaration_id")
        if not isinstance(declaration_id, str) or not declaration_id:
            raise _Unknown("native_callee_id_missing")
        nodes, pending, count = {}, [root], 0
        while pending:
            node = pending.pop()
            count += 1
            if count > budget:
                raise _Unknown("ast_node_budget_exceeded")
            if not isinstance(node, dict):
                raise _Unknown("ast_node_malformed")
            identifier = node.get("id")
            if isinstance(identifier, str) and identifier:
                nodes.setdefault(identifier, []).append(node)
            children = node.get("inner", [])
            if not isinstance(children, list):
                raise _Unknown("ast_children_malformed")
            pending.extend(children)

        def unique(identifier):
            matches = nodes.get(identifier, [])
            if len(matches) != 1:
                raise _Unknown("selected_ast_identity_not_unique")
            return matches[0]

        call, declaration = unique(call_expression_id), unique(declaration_id)
        _typed(call, "CallExpr", "float", "prvalue")
        arguments = "const char *" if name == "__builtin_nanf" else ""
        signature = f"float ({arguments})"
        declaration_type = declaration.get("type")
        if declaration_type == {"qualType": signature + " noexcept"}:
            suffix = " noexcept"
        elif declaration_type == {"qualType": signature}:
            suffix = ""
        else:
            raise _Unknown("builtin_declaration_type_mismatch")
        if (declaration.get("kind") != "FunctionDecl" or declaration.get("name") != name or
                declaration.get("variadic")):
            raise _Unknown("builtin_declaration_mismatch")
        declaration_children = _children(declaration)
        if (sum(c.get("kind") == "BuiltinAttr" for c in declaration_children) != 1 or
                any(c.get("kind") not in {"ParmVarDecl", "BuiltinAttr", "NoThrowAttr", "ConstAttr", "PureAttr"}
                    or _children(c) for c in declaration_children)):
            raise _Unknown("builtin_declaration_structure_unsupported")
        parameters = [c for c in declaration_children if c.get("kind") == "ParmVarDecl"]
        expected_count = 1 if arguments else 0
        if (len(parameters) != expected_count or
                any(p.get("type") != {"qualType": "const char *"} for p in parameters)):
            raise _Unknown("builtin_parameters_mismatch")
        parts = _children(call)
        if len(parts) != expected_count + 1:
            raise _Unknown("call_arity_mismatch")
        decay = parts[0]
        _typed(decay, "ImplicitCastExpr", f"float (*)({arguments})" + suffix, "prvalue")
        if decay.get("castKind") != "BuiltinFnToFnPtr" or len(_children(decay)) != 1:
            raise _Unknown("builtin_callee_decay_mismatch")
        callee = _children(decay)[0]
        _typed(callee, "DeclRefExpr", "<builtin fn type>", "prvalue")
        ref = callee.get("referencedDecl")
        if (_children(callee) or not isinstance(ref, dict) or ref.get("kind") != "FunctionDecl" or
                ref.get("id") != declaration_id or ref.get("name") != name or
                ref.get("type") != declaration_type):
            raise _Unknown("callee_reference_mismatch")
        ids = observed.get("argument_expression_ids")
        if (not isinstance(ids, list) or any(not isinstance(i, str) or not i for i in ids) or
                ids != [a.get("id") for a in parts[1:]]):
            raise _Unknown("native_argument_identity_mismatch")
        for identifier, arg in zip(ids, parts[1:]):
            if unique(identifier) is not arg:
                raise _Unknown("argument_identity_mismatch")
            _typed(arg, "ImplicitCastExpr", "const char *", "prvalue")
            if arg.get("castKind") != "ArrayToPointerDecay" or len(_children(arg)) != 1:
                raise _Unknown("argument_not_literal_decay")
            literal = _children(arg)[0]
            _typed(literal, "StringLiteral", "const char[1]", "lvalue")
            if _children(literal) or literal.get("value") != '""':
                raise _Unknown("argument_not_empty_string")
        report["input_sha256"] = {"native_envelope": _hash(payload), "call_expression_id": _hash(call_expression_id)}
        report.update(status="checked", observation=dict(observed),
                      argument_structure="empty_string_literal" if arguments else "no_arguments")
    except _Unknown as error:
        report["reason"] = str(error)
    except (TypeError, ValueError, RecursionError):
        report["reason"] = "unsupported_input_representation"
    return report


def check_no_memory_write(payload, call_expression_id, effect_protocol, *, max_ast_nodes=None):
    """Compose restricted argument evaluation with an explicit external leaf effect.

    The protocol is an assumption, not a certificate. No return value, FP
    environment, purity, enclosing expression or invocation history is proved.
    """
    structure = inspect_structure(payload, call_expression_id, max_ast_nodes=max_ast_nodes)
    result = {
        "schema_version": "builtin-call-no-memory-write/v1", "status": "unknown", "reason": None,
        "scope": "exact_builtin_call_expression_under_explicit_external_leaf_effect",
        "structure_check": structure, "source_program_checked": False, "deployable": False,
        "value_semantics": "not_established", "external_leaf_effect_verified": False,
        "assumptions": ["native envelope and embedded AST faithfully describe one compiler ASTContext",
                        "compiler and native plugin are trusted frontend components",
                        "the exact builtin callee implementation performs no memory writes (argument evaluation excluded)",
                        "the selected source call is valid and returns normally"],
        "limitations": ["external evidence reference is recorded but not verified",
                        "only no-memory-write is composed, not purity or complete absence of effects",
                        "builtin return value and floating-point environment behavior are not established",
                        "enclosing expression, wrapper body, loop, and invocation history are excluded",
                        "no machine-code or GPU execution guarantee"],
    }
    if structure.get("status") != "checked":
        result["reason"] = "fresh_builtin_structure_not_checked"
        return result
    if not isinstance(effect_protocol, dict):
        result["reason"] = "invalid_effect_protocol"
        return result
    try:
        hashes = structure["input_sha256"]
        result["input_sha256"] = dict(hashes, effect_protocol=_hash(effect_protocol))
        observation = structure["observation"]
        evidence = effect_protocol.get("evidence_reference")
        if (effect_protocol.get("schema_version") != "builtin-leaf-effect-assumption/v1" or
                effect_protocol.get("native_envelope_sha256") != hashes["native_envelope"] or
                effect_protocol.get("call_expression_id") != call_expression_id or
                effect_protocol.get("callee_declaration_id") != observation["callee_declaration_id"] or
                effect_protocol.get("builtin_no_memory_write_assumed") is not True or
                effect_protocol.get("valid_call_and_normal_return_assumed") is not True or
                not isinstance(evidence, str) or not evidence.strip()):
            result["reason"] = "effect_protocol_not_applicable"
            return result
        # Fresh structure admits only a direct builtin decay plus either no
        # operands or a literal array-to-pointer decay. No hidden argument
        # evaluation is removed by trusting the leaf's effect assumption.
        result.update(status="checked", effect_evidence={
            "reference": evidence, "verification_status": "unverified"},
            argument_evaluation={"status": "checked_in_supported_structure",
                                 "property": "no_memory_write",
                                 "shape": structure["argument_structure"]},
            conclusion={"status": "conditional", "property": "no_memory_write",
                        "subject": "exact_builtin_call_expression",
                        "call_expression_id": call_expression_id,
                        "callee_declaration_id": observation["callee_declaration_id"],
                        "premise": "the call is valid and returns normally; the exact builtin implementation performs no memory writes, excluding argument evaluation"})
    except (TypeError, ValueError, RecursionError):
        result["reason"] = "unsupported_effect_protocol_representation"
    return result


def check_wrapper_no_memory_write(payload, start_declaration_id, effect_protocol, *, max_ast_nodes=None):
    """Check entire single-return wrapper bodies, not their external call sites."""
    budget = MAX_AST_NODES if max_ast_nodes is None else max_ast_nodes
    result = {
        "schema_version": "builtin-wrapper-no-memory-write/v1", "status": "unknown", "reason": None,
        "scope": "restricted_single_return_wrapper_chain_under_external_builtin_effect",
        "source_program_checked": False, "deployable": False,
        "value_semantics": "not_established", "external_leaf_effect_verified": False,
        "wrapper_declaration_ids": [], "leaf_check": None,
        "assumptions": ["native envelope and embedded AST faithfully describe one compiler ASTContext",
                        "source calls and wrapper definitions are valid and denote the bound implementations",
                        "the supplied builtin no-write and normal-return premises hold"],
        "limitations": ["external caller receiver and argument evaluation are excluded",
                        "no return value, FP-environment, purity or machine-code equivalence guarantee",
                        "external effect evidence remains unverified; no loop or deployment acceptance"],
        "budget": {"max_ast_nodes_per_scan": budget, "max_wrappers": 32},
    }
    try:
        if (type(budget) is not int or not 1 <= budget <= HARD_MAX_AST_NODES or
                not isinstance(payload, dict) or not isinstance(effect_protocol, dict) or
                not isinstance(start_declaration_id, str) or not start_declaration_id):
            raise _Unknown("invalid_inputs_or_budget")
        leaf_call_id = effect_protocol.get("call_expression_id")
        if not isinstance(leaf_call_id, str) or not leaf_call_id:
            raise _Unknown("external_leaf_call_id_missing")
        index, pending, count = {}, [payload.get("ast")], 0
        while pending:
            node = pending.pop()
            count += 1
            if count > budget:
                raise _Unknown("ast_node_budget_exceeded")
            if not isinstance(node, dict) or not isinstance(node.get("inner", []), list):
                raise _Unknown("malformed_ast")
            identifier = node.get("id")
            if isinstance(identifier, str) and identifier:
                index.setdefault(identifier, []).append(node)
            pending.extend(node.get("inner", []))

        def unique(identifier):
            found = index.get(identifier, [])
            if len(found) != 1:
                raise _Unknown("wrapper_identity_not_unique")
            return found[0]

        def signature(declaration):
            info = declaration.get("type")
            if info == {"qualType": "float ()"}:
                return ""
            if info == {"qualType": "float () noexcept"}:
                return " noexcept"
            raise _Unknown("wrapper_signature_unsupported")

        current = start_declaration_id
        visited = set()
        while True:
            if current in visited or len(visited) >= 32:
                raise _Unknown("wrapper_cycle_or_depth_budget")
            visited.add(current)
            declaration = unique(current)
            kind = declaration.get("kind")
            if (kind not in {"FunctionDecl", "CXXMethodDecl"} or
                    (kind == "CXXMethodDecl" and declaration.get("storageClass") != "static") or
                    declaration.get("virtual") or declaration.get("variadic")):
                raise _Unknown("wrapper_declaration_unsupported")
            signature(declaration)
            children = _children(declaration)
            allowed_attrs = {"CUDAHostAttr", "CUDADeviceAttr", "AlwaysInlineAttr", "NoInlineAttr",
                             "NoThrowAttr", "ConstAttr", "PureAttr", "UsedAttr"}
            bodies = [c for c in children if c.get("kind") == "CompoundStmt"]
            if (len(bodies) != 1 or any(c.get("kind") != "CompoundStmt" and
                    (c.get("kind") not in allowed_attrs or _children(c)) for c in children)):
                raise _Unknown("wrapper_body_or_declaration_effect_unsupported")
            statements = _children(bodies[0])
            if (len(statements) != 1 or statements[0].get("kind") != "ReturnStmt" or
                    len(_children(statements[0])) != 1):
                raise _Unknown("wrapper_not_single_return")
            call = _children(statements[0])[0]
            _typed(call, "CallExpr", "float", "prvalue")
            call_id = call.get("id")
            if not isinstance(call_id, str) or not call_id or unique(call_id) is not call:
                raise _Unknown("wrapper_return_call_identity_mismatch")
            result["wrapper_declaration_ids"].append(current)
            if call_id == leaf_call_id:
                leaf = check_no_memory_write(payload, call_id, effect_protocol, max_ast_nodes=budget)
                result["leaf_check"] = leaf
                if leaf.get("status") != "checked":
                    raise _Unknown("fresh_builtin_effect_not_checked")
                result["input_sha256"] = dict(leaf["input_sha256"], start_declaration_id=_hash(start_declaration_id))
                result.update(status="checked", conclusion={
                    "status": "conditional", "property": "no_memory_write",
                    "subject": "restricted_single_return_wrapper_chain",
                    "start_declaration_id": start_declaration_id,
                    "external_leaf_call_expression_id": call_id})
                return result
            parts = _children(call)
            if len(parts) != 1:
                raise _Unknown("wrapper_call_arguments_unsupported")
            decay = parts[0]
            if (decay.get("kind") != "ImplicitCastExpr" or
                    decay.get("castKind") != "FunctionToPointerDecay" or len(_children(decay)) != 1):
                raise _Unknown("wrapper_callee_decay_unsupported")
            callee = _children(decay)[0]
            ref = callee.get("referencedDecl")
            if (callee.get("kind") != "DeclRefExpr" or _children(callee) or
                    not isinstance(ref, dict) or not isinstance(ref.get("id"), str) or not ref["id"]):
                raise _Unknown("wrapper_callee_not_direct_reference")
            target = unique(ref["id"])
            suffix = signature(target)
            _typed(callee, "DeclRefExpr", "float ()" + suffix, "lvalue")
            _typed(decay, "ImplicitCastExpr", "float (*)()" + suffix, "prvalue")
            if (ref.get("kind") != target.get("kind") or ref.get("type") != target.get("type") or
                    ref.get("name") != target.get("name")):
                raise _Unknown("wrapper_callee_declaration_mismatch")
            current = ref["id"]
    except _Unknown as error:
        result["reason"] = str(error)
    except (TypeError, ValueError, RecursionError):
        result["reason"] = "unsupported_wrapper_representation"
    return result
