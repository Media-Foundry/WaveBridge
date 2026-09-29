"""Check an integer field snapshot/counter/return suffix, not device API semantics."""
from wavebridge.verification.getter_returns import _hash

FIELD_READ_PREMISE = "selected field is valid to read"


def check(root, function_id, *, max_ast_nodes=1_000_000):
    result = {"schema_version": "field-snapshot-return/v1", "status": "unknown", "reason": None,
              "scope": "returned_integer_equals_field_value_read_at_selected_suffix_assignment",
              "prefix_effects_checked": False, "field_value_initialized": False,
              "field_numeric_domain": None, "API_success_verified": False,
              "function_reachability_proved": False, "source_program_checked": False, "deployable": False,
              "obligations": {"field_read_validity": FIELD_READ_PREMISE,
                              "counter_increment_defined": "counter increment has defined behavior"},
              "assumptions": ["faithful valid C++ AST and ordinary sequential execution",
                  "execution reaches the selected suffix and returns normally",
                  FIELD_READ_PREMISE, "counter increment has defined behavior",
                  "distinct selected global declarations denote distinct storage",
                  "no asynchronous interference, nonlocal jumps or lifetime replacement"],
              "limitations": ["not a proof of API success, initialized properties, device selection or field range",
                  "prefix calls, runtime linkage and whole-function safety are not checked"]}
    try:
        if (not isinstance(root, dict) or root.get("kind") != "TranslationUnitDecl" or
                not isinstance(function_id, str) or not function_id or type(max_ast_nodes) is not int or
                not 1 <= max_ast_nodes <= 10_000_000):
            raise ValueError("invalid_selection_or_budget")
        pending, index, parents, count = [(root, None)], {}, {}, 0
        while pending:
            node, parent = pending.pop(); count += 1
            if count > max_ast_nodes: raise ValueError("ast_node_budget_exceeded")
            if not isinstance(node, dict) or not isinstance(node.get("inner", []), list):
                raise ValueError("malformed_ast")
            index.setdefault(node.get("id"), []).append(node)
            parents[id(node)] = parent
            pending.extend((c, node) for c in node.get("inner", []))

        def unique(identifier):
            values = index.get(identifier, [])
            if not isinstance(identifier, str) or len(values) != 1:
                raise ValueError("identity_not_unique")
            return values[0]

        def children(node, kind, size=None):
            if node.get("kind") != kind or unique(node.get("id")) is not node:
                raise ValueError("shape_or_identity_unsupported")
            values = node.get("inner", [])
            if size is not None and len(values) != size: raise ValueError("arity_unsupported")
            return values

        def typed(node, category):
            if node.get("type") != {"qualType": "int"} or node.get("valueCategory") != category:
                raise ValueError("plain_int_type_required")

        function = unique(function_id)
        members = children(function, "FunctionDecl")
        bodies = [n for n in members if n.get("kind") == "CompoundStmt"]
        if (function.get("type") != {"qualType": "int ()"} or len(bodies) != 1 or
                any(n.get("kind") == "ParmVarDecl" for n in members)):
            raise ValueError("plain_zero_argument_function_required")
        body = bodies[0]
        statements = children(body, "CompoundStmt")
        if len(statements) < 4: raise ValueError("snapshot_suffix_missing")
        assignment, increment, returned = statements[-3:]
        lhs, rhs = children(assignment, "BinaryOperator", 2); typed(assignment, "lvalue")
        if assignment.get("opcode") != "=": raise ValueError("snapshot_not_assignment")

        def global_storage(node):
            children(node, "DeclRefExpr", 0); typed(node, "lvalue")
            reference = node.get("referencedDecl", {})
            declaration = unique(reference.get("id"))
            if (declaration.get("kind") != "VarDecl" or reference.get("kind") != "VarDecl" or
                    declaration.get("type") != {"qualType": "int"} or reference.get("type") != declaration["type"] or
                    parents[id(declaration)].get("kind") not in {"TranslationUnitDecl", "NamespaceDecl"} or
                    declaration.get("init") is None or
                    any(declaration.get(k) is not None for k in ("tls", "tlsKind", "thread_local", "threadLocal")) or
                    any(n.get("kind", "").endswith("Attr") for n in declaration.get("inner", []))):
                raise ValueError("plain_defined_global_int_required")
            return declaration

        snapshot = global_storage(lhs)
        member, = children(rhs, "ImplicitCastExpr", 1); typed(rhs, "prvalue")
        if rhs.get("castKind") != "LValueToRValue": raise ValueError("field_conversion_unsupported")
        base, = children(member, "MemberExpr", 1); typed(member, "lvalue")
        if member.get("isArrow") is not False: raise ValueError("direct_object_field_required")
        field = unique(member.get("referencedMemberDecl"))
        if field.get("kind") != "FieldDecl" or field.get("type") != {"qualType": "int"} or field.get("isBitfield"):
            raise ValueError("plain_int_field_required")
        children(base, "DeclRefExpr", 0)
        reference = base.get("referencedDecl", {})
        obj = unique(reference.get("id"))
        declaration_statement = parents[id(obj)]
        if (obj.get("kind") != "VarDecl" or reference.get("kind") != "VarDecl" or
                base.get("type") != obj.get("type") or reference.get("type") != obj.get("type") or
                base.get("valueCategory") != "lvalue" or obj.get("init") is None or
                obj.get("storageClass") not in (None, "auto", "register") or
                any(obj.get(k) is not None for k in ("tls", "tlsKind", "thread_local", "threadLocal")) or
                declaration_statement.get("kind") != "DeclStmt" or parents[id(declaration_statement)] is not body or
                statements.index(declaration_statement) >= len(statements) - 3):
            raise ValueError("field_base_not_prior_automatic_object")
        counter_ref, = children(increment, "UnaryOperator", 1)
        if increment.get("opcode") != "++" or type(increment.get("isPostfix")) is not bool:
            raise ValueError("counter_increment_unsupported")
        typed(increment, "prvalue" if increment["isPostfix"] else "lvalue")
        counter = global_storage(counter_ref)
        if counter["id"] == snapshot["id"]: raise ValueError("counter_overwrites_snapshot")
        read, = children(returned, "ReturnStmt", 1)
        ref, = children(read, "ImplicitCastExpr", 1); typed(read, "prvalue")
        if read.get("castKind") != "LValueToRValue" or global_storage(ref)["id"] != snapshot["id"]:
            raise ValueError("return_not_same_snapshot")
        result.update(status="checked", function_id=function_id,
                      snapshot_assignment_id=assignment["id"], field_read_id=rhs["id"],
                      object_declaration_id=obj["id"], field_declaration_id=field["id"],
                      snapshot_declaration_id=snapshot["id"], counter_declaration_id=counter["id"],
                      unchecked_prefix_statement_ids=[n.get("id") for n in statements[:-3]],
                      input_sha256={"root": _hash(root), "function": _hash(function_id)})
    except (ValueError, TypeError, KeyError, IndexError, AttributeError, RecursionError) as error:
        result["reason"] = str(error)
    return result


def check_query_power_minimum(payload, initializer_id, assignment_id, power_selection,
                              conversion_contract, output_contract, *, int_bits=32,
                              max_ast_nodes=1_000_000):
    """Freshly bind both minimum operands; the query value remains symbolic.

    power_selection contains identities, never a numeric domain or prior report.
    The relation concerns the first assignment in the selected guarded invocation.
    """
    from wavebridge.verification.integer_selection import check_local_minimum_update
    from wavebridge.verification.power_ceiling import check_guarded_shift

    result = {"schema_version": "query-power-minimum/v1", "status": "unknown", "reason": None,
              "scope": "first_minimum_assignment_for_selected_normally_reached_guarded_invocation",
              "checks": {}, "conditional_assignment_relation": False, "state_relation": None,
              "query_numeric_domain": None, "result_numeric_domain": None,
              "API_protocol_verified": False, "actual_lowering_verified": False,
              "later_history_checked": False, "call_reachability_proved": False,
              "source_program_checked": False, "deployable": False, "assumptions": [],
              "limitations": ["query output and conversion protocols remain external assumptions",
                              "not an API width, nonzero divisor, launch value or device guarantee",
                              "relation is conditional on this selected caller, not all callee invocations"]}
    keys = {"caller_id", "local_id", "guard_id", "call_id", "callee_id",
            "argument_position", "exponent_id", "power_id"}
    if (not isinstance(payload, dict) or not isinstance(power_selection, dict) or
            set(power_selection) != keys or type(int_bits) is not int or not 2 <= int_bits <= 64 or
            payload.get("ast_int_bits") != int_bits or
            any(not isinstance(power_selection[k], str) or not power_selection[k]
                for k in keys - {"argument_position"}) or
            type(power_selection["argument_position"]) is not int or power_selection["argument_position"] < 0):
        result["reason"] = "invalid_selection_or_integer_ABI_binding"
        return result
    query = check_query_initializer_to_statement(payload, initializer_id, assignment_id,
                conversion_contract, output_contract, max_ast_nodes=max_ast_nodes)
    result["checks"]["query"] = query
    result["assumptions"] = list(query["assumptions"])
    if query["status"] != "checked" or query.get("value_preserved_to_target_entry") is not True:
        result["reason"] = "fresh_query_history_not_checked"
        return result
    root = payload["ast"]
    minimum = check_local_minimum_update(root, assignment_id,
                {"int": {"bits": int_bits, "signed": True}}, max_ast_nodes=max_ast_nodes)
    result["checks"]["minimum"] = minimum
    result["assumptions"] = list(dict.fromkeys(result["assumptions"] + minimum["assumptions"]))
    if minimum["status"] != "checked":
        result["reason"] = "fresh_minimum_not_checked"
        return result
    if (minimum["target_declaration_id"] != initializer_id or
            set(minimum["operand_declaration_ids"]) != {initializer_id, power_selection["power_id"]} or
            minimum["function_id"] != query["initializer_check"]["owner_id"] or
            minimum["function_id"] != power_selection["callee_id"]):
        result["reason"] = "minimum_operand_or_invocation_binding_mismatch"
        return result
    power = check_guarded_shift(root, **power_selection, int_bits=int_bits,
                max_ast_nodes=max_ast_nodes, target_statement_id=assignment_id)
    result["checks"]["power"] = power
    result["assumptions"] = list(dict.fromkeys(result["assumptions"] + power["assumptions"]))
    if power["status"] != "checked" or power.get("value_preserved_to_target_entry") is not True:
        result["reason"] = "fresh_power_history_not_checked"
        return result
    roots = [item["input_sha256"]["root"] for item in (minimum, power)]
    roots.append(query["initializer_check"]["getter_output_check"]["object_check"]["input_sha256"]["root"])
    if len(set(roots)) != 1:
        result["reason"] = "root_binding_mismatch"
        return result
    result.update(status="checked", conditional_assignment_relation=True,
                  state_relation={"target_declaration_id": initializer_id, "operation": "minimum",
                      "query_operand_origin": query["value_origin"],
                      "power_operand": {"declaration_id": power_selection["power_id"],
                                        "value_set": power["result_values"]},
                      "time": "immediately_after_first_selected_assignment"},
                  input_sha256={"root": roots[0], "payload": _hash(payload),
                      "selection": _hash([initializer_id, assignment_id, power_selection, int_bits]),
                      "conversion_contract": _hash(conversion_contract),
                      "output_contract": _hash(output_contract)})
    return result


def check_query_object(root, function_id, *, max_ast_nodes=1_000_000):
    """Bind an adjacent guarded query's address argument to the snapshot object.

    This proves an address/field-base correspondence in the supported syntax,
    not that the query treats the pointer as an output or writes that field.
    """
    from wavebridge.verification.normal_return_guard import check_call
    from wavebridge.verification.using_shadow_identity import UsingShadowIndex, IDENTITY_POLICY

    result = {"schema_version": "query-snapshot-object/v1", "status": "unknown", "reason": None,
              "scope": "adjacent_guarded_query_address_argument_and_snapshot_field_base_share_declaration",
              "snapshot_check": None, "query_result_check": None,
              "query_argument_direction": "unverified", "query_output_effects_verified": False,
              "field_value_initialized": False, "field_numeric_domain": None,
              "API_success_verified": False, "call_normal_return_proved": False,
              "dynamic_lifetime_verified": False, "source_program_checked": False, "deployable": False,
              "assumptions": [],
              "limitations": ["address correspondence does not establish an output-pointer API contract",
                              "no proof that query initializes or writes the selected field",
                              "not a whole-function reachability or lifetime proof"]}
    try:
        snapshot = check(root, function_id, max_ast_nodes=max_ast_nodes)
        result["snapshot_check"] = snapshot
        if snapshot["status"] != "checked":
            raise ValueError("snapshot_relation_not_established")
        # The snapshot checker establishes the final three top-level statements.
        # Only the immediately preceding statement can be the selected guard.
        prefixes = snapshot["unchecked_prefix_statement_ids"]
        if not prefixes:
            raise ValueError("adjacent_query_statement_missing")
        query = check_call(root, prefixes[-1], max_ast_nodes=max_ast_nodes)
        result["query_result_check"] = query
        if query["status"] != "checked":
            raise ValueError("adjacent_guarded_query_not_established")
        if snapshot["input_sha256"]["root"] != query["input_sha256"]["root"]:
            raise ValueError("fresh_root_binding_mismatch")
        index = UsingShadowIndex(root, max_ast_nodes)
        obj = index.unique(snapshot["object_declaration_id"])
        candidates = []
        for argument in query["query_arguments"]:
            address = index.unique(argument["expression_id"])
            if (address.get("kind") != "UnaryOperator" or address.get("opcode") != "&" or
                    address.get("valueCategory") != "prvalue" or len(address.get("inner", [])) != 1):
                continue
            ref = address["inner"][0]
            if (ref.get("kind") != "DeclRefExpr" or ref.get("inner") or
                    ref.get("valueCategory") != "lvalue" or index.unique(ref.get("id")) is not ref):
                continue
            binding = ref.get("referencedDecl", {})
            if (binding.get("kind") != "VarDecl" or binding.get("id") != obj["id"] or
                    binding.get("type") != obj.get("type") or ref.get("type") != obj.get("type")):
                continue
            # Builtin '&' of this exact object, with no argument conversion.
            if address.get("type") != {"qualType": obj["type"]["qualType"] + " *"}:
                raise ValueError("address_pointer_type_unsupported")
            candidates.append(argument)
        if len(candidates) != 1:
            raise ValueError("unique_direct_object_address_argument_required")
        argument = candidates[0]
        selection = {"function_id": function_id, "wrapper_call_id": query["call_id"],
                     "query_call_id": query["query_call_id"], "argument_position": argument["position"],
                     "object_declaration_id": obj["id"], "field_declaration_id": snapshot["field_declaration_id"]}
        result.update(status="checked", **selection, argument_expression_id=argument["expression_id"],
                      query_parameter_id=argument["parameter_id"],
                      query_declaration_id=query["query_declaration_id"],
                      snapshot_assignment_id=snapshot["snapshot_assignment_id"],
                      field_read_id=snapshot["field_read_id"],
                      same_object_declaration=True, adjacent_top_level_statements=True,
                      assumptions=list(dict.fromkeys(snapshot["assumptions"] + query["assumptions"])),
                      input_sha256={"root": snapshot["input_sha256"]["root"],
                                    "selection": _hash(selection), "identity_policy": _hash(IDENTITY_POLICY)},
                      identity_policy=IDENTITY_POLICY, identity_observations=index.observations)
    except (ValueError, TypeError, KeyError, IndexError, AttributeError, RecursionError) as error:
        result["reason"] = str(error)
    return result


def check_query_output(payload, function_id, conversion_contract, output_contract, *, max_ast_nodes=1_000_000):
    """Conditional output-to-getter relation, not a verified API implementation."""
    from wavebridge.verification.normal_return_guard import check_call_enum_equality

    result = {"schema_version": "query-output-snapshot/v1", "status": "unknown", "reason": None,
              "object_check": None, "query_equality_check": None,
              "scope": "getter_return_equals_selected_query_poststate_field_under_external_contracts",
              "conditional_output_to_return_relation": False,
              "API_output_contract_verified": False, "query_output_effects_verified": False,
              "actual_lowering_verified": False, "dynamic_lifetime_verified": False,
              "runtime_linkage_verified": False, "external_API_protocol_assumed": False,
              "function_reachability_proved": False, "call_normal_return_proved": False,
              "field_numeric_domain": None, "source_program_checked": False, "deployable": False,
              "assumptions": [], "discharged_child_assumptions": [],
              "limitations": ["output and conversion protocols are external assumptions, not implementation proofs",
                              "no device identity, wave width, numeric domain or whole-program guarantee"]}
    try:
        if not isinstance(payload, dict):
            raise ValueError("native_payload_required")
        objects = check_query_object(payload.get("ast"), function_id, max_ast_nodes=max_ast_nodes)
        result["object_check"] = objects
        if objects["status"] != "checked":
            raise ValueError("fresh_query_object_not_checked")
        equality = check_call_enum_equality(payload, objects["wrapper_call_id"], conversion_contract,
                                            max_ast_nodes=max_ast_nodes)
        result["query_equality_check"] = equality
        if equality["status"] != "checked":
            raise ValueError("fresh_query_equality_not_checked")
        if (equality["call_check"]["input_sha256"]["root"] != objects["input_sha256"]["root"] or
                any(equality[key] != objects[key] for key in ("query_call_id", "query_declaration_id"))):
            raise ValueError("query_output_identity_mismatch")
        original_call = objects["query_result_check"]
        current_call = equality["call_check"]
        if any(original_call[key] != current_call[key] for key in
               ("call_id", "wrapper_id", "parameter_id", "constant_id", "converted_operand_ids", "query_arguments")):
            raise ValueError("fresh_query_argument_or_guard_mismatch")
        selection = {key: objects[key] for key in
                     ("function_id", "wrapper_call_id", "query_call_id", "query_declaration_id",
                      "query_parameter_id", "argument_position", "argument_expression_id",
                      "object_declaration_id", "field_declaration_id", "field_read_id")}
        required = {"schema_version": "query-field-output-contract/v1", **selection,
                    "payload_sha256": equality["input_sha256"]["payload"],
                    "status_constant_id": equality["constant_id"],
                    "arguments": [{key: arg[key] for key in ("position", "parameter_id", "expression_id")}
                                  for arg in current_call["query_arguments"]],
                    "effect": "on_equal_status_selected_field_holds_API_initialized_determinate_plain_int_in_completed_query_poststate",
                    "validity": "all_argument_evaluations_and_API_preconditions_hold_including_aliasing_layout_alignment_and_live_readable_writable_object_field",
                    "preservation": "query_poststate_field_and_lifetime_remain_unchanged_through_selected_read_including_callbacks_and_retained_aliases",
                    "linkage": "selected_query_declaration_invokes_implementation_obeying_this_contract"}
        if (not isinstance(output_contract, dict) or
                type(output_contract.get("argument_position")) is not int or
                not isinstance(output_contract.get("arguments"), list) or
                any(not isinstance(arg, dict) or type(arg.get("position")) is not int
                    for arg in output_contract["arguments"]) or output_contract != required):
            raise ValueError("exact_external_output_contract_required")
        premise = objects["snapshot_check"]["obligations"].get("field_read_validity")
        if premise != FIELD_READ_PREMISE or premise not in objects["assumptions"]:
            raise ValueError("snapshot_read_premise_not_identified")
        assumptions = [a for a in objects["assumptions"] if a != premise]
        assumptions += equality["assumptions"] + [required[k] for k in ("effect", "validity", "preservation", "linkage")]
        result.update(status="checked", **selection, conditional_output_to_return_relation=True,
                      external_API_protocol_assumed=True,
                      control_flow_bridge="ordinary_sequential_execution_reaching_direct_suffix_follows_normal_completion_of_adjacent_wrapper",
                      external_output_contract=dict(output_contract),
                      returned_value_origin={"query_call_id": objects["query_call_id"],
                                             "object_declaration_id": objects["object_declaration_id"],
                                             "field_declaration_id": objects["field_declaration_id"],
                                             "time": "selected_query_normal_return"},
                      assumptions=list(dict.fromkeys(assumptions)),
                      discharged_child_assumptions=[{"obligation_id": "field_read_validity", "premise": premise,
                          "by": "conditionally_supplied_by_external_API_poststate_lifetime_and_preservation_protocol"}],
                      input_sha256={**equality["input_sha256"], "selection": _hash(selection),
                                    "output_contract": _hash(output_contract)})
    except (ValueError, TypeError, KeyError, IndexError, AttributeError, RecursionError) as error:
        result["reason"] = str(error)
    return result


def check_query_initializer(payload, initializer_id, conversion_contract, output_contract, *, max_ast_nodes=1_000_000):
    """Bind one automatic int initialization to this getter invocation's field.

    The conclusion ends at initialization. No purity, later value preservation,
    numeric interval, or relation between distinct getter invocations is inferred.
    """
    from wavebridge.verification.using_shadow_identity import UsingShadowIndex, IDENTITY_POLICY
    from wavebridge.verification.launch_binding import _direct_callee

    result = {"schema_version": "query-output-initializer/v1", "status": "unknown", "reason": None,
              "scope": "automatic_int_initial_value_equals_this_getter_invocation_query_poststate_under_contracts",
              "getter_output_check": None, "conditional_initial_value_relation": False,
              "history_preserved_to_use": False, "runtime_implementation_linkage_verified": False,
              "initializer_reached_or_completed": False, "getter_purity_verified": False,
              "runtime_return_interval": None, "source_program_checked": False, "deployable": False,
              "assumptions": [],
              "limitations": ["only the completed initialization, not any subsequent use or minimum update",
                              "distinct calls may return different values and may have side effects"]}
    try:
        if (not isinstance(payload, dict) or not isinstance(initializer_id, str) or not initializer_id or
                type(max_ast_nodes) is not int or not 1 <= max_ast_nodes <= 10_000_000):
            raise ValueError("invalid_input_or_budget")
        root = payload.get("ast")
        if not isinstance(root, dict) or root.get("kind") != "TranslationUnitDecl":
            raise ValueError("translation_unit_required")
        index = UsingShadowIndex(root, max_ast_nodes)
        variable = index.unique(initializer_id)
        locations, pending = {}, [(root, None, None)]
        while pending:
            node, parent, owner = pending.pop()
            locations[id(node)] = (parent, owner)
            if node.get("kind") in {"FunctionDecl", "CXXMethodDecl", "CXXConstructorDecl",
                                    "CXXDestructorDecl", "LambdaExpr"}:
                owner = node
            pending.extend((n, node, owner) for n in node.get("inner", []))
        statement, owner = locations[id(variable)]
        block = locations[id(statement)][0] if statement else None
        if (variable.get("kind") != "VarDecl" or variable.get("type") != {"qualType": "int"} or
                variable.get("init") != "c" or variable.get("storageClass") not in (None, "auto", "register") or
                any(variable.get(k) is not None for k in ("tls", "tlsKind", "thread_local", "threadLocal")) or
                len(variable.get("inner", [])) != 1 or not statement or statement.get("kind") != "DeclStmt" or
                statement.get("inner") != [variable] or
                not block or block.get("kind") != "CompoundStmt" or not owner or owner.get("kind") != "FunctionDecl"):
            raise ValueError("direct_automatic_plain_int_initializer_required")
        lexical_path, context = [], block
        while context is not owner:
            if (context is None or context.get("kind") not in {"CompoundStmt", "IfStmt"} or
                    index.unique(context.get("id")) is not context):
                raise ValueError("initializer_lexical_context_unsupported")
            lexical_path.append({"id": context["id"], "kind": context["kind"]})
            context = locations[id(context)][0]
        if not lexical_path or lexical_path[-1]["kind"] != "CompoundStmt":
            raise ValueError("function_body_context_required")
        for node in (statement, block, owner):
            if index.unique(node.get("id")) is not node:
                raise ValueError("initializer_context_not_unique")
        call = variable["inner"][0]
        if (call.get("kind") != "CallExpr" or index.unique(call.get("id")) is not call or
                call.get("type") != {"qualType": "int"} or call.get("valueCategory") != "prvalue" or
                len(call.get("inner", [])) != 1):
            raise ValueError("direct_zero_argument_int_call_required")
        callee = call["inner"][0]
        if (callee.get("kind") != "ImplicitCastExpr" or callee.get("castKind") != "FunctionToPointerDecay" or
                index.unique(callee.get("id")) is not callee or
                callee.get("valueCategory") != "prvalue" or len(callee.get("inner", [])) != 1):
            raise ValueError("direct_function_decay_required")
        leaf = callee["inner"][0]
        getter = index.unique(leaf.get("referencedDecl", {}).get("id"))
        # A template may reuse the same DeclRefExpr ID in an instantiation.
        # Select this occurrence via the unique call's child path, not leaf ID.
        if (leaf.get("valueCategory") != "lvalue" or getter.get("kind") != "FunctionDecl" or
                getter.get("type") != {"qualType": "int ()"} or not _direct_callee(callee, getter)):
            raise ValueError("getter_definition_binding_required")
        occurrences = index.nodes.get(leaf.get("id"), [])
        keys = ("kind", "type", "valueCategory", "referencedDecl")
        if not occurrences or any(node.get("inner") or any(node.get(k) != leaf.get(k) for k in keys)
                                  for node, _ in occurrences):
            raise ValueError("shared_callee_reference_conflict")
        output = check_query_output(payload, getter["id"], conversion_contract, output_contract,
                                    max_ast_nodes=max_ast_nodes)
        result["getter_output_check"] = output
        if output["status"] != "checked" or output["function_id"] != getter["id"]:
            raise ValueError("fresh_getter_output_not_checked")
        selection = {"initializer_id": initializer_id, "getter_call_id": call["id"],
                     "getter_definition_id": getter["id"], "owner_id": owner["id"],
                     "declaration_statement_id": statement["id"]}
        result.update(status="checked", **selection, conditional_initial_value_relation=True,
                      initial_value_origin={**output["returned_value_origin"], "getter_call_id": call["id"],
                                            "invocation": "the_same_dynamic_invocation_used_by_this_initializer"},
                      assumptions=output["assumptions"] + ["selected initializer completes normally with a live local object",
                          "selected getter call executes the checked getter definition"],
                      input_sha256={**output["input_sha256"], "selection": _hash(selection),
                                    "identity_policy": _hash(IDENTITY_POLICY)},
                      callee_occurrence_policy="unique_call_direct_child_path_with_consistent_shared_leaf_references",
                      lexical_context_path=lexical_path, branch_reachability_proved=False,
                      callee_reference_occurrences=len(occurrences))
    except (ValueError, TypeError, KeyError, IndexError, AttributeError, RecursionError) as error:
        result["reason"] = str(error)
    return result


def check_query_initializer_to_statement(payload, initializer_id, statement_id, conversion_contract,
                                         output_contract, *, max_ast_nodes=1_000_000):
    """Carry a fresh symbolic query-origin value to the first target entry."""
    from wavebridge.verification.integer_selection import _preserve_to_statement

    initialized = check_query_initializer(payload, initializer_id, conversion_contract, output_contract,
                                          max_ast_nodes=max_ast_nodes)
    result = {"schema_version": "query-initializer-to-statement/v1", "status": "unknown", "reason": None,
              "scope": "query_origin_initial_value_at_first_entry_to_later_same_block_statement",
              "initializer_check": initialized, "preservation_check": None,
              "value_preserved_to_target_entry": False, "target_statement_checked": False,
              "runtime_return_interval": None, "source_program_checked": False, "deployable": False,
              "assumptions": initialized["assumptions"],
              "limitations": ["target expression evaluation and all later history are outside this check",
                              "external API/conversion protocols and actual linkage remain unverified"]}
    if initialized["status"] != "checked":
        result["reason"] = "fresh_query_initializer_not_checked"
        return result
    seed = {"status": "checked", "target_declaration_id": initializer_id,
            "function_id": initialized["owner_id"], "state_relation": initialized["initial_value_origin"],
            "input_sha256": initialized["input_sha256"], "assumptions": initialized["assumptions"]}
    history = _preserve_to_statement(payload["ast"], seed, initialized["declaration_statement_id"],
                                     statement_id, max_ast_nodes, initialized_local=True, stop_at_target_entry=True)
    result["preservation_check"] = history
    result["assumptions"] = history["assumptions"]
    if history["status"] != "checked" or history.get("history_preserved_to_use") is not True:
        result["reason"] = "fresh_initializer_history_not_checked"
        return result
    result.update(status="checked", initializer_id=initializer_id, statement_id=statement_id,
                  value_preserved_to_target_entry=True, value_origin=history["state_relation"],
                  input_sha256=history["input_sha256"])
    return result
