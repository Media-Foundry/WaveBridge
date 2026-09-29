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


def check_call_enum_equality(payload, call_id, conversion_contract, *, max_ast_nodes=1_000_000):
    """Relate this query invocation's returned value, never a re-evaluation.

    Both constituent checks are fresh; the external conversion contract remains
    an assumption. A constant named 'success' is not an API specification.
    """
    result = {"schema_version": "normal-return-query-enum-equality/v1", "status": "unknown",
              "reason": None, "call_check": None, "enum_equality_check": None,
              "scope": "normal_wrapper_return_implies_this_query_result_equals_guard_constant_under_contract",
              "conditional_query_enum_equality_under_external_lowering_assumption": False,
              "actual_lowering_verified": False, "conversion_contract_verified": False,
              "call_normal_return_proved": False, "API_success_verified": False,
              "query_output_effects_verified": False, "runtime_linkage_verified": False,
              "source_program_checked": False, "deployable": False,
              "assumptions": [],
              "limitations": ["only the selected invocation's return value, not a subsequent query call",
                              "does not prove API success, output writes, reachability or normal return",
                              "conversion protocol and linked implementation remain external premises"]}
    try:
        if not isinstance(payload, dict):
            raise ValueError("native_payload_required")
        call = check_call(payload.get("ast"), call_id, max_ast_nodes=max_ast_nodes)
        result["call_check"] = call
        if call["status"] != "checked" or call["query_result_preserved_to_parameter"] is not True:
            raise ValueError("fresh_query_call_not_checked")
        equality = check_enum_equality(payload, call["wrapper_id"], conversion_contract,
                                       max_ast_nodes=max_ast_nodes)
        result["enum_equality_check"] = equality
        if (equality["status"] != "checked" or
                equality["conditional_enum_equality_under_external_lowering_assumption"] is not True):
            raise ValueError("fresh_enum_equality_not_checked")
        binding = equality["enum_binding_check"]
        if (binding["guard_check"]["input_sha256"]["root"] != call["input_sha256"]["root"] or
                any(binding[key] != call[key] for key in
                    ("parameter_id", "constant_id", "converted_operand_ids"))):
            raise ValueError("call_enum_binding_mismatch")
        selection = {key: call[key] for key in
                     ("call_id", "wrapper_id", "query_call_id", "query_declaration_id")}
        result.update(status="checked", **selection,
                      conditional_query_enum_equality_under_external_lowering_assumption=True,
                      parameter_id=call["parameter_id"], constant_id=call["constant_id"],
                      assumptions=list(dict.fromkeys(call["assumptions"] + equality["assumptions"])),
                      input_sha256={**equality["input_sha256"], "selection": _hash(selection)})
    except (ValueError, TypeError, KeyError, IndexError, AttributeError, RecursionError) as error:
        result["reason"] = str(error)
    return result


def check_enum_binding(payload, function_id, *, max_ast_nodes=1_000_000):
    """Bind compiler enum observations to a freshly checked guard.

    This is a declaration/observation correspondence, not an inverse conversion
    theorem. In particular, enumerator values are not a runtime value domain.
    """
    result = {"schema_version": "normal-return-enum-binding/v1", "status": "unknown",
              "reason": None, "guard_check": None,
              "scope": "guard_parameter_and_constant_share_observed_enum_declaration",
              "enum_equality_established": False, "API_success_verified": False,
              "source_program_checked": False, "deployable": False,
              "assumptions": ["native metadata and embedded AST faithfully originate from the same compiler invocation"],
              "limitations": ["no runtime value domain or inverse integral conversion proof",
                              "compiler observations are trusted, not independently proved"]}
    try:
        if not isinstance(payload, dict) or payload.get("schema_version") != "clang-native-captures/v1":
            raise ValueError("native_envelope_required")
        root = payload.get("ast")
        guard = check(root, function_id, max_ast_nodes=max_ast_nodes)
        result["guard_check"] = guard
        if guard["status"] != "checked":
            raise ValueError("fresh_guard_not_checked")
        result["assumptions"].extend(guard["assumptions"])
        index = UsingShadowIndex(root, max_ast_nodes)
        parameter = index.unique(guard["parameter_id"])
        alias = index.unique(parameter["type"].get("typeAliasDeclId"))
        if alias.get("kind") not in {"TypedefDecl", "TypeAliasDecl"}:
            raise ValueError("direct_enum_alias_required")
        types = alias.get("inner", [])
        # Clang wraps typedef enum declarations in ElaboratedType. Do not
        # unwrap arbitrary aliases, qualifiers, pointers or references.
        if len(types) == 1 and types[0].get("kind") == "ElaboratedType":
            types = types[0].get("inner", [])
        if len(types) != 1 or types[0].get("kind") != "EnumType":
            raise ValueError("direct_enum_type_required")
        enum_ref = types[0].get("decl", {})
        enum = index.unique(enum_ref.get("id"))
        if enum_ref.get("kind") != "EnumDecl" or enum.get("kind") != "EnumDecl":
            raise ValueError("enum_declaration_required")
        constants = [n for n in enum.get("inner", []) if n.get("kind") == "EnumConstantDecl"]
        ids = [n.get("id") for n in constants]
        if guard["constant_id"] not in ids or any(index.unique(n.get("id")) is not n for n in constants):
            raise ValueError("guard_constant_not_in_parameter_enum")
        records = payload.get("enum_types")
        if not isinstance(records, list) or any(not isinstance(r, dict) for r in records):
            raise ValueError("enum_observations_required")
        matches = [r for r in records if r.get("enum_declaration_id") == enum["id"]]
        if len(matches) != 1:
            raise ValueError("enum_observation_not_unique")
        record = matches[0]
        bits = payload.get("ast_int_bits")
        if (type(bits) is not int or not 1 <= bits <= 1024 or
                record.get("is_scoped") is not False or type(record.get("is_fixed")) is not bool or
                record.get("underlying_type") not in {"int", "unsigned int"} or
                type(record.get("underlying_bits")) is not int or record["underlying_bits"] != bits or
                record.get("underlying_signed") is not (record["underlying_type"] == "int") or
                record.get("promotion_type") != "int" or record.get("promotion_signed") is not True or
                type(record.get("promotion_bits")) is not int or record["promotion_bits"] != bits):
            raise ValueError("supported_int_promotion_observation_required")
        values = record.get("enumerators")
        if (not isinstance(values, list) or any(not isinstance(v, dict) for v in values) or
                [v.get("declaration_id") for v in values] != ids):
            raise ValueError("enumerator_identity_list_mismatch")
        for value in values:
            spelling = value.get("value_decimal")
            if (not isinstance(spelling, str) or len(spelling) > 400 or
                    str(int(spelling)) != spelling):
                raise ValueError("canonical_decimal_constant_required")
        selected = values[ids.index(guard["constant_id"])]
        result.update(status="checked", function_id=function_id, parameter_id=parameter["id"],
                      alias_id=alias["id"], enum_declaration_id=enum["id"],
                      constant_id=guard["constant_id"], constant_value_decimal=selected["value_decimal"],
                      converted_operand_ids=guard["converted_operand_ids"], enum_observation=record,
                      input_sha256={"payload": _hash(payload), "selection": _hash(function_id)})
    except (ValueError, TypeError, KeyError, IndexError, AttributeError, RecursionError) as error:
        result["reason"] = str(error)
    return result


def check_enum_equality(payload, function_id, conversion_contract, *, max_ast_nodes=1_000_000):
    """Conditional inverse of the guard casts under an explicit lowering contract.

    No compiler-name heuristic or named-constant range discharges this contract.
    It is deliberately distinct from check_enum_binding's compiler observations.
    """
    from wavebridge.verification.integer_conversion import check_bitpattern_equality

    result = {"schema_version": "normal-return-enum-equality/v1", "status": "unknown",
              "reason": None, "enum_binding_check": None, "conversion_check": None,
              "scope": "normal_return_implies_parameter_equals_constant_under_explicit_bitpattern_contract",
              "conditional_enum_equality_under_external_lowering_assumption": False,
              "conversion_contract_verified": False, "actual_lowering_verified": False,
              "API_success_verified": False, "source_program_checked": False, "deployable": False,
              "assumptions": [],
              "limitations": ["lowering contract is an external assumption, not verified compiler or machine code",
                              "no API success, output effect, reachability or normal-return proof"]}
    try:
        binding = check_enum_binding(payload, function_id, max_ast_nodes=max_ast_nodes)
        result["enum_binding_check"] = binding
        if binding["status"] != "checked":
            raise ValueError("fresh_enum_binding_not_checked")
        bits = binding["enum_observation"]["underlying_bits"]
        required = {
            "schema_version": "enum-bitpattern-contract/v1",
            "payload_sha256": binding["input_sha256"]["payload"],
            "function_id": function_id,
            "parameter_id": binding["parameter_id"],
            "constant_id": binding["constant_id"],
            "enum_declaration_id": binding["enum_declaration_id"],
            "converted_operand_ids": binding["converted_operand_ids"],
            "bits": bits,
            "semantics": "both_casts_preserve_all_bits_of_determinate_full_underlying_representation",
            "equality": "enum_and_int_equality_compare_all_representation_bits",
            "representation": "padding_free_trap_free_unique_bitvectors_twos_complement_signed_decode",
        }
        if (not isinstance(conversion_contract, dict) or
                type(conversion_contract.get("bits")) is not int or conversion_contract != required):
            raise ValueError("exact_external_conversion_contract_required")
        conversion = check_bitpattern_equality(bits)
        result["conversion_check"] = conversion
        if conversion["status"] != "checked":
            raise ValueError("bitpattern_equality_not_checked")
        result.update(status="checked", conditional_enum_equality_under_external_lowering_assumption=True,
                      function_id=function_id, parameter_id=binding["parameter_id"],
                      constant_id=binding["constant_id"],
                      equality_condition="only_if_the_explicit_conversion_contract_holds",
                      external_conversion_contract=dict(conversion_contract),
                      assumptions=binding["assumptions"] + conversion["assumptions"],
                      input_sha256={**binding["input_sha256"],
                                    "conversion_contract": _hash(conversion_contract),
                                    "identity_policy": _hash(IDENTITY_POLICY)})
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
