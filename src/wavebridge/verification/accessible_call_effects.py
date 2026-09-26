"""Conditional accessible-storage preservation of scalar wrapper execution.

Outer argument evaluation is deliberately excluded; callers must check it.
An inaccessible-memory intrinsic is not mislabeled as globally memory-free.
"""
from wavebridge.verification.builtin_calls import _children, _Unknown
from wavebridge.verification.getter_returns import _hash
from wavebridge.verification.scalar_expression_effects import _type, check_no_memory_write


def check_callee(payload, call_id, protocol, *, max_ast_nodes=None):
    budget = 1_000_000 if max_ast_nodes is None else max_ast_nodes
    result = {"schema_version": "callee-accessible-storage-check/v1", "status": "unknown", "reason": None,
              "scope": "callee_execution_excluding_outer_argument_evaluation",
              "outer_argument_effects_checked": False, "external_leaf_effect_verified": False,
              "source_program_checked": False, "deployable": False, "wrapper_checks": [], "argument_checks": [],
              "assumptions": ["native metadata and AST are faithful observations of the same valid translation unit",
                              "runtime implementations match the selected source definitions",
                              "all executions are valid and return normally, including collective participation",
                              "leaf implementation preserves program-accessible storage for every reached argument",
                              "scalar loads and arithmetic are valid; no asynchronous interference"],
              "limitations": ["leaf effect and evidence reference remain external unverified premises",
                              "not memory-free, pure, synchronization-free, value or communication equivalence",
                              "outer argument evaluation and enclosing statements must be checked separately"],
              "budget": {"max_ast_nodes": budget, "max_wrappers": 4, "max_parameters": 8}}
    try:
        if (not isinstance(payload, dict) or payload.get("schema_version") != "clang-native-captures/v1" or
                not isinstance(protocol, dict) or not isinstance(call_id, str) or not call_id or
                type(budget) is not int or not 1 <= budget <= 10_000_000):
            raise _Unknown("invalid_inputs_or_budget")
        root = payload.get("ast")
        if not isinstance(root, dict) or root.get("kind") != "TranslationUnitDecl":
            raise _Unknown("full_ast_missing")
        native_hash = _hash(payload)
        if (protocol.get("schema_version") != "builtin-accessible-storage-assumption/v1" or
                protocol.get("native_envelope_sha256") != native_hash or
                protocol.get("call_expression_id") != call_id or
                protocol.get("leaf_preserves_accessible_storage_assumed") is not True or
                protocol.get("valid_execution_and_normal_return_assumed") is not True or
                not isinstance(protocol.get("evidence_reference"), str) or not protocol["evidence_reference"].strip()):
            raise _Unknown("protocol_missing_or_mismatched")
        index, functions, pending, count = {}, [], [root], 0
        while pending:
            node = pending.pop()
            count += 1
            if count > budget:
                raise _Unknown("ast_node_budget_exceeded")
            if not isinstance(node, dict) or not isinstance(node.get("inner", []), list):
                raise _Unknown("malformed_ast")
            if isinstance(node.get("id"), str):
                index.setdefault(node["id"], []).append(node)
            if node.get("kind") == "FunctionDecl":
                functions.append(node)
            pending.extend(node.get("inner", []))

        def exact(identifier):
            if not isinstance(identifier, str) or len(index.get(identifier, [])) != 1:
                raise _Unknown("identity_not_unique")
            return index[identifier][0]

        current, seen = exact(call_id), set()
        for depth in range(5):
            if current.get("id") in seen:
                raise _Unknown("recursive_call_chain")
            seen.add(current.get("id"))
            parts = _children(current)
            if current.get("kind") != "CallExpr" or _type(current) != "float" or not parts:
                raise _Unknown("call_shape_unsupported")
            decay = parts[0]
            if (decay.get("kind") != "ImplicitCastExpr" or decay.get("castKind") not in
                    {"FunctionToPointerDecay", "BuiltinFnToFnPtr"} or len(_children(decay)) != 1):
                raise _Unknown("callee_not_direct")
            reference = _children(decay)[0]
            ref = reference.get("referencedDecl", {})
            function = exact(ref.get("id"))
            if (reference.get("kind") != "DeclRefExpr" or _children(reference) or
                    ref.get("kind") != "FunctionDecl" or function.get("kind") != "FunctionDecl" or
                    _type(ref) != _type(function) or function.get("variadic")):
                raise _Unknown("callee_declaration_mismatch")
            params = [n for n in _children(function) if n.get("kind") == "ParmVarDecl"]
            types = [_type(n) for n in params]
            if len(params) > 8 or len(parts) != len(params) + 1 or any(t not in {"float", "int", "unsigned int"} for t in types):
                raise _Unknown("signature_or_arity_unsupported")
            signature = "float (" + ", ".join(types) + ")"
            suffix = " noexcept" if _type(function).endswith(" noexcept") else ""
            if (_type(function) != signature + suffix or
                    _type(decay) != "float (*)(" + ", ".join(types) + ")" + suffix or
                    _type(reference) != ("<builtin fn type>" if decay.get("castKind") == "BuiltinFnToFnPtr" else signature + suffix)):
                raise _Unknown("callee_type_chain_mismatch")
            for parameter, argument in zip(params, parts[1:]):
                if exact(parameter.get("id")) is not parameter or _type(argument) != _type(parameter):
                    raise _Unknown("argument_parameter_type_mismatch")
                if depth:
                    checked = check_no_memory_write(root, argument.get("id"), max_ast_nodes=budget,
                                                    allow_constant_globals=True, allow_integer_bitwise=True)
                    result["argument_checks"].append(checked)
                    if checked["status"] != "checked":
                        raise _Unknown("wrapper_argument_effect_not_checked")
            if current.get("id") == protocol.get("leaf_call_expression_id"):
                observations = payload.get("builtin_calls")
                if (function["id"] != protocol.get("leaf_declaration_id") or not isinstance(observations, list) or
                        any(n.get("kind") == "CompoundStmt" for n in _children(function)) or
                        payload.get("builtin_call_semantics") != "compiler_identity_not_value_or_effect_proof"):
                    raise _Unknown("leaf_identity_or_native_evidence_mismatch")
                matches = [n for n in observations if isinstance(n, dict) and n.get("call_expression_id") == current["id"]]
                if (len(matches) != 1 or matches[0].get("callee_declaration_id") != function["id"] or
                        type(matches[0].get("builtin_id")) is not int or matches[0]["builtin_id"] <= 0 or
                        matches[0].get("builtin_name") != function.get("name") or
                        matches[0].get("argument_expression_ids") != [n.get("id") for n in parts[1:]]):
                    raise _Unknown("native_builtin_binding_mismatch")
                result.update(status="checked", native_builtin=matches[0], effect_protocol=dict(protocol),
                              evidence_status="unverified", native_payload_sha256=native_hash,
                              conclusion={"status": "conditional", "property": "preserves_program_accessible_storage",
                                          "subject": "callee_execution_only", "call_expression_id": call_id})
                break
            if depth == 4 or function.get("previousDecl") or any(n.get("previousDecl") == function["id"] for n in functions):
                raise _Unknown("wrapper_depth_or_redeclaration_unsupported")
            members = _children(function)
            if any(n.get("kind") not in {"ParmVarDecl", "TemplateArgument", "CompoundStmt", "CUDADeviceAttr",
                                         "CUDAHostAttr", "AlwaysInlineAttr"} for n in members):
                raise _Unknown("wrapper_declaration_unsupported")
            bodies = [n for n in members if n.get("kind") == "CompoundStmt"]
            statements = _children(bodies[0]) if len(bodies) == 1 else []
            if len(statements) != 1 or statements[0].get("kind") != "ReturnStmt" or len(_children(statements[0])) != 1:
                raise _Unknown("wrapper_not_single_return")
            returned = _children(statements[0])[0]
            if returned.get("kind") != "CallExpr" or exact(returned.get("id")) is not returned:
                raise _Unknown("wrapper_return_not_direct_call")
            result["wrapper_checks"].append({"function_id": function["id"], "return_call_id": returned["id"]})
            current = returned
    except _Unknown as error:
        result["reason"] = str(error)
    except (TypeError, ValueError, KeyError, IndexError, RecursionError):
        result["reason"] = "unsupported_input_representation"
    return result
