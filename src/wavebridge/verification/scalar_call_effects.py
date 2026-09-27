"""Conditional no-write composition for direct unary-float wrapper calls."""
from wavebridge.verification.builtin_calls import _children, _typed, _Unknown
from wavebridge.verification.getter_returns import _hash
from wavebridge.verification.scalar_forwarding import inspect_structure, MAX_AST_NODES, HARD_MAX_AST_NODES
from wavebridge.verification.scalar_expression_effects import check_no_memory_write as check_argument
from wavebridge.verification.using_shadow_identity import UsingShadowIndex, IdentityUnknown, IDENTITY_POLICY


def check_no_memory_write(root, call_expression_id, effect_protocol, *, max_ast_nodes=None,
                          allow_using_shadows=False):
    budget = MAX_AST_NODES if max_ast_nodes is None else max_ast_nodes
    result = {"schema_version": "scalar-call-no-memory-write/v1", "status": "unknown", "reason": None,
              "scope": "one_direct_unary_float_wrapper_call",
              "source_program_checked": False, "deployable": False,
              "external_leaf_effect_verified": False, "value_semantics": "not_established",
              "numeric_contract_checked": False,
              "assumptions": ["AST faithfully describes a valid translation unit",
                              "runtime definitions match the selected declarations and wrapper bodies"],
              "limitations": ["external leaf implementation and evidence reference are not verified",
                              "not FP-environment preservation, purity or returned-value equivalence",
                              "enclosing expressions, statements, loops and machine code are excluded"],
              "forwarding_check": None, "argument_check": None}
    result.update(using_shadow_references_enabled=allow_using_shadows, using_shadow_references=[])
    result["identity_policy"] = {"allow_using_shadows": allow_using_shadows,
                                 "schema_version": IDENTITY_POLICY if allow_using_shadows else "strict-single-occurrence/v1"}
    try:
        if (not isinstance(root, dict) or root.get("kind") != "TranslationUnitDecl" or
                not isinstance(call_expression_id, str) or not call_expression_id or
                type(budget) is not int or not 1 <= budget <= HARD_MAX_AST_NODES or
                not isinstance(effect_protocol, dict) or type(allow_using_shadows) is not bool):
            raise _Unknown("invalid_inputs_or_budget")
        identities = UsingShadowIndex(root, budget) if allow_using_shadows else None
        if identities is not None:
            result["using_shadow_references"] = identities.observations
        index, pending, count = {}, [root], 0
        if identities is not None:
            pending = []
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
            if identities is not None:
                return identities.unique(identifier)
            if not isinstance(identifier, str) or not identifier or len(index.get(identifier, [])) != 1:
                raise _Unknown("identity_not_unique")
            return index[identifier][0]

        root_hash = _hash(root)
        protocol = effect_protocol
        if (protocol.get("schema_version") != "scalar-leaf-effect-assumption/v1" or
                protocol.get("root_sha256") != root_hash or
                protocol.get("call_expression_id") != call_expression_id or
                protocol.get("leaf_no_memory_write_assumed") is not True or
                protocol.get("valid_call_and_normal_return_assumed") is not True or
                not isinstance(protocol.get("evidence_reference"), str) or
                not protocol["evidence_reference"].strip()):
            raise _Unknown("effect_protocol_missing_or_mismatched")
        leaf_id = protocol.get("leaf_declaration_id")
        unique(leaf_id)
        call = unique(call_expression_id)
        _typed(call, "CallExpr", "float", "prvalue")
        parts = _children(call)
        if len(parts) != 2:
            raise _Unknown("call_not_unary")
        decay, argument = parts
        if (decay.get("kind") != "ImplicitCastExpr" or decay.get("castKind") != "FunctionToPointerDecay" or
                len(_children(decay)) != 1):
            raise _Unknown("callee_not_direct_function_decay")
        callee = _children(decay)[0]
        ref = callee.get("referencedDecl")
        if not isinstance(ref, dict) or ref.get("kind") != "FunctionDecl" or _children(callee):
            raise _Unknown("callee_not_exact_free_function")
        target = unique(ref.get("id"))
        signature = target.get("type")
        if signature == {"qualType": "float (float)"}:
            suffix = ""
        elif signature == {"qualType": "float (float) noexcept"}:
            suffix = " noexcept"
        else:
            raise _Unknown("target_signature_unsupported")
        _typed(callee, "DeclRefExpr", "float (float)" + suffix, "lvalue")
        _typed(decay, "ImplicitCastExpr", "float (*)(float)" + suffix, "prvalue")
        if ref.get("type") != signature or ref.get("name") != target.get("name"):
            raise _Unknown("callee_declaration_mismatch")
        forwarding = inspect_structure(root, ref["id"], leaf_id, max_ast_nodes=budget,
                                       allow_using_shadows=allow_using_shadows)
        result["forwarding_check"] = forwarding
        if forwarding["status"] != "checked":
            raise _Unknown("forwarding_not_checked")
        argument_id = argument.get("id")
        if unique(argument_id) is not argument:
            raise _Unknown("argument_identity_conflicting")
        checked_argument = check_argument(root, argument_id, max_ast_nodes=budget)
        result["argument_check"] = checked_argument
        if checked_argument["status"] != "checked" or checked_argument.get("result_type") != "float":
            raise _Unknown("argument_not_checked_float")
        result.update(status="checked", effect_protocol=dict(protocol), evidence_status="unverified",
                      input_sha256={"root": root_hash, "protocol": _hash(protocol),
                                    "identity_policy": _hash(result["identity_policy"])},
                      conclusion={"status": "conditional", "property": "no_memory_write",
                                  "subject": "exact_call_expression", "call_expression_id": call_expression_id})
        result["assumptions"].extend(checked_argument["assumptions"])
        result["assumptions"].extend([
            "external leaf implementation does not write memory for every value reached by this call",
            "the call is valid and returns normally; external leaf premise excludes argument evaluation"])
    except (_Unknown, IdentityUnknown) as error:
        result["reason"] = str(error)
    except (TypeError, ValueError, RecursionError):
        result["reason"] = "unsupported_input_representation"
    return result
