"""A normal-return necessary condition, not an API-success proof."""
from wavebridge.verification.getter_returns import _hash
from wavebridge.verification.launch_binding import _direct_callee
from wavebridge.verification.using_shadow_identity import UsingShadowIndex, IDENTITY_POLICY


def check(root, function_id, *, max_ast_nodes=1_000_000):
    result = {
        "schema_version": "normal-return-guard/v1", "status": "unknown", "reason": None,
        "scope": "normal_return_implies_selected_converted_comparison_is_false",
        "API_success_verified": False, "enum_equality_established": False,
        "runtime_linkage_verified": False, "source_program_checked": False, "deployable": False,
        "assumptions": ["faithful valid C++ AST and ordinary sequential execution",
                        "noreturn declaration contract is respected by the linked implementation",
                        "no nonlocal jumps or asynchronous interference"],
        "limitations": ["necessary condition only; does not prove return or call reachability",
                        "no enum conversion injectivity, API success, or property value guarantee",
                        "calls preceding the terminal call are not checked for purity"],
    }
    try:
        if (not isinstance(root, dict) or root.get("kind") != "TranslationUnitDecl" or
                not isinstance(function_id, str) or not function_id or
                type(max_ast_nodes) is not int or not 1 <= max_ast_nodes <= 10_000_000):
            raise ValueError("invalid_input_or_budget")
        index = UsingShadowIndex(root, max_ast_nodes)

        def children(node, kind, size=None):
            if node.get("kind") != kind or index.unique(node.get("id")) is not node:
                raise ValueError("unsupported_shape_or_identity")
            values = node.get("inner", [])
            if size is not None and len(values) != size:
                raise ValueError("unsupported_arity")
            return values

        function = index.unique(function_id)
        members = children(function, "FunctionDecl")
        pending = [function]
        forbidden = {"ReturnStmt", "GotoStmt", "IndirectGotoStmt", "LabelStmt", "StmtExpr",
                     "SwitchStmt", "CaseStmt", "DefaultStmt", "GCCAsmStmt", "MSAsmStmt",
                     "CXXTryStmt", "CXXCatchStmt", "SEHTryStmt", "SEHExceptStmt", "SEHFinallyStmt",
                     "CoroutineBodyStmt", "CoawaitExpr", "CoyieldExpr", "CoreturnStmt", "LambdaExpr"}
        while pending:
            node = pending.pop()
            if node.get("kind") in forbidden:
                raise ValueError("nonordinary_control_unsupported")
            pending.extend(node.get("inner", []))
        parameters = [n for n in members if n.get("kind") == "ParmVarDecl"]
        bodies = [n for n in members if n.get("kind") == "CompoundStmt"]
        if (len(parameters) != 1 or len(bodies) != 1 or len(members) != 2 or
                function.get("variadic") or
                not function.get("type", {}).get("qualType", "").startswith("void (")):
            raise ValueError("single_parameter_void_function_required")
        parameter = parameters[0]
        semantic_type = parameter.get("type", {}).get("desugaredQualType", "")
        # Do not infer semantic enum equality from compiler-dependent spellings.
        if (not semantic_type or any(c in semantic_type for c in "&*") or
                any(q in semantic_type.split() for q in ("const", "volatile"))):
            raise ValueError("by_value_unqualified_parameter_required")
        guard, = children(bodies[0], "CompoundStmt", 1)
        condition, failed = children(guard, "IfStmt", 2)
        if any(guard.get(k) for k in ("hasElse", "hasInit", "hasVar", "isConstexpr")):
            raise ValueError("plain_guard_required")
        left, right = children(condition, "BinaryOperator", 2)
        if (condition.get("opcode") != "!=" or condition.get("type") != {"qualType": "bool"} or
                condition.get("valueCategory") != "prvalue"):
            raise ValueError("inequality_guard_required")

        def converted(node):
            value, = children(node, "ImplicitCastExpr", 1)
            if (node.get("castKind") != "IntegralCast" or node.get("type") != {"qualType": "int"} or
                    node.get("valueCategory") != "prvalue"):
                raise ValueError("enum_to_int_conversion_required")
            return value

        load = converted(left)
        ref, = children(load, "ImplicitCastExpr", 1)
        if (load.get("castKind") != "LValueToRValue" or load.get("valueCategory") != "prvalue" or
                load.get("type") != parameter.get("type")):
            raise ValueError("parameter_load_required")
        children(ref, "DeclRefExpr", 0)
        binding = ref.get("referencedDecl", {})
        if (binding.get("id") != parameter.get("id") or binding.get("kind") != "ParmVarDecl" or
                binding.get("type") != parameter.get("type") or ref.get("type") != parameter.get("type") or
                ref.get("valueCategory") != "lvalue"):
            raise ValueError("wrong_guard_parameter")
        constant_ref = converted(right)
        children(constant_ref, "DeclRefExpr", 0)
        binding = constant_ref.get("referencedDecl", {})
        constant = index.unique(binding.get("id"))
        if (constant.get("kind") != "EnumConstantDecl" or binding.get("kind") != "EnumConstantDecl" or
                constant_ref.get("type") != constant.get("type") or binding.get("type") != constant.get("type") or
                constant_ref.get("valueCategory") != "prvalue"):
            raise ValueError("enum_constant_required")
        statements = children(failed, "CompoundStmt")
        if not statements or any(n.get("kind") != "CallExpr" for n in statements):
            raise ValueError("failure_branch_call_sequence_required")
        terminal = statements[-1]
        terminal_parts = children(terminal, "CallExpr")
        if not terminal_parts or terminal.get("type") != {"qualType": "void"}:
            raise ValueError("terminal_void_call_required")
        designator = terminal_parts[0]
        leaf = designator
        while leaf.get("kind") in {"ParenExpr", "ImplicitCastExpr"}:
            values = leaf.get("inner", [])
            if len(values) != 1: raise ValueError("unsupported_callee")
            leaf = values[0]
        declaration = index.unique(leaf.get("referencedDecl", {}).get("id"))
        if (declaration.get("kind") != "FunctionDecl" or
                not _direct_callee(designator, declaration) or
                "__attribute__((noreturn))" not in declaration.get("type", {}).get("qualType", "")):
            raise ValueError("direct_noreturn_declaration_required")
        result.update(status="checked", comparison_false_on_normal_return=True,
                      function_id=function_id, parameter_id=parameter["id"],
                      guard_id=guard["id"], comparison_id=condition["id"],
                      converted_operand_ids=[left["id"], right["id"]],
                      constant_id=constant["id"], terminal_call_id=terminal["id"],
                      noreturn_declaration_id=declaration["id"],
                      unchecked_prefix_call_ids=[n["id"] for n in statements[:-1]],
                      input_sha256={"root": _hash(root), "selection": _hash(function_id),
                                    "identity_policy": _hash(IDENTITY_POLICY)}, identity_policy=IDENTITY_POLICY,
                      identity_observations=index.observations)
    except (ValueError, TypeError, KeyError, IndexError, AttributeError, RecursionError) as error:
        result["reason"] = str(error)
    return result


def check_call(root, call_id, *, max_ast_nodes=1_000_000):
    """Freshly compose a direct nested query result with its guard definition.

    No saved guard report or API-success assertion is accepted as input. The
    conclusion concerns the value returned by this query invocation, not a
    later re-evaluation of the query and not its effects on output pointers.
    """
    result = {"schema_version": "normal-return-query-call/v1", "status": "unknown", "reason": None,
              "scope": "normal_wrapper_call_return_implies_converted_nested_query_result_matches_guard_constant",
              "query_result_preserved_to_parameter": False, "wrapper_check": None,
              "API_success_verified": False, "enum_equality_established": False,
              "call_normal_return_proved": False, "query_output_effects_verified": False,
              "runtime_linkage_verified": False, "source_program_checked": False, "deployable": False,
              "assumptions": ["faithful valid C++ AST and ordinary sequential execution",
                              "selected wrapper call executes the selected definition",
                              "noreturn declaration contract is respected by the linked implementation",
                              "no nonlocal jumps or asynchronous interference"],
              "limitations": ["does not establish reachability, normal return, API success or output writes",
                              "no inverse interpretation of enum-to-int conversion",
                              "query arguments are recorded, not proven valid or effect-free"]}
    try:
        if (not isinstance(root, dict) or root.get("kind") != "TranslationUnitDecl" or
                not isinstance(call_id, str) or not call_id or type(max_ast_nodes) is not int or
                not 1 <= max_ast_nodes <= 10_000_000):
            raise ValueError("invalid_input_or_budget")
        index = UsingShadowIndex(root, max_ast_nodes)

        def direct_call(node):
            if (node.get("kind") != "CallExpr" or index.unique(node.get("id")) is not node or
                    node.get("valueCategory") != "prvalue" or not node.get("inner")):
                raise ValueError("direct_prvalue_call_required")
            designator = node["inner"][0]
            leaf = designator
            while leaf.get("kind") in {"ParenExpr", "ImplicitCastExpr"}:
                if index.unique(leaf.get("id")) is not leaf or len(leaf.get("inner", [])) != 1:
                    raise ValueError("callee_chain_identity_or_arity")
                leaf = leaf["inner"][0]
            if index.unique(leaf.get("id")) is not leaf:
                raise ValueError("callee_reference_identity")
            declaration = index.unique(leaf.get("referencedDecl", {}).get("id"))
            if declaration.get("kind") != "FunctionDecl" or not _direct_callee(designator, declaration):
                raise ValueError("callee_not_exact_direct_function")
            parameters = [n for n in declaration.get("inner", []) if n.get("kind") == "ParmVarDecl"]
            if len(parameters) != len(node["inner"]) - 1:
                raise ValueError("call_parameter_count_mismatch")
            if any(index.unique(p.get("id")) is not p for p in parameters):
                raise ValueError("parameter_identity_not_unique")
            return declaration, parameters

        call = index.unique(call_id)
        wrapper, parameters = direct_call(call)
        if len(parameters) != 1 or call.get("type") != {"qualType": "void"}:
            raise ValueError("one_argument_void_wrapper_required")
        query = call["inner"][1]
        declaration, query_parameters = direct_call(query)
        parameter = parameters[0]
        if query.get("type") != parameter.get("type"):
            raise ValueError("query_result_parameter_type_mismatch")
        # A direct scalar prvalue argument with exactly the parameter type has
        # no intervening conversion, comma, conditional, constructor or load.
        guard = check(root, wrapper["id"], max_ast_nodes=max_ast_nodes)
        result["wrapper_check"] = guard
        if guard["status"] != "checked" or guard["parameter_id"] != parameter["id"]:
            raise ValueError("wrapper_normal_return_condition_not_established")
        selection = {"call_id": call_id, "wrapper_id": wrapper["id"],
                     "query_call_id": query["id"], "query_declaration_id": declaration["id"]}
        result.update(status="checked", **selection, parameter_id=parameter["id"],
                      query_result_preserved_to_parameter=True,
                      converted_query_result_matches_constant_on_normal_return=True,
                      constant_id=guard["constant_id"], converted_operand_ids=guard["converted_operand_ids"],
                      query_arguments=[{"position": position, "parameter_id": formal["id"],
                                        "expression_id": arg.get("id"), "expression_ast": arg}
                                       for position, (formal, arg) in enumerate(zip(query_parameters, query["inner"][1:]))],
                      input_sha256={"root": guard["input_sha256"]["root"], "selection": _hash(selection),
                                    "identity_policy": _hash(IDENTITY_POLICY)},
                      identity_policy=IDENTITY_POLICY, identity_observations=index.observations)
    except (ValueError, TypeError, KeyError, IndexError, AttributeError, RecursionError) as error:
        result["reason"] = str(error)
    return result
