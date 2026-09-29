"""Exact unary-float parameter forwarding, with no external-call semantics."""
from wavebridge.verification.builtin_calls import _children, _typed, _Unknown
from wavebridge.verification.getter_returns import _hash
from wavebridge.verification.using_shadow_identity import UsingShadowIndex, IdentityUnknown, IDENTITY_POLICY

MAX_AST_NODES = 1_000_000
HARD_MAX_AST_NODES = 10_000_000
ATTRIBUTES = {"CUDAHostAttr", "CUDADeviceAttr", "AlwaysInlineAttr", "NoInlineAttr",
              "NoThrowAttr", "ConstAttr", "PureAttr", "UsedAttr", "BuiltinAttr"}


def inspect_structure(root, start_declaration_id, leaf_declaration_id, *, max_ast_nodes=None,
                      allow_using_shadows=False):
    return _inspect_forwarding(root, start_declaration_id, leaf_declaration_id,
                               max_ast_nodes=max_ast_nodes, allow_using_shadows=allow_using_shadows)


def _inspect_forwarding(root, start_declaration_id, leaf_declaration_id, *, max_ast_nodes=None,
                        allow_using_shadows=False, native_leaf=None):
    budget = MAX_AST_NODES if max_ast_nodes is None else max_ast_nodes
    result = {"schema_version": "scalar-forwarding-structure/v1", "status": "unknown", "reason": None,
              "scope": "exact_scalar_parameter_forwarding_chain",
              "wrapper_declaration_ids": [], "call_edges": [],
              "using_shadow_references_enabled": allow_using_shadows, "using_shadow_references": [],
              "source_program_checked": False, "deployable": False,
              "value_semantics": "not_established", "effect_semantics": "not_established",
              "assumptions": ["AST faithfully describes one valid translation unit"],
              "limitations": ["external leaf meaning, effects and normal return are not checked",
                              "caller argument evaluation and prior initialization are excluded",
                              "not an FP value-equivalence or compiled-code guarantee"],
              "budget": {"max_ast_nodes": budget, "max_wrappers": 32}}
    result["identity_policy"] = {"allow_using_shadows": allow_using_shadows,
                                 "schema_version": IDENTITY_POLICY if allow_using_shadows else "strict-single-occurrence/v1"}
    if native_leaf is not None:
        result.update(schema_version="scalar-native-forwarding-chain/v1",
                      scope="exact_scalar_parameter_chain_with_fresh_native_terminal",
                      terminal_mode="native_builtin", native_leaf_call_id=native_leaf["observation"]["call_expression_id"])
    try:
        if (not isinstance(root, dict) or root.get("kind") != "TranslationUnitDecl" or
                any(not isinstance(i, str) or not i for i in (start_declaration_id, leaf_declaration_id)) or
                type(budget) is not int or not 1 <= budget <= HARD_MAX_AST_NODES or
                type(allow_using_shadows) is not bool):
            raise _Unknown("invalid_inputs_or_budget")
        identities = UsingShadowIndex(root, budget) if allow_using_shadows else None
        if identities is not None:
            result["using_shadow_references"] = identities.observations
        nodes, pending, count = {}, [root], 0
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
                nodes.setdefault(identifier, []).append(node)
            pending.extend(node.get("inner", []))

        def unique(identifier):
            if identities is not None:
                return identities.unique(identifier)
            candidates = nodes.get(identifier, [])
            if len(candidates) != 1:
                raise _Unknown("declaration_or_expression_identity_not_unique")
            return candidates[0]

        def describe(identifier):
            declaration = unique(identifier)
            if declaration.get("kind") != "FunctionDecl" or declaration.get("variadic"):
                raise _Unknown("not_nonvariadic_free_function")
            signature = declaration.get("type")
            if signature == {"qualType": "float (float)"}:
                suffix = ""
            elif signature == {"qualType": "float (float) noexcept"}:
                suffix = " noexcept"
            else:
                raise _Unknown("function_signature_unsupported")
            children = _children(declaration)
            if any(c.get("kind") not in {"ParmVarDecl", "CompoundStmt"} and
                   (c.get("kind") not in ATTRIBUTES or _children(c)) for c in children):
                raise _Unknown("function_declaration_structure_unsupported")
            parameters = [c for c in children if c.get("kind") == "ParmVarDecl"]
            if (len(parameters) != 1 or parameters[0].get("type") != {"qualType": "float"} or
                    _children(parameters[0]) or not isinstance(parameters[0].get("id"), str) or
                    not parameters[0]["id"] or unique(parameters[0]["id"]) is not parameters[0]):
                raise _Unknown("parameter_not_unique_plain_float")
            return declaration, suffix, parameters[0], [c for c in children if c.get("kind") == "CompoundStmt"]

        leaf, _, leaf_parameter, leaf_bodies = describe(leaf_declaration_id)
        if leaf_bodies or leaf.get("isDeleted") or leaf.get("explicitlyDefaulted"):
            raise _Unknown("selected_leaf_not_external_declaration")
        if start_declaration_id == leaf_declaration_id:
            raise _Unknown("no_wrapper_to_check")
        visited, current, native_consumed = set(), start_declaration_id, False
        while current != leaf_declaration_id:
            if current in visited or len(visited) >= 32:
                raise _Unknown("wrapper_cycle_or_depth_budget")
            visited.add(current)
            declaration, _, parameter, bodies = describe(current)
            if len(bodies) != 1:
                raise _Unknown("wrapper_unique_body_missing")
            statements = _children(bodies[0])
            if (len(statements) != 1 or statements[0].get("kind") != "ReturnStmt" or
                    len(_children(statements[0])) != 1):
                raise _Unknown("wrapper_not_single_return")
            call = _children(statements[0])[0]
            _typed(call, "CallExpr", "float", "prvalue")
            if not isinstance(call.get("id"), str) or not call["id"] or unique(call["id"]) is not call:
                raise _Unknown("call_identity_missing_or_conflicting")
            if native_leaf is not None and call["id"] == native_leaf["observation"]["call_expression_id"]:
                if native_leaf.get("argument_read_declaration_id") != parameter["id"]:
                    raise _Unknown("native_argument_not_current_parameter")
                result["wrapper_declaration_ids"].append(current)
                result["call_edges"].append({"caller_id": current, "callee_id": leaf_declaration_id,
                    "call_expression_id": call["id"], "source_parameter_id": parameter["id"],
                    "target_parameter_id": leaf_parameter["id"], "kind": "native_builtin_terminal"})
                native_consumed, current = True, leaf_declaration_id
                continue
            parts = _children(call)
            if len(parts) != 2:
                raise _Unknown("call_not_unary")
            decay, argument = parts
            if (decay.get("kind") != "ImplicitCastExpr" or decay.get("castKind") != "FunctionToPointerDecay" or
                    len(_children(decay)) != 1):
                raise _Unknown("callee_not_direct_function_decay")
            callee = _children(decay)[0]
            reference = callee.get("referencedDecl")
            if (callee.get("kind") != "DeclRefExpr" or _children(callee) or
                    not isinstance(reference, dict) or reference.get("kind") != "FunctionDecl" or
                    not isinstance(reference.get("id"), str) or not reference["id"]):
                raise _Unknown("callee_not_exact_function_reference")
            target, suffix, target_parameter, _ = describe(reference["id"])
            _typed(callee, "DeclRefExpr", "float (float)" + suffix, "lvalue")
            _typed(decay, "ImplicitCastExpr", "float (*)(float)" + suffix, "prvalue")
            if reference.get("type") != target.get("type") or reference.get("name") != target.get("name"):
                raise _Unknown("callee_declaration_mismatch")
            _typed(argument, "ImplicitCastExpr", "float", "prvalue")
            if argument.get("castKind") != "LValueToRValue" or len(_children(argument)) != 1:
                raise _Unknown("argument_not_plain_parameter_read")
            value = _children(argument)[0]
            _typed(value, "DeclRefExpr", "float", "lvalue")
            ref = value.get("referencedDecl")
            if (_children(value) or not isinstance(ref, dict) or ref.get("kind") != "ParmVarDecl" or
                    ref.get("id") != parameter["id"] or ref.get("type") != parameter.get("type") or
                    ref.get("name") != parameter.get("name")):
                raise _Unknown("argument_not_current_parameter")
            result["wrapper_declaration_ids"].append(current)
            result["call_edges"].append({"caller_id": current, "callee_id": reference["id"],
                                         "call_expression_id": call["id"],
                                         "source_parameter_id": parameter["id"],
                                         "target_parameter_id": target_parameter["id"]})
            current = reference["id"]
        if native_leaf is not None and not native_consumed:
            raise _Unknown("exact_native_leaf_call_not_reached")
        result.update(status="checked", external_leaf_declaration_id=leaf_declaration_id,
                      external_leaf_parameter_id=leaf_parameter["id"],
                      input_sha256={"root": _hash(root), "start_declaration_id": _hash(start_declaration_id),
                                    "leaf_declaration_id": _hash(leaf_declaration_id),
                                    "identity_policy": _hash(result["identity_policy"])})
        if native_leaf is not None:
            result["input_sha256"].update(
                native_envelope=native_leaf["input_sha256"]["native_envelope"],
                native_leaf_call=_hash(native_leaf["observation"]["call_expression_id"]),
                builtin_structure_policy=native_leaf["input_sha256"]["structure_policy"])
    except (_Unknown, IdentityUnknown) as error:
        result["reason"] = str(error)
    except (TypeError, ValueError, RecursionError):
        result["reason"] = "unsupported_input_representation"
    return result


def inspect_builtin_structure(payload, start_declaration_id, leaf_call_id, *, max_ast_nodes=None,
                              allow_using_shadows=False):
    """Fresh exact forwarding to a native unary builtin; excludes caller effects."""
    from wavebridge.verification.builtin_calls import inspect_structure as inspect_builtin
    result = {"schema_version": "scalar-native-forwarding-structure/v1", "status": "unknown",
              "reason": None, "scope": "exact_scalar_parameter_forwarding_to_native_builtin",
              "source_program_checked": False, "deployable": False,
              "value_semantics": "not_established", "effect_semantics": "not_established",
              "outer_argument_effects_checked": False, "native_leaf_structure": None,
              "assumptions": ["native envelope and AST faithfully describe one compiler ASTContext",
                              "compiler and plugin are trusted frontend components"],
              "limitations": ["outer call argument evaluation is excluded",
                              "builtin value, effects and normal return are not established",
                              "not whole-kernel, floating-point equivalence or machine-code verification"]}
    if not isinstance(start_declaration_id, str) or not start_declaration_id:
        result["reason"] = "invalid_start_declaration_id"
        return result
    leaf = inspect_builtin(payload, leaf_call_id, max_ast_nodes=max_ast_nodes,
                           allow_unary_float=True, allow_using_shadows=allow_using_shadows)
    result["native_leaf_structure"] = leaf
    if leaf["status"] != "checked" or leaf.get("argument_structure") != "plain_float_parameter_read":
        result["reason"] = "native_unary_leaf_structure_not_checked"
        return result
    chain = _inspect_forwarding(payload["ast"], start_declaration_id,
        leaf["observation"]["callee_declaration_id"], max_ast_nodes=max_ast_nodes,
        allow_using_shadows=allow_using_shadows, native_leaf=leaf)
    result["forwarding_check"] = chain
    result["assumptions"] = list(dict.fromkeys(result["assumptions"] + leaf["assumptions"] + chain["assumptions"]))
    result["status"], result["reason"] = chain["status"], chain["reason"]
    if chain["status"] == "checked":
        result["input_sha256"] = {**chain["input_sha256"],
            "native_envelope": leaf["input_sha256"]["native_envelope"],
            "native_leaf_call": _hash(leaf_call_id),
            "builtin_structure_policy": leaf["input_sha256"]["structure_policy"]}
    return result
