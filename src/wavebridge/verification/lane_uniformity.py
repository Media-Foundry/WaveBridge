"""Relational dependency check of a bounded scalar source prefix.

Equal inputs to deterministic builtin integer operations give equal outputs;
equal intervals alone do not. API identities are explicitly assumed, never
inferred from names. This does not establish arithmetic definedness, convergence,
or the value/history of a later loop count.
"""
from wavebridge.analysis.initializer_value import link
from wavebridge.verification.getter_returns import _hash


def check_prefix(root, function_id, target_statement_id, declaration_id, api_contract,
                 *, max_ast_nodes=1_000_000):
    """Check one scalar at the first entry to a direct function-body statement.

Only scalar declarations, builtin assignments and structured if/compound
prefixes are interpreted. Both branches are checked; control dependencies are
included even when both branches have the same abstract dependency set.
"""
    report = {"schema_version": "lane-uniform-prefix/v1", "status": "unknown", "reason": None,
        "scope": "selected_scalar_at_first_target_entry_in_fixed_workgroup_yz_varying_x_family",
        "common_value_at_target_checked": False, "api_semantics_verified": False,
        "integer_definedness_checked": False, "target_execution_checked": False,
        "actual_thread_participation_checked": False, "count_common_across_lanes_checked": False,
        "source_program_checked": False, "deployable": False, "getter_checks": [],
        "variable_dependencies": {}, "assumptions": [
            "the complete AST faithfully represents one valid translation unit",
            "compared executions are in the declared lane family and normally reach the target for the first time",
            "prefix integer arithmetic and conversions are defined with the same target implementation semantics",
            "API leaves obey the explicitly bound value, stability and no-memory-write assumptions",
            "scalar kernel arguments start with equal values across the declared lane family",
            "property receivers are initialized/live and the frontend static-member extension semantics hold",
            "ordinary sequential execution, live local objects, no asynchronous interference or external nonlocal transfer"],
        "limitations": ["no numeric interval, overflow, allocation or runtime API validation",
            "no actual lane participation or correspondence of loop iterations",
            "target itself and ordinary suffix statements are not executed by this check",
            "a varying dependency means not established, not a counterexample to equality"]}
    try:
        if (not isinstance(root, dict) or root.get("kind") != "TranslationUnitDecl" or
                any(not isinstance(x, str) or not x for x in (function_id, target_statement_id, declaration_id)) or
                type(max_ast_nodes) is not int or not 1 <= max_ast_nodes <= 10_000_000):
            raise ValueError("invalid_selection_or_budget")
        index, pending, scanned = {}, [root], 0
        while pending:
            node = pending.pop(); scanned += 1
            if scanned > max_ast_nodes or not isinstance(node, dict):
                raise ValueError("ast_budget_or_representation")
            if isinstance(node.get("id"), str):
                index.setdefault(node["id"], []).append(node)
            for key in ("inner", "array_filler"):
                parts = node.get(key, [])
                if not isinstance(parts, list) or any(not isinstance(c, dict) for c in parts):
                    raise ValueError("malformed_semantic_children")
                pending.extend(parts)
        root_hash = _hash(root)
        keys = {"schema_version", "ast_root_sha256", "function_id", "family", "leaves", "evidence_reference",
                "scalar_arguments_common_assumed", "coordinate_calls_stable_and_no_memory_write_assumed",
                "property_receivers_valid_and_static_semantics_assumed", "same_target_integer_semantics_assumed"}
        if (not isinstance(api_contract, dict) or set(api_contract) != keys or
                api_contract["schema_version"] != "lane-family-api-assumptions/v1" or
                api_contract["ast_root_sha256"] != root_hash or api_contract["function_id"] != function_id or
                api_contract["family"] != "same_invocation_same_workgroup_fixed_local_yz_vary_local_x" or
                any(api_contract[k] is not True for k in keys if k.endswith("_assumed")) or
                not isinstance(api_contract["evidence_reference"], str) or not api_contract["evidence_reference"].strip()):
            raise ValueError("api_contract_not_applicable")
        report["input_sha256"] = {"root": root_hash, "function_id": _hash(function_id),
            "target_statement_id": _hash(target_statement_id), "declaration_id": _hash(declaration_id),
            "api_contract": _hash(api_contract), "budget": _hash(max_ast_nodes)}

        def unique(identifier):
            values = index.get(identifier, [])
            if len(values) != 1:
                raise ValueError("identity_not_unique:" + str(identifier))
            return values[0]

        def spelling(node):
            info = node.get("type", {})
            if not isinstance(info, dict) or ("typeAliasDeclId" in info and "desugaredQualType" not in info):
                raise ValueError("unresolved_declaration_type")
            return info.get("desugaredQualType", info.get("qualType"))

        def scalar(node):
            text = spelling(node)
            if text not in {"int", "unsigned int", "unsigned long", "bool",
                            "const int", "const unsigned int", "const unsigned long", "const bool"}:
                raise ValueError("unsupported_scalar_type")
            return text.removeprefix("const ")

        def children(node, kind=None, arity=None, shared=False):
            copies = index.get(node.get("id"), [])
            if ((kind is not None and node.get("kind") != kind) or not copies or
                    (any(n != node for n in copies) if shared else unique(node.get("id")) is not node) or
                    node.get("array_filler", []) != []):
                raise ValueError("unsupported_shape_or_identity")
            parts = node.get("inner", [])
            if arity is not None and len(parts) != arity:
                raise ValueError("unsupported_arity")
            return parts

        def automatic(node):
            if (node.get("storageClass") not in (None, "auto", "register") or
                    any(node.get(k) is not None for k in ("tls", "tlsKind", "thread_local", "threadLocal"))):
                raise ValueError("nonautomatic_storage")

        def reference(node):
            children(node, "DeclRefExpr", 0)
            ref = node.get("referencedDecl", {})
            decl = unique(ref.get("id"))
            if (decl.get("kind") not in {"VarDecl", "ParmVarDecl"} or ref.get("kind") != decl["kind"] or
                    ref.get("type") != decl.get("type") or node.get("type") != decl.get("type") or
                    node.get("valueCategory") != "lvalue"):
                raise ValueError("reference_declaration_mismatch")
            scalar(decl)
            return decl

        leaves, used, origins = {}, set(), {}
        specs = api_contract["leaves"]
        if not isinstance(specs, list) or len(specs) > 16:
            raise ValueError("invalid_api_leaves")
        for spec in specs:
            if (not isinstance(spec, dict) or set(spec) != {"declaration_id", "return_type", "arguments", "semantics"} or
                    not isinstance(spec["arguments"], list) or len(spec["arguments"]) != 1 or
                    type(spec["arguments"][0]) is not int or spec["arguments"][0] not in (0, 1, 2) or
                    spec["semantics"] not in {"workgroup_local_id", "workgroup_id", "workgroup_size"} or
                    spec["return_type"] not in ({"qualType": "unsigned long"}, {"qualType": "unsigned int"})):
                raise ValueError("invalid_api_leaf")
            key = (spec["declaration_id"], spec["arguments"][0])
            if key in leaves:
                raise ValueError("duplicate_api_leaf")
            decl = unique(key[0])
            parts = children(decl, "FunctionDecl")
            params = [n for n in parts if n.get("kind") == "ParmVarDecl"]
            if (decl.get("variadic") or len(params) != 1 or scalar(params[0]) not in {"int", "unsigned int"} or
                    any(n.get("kind") in {"CompoundStmt", "CXXTryStmt", "CoroutineBodyStmt"} for n in parts)):
                raise ValueError("api_leaf_not_supported_external_function")
            leaves[key] = spec

        active_getters = set()

        def getter_value(node, depth=0):
            if depth > 32 or node.get("valueCategory") != "prvalue":
                raise ValueError("getter_depth_or_category")
            ty = scalar(node)
            parts = children(node)
            if node.get("kind") == "ParenExpr" and len(parts) == 1 and scalar(parts[0]) == ty:
                return getter_value(parts[0], depth + 1)
            if (node.get("kind") in {"ImplicitCastExpr", "CStyleCastExpr", "CXXStaticCastExpr"} and
                    node.get("castKind") == "IntegralCast" and len(parts) == 1):
                return getter_value(parts[0], depth + 1)
            if node.get("kind") != "CallExpr" or not parts:
                raise ValueError("getter_not_pure_direct_call_chain")
            decay = parts[0]
            callee, = children(decay, "ImplicitCastExpr", 1)
            children(callee, "DeclRefExpr", 0, shared=True)
            ref = callee.get("referencedDecl", {})
            target = unique(ref.get("id"))
            if (decay.get("castKind") != "FunctionToPointerDecay" or target.get("kind") != "FunctionDecl" or
                    ref.get("kind") != "FunctionDecl" or ref.get("type") != target.get("type")):
                raise ValueError("getter_callee_binding_mismatch")
            if len(parts) == 2:
                arg = parts[1]
                parameter, = [n for n in target.get("inner", []) if n.get("kind") == "ParmVarDecl"]
                if scalar(arg) != scalar(parameter):
                    raise ValueError("api_axis_parameter_type_mismatch")
                # Axes 0/1/2 are preserved by int -> unsigned int on every
                # supported C++ target. No arbitrary runtime cast is evaluated.
                while arg.get("kind") == "ImplicitCastExpr":
                    operand, = children(arg, "ImplicitCastExpr", 1)
                    if (arg.get("castKind") != "IntegralCast" or scalar(arg) != "unsigned int" or
                            scalar(operand) != "int" or arg.get("valueCategory") != "prvalue"):
                        raise ValueError("unsupported_api_axis_conversion")
                    arg = operand
                children(arg, "IntegerLiteral", 0, shared=True)
                if scalar(arg) not in {"int", "unsigned int"} or arg.get("valueCategory") != "prvalue":
                    raise ValueError("api_axis_not_integer_literal")
                key = (target["id"], int(arg["value"]))
                # The typed CallExpr supplies the semantic return type, including
                # desugared size_t. Its callee is bound to the exact declaration;
                # do not classify a typedef by a function-signature substring.
                if key not in leaves or ty != leaves[key]["return_type"]["qualType"]:
                    raise ValueError("api_call_not_bound")
                used.add(key)
                spec = leaves[key]
                token = "api:" + key[0] + ":" + str(key[1])
                origins[token] = {**spec, "varying": spec["semantics"] == "workgroup_local_id" and key[1] == 0}
                return frozenset({token})
            if len(parts) != 1:
                raise ValueError("getter_arguments_unsupported")
            return follow(target["id"], ty, depth + 1)

        def follow(identifier, return_type, depth=0):
            if depth > 32 or identifier in active_getters:
                raise ValueError("getter_cycle_or_depth")
            decl = unique(identifier)
            parts = children(decl)
            if (decl.get("kind") not in {"FunctionDecl", "CXXMethodDecl"} or decl.get("variadic") or
                    (decl.get("kind") == "CXXMethodDecl" and decl.get("storageClass") != "static") or
                    any(n.get("kind") in {"ParmVarDecl", "CXXTryStmt", "CoroutineBodyStmt"} for n in parts)):
                raise ValueError("getter_not_static_zero_argument_definition")
            body, = [n for n in parts if n.get("kind") == "CompoundStmt"]
            statement, = children(body, "CompoundStmt", 1)
            returned, = children(statement, "ReturnStmt", 1)
            if scalar(returned) != return_type:
                raise ValueError("getter_return_type_mismatch")
            active_getters.add(identifier)
            try:
                deps = getter_value(returned, depth + 1)
            finally:
                active_getters.remove(identifier)
            report["getter_checks"].append({"declaration_id": identifier, "return_expression_id": returned["id"],
                                            "dependencies": sorted(deps)})
            return deps

        active_constants = set()

        def value(node, state, depth=0):
            if depth > 48 or node.get("valueCategory") != "prvalue":
                raise ValueError("value_depth_or_category")
            ty, kind = scalar(node), node.get("kind")
            parts = children(node, shared=kind in {"IntegerLiteral", "CXXBoolLiteralExpr"})
            if kind in {"IntegerLiteral", "CXXBoolLiteralExpr"} and not parts:
                if kind == "IntegerLiteral":
                    int(node["value"])
                elif ty != "bool" or type(node.get("value")) is not bool:
                    raise ValueError("invalid_bool_literal")
                return frozenset()
            if kind == "SubstNonTypeTemplateParmExpr" and len(parts) in (1, 2):
                if ((len(parts) == 2 and (parts[0].get("kind") != "NonTypeTemplateParmDecl" or
                                         scalar(parts[0]) != ty or parts[0].get("isParameterPack"))) or
                        parts[-1].get("kind") not in {"IntegerLiteral", "CXXBoolLiteralExpr"} or scalar(parts[-1]) != ty):
                    raise ValueError("unsupported_template_substitution")
                return value(parts[-1], state, depth + 1)
            if kind in {"ParenExpr", "ConstantExpr"} and len(parts) == 1 and scalar(parts[0]) == ty:
                return value(parts[0], state, depth + 1)
            if kind == "ImplicitCastExpr" and len(parts) == 1 and node.get("castKind") == "LValueToRValue":
                decl = reference(parts[0]); identifier = decl["id"]
                if scalar(decl) != ty:
                    raise ValueError("read_type_mismatch")
                if identifier in state:
                    return state[identifier]
                if (decl.get("kind") != "VarDecl" or decl.get("constexpr") is not True or
                        not spelling(decl).startswith("const ") or identifier in active_constants):
                    raise ValueError("read_without_supported_reaching_definition")
                initializer, = children(decl, "VarDecl", 1)
                active_constants.add(identifier)
                try:
                    return value(initializer, {}, depth + 1)
                finally:
                    active_constants.remove(identifier)
            if (kind in {"ImplicitCastExpr", "CStyleCastExpr", "CXXStaticCastExpr"} and len(parts) == 1 and
                    node.get("castKind") in {"IntegralCast", "IntegralToBoolean", "NoOp"}):
                return value(parts[0], state, depth + 1)
            if kind == "UnaryOperator" and len(parts) == 1 and node.get("opcode") in {"+", "-", "~", "!"}:
                return value(parts[0], state, depth + 1)
            if kind == "BinaryOperator" and len(parts) == 2 and node.get("opcode") in {
                    "+", "-", "*", "/", "%", "<<", ">>", "&", "|", "^", "<", "<=", ">", ">=", "==", "!=", "&&", "||"}:
                return value(parts[0], state, depth + 1) | value(parts[1], state, depth + 1)
            if kind == "ConditionalOperator" and len(parts) == 3 and scalar(parts[0]) == "bool":
                return frozenset().union(*(value(c, state, depth + 1) for c in parts))
            if kind in {"PseudoObjectExpr", "CallExpr"}:
                linked = link(root, node)
                if linked["status"] != "recovered":
                    raise ValueError("getter_origin_not_recovered")
                if kind == "PseudoObjectExpr" and linked["receiver_evaluation_observation"].get("memory_effect") != \
                        "no_memory_read_or_write_during_receiver_expression_evaluation":
                    raise ValueError("property_receiver_not_supported")
                return follow(linked["callee_declaration_id"], ty)
            raise ValueError("unsupported_value_expression:" + str(kind))

        def statement(node, state, depth=0):
            if depth > 32:
                raise ValueError("statement_depth_budget")
            kind, parts = node.get("kind"), children(node)
            if kind == "NullStmt" and not parts:
                return set()
            if kind == "CompoundStmt":
                original, written = set(state), set()
                for child in parts:
                    written |= statement(child, state, depth + 1)
                for identifier in set(state) - original:
                    del state[identifier]
                return written & original
            if kind == "DeclStmt" and len(parts) == 1:
                decl, = parts
                initializer, = children(decl, "VarDecl", 1)
                automatic(decl); scalar(decl)
                if decl.get("init") is None or decl["id"] in state:
                    raise ValueError("unsupported_scalar_initialization")
                state[decl["id"]] = value(initializer, state)
                return {decl["id"]}
            if kind in {"BinaryOperator", "CompoundAssignOperator"} and len(parts) == 2 and node.get("opcode") in {"=", "+=", "-=", "*="}:
                decl = reference(parts[0]); identifier = decl["id"]
                if identifier not in state or spelling(decl).startswith("const "):
                    raise ValueError("assignment_without_mutable_reaching_definition")
                state[identifier] = value(parts[1], state) | (state[identifier] if node["opcode"] != "=" else frozenset())
                return {identifier}
            if kind == "IfStmt" and len(parts) in (2, 3) and not any(node.get(k) for k in ("hasInit", "hasVar", "isConstexpr", "isConsteval")):
                if scalar(parts[0]) != "bool":
                    raise ValueError("if_condition_not_bool")
                control = value(parts[0], state)
                left, right = dict(state), dict(state)
                written = statement(parts[1], left, depth + 1)
                if len(parts) == 3:
                    written |= statement(parts[2], right, depth + 1)
                # Include control dependence even if both abstract values are empty.
                for identifier in written & state.keys():
                    state[identifier] = left[identifier] | right[identifier] | control
                return written & state.keys()
            raise ValueError("unsupported_prefix_statement:" + str(kind))

        function = unique(function_id)
        members = children(function, "FunctionDecl")
        body, = [n for n in members if n.get("kind") == "CompoundStmt"]
        statements = children(body, "CompoundStmt")
        target = unique(target_statement_id)
        if target not in statements:
            raise ValueError("target_not_direct_body_statement")
        # A suffix goto could invalidate the first-entry prefix argument. Ordinary
        # suffix loops/writes are outside scope, but nonlocal control is rejected.
        pending = [function]
        while pending:
            node = pending.pop()
            if node.get("kind") in {"GotoStmt", "IndirectGotoStmt", "LabelStmt", "AddrLabelExpr", "LambdaExpr", "BlockExpr",
                                    "CoroutineBodyStmt", "CXXTryStmt", "GCCAsmStmt", "MSAsmStmt", "SEHTryStmt", "StmtExpr"}:
                raise ValueError("unsupported_function_nonlocal_control_or_capture")
            pending.extend(node.get("inner", []) + node.get("array_filler", []))
        state = {}
        for param in members:
            if param.get("kind") == "ParmVarDecl" and spelling(param) in {
                    "int", "unsigned int", "unsigned long", "bool", "const int", "const unsigned int", "const unsigned long", "const bool"}:
                unique(param["id"])
                token = "parameter:" + param["id"]
                origins[token] = {"declaration_id": param["id"], "varying": False, "basis": "external_invocation_argument_semantics"}
                state[param["id"]] = frozenset({token})
        position = statements.index(target)
        for stmt in statements[:position]:
            statement(stmt, state)
        if set(leaves) != used:
            raise ValueError("unused_api_leaf_contract")
        if declaration_id not in state:
            raise ValueError("selected_scalar_not_live_at_target")
        report.update(variable_dependencies={k: sorted(v) for k, v in state.items()}, dependency_origins=origins,
                      function_id=function_id, target_statement_id=target_statement_id,
                      declaration_id=declaration_id, prefix_statement_ids=[n["id"] for n in statements[:position]],
                      selected_dependencies=sorted(state[declaration_id]))
        if any(origins[token]["varying"] for token in state[declaration_id]):
            raise ValueError("selected_value_has_varying_lane_dependency")
        report.update(status="checked", common_value_at_target_checked=True)
    except (ValueError, TypeError, KeyError, IndexError, AttributeError, RecursionError) as error:
        report["reason"] = str(error)
    return report
