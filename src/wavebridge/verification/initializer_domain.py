"""Compose trusted initializer and getter evidence under one explicit integer ABI.

This checker does not parse source AST or reinterpret a pseudo-object receiver.  It
only checks report bindings and value preservation through the recorded outer
initializer conversions.
"""

from __future__ import annotations

from typing import Any

from wavebridge.verification.getter_returns import _hash
from wavebridge.verification.integer_conversion import check_interval
from wavebridge.verification.kernel_arguments import _abi_type, _Unknown


MAX_CASTS = 32


def check_fixed_nested_entry(payload, declaration_id, outer_loop_id, inner_loop_id,
                             leaf_contract, integer_types, history_call_protocols,
                             work_call_protocols, *, max_ast_nodes=None):
    """Preserve a local through ordinary, one-level constant-bound ForStmt nests.

    Unlike the exit-guard path, no synthetic break partition is introduced.
    Finite header sequences do not establish valid memory, body completion or
    reachability. Store non-aliasing and external call effects remain premises.
    """
    from wavebridge.analysis.column_loops import (
        observe_header, _recover_loop, _check_body, _check_nested_loop,
        _Unknown as BodyUnknown)
    from wavebridge.verification.builtin_calls import check_call_no_memory_write
    from wavebridge.verification.scalar_call_effects import check_no_memory_write

    result = {"schema_version": "initializer-to-fixed-nested-entry/v1",
              "status": "unknown", "reason": None, "history_check": None,
              "header_check": None, "recurrence_check": None,
              "nested_checks": [], "call_effect_checks": {}, "assumptions": [],
              "scope": "initialized_local_at_each_reached_fixed_nested_loop_entry",
              "value_preserved_to_nested_entry": False,
              "external_call_effects_verified": False, "reachability_proved": False,
              "body_completion_proved": False, "column_coverage_checked": False,
              "source_program_checked": False, "deployable": False}
    budget = 1_000_000 if max_ast_nodes is None else max_ast_nodes
    try:
        if (not isinstance(work_call_protocols, dict) or len(work_call_protocols) > 64 or
                any(not isinstance(k, str) or not k or not isinstance(v, dict)
                    for k, v in work_call_protocols.items()) or
                not isinstance(inner_loop_id, str) or not inner_loop_id or inner_loop_id == outer_loop_id or
                not isinstance(integer_types, dict) or integer_types.get("int", {}).get("signed") is not True):
            raise _Unknown("invalid_fixed_nested_inputs")
        bits = integer_types["int"]["bits"]
        history = check_to_statement(payload, declaration_id, outer_loop_id, leaf_contract,
                                     integer_types, history_call_protocols, max_ast_nodes=budget)
        result["history_check"] = history
        result["assumptions"].extend(history["assumptions"])
        if history["status"] != "checked" or history["value_preserved_to_statement"] is not True:
            raise _Unknown("outer_entry_history_not_checked")
        root = payload["ast"]
        header = observe_header(root, outer_loop_id, bits, max_ast_nodes=budget)
        result["header_check"] = header
        if header["status"] != "observed":
            raise _Unknown("outer_header_not_observed")
        if header["input_sha256"]["root"] != history["input_sha256"]["root"]:
            raise _Unknown("input_changed_between_checks")
        result["assumptions"].extend(header["assumptions"])
        nodes, pending, count = {}, [root], 0
        while pending:
            node = pending.pop()
            count += 1
            if count > budget:
                raise _Unknown("semantic_ast_node_budget_exceeded")
            if not isinstance(node, dict):
                raise _Unknown("malformed_semantic_node")
            nodes.setdefault(node.get("id"), []).append(node)
            for key in ("inner", "array_filler"):
                children = node.get(key, [])
                if not isinstance(children, list) or any(not isinstance(n, dict) for n in children):
                    raise _Unknown("malformed_semantic_children")
                pending.extend(children)
        outer, = nodes[outer_loop_id]
        inner, = nodes.get(inner_loop_id, [])
        if inner.get("kind") != "ForStmt":
            raise _Unknown("inner_not_for_statement")

        def call(node):
            identifier = node.get("id")
            if identifier not in work_call_protocols:
                return False
            reports = result["call_effect_checks"]
            if identifier not in reports:
                protocol = work_call_protocols[identifier]
                if protocol.get("schema_version") == "scalar-leaf-effect-assumption/v1":
                    checked = check_no_memory_write(root, identifier, protocol, max_ast_nodes=budget)
                else:
                    checked = check_call_no_memory_write(payload, identifier, protocol, max_ast_nodes=budget)
                reports[identifier] = checked
                result["assumptions"].extend(checked.get("assumptions", []))
            return reports[identifier]["status"] == "checked"

        def label_effect_policy(recovered):
            if not result["call_effect_checks"]:
                return
            recovered["assumptions"]["external_call_effects"] = "explicit_unverified_protocols"
            for key in ("body_preserves_induction", "body_preserves_bound"):
                if recovered.get(key) == "established_in_supported_effect_subset":
                    recovered[key] = "established_under_external_call_effect_assumptions"
            for child in recovered.get("nested_loops", []):
                child["enclosing_storage_preserved"] = "established_under_external_call_effect_assumptions"
                label_effect_policy(child["recurrence"])

        recurrence = _recover_loop(root, outer, bits, call_callback=call)
        label_effect_policy(recurrence)
        result["recurrence_check"] = recurrence
        if recurrence["status"] != "recovered":
            raise _Unknown("outer_recurrence_not_recovered:" + str(recurrence["reason"]))
        start, bound, step = recurrence["start"], recurrence["bound"], recurrence["step"]
        if (start["kind"] != "integer_literal" or bound["kind"] != "constant_declaration" or
                start["value"] < 0 or bound["value"] < 0):
            raise _Unknown("outer_domain_not_nonnegative_constants")
        count = max(0, (bound["value"] - start["value"] + step - 1) // step)
        final = start["value"] + count * step
        if final > (1 << (bits - 1)) - 1:
            raise _Unknown("outer_signed_increment_overflow")
        if recurrence["induction"]["declaration_id"] == declaration_id:
            raise _Unknown("protected_local_is_outer_induction")

        def nested(node):
            checked = _check_nested_loop(root, node, bits, {declaration_id}, call_callback=call)
            label_effect_policy(checked["recurrence"])
            if result["call_effect_checks"]:
                checked["enclosing_storage_preserved"] = "established_under_external_call_effect_assumptions"
            result["nested_checks"].append({"loop_id": node["id"], "check": checked})

        # Inspect ALL components, including siblings after the inner loop: they
        # can change the protected value before the next outer iteration.
        for component in (outer["inner"][0], *outer["inner"][2:]):
            _check_body(component, {declaration_id}, call_callback=call, nested_callback=nested)
        selected = [c for c in result["nested_checks"] if c["loop_id"] == inner_loop_id]
        if len(selected) != 1:
            raise _Unknown("selected_inner_not_checked")
        result["unused_call_protocol_ids"] = sorted(set(work_call_protocols) - set(result["call_effect_checks"]))
        if result["unused_call_protocol_ids"]:
            raise _Unknown("unused_work_call_protocols")
        result["assumptions"].extend([
            "all loop memory stores do not alias the protected local or recurrence storage",
            "source execution is valid; objects remain live without asynchronous interference",
            "reached loop bodies and invoked calls complete normally; header counts alone do not prove completion"])
        result.update(status="checked", value_preserved_to_nested_entry=True,
                      result_interval=history["result_interval"], declaration_id=declaration_id,
                      outer_loop_id=outer_loop_id, inner_loop_id=inner_loop_id,
                      outer_header_iterations=count, outer_final_induction=final,
                      input_sha256={"history": history["input_sha256"], "header": header["input_sha256"],
                                    "inner_loop_id": _hash(inner_loop_id), "native_envelope": _hash(payload),
                                    "work_call_protocols": _hash(work_call_protocols), "budget": _hash(budget)})
    except (BodyUnknown, _Unknown) as error:
        result["reason"] = str(error)
    except (ValueError, TypeError, KeyError, IndexError, AttributeError, RecursionError):
        result["reason"] = "unsupported_fixed_nested_representation"
    return result


def check_nested_iteration_bounds(payload, declaration_id, outer_loop_id, inner_loop_id,
                                   leaf_contract, integer_types, history_call_protocols,
                                   work_call_protocols, inner_call_protocols, declaration_intervals, *,
                                   max_ast_nodes=None, use_static_branches=False, use_source_constants=False):
    """Use a freshly established nested-entry domain in guarded-loop bounds.

    Other intervals remain explicit assumptions; callers cannot replace the
    source interval or supply an old successful entry report.
    """
    from wavebridge.verification.loop_exit_guards import check_iteration_bounds

    result = {"schema_version": "initializer-to-nested-iteration-bounds/v1", "status": "unknown", "reason": None,
              "scope": "conditional_nested_work_count_bounds_with_one_initializer_derived_entry_domain",
              "entry_check": None, "iteration_check": None, "iteration_bounds_established": False,
              "value_preserved_to_nested_entry": False, "full_iteration_domain_established": False,
              "source_program_checked": False, "deployable": False, "assumptions": [],
              "limitations": ["remaining entry intervals are external assumptions, not launch facts",
                              "bounds apply to one reached inner-loop invocation, not a sum across outer iterations",
                              "not exact per-input counts, full coverage, termination or output equivalence"]}
    try:
        if (not isinstance(declaration_intervals, dict) or declaration_id in declaration_intervals or
                type(use_source_constants) is not bool):
            raise _Unknown("invalid_external_intervals_or_source_override")
        entry = check_nested_entry(payload, declaration_id, outer_loop_id, inner_loop_id, leaf_contract,
                                   integer_types, history_call_protocols, work_call_protocols,
                                   max_ast_nodes=max_ast_nodes, use_static_branches=use_static_branches)
        result["entry_check"] = entry
        if entry["status"] != "checked" or entry.get("value_preserved_to_nested_entry") is not True:
            raise _Unknown("nested_entry_domain_not_checked")
        interval = entry["result_interval"]
        combined = {**declaration_intervals, declaration_id: [interval["lower"], interval["upper"]]}
        result.update(value_preserved_to_nested_entry=True, source_interval=interval,
                      source_declaration_id=declaration_id,
                      remaining_external_declaration_intervals=declaration_intervals,
                      source_interval_origin="fresh_nested_entry_check_under_explicit_leaf_contract")
        checked = check_iteration_bounds(payload, inner_loop_id, integer_types["int"]["bits"],
                                          inner_call_protocols, combined, max_ast_nodes=max_ast_nodes,
                                          use_static_branches=use_static_branches, use_nested_loops=True,
                                          use_source_constants=use_source_constants)
        result["iteration_check"] = checked
        if checked["status"] != "checked" or checked.get("iteration_bounds_established") is not True:
            raise _Unknown("nested_iteration_bounds_not_checked")
        if entry["input_sha256"]["history"]["root"] != checked["input_sha256"]["root"]:
            raise _Unknown("input_changed_between_checks")
        result.update(status="checked", iteration_bounds_established=True,
                      work_count_bounds=checked["work_count_bounds"],
                      input_sha256={"entry": entry["input_sha256"], "iteration": checked["input_sha256"],
                                    "remaining_external_intervals": _hash(declaration_intervals)})
        result["assumptions"].extend(entry["assumptions"] + checked["assumptions"])
        for child in checked["work_check"]["call_effect_checks"].values():
            result["assumptions"].extend(child.get("assumptions", []))
    except _Unknown as error:
        result["reason"] = str(error)
    except (TypeError, ValueError, KeyError, IndexError, RecursionError):
        result["reason"] = "unsupported_input_representation"
    return result


def check_nested_entry(payload, declaration_id, outer_loop_id, inner_loop_id, leaf_contract,
                       integer_types, history_call_protocols, work_call_protocols, *,
                       max_ast_nodes=None, use_static_branches=False):
    """Freshly carry one local's initializer domain to each reached nested entry.

    Outer siblings before AND after the selected child must preserve storage;
    preserving only the child's own dependency set is insufficient.
    """
    from wavebridge.verification.loop_exit_guards import _check_work_preservation

    result = {"schema_version": "initializer-to-nested-entry/v1", "status": "unknown", "reason": None,
              "scope": "initialized_local_at_each_reached_nested_loop_entry",
              "history_check": None, "work_check": None, "value_preserved_to_nested_entry": False,
              "nested_loop_reachability_established": False, "source_program_checked": False,
              "deployable": False, "assumptions": [],
              "limitations": ["not reachability, termination, trip count, iteration-domain or output equivalence",
                              "all external getter, call-effect, valid-execution and no-alias premises remain conditional"]}
    try:
        abi = integer_types.get("int") if isinstance(integer_types, dict) else None
        if (not isinstance(abi, dict) or abi.get("signed") is not True or
                type(abi.get("bits")) is not int or not 1 <= abi["bits"] <= 64 or
                not isinstance(inner_loop_id, str) or not inner_loop_id or inner_loop_id == outer_loop_id):
            raise _Unknown("invalid_integer_abi_or_nested_selection")
        history = check_to_statement(payload, declaration_id, outer_loop_id, leaf_contract,
                                     integer_types, history_call_protocols, max_ast_nodes=max_ast_nodes,
                                     use_static_branches=use_static_branches)
        result["history_check"] = history
        if history["status"] != "checked" or history.get("value_preserved_to_statement") is not True:
            raise _Unknown("outer_entry_history_not_checked")
        work = _check_work_preservation(payload, outer_loop_id, abi["bits"], work_call_protocols,
                                        max_ast_nodes=max_ast_nodes, use_static_branches=use_static_branches,
                                        use_nested_loops=True, extra_protected_ids=(declaration_id,))
        result["work_check"] = work
        if (work["status"] != "checked" or
                work.get("outer_header_and_prefix_preserve_additional_storage") != "conditional"):
            raise _Unknown("outer_loop_storage_preservation_not_checked")
        if history["input_sha256"]["root"] != work["input_sha256"]["root"]:
            raise _Unknown("input_changed_between_checks")
        selected = [item for item in work["nested_loop_checks"] if item.get("loop_id") == inner_loop_id]
        if (len(selected) != 1 or selected[0].get("status") != "checked" or
                declaration_id not in selected[0].get("ancestor_protected_declaration_ids", [])):
            raise _Unknown("selected_nested_entry_not_checked")
        result.update(status="checked", value_preserved_to_nested_entry=True,
                      result_interval=history["result_interval"], declaration_id=declaration_id,
                      outer_loop_id=outer_loop_id, inner_loop_id=inner_loop_id,
                      nested_loop_relative_child_path=selected[0]["loop_relative_child_path"],
                      input_sha256={"history": history["input_sha256"], "work": work["input_sha256"],
                                    "inner_loop_id": _hash(inner_loop_id)})
        result["assumptions"].extend(history["assumptions"] + work["assumptions"])
        for child in work["call_effect_checks"].values():
            result["assumptions"].extend(child.get("assumptions", []))
    except _Unknown as error:
        result["reason"] = str(error)
    except (TypeError, ValueError, KeyError, IndexError, RecursionError):
        result["reason"] = "unsupported_input_representation"
    return result


def check_to_statement(payload, declaration_id, statement_id, leaf_contract, integer_types,
                       call_protocols, *, max_ast_nodes=None, use_static_branches=False):
    """Preserve an initialized local up to a later direct statement's first entry."""
    from wavebridge.analysis.column_loops import (
        _check_body, _static_bool_value, _hinted_loop, _Unknown as BodyUnknown)
    from wavebridge.verification.builtin_calls import check_call_no_memory_write
    from wavebridge.verification.scalar_call_effects import check_no_memory_write as check_scalar_call
    from wavebridge.verification.array_call_effects import check as check_array_call

    result = {"schema_version": "initializer-to-statement-preservation/v1", "status": "unknown", "reason": None,
              "scope": "local_value_at_first_entry_to_later_direct_statement",
              "initializer_check": None, "statement_checks": [], "call_effect_checks": {},
              "static_branch_decisions": [], "value_preserved_to_statement": False,
              "source_program_checked": False, "deployable": False, "target_body_checked": False,
              "assumptions": ["execution reaches the target normally after this initialization",
                              "intervening stores do not alias the protected local and no asynchronous interference occurs",
                              "all initialization and consumed external call premises apply"],
              "limitations": ["not a reachability, termination, target-body or later-iteration guarantee",
                              "only direct statements in one ordinary function body; no goto or labels",
                              "coordinate meaning, launch domain and external leaf effects remain unverified"],
              "budget": {"max_call_protocols": 64, "max_nested_loops": 16, "max_nested_depth": 8}}
    if (not isinstance(payload, dict) or not isinstance(payload.get("ast"), dict) or
            not isinstance(statement_id, str) or not statement_id or type(use_static_branches) is not bool or
            not isinstance(call_protocols, dict) or len(call_protocols) > 64 or
            any(not isinstance(k, str) or not k or not isinstance(v, dict) for k, v in call_protocols.items())):
        result["reason"] = "invalid_inputs_or_protocols"
        return result
    root = payload["ast"]
    initialized = check_source(root, declaration_id, leaf_contract, integer_types, max_ast_nodes=max_ast_nodes)
    result["initializer_check"] = initialized
    if initialized["status"] != "checked":
        result["reason"] = "source_initializer_not_checked"
        return result
    try:
        index, functions, pending = {}, [], [root]
        while pending:
            node = pending.pop()
            if isinstance(node.get("id"), str):
                index.setdefault(node["id"], []).append(node)
            if node.get("kind") in {"FunctionDecl", "CXXMethodDecl"}:
                functions.append(node)
            pending.extend(node.get("inner", []))
        if len(index.get(statement_id, [])) != 1:
            raise _Unknown("target_statement_not_unique")
        contexts = []
        for function in functions:
            for body in function.get("inner", []):
                if body.get("kind") != "CompoundStmt":
                    continue
                for position, statement in enumerate(body.get("inner", [])):
                    children = statement.get("inner", [])
                    if (statement.get("kind") == "DeclStmt" and len(children) == 1 and
                            children[0].get("id") == declaration_id):
                        contexts.append((function, body, position))
        if len(contexts) != 1:
            raise _Unknown("declaration_not_unique_direct_function_statement")
        function, body, begin = contexts[0]
        paths, pending = {}, [(body, [])]
        forbidden = {"GotoStmt", "IndirectGotoStmt", "LabelStmt", "AddrLabelExpr",
                     "CoawaitExpr", "CoyieldExpr", "CoreturnStmt"}
        while pending:
            node, path = pending.pop()
            paths.setdefault(id(node), []).append(path)
            if node.get("kind") in forbidden:
                raise _Unknown("function_control_transfer_unsupported")
            pending.extend((child, path + [position]) for position, child in enumerate(node.get("inner", [])))
        statements = body["inner"]
        targets = []
        for position, statement in enumerate(statements):
            candidate = _hinted_loop(statement) if statement.get("kind") == "AttributedStmt" else statement
            if candidate.get("id") == statement_id:
                targets.append(position)
        if len(targets) != 1 or targets[0] <= begin:
            raise _Unknown("target_not_later_direct_statement")
        end = targets[0]
        result["selection"] = {"function_id": function.get("id"), "declaration_id": declaration_id,
                               "target_statement_id": statement_id, "declaration_statement_index": begin,
                               "target_statement_index": end}
        loops_used = 0
        native_hash = None

        def call_effect(node):
            nonlocal native_hash
            identifier = node.get("id")
            if identifier not in call_protocols:
                result["unknown_call_id"] = identifier
                return False
            checks = result["call_effect_checks"]
            if identifier not in checks:
                protocol = call_protocols[identifier]
                if protocol.get("schema_version") == "array-call-preservation-request/v1":
                    if native_hash is None:
                        native_hash = _hash(payload)
                    expected_keys = {"schema_version", "native_envelope_sha256", "call_expression_id",
                                     "protected_declaration_id", "accessible_call_protocols"}
                    effects = protocol.get("accessible_call_protocols")
                    if (set(protocol) != expected_keys or protocol.get("native_envelope_sha256") != native_hash or
                            protocol.get("call_expression_id") != identifier or
                            protocol.get("protected_declaration_id") != declaration_id or
                            not isinstance(effects, dict) or len(effects) > 64):
                        checks[identifier] = {"status": "unknown", "reason": "array_request_missing_or_misbound"}
                    else:
                        checks[identifier] = check_array_call(root, identifier, declaration_id,
                            max_ast_nodes=max_ast_nodes, use_scalar_operators=True, use_literal_defaults=True,
                            native_payload=payload, accessible_call_protocols=effects)
                        if (checks[identifier]["status"] == "checked" and
                                checks[identifier].get("protected_storage_preserved") is not True):
                            checks[identifier] = {"status": "unknown", "reason": "array_storage_preservation_missing"}
                else:
                    checks[identifier] = (check_scalar_call(root, identifier, protocol, max_ast_nodes=max_ast_nodes)
                                      if protocol.get("schema_version") == "scalar-leaf-effect-assumption/v1"
                                      else check_call_no_memory_write(payload, identifier, protocol,
                                                                     max_ast_nodes=max_ast_nodes))
                if checks[identifier]["status"] == "checked":
                    result["assumptions"].extend(checks[identifier].get("assumptions", []))
            if checks[identifier]["status"] != "checked":
                result["unknown_call_id"] = identifier
            return checks[identifier]["status"] == "checked"

        def branch(node):
            if any(node.get(flag) for flag in ("hasInit", "hasVar", "isConstexpr", "isConsteval")):
                return None
            children = node.get("inner", [])
            if len(children) != (3 if node.get("hasElse") else 2):
                return None
            try:
                value = _static_bool_value(children[0])
            except BodyUnknown:
                return None
            locations = paths.get(id(node), [])
            if len(locations) != 1:
                raise _Unknown("static_branch_occurrence_not_unique")
            result["static_branch_decisions"].append({"if_id": node.get("id"), "condition_ast": children[0],
                                                       "condition_value": value, "range": node.get("range"),
                                                       "function_body_child_path": locations[0]})
            return [children[1]] if value else children[2:]

        def scan(node, depth=0):
            def nested(loop):
                nonlocal loops_used
                loops_used += 1
                parts = loop.get("inner", [])
                if (depth >= 8 or loops_used > 16 or len(parts) != 5 or parts[1] != {} or
                        any(not isinstance(parts[i], dict) or not parts[i] for i in (0, 2, 3, 4))):
                    raise _Unknown("intervening_loop_layout_or_budget_unsupported")
                for position in (0, 2, 3, 4):
                    scan(parts[position], depth + 1)
            _check_body(node, {declaration_id}, nested_callback=nested, call_callback=call_effect,
                        branch_callback=branch if use_static_branches else None)

        for position in range(begin + 1, end):
            statement = statements[position]
            item = {"function_body_child_index": position, "statement_id": statement.get("id"), "status": "unknown"}
            result["statement_checks"].append(item)
            scan(statement)
            item["status"] = "checked"
        unused = sorted(set(call_protocols) - set(result["call_effect_checks"]))
        result["unused_call_protocol_ids"] = unused
        if unused:
            raise _Unknown("unused_call_protocols")
        result.update(status="checked", value_preserved_to_statement=True,
                      result_interval=initialized["result_interval"],
                      input_sha256={**initialized["input_sha256"], "statement_id": _hash(statement_id),
                                    "call_protocols": _hash(call_protocols), "static_branches": _hash(use_static_branches)})
        result["assumptions"].extend(initialized["assumptions"])
    except BodyUnknown as error:
        result["reason"], result["unknown_range"] = error.reason, error.range
    except _Unknown as error:
        result["reason"] = str(error)
    except (TypeError, ValueError, KeyError, IndexError, RecursionError):
        result["reason"] = "unsupported_input_representation"
    return result


def check_source(root, declaration_id, leaf_contract, integer_types, *, max_ast_nodes=None):
    """Freshly bind a local scalar initializer; no post-initialization history claim."""
    from wavebridge.analysis.initializer_value import link
    from wavebridge.verification.getter_returns import check as check_getter
    from wavebridge.verification.scalar_expression_effects import _type

    budget = 1_000_000 if max_ast_nodes is None else max_ast_nodes
    result = {"schema_version": "source-initializer-domain-check/v1", "status": "unknown", "reason": None,
              "scope": "selected_local_scalar_value_at_initialization_only",
              "source_program_checked": False, "deployable": False, "value_preserved_to_use": False,
              "coordinate_semantics": "not_established", "receiver_purity": "not_established",
              "checks": {}, "budget": {"max_ast_nodes": budget},
              "assumptions": ["AST faithfully represents a valid translation unit and initialization is reached",
                              "external leaf domain and integer ABI are valid; initialization completes normally"],
              "limitations": ["no value history, reaching definition, loop-entry or launch-domain guarantee",
                              "no thread-coordinate semantics or complete initializer effect guarantee"]}
    try:
        if (not isinstance(root, dict) or root.get("kind") != "TranslationUnitDecl" or
                not isinstance(declaration_id, str) or not declaration_id or
                type(budget) is not int or not 1 <= budget <= 10_000_000):
            raise _Unknown("invalid_inputs_or_budget")
        index, selected, pending, count = {}, [], [(root, ())], 0
        while pending:
            node, parents = pending.pop()
            count += 1
            if count > budget:
                raise _Unknown("ast_node_budget_exceeded")
            if not isinstance(node, dict) or not isinstance(node.get("inner", []), list):
                raise _Unknown("malformed_ast")
            if isinstance(node.get("id"), str):
                index.setdefault(node["id"], []).append(node)
            if node.get("id") == declaration_id:
                selected.append((node, parents))
            pending.extend((child, (parents + (node.get("kind"),))[-2:]) for child in node.get("inner", []))
        if len(selected) != 1:
            raise _Unknown("initializer_declaration_not_unique")
        declaration, parents = selected[0]
        if (declaration.get("kind") != "VarDecl" or parents != ("CompoundStmt", "DeclStmt") or
                _type(declaration) not in {"int", "const int"} or
                declaration.get("storageClass") not in (None, "auto", "register") or
                any(declaration.get(key) is not None for key in ("tls", "tlsKind", "thread_local", "threadLocal")) or
                declaration.get("init") is None or len(declaration.get("inner", [])) != 1):
            raise _Unknown("unsupported_local_scalar_declaration")
        initializer = declaration["inner"][0]
        if len(index.get(initializer.get("id"), [])) != 1:
            raise _Unknown("initializer_expression_not_unique")
        result.update(declaration_id=declaration_id, initializer_id=initializer.get("id"),
                      declaration_range=declaration.get("range"), initializer_ast=initializer)
        origin = link(root, initializer)
        result["checks"]["value_link"] = origin
        if origin["status"] != "recovered":
            raise _Unknown("initializer_value_link_not_recovered")
        getter = check_getter(root, origin["callee_declaration_id"], leaf_contract, integer_types,
                              max_ast_nodes=budget)
        result["checks"]["getter"] = getter
        if getter["status"] != "checked":
            result.update(status=getter["status"], reason="initializer_getter_not_checked")
            return result
        domain = check(origin, getter, integer_types)
        result["checks"]["conversion"] = domain
        if domain["status"] != "checked":
            result.update(status=domain["status"], reason="initializer_conversion_not_checked")
            return result
        if domain["result_type"] != "int":
            raise _Unknown("initializer_result_declaration_type_mismatch")
        result.update(status="checked", result_type="int", result_interval=domain["result_interval"],
                      input_sha256={"root": _hash(root), "declaration_id": _hash(declaration_id),
                                    "leaf_contract": _hash(leaf_contract), "integer_types": _hash(integer_types)})
        result["assumptions"].extend(origin["assumptions"] + getter["assumptions"])
    except _Unknown as error:
        result["reason"] = str(error)
    except (TypeError, ValueError, KeyError, IndexError, RecursionError):
        result["reason"] = "unsupported_input_representation"
    return result


def check(value_link: object, getter_report: object,
          integer_types: object) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema_version": "initializer-domain-check/v1",
        "status": "unknown",
        "reason": None,
        "result_type": None,
        "result_interval": None,
        "conversion_checks": [],
        "source_program_checked": False,
        "deployable": False,
        "receiver_purity": "not_established",
        "coordinate_semantics": "not_established",
        "scope": "trusted_initializer_value_link_and_getter_domain_composition",
        "assumptions": [
            "value_link is trusted frontend initializer-value-link/v1 evidence from the source AST",
            "getter_report is genuine getter-return-domain-check/v1 checker evidence for the same source",
            "the explicit integer ABI matches both evidence reports and the compilation target",
            "receiver purity and coordinate meaning are not established by this composition",
        ],
        "budget": {"max_casts": MAX_CASTS, "casts_used": 0},
    }
    if (not isinstance(value_link, dict) or not isinstance(getter_report, dict) or
            not isinstance(integer_types, dict)):
        result["reason"] = "inputs_not_expected_objects"
        return result
    try:
        result["input_sha256"] = {
            "value_link": _hash(value_link),
            "getter_report": _hash(getter_report),
            "integer_types": _hash(integer_types),
        }
    except (TypeError, ValueError, RecursionError):
        result["reason"] = "input_hash_unsupported"
        return result

    try:
        if (value_link.get("schema_version") != "initializer-value-link/v1" or
                value_link.get("status") != "recovered"):
            raise _Unknown("initializer_value_link_not_recovered")
        if (getter_report.get("schema_version") != "getter-return-domain-check/v1" or
                getter_report.get("status") != "checked"):
            raise _Unknown("getter_domain_not_checked")
        call_id = value_link.get("call_id")
        callee_id = value_link.get("callee_declaration_id")
        if not isinstance(call_id, str) or not call_id or not isinstance(callee_id, str) or not callee_id:
            raise _Unknown("initializer_call_binding_missing")
        if getter_report.get("start_declaration_id") != callee_id:
            raise _Unknown("getter_start_does_not_match_initializer_callee")

        getter_hashes = getter_report.get("input_sha256")
        if (not isinstance(getter_hashes, dict) or
                getter_hashes.get("integer_types") != _hash(integer_types)):
            raise _Unknown("getter_integer_abi_not_bound")

        interval = getter_report.get("return_interval")
        if not isinstance(interval, dict):
            raise _Unknown("getter_return_interval_missing")
        lower, upper = interval.get("lower"), interval.get("upper")
        if type(lower) is not int or type(upper) is not int or lower > upper:
            raise _Unknown("getter_return_interval_invalid")
        getter_type = getter_report.get("return_type")
        current_name, current_bits, current_signed = _abi_type(
            {"qualType": getter_type}, integer_types)
        initial = check_interval(lower, upper, current_bits, current_signed,
                                 current_bits, current_signed)
        if initial.get("status") != "checked":
            raise _Unknown("getter_interval_not_representable")
        call_name, _, _ = _abi_type({"qualType": value_link.get("call_type")}, integer_types)
        if call_name != current_name:
            raise _Unknown("initializer_call_type_mismatch")

        conversions = value_link.get("conversions_outer_to_inner")
        if not isinstance(conversions, list):
            raise _Unknown("initializer_conversion_chain_missing")
        result["budget"]["casts_used"] = len(conversions)
        if len(conversions) > MAX_CASTS:
            raise _Unknown("initializer_conversion_budget_exceeded")
        for conversion in reversed(conversions):
            if not isinstance(conversion, dict) or conversion.get("cast_kind") != "IntegralCast":
                raise _Unknown("unsupported_initializer_conversion")
            source_name, source_bits, source_signed = _abi_type(
                {"qualType": conversion.get("source_type")}, integer_types)
            target_name, target_bits, target_signed = _abi_type(
                {"qualType": conversion.get("target_type")}, integer_types)
            if source_name != current_name:
                raise _Unknown("initializer_conversion_chain_discontinuous")
            interval_check = check_interval(lower, upper, source_bits, source_signed,
                                            target_bits, target_signed)
            evidence = {
                "cast_kind": "IntegralCast",
                "source_type": source_name,
                "target_type": target_name,
                "range": conversion.get("range"),
                "conversion": interval_check,
            }
            result["conversion_checks"].append(evidence)
            if interval_check.get("status") == "rejected":
                result.update(status="rejected", reason="initializer_conversion_not_value_preserving",
                              result_type=target_name)
                return result
            if interval_check.get("status") != "checked":
                raise _Unknown("initializer_conversion_check_unknown")
            current_name, current_bits, current_signed = target_name, target_bits, target_signed

        result.update(status="checked", result_type=current_name,
                      result_interval={"lower": lower, "upper": upper})
    except _Unknown as error:
        result["reason"] = error.reason
    return result
