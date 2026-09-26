"""Audit the explicit uses of one initialized automatic record object.

``checked`` means that the complete supported semantic view of the containing
ordinary function has a closed set of explicit references.  It deliberately
does not mean that the object's value is preserved or that aliases/effects not
represented by those references do not exist.
"""

from __future__ import annotations

from typing import Any

from wavebridge.capture_source_check import check as check_capture_source
from wavebridge.record_copy_check import check as check_record_copy
from wavebridge.verification.integer_selection import _hash
from wavebridge.verification.kernel_arguments import _Unknown
from wavebridge.verification.lambda_invocation import (
    _same_ast,
    check as check_lambda_invocation,
)
from wavebridge.verification.object_initialization import (
    CLEANUP_COUNT_SEMANTICS,
    CLEANUP_COVERAGE,
    check as check_object_initialization,
)


MAX_AST_NODES = 1_000_000
HARD_MAX_AST_NODES = 10_000_000
MAX_EXPLICIT_USES = 256


def _copy_cleanup_observations(payload, root_hash, semantic_paths, semantic_ids, copy_paths, index, budget):
    """Bind native flags for enclosing wrappers, not all destructor events."""
    result = {
        "schema_version": "copy-enclosing-cleanup-observations/v1",
        "status": "unknown", "reason": None, "copies": [], "wrappers": [],
        "scope": "native_flags_for_all_ExprWithCleanups_ancestors_of_selected_copies",
        "root_sha256": root_hash, "source_program_checked": False, "deployable": False,
        "source_lifetime": "not_established", "source_value_preservation": "not_established",
        "other_scope_destructors_and_cleanup_events": "not_established",
        "callee_and_other_argument_effects": "not_established",
        "assumptions": [
            "the embedded AST and native observations faithfully describe the same Clang ASTContext",
            "cleanupsHaveSideEffects is trusted frontend evidence, not an independent effect proof",
            "getNumObjects is not the number of C++ temporary destructor events",
        ],
    }
    try:
        wrappers = {}
        for copy_id in sorted(copy_paths):
            occurrences = semantic_ids.get(copy_id, [])
            if len(occurrences) != 1:
                raise _Unknown("cleanup_copy_semantic_occurrence_not_unique")
            path = semantic_paths.get(id(occurrences[0]))
            if not path or path[-1].get("id") != copy_id:
                raise _Unknown("cleanup_copy_semantic_path_missing")
            enclosing = []
            for node in path[:-1]:
                if node.get("kind") != "ExprWithCleanups":
                    continue
                identifier = node.get("id")
                if (not isinstance(identifier, str) or not identifier or
                        len(semantic_ids.get(identifier, [])) != 1 or
                        not index.get(identifier) or
                        any(not _same_ast(item, node) for item in index[identifier])):
                    raise _Unknown("cleanup_wrapper_occurrences_missing_or_conflicting")
                wrappers[identifier] = node
                enclosing.append(identifier)
            result["copies"].append({"copy_expression_id": copy_id, "wrapper_ids": enclosing})
        if not wrappers:
            result.update(status="checked", relation="no_enclosing_ExprWithCleanups_on_selected_copy_paths",
                          metadata_required=False)
            return result
        observations = payload.get("expression_cleanups")
        if (payload.get("cleanup_coverage") != CLEANUP_COVERAGE or
                payload.get("cleanup_object_count_semantics") != CLEANUP_COUNT_SEMANTICS or
                not isinstance(observations, list) or len(observations) > budget or
                any(not isinstance(item, dict) for item in observations)):
            raise _Unknown("cleanup_metadata_missing_or_wrong_schema")
        identifiers = [item.get("expression_id") for item in observations]
        if (any(not isinstance(identifier, str) or not identifier for identifier in identifiers) or
                len(set(identifiers)) != len(identifiers)):
            raise _Unknown("cleanup_metadata_ids_missing_or_duplicate")
        result["cleanup_metadata_sha256"] = _hash({
            "coverage": payload["cleanup_coverage"],
            "count_semantics": payload["cleanup_object_count_semantics"],
            "plugin_build_clang_version": payload.get("plugin_build_clang_version"),
            "ast_target_triple": payload.get("ast_target_triple"),
            "expression_cleanups": observations,
        })
        by_id = dict(zip(identifiers, observations))
        for identifier, wrapper in sorted(wrappers.items()):
            children = _children(wrapper, strict=True)
            observed = by_id.get(identifier)
            if (len(children) != 1 or not isinstance(children[0].get("id"), str) or
                    not children[0]["id"]):
                raise _Unknown("cleanup_wrapper_subexpression_missing_or_ambiguous")
            if not observed or observed.get("subexpression_id") != children[0]["id"]:
                raise _Unknown("cleanup_metadata_binding_missing_or_mismatched")
            count = observed.get("num_objects")
            effects = observed.get("cleanups_have_side_effects")
            if type(count) is not int or count != 0 or type(effects) is not bool or effects is not False:
                raise _Unknown("cleanup_native_flag_not_supported_side_effect_free_shape")
            json_effects = wrapper.get("cleanupsHaveSideEffects")
            if "cleanupsHaveSideEffects" in wrapper and (type(json_effects) is not bool or json_effects is not False):
                raise _Unknown("cleanup_ast_and_native_flag_conflict")
            result["wrappers"].append({
                "expression_id": identifier, "subexpression_id": children[0]["id"],
                "num_objects": count, "cleanups_have_side_effects": effects,
            })
        result.update(status="checked", relation="all_selected_enclosing_wrappers_have_supported_native_flags",
                      metadata_required=True)
    except _Unknown as error:
        result["reason"] = error.reason
    except (TypeError, ValueError, RecursionError):
        result["reason"] = "cleanup_input_hash_unsupported"
    return result


def _reference_use_effects(variable_id, root_hash, copy_paths, copies, captures):
    """Compose fresh copy access classifications, not dynamic preservation."""
    result = {
        "schema_version": "source-reference-use-effects/v1",
        "status": "unknown", "reason": None, "copies": [],
        "scope": "closed_explicit_references_and_selected_copy_AST_role_effects",
        "source_declaration_id": variable_id, "root_sha256": root_hash,
        "source_program_checked": False, "deployable": False,
        "source_object_preservation": "not_established",
        "source_destination_nonoverlap": "not_established",
        "opaque_call_and_implicit_lifetime_effects": "not_established",
        "capture_identity": "conditional_on_existing_capture_protocols",
    }
    reports = [(report, "direct") for report in copies]
    reports.extend((report.get("copy_check", {}), "captured") for report in captures)
    seen = set()
    for report, route in reports:
        copy_id = report.get("expression_id")
        if (copy_id not in copy_paths or copy_id in seen or
                bool(copy_paths[copy_id]) != (route == "captured") or
                report.get("status") != "checked" or
                report.get("source_declaration_id") != variable_id or
                report.get("input_sha256", {}).get("root") != root_hash):
            result["reason"] = "fresh_copy_effect_binding_mismatch"
            return result
        seen.add(copy_id)
        effects = report.get("local_copy_effects", {})
        supported = (
            effects.get("status") == "checked" and
            effects.get("source_parameter_accesses") == "direct_integer_field_reads_only" and
            effects.get("destination_accesses") == "direct_field_initializations_only" and
            effects.get("additional_address_publication") ==
            "not_observed_beyond_selected_const_reference_binding")
        result["copies"].append({
            "copy_expression_id": copy_id, "route": route,
            "constructor_declaration_id": report.get("constructor_declaration_id"),
            "status": "checked" if supported else "unknown",
            "reason": None if supported else "fresh_local_copy_effects_not_checked",
            "local_effect_reason": effects.get("reason"),
        })
    if seen != set(copy_paths):
        result["reason"] = "fresh_copy_effect_set_incomplete"
    elif any(row["status"] != "checked" for row in result["copies"]):
        result["reason"] = "one_or_more_copy_effects_unknown"
    else:
        result.update(status="checked", reference_capture_storage=
                      "only_exact_native_reference_captures_in_fresh_checked_immediate_lambdas")
    return result


def _false_do_condition(condition):
    """Only literal false or the exact builtin int-zero-to-bool conversion."""
    if (condition.get("type") not in ({"qualType": "bool"},
                                      {"qualType": "bool", "desugaredQualType": "bool"}) or
            condition.get("valueCategory") != "prvalue"):
        return False
    children = _children(condition, strict=True)
    if condition.get("kind") == "CXXBoolLiteralExpr":
        return condition.get("value") is False and not children
    if (condition.get("kind") != "ImplicitCastExpr" or
            condition.get("castKind") != "IntegralToBoolean" or len(children) != 1):
        return False
    literal = children[0]
    return (literal.get("kind") == "IntegerLiteral" and literal.get("value") == "0" and
            literal.get("type") == {"qualType": "int"} and
            literal.get("valueCategory") == "prvalue" and not _children(literal, strict=True))


def _source_order(variable, semantic_paths, semantic_ids, copy_paths, invocations):
    """Check statement order and receiver paths, not dynamic lifetime."""
    result = {
        "schema_version": "source-copy-structural-order/v1",
        "status": "unknown", "reason": None, "copies": [],
        "scope": "ordered_compound_children_and_fresh_immediate_lambda_paths",
        "source_program_checked": False, "deployable": False,
        "source_lifetime": "not_established", "source_value_preservation": "not_established",
        "execution_reachability_and_count": "not_established",
        "external_nonlocal_control_effects": "not_established",
    }
    try:
        forbidden = {"GotoStmt", "IndirectGotoStmt", "LabelStmt", "AddrLabelExpr",
                     "ForStmt", "WhileStmt",
                     "CXXForRangeStmt", "CXXTryStmt", "CXXCatchStmt",
                     "CoroutineBodyStmt", "CoawaitExpr", "CoyieldExpr", "CoreturnStmt",
                     "SEHTryStmt", "SEHExceptStmt", "SEHFinallyStmt", "StmtExpr",
                     "DependentCoawaitExpr", "CoroutineSuspendExpr"}
        statements_supported = {"CompoundStmt", "DeclStmt", "IfStmt", "ReturnStmt",
                                "NullStmt", "SwitchStmt", "CaseStmt", "DefaultStmt", "BreakStmt", "DoStmt"}
        # Every semantic node has its own path; the last element visits all
        # nodes, not merely terminal leaves of the function.
        for path in semantic_paths.values():
            node = path[-1]
            if (node.get("kind") in forbidden or
                    (str(node.get("kind", "")).endswith("Stmt") and node["kind"] not in statements_supported)):
                result["unsupported_node"] = {"id": node.get("id"), "kind": node.get("kind")}
                raise _Unknown("source_order_control_flow_unsupported")
        source_path = semantic_paths[id(variable)]
        if (len(source_path) < 3 or source_path[-2].get("kind") != "DeclStmt" or
                source_path[-3].get("kind") != "CompoundStmt"):
            raise _Unknown("source_order_declaration_scope_unsupported")
        declaration, scope = source_path[-2], source_path[-3]
        statements = _children(scope, strict=True)
        source_position = next(i for i, node in enumerate(statements) if node is declaration)
        switches = []
        do_wrappers = []
        for path in semantic_paths.values():
            node = path[-1]
            kind = node.get("kind")
            if kind not in {"SwitchStmt", "DoStmt"}:
                continue
            label = "switch" if kind == "SwitchStmt" else "do"
            identifier = node.get("id")
            occurrences = semantic_ids.get(identifier, []) if isinstance(identifier, str) else []
            if not identifier or len(occurrences) != 1 or occurrences[0] is not node:
                raise _Unknown(f"source_order_{label}_not_semantically_unique")
            if kind == "DoStmt":
                children = _children(node, strict=True)
                if (len(children) != 2 or children[0].get("kind") != "CompoundStmt" or
                        not _false_do_condition(children[1])):
                    result["unsupported_node"] = {"id": identifier, "kind": kind}
                    raise _Unknown("source_order_do_condition_unsupported")
            scope_positions = [i for i, parent in enumerate(path) if parent is scope]
            if len(scope_positions) != 1 or scope_positions[0] + 1 >= len(path):
                raise _Unknown(f"source_order_{label}_outside_source_scope")
            statement = path[scope_positions[0] + 1]
            switch_position = next((i for i, child in enumerate(statements) if child is statement), -1)
            if switch_position <= source_position:
                raise _Unknown(f"source_order_{label}_not_after_source_declaration")
            (switches if kind == "SwitchStmt" else do_wrappers).append(node)
        control_objects = {id(node) for node in switches + do_wrappers}
        for path in semantic_paths.values():
            if path[-1].get("kind") in {"CaseStmt", "DefaultStmt", "BreakStmt"}:
                enclosing = [node for node in path[:-1] if node.get("kind") in {"SwitchStmt", "DoStmt", "LambdaExpr"}]
                if not enclosing or id(enclosing[-1]) not in control_objects:
                    raise _Unknown("source_order_transfer_without_supported_control")
                if path[-1].get("kind") != "BreakStmt" and enclosing[-1].get("kind") != "SwitchStmt":
                    raise _Unknown("source_order_case_crosses_do_wrapper")
        invocation_by_lambda = {r["lambda_id"]: r["call_expression_id"] for r in invocations}
        rows = []
        for copy_id, expected_lambdas in sorted(copy_paths.items()):
            candidates = semantic_ids.get(copy_id, [])
            if len(candidates) != 1:
                raise _Unknown("source_order_copy_semantic_occurrence_not_unique")
            path = semantic_paths[id(candidates[0])]
            scope_positions = [i for i, node in enumerate(path) if node is scope]
            if len(scope_positions) != 1 or scope_positions[0] + 1 >= len(path):
                raise _Unknown("copy_not_within_source_compound_scope")
            statement = path[scope_positions[0] + 1]
            copy_position = next((i for i, node in enumerate(statements) if node is statement), -1)
            if copy_position <= source_position:
                raise _Unknown("copy_statement_not_after_source_declaration")
            lambda_positions = [(i, node["id"]) for i, node in enumerate(path)
                                if node.get("kind") == "LambdaExpr"]
            if tuple(identifier for _, identifier in lambda_positions) != expected_lambdas:
                raise _Unknown("source_order_lambda_path_mismatch")
            previous_body = scope_positions[0]
            chain = []
            for position, lambda_id in lambda_positions:
                call_id = invocation_by_lambda.get(lambda_id)
                calls = [i for i, node in enumerate(path[:position])
                         if node.get("id") == call_id and node.get("kind") == "CXXOperatorCallExpr"]
                if len(calls) != 1 or calls[0] <= previous_body:
                    raise _Unknown("source_order_immediate_invocation_path_mismatch")
                if position + 1 >= len(path) or path[position + 1].get("kind") != "CompoundStmt":
                    raise _Unknown("copy_not_in_invoked_lambda_body")
                previous_body = position + 1
                chain.append({"lambda_id": lambda_id, "call_expression_id": call_id})
            rows.append({"copy_expression_id": copy_id, "source_statement_position": source_position,
                         "source_declaration_statement_id": declaration.get("id"),
                         "copy_enclosing_statement_id": statement.get("id"),
                         "copy_enclosing_statement_position": copy_position,
                         "immediate_invocation_chain": chain})
        result.update(status="checked", copies=rows, source_scope_id=scope.get("id"),
                      structured_switch_ids=[node.get("id") for node in switches],
                      false_condition_do_wrappers=[{
                          "id": node["id"], "body_id": node["inner"][0].get("id"),
                          "condition_ast": node["inner"][1],
                      } for node in do_wrappers])
    except (_Unknown, KeyError, StopIteration) as error:
        result["reason"] = error.reason if isinstance(error, _Unknown) else "source_order_path_missing"
    return result


def _children(node: object, *, strict: bool = False) -> list[dict[str, Any]]:
    if not isinstance(node, dict):
        raise _Unknown("ast_node_not_object")
    children = node.get("inner", [])
    if not isinstance(children, list) or any(not isinstance(child, dict) for child in children):
        raise _Unknown("ast_children_not_list_of_objects")
    if strict and any(not child for child in children):
        raise _Unknown("selected_ast_contains_empty_placeholder")
    return [child for child in children if child]


def _template_marker(node: dict[str, Any]) -> bool:
    children = node.get("inner", [])
    return (any(key in node for key in (
        "templateArgs", "templateKind", "specializationKind", "instantiatedFrom",
        "instantiatedFromMemberFunction", "describedFunctionTemplate",
    )) or node.get("isDependent") is True or
        node.get("isInstantiationDependent") is True or
        (isinstance(children, list) and any(
            isinstance(child, dict) and child.get("kind") in {
                "TemplateArgument", "TemplateTypeParmDecl", "NonTypeTemplateParmDecl",
                "TemplateTemplateParmDecl", "FunctionTemplateDecl",
            } for child in children)))


def check(payload: object, variable_id: object, integer_types: object,
          initialization_selection_domains: object, capture_protocols: object,
          *, max_ast_nodes: int | None = None) -> dict[str, Any]:
    budget = MAX_AST_NODES if max_ast_nodes is None else max_ast_nodes
    result: dict[str, Any] = {
        "schema_version": "object-explicit-use-closure-check/v1",
        "status": "unknown", "reason": None,
        "variable_id": variable_id, "function_id": None,
        "initialization": None,
        "explicit_source_references": [], "capture_initializers": [],
        "direct_copy_expression_ids": [], "captured_copy_expression_ids": [],
        "copy_checks": [], "capture_checks": [],
        "lambda_ids": [], "lambda_invocation_checks": [],
        "source_reference_count": 0, "capture_count": 0,
        "copy_count": 0, "lambda_count": 0,
        "counts": {
            "explicit_source_references": 0, "capture_initializers": 0,
            "direct_copies": 0, "captured_copies": 0, "lambdas": 0,
        },
        "scope": "complete_supported_explicit_source_reference_set_in_the_containing_ordinary_function",
        "source_program_checked": False, "deployable": False,
        "source_object_preservation": "not_established",
        "source_mutation_history": "not_established",
        "source_order": {"status": "unknown", "reason": "explicit_use_closure_not_checked"},
        "source_reference_use_effects": {"status": "unknown", "reason": "explicit_use_closure_not_checked"},
        "copy_cleanup_observations": {"status": "unknown", "reason": "explicit_use_closure_not_checked"},
        "prior_aliases": "not_established",
        "untracked_memory_effects": "not_established",
        "opaque_call_effects": "not_established",
        "reachability_and_execution_order": "not_established",
        "launch_semantics": "not_established",
        "assumptions": [
            "the embedded AST and native capture metadata faithfully describe the same complete translation unit",
            "the source program is valid",
            "explicit-reference closure is not a proof that prior aliases or untracked memory effects do not exist",
            "opaque calls without an explicit source reference remain outside the established effect guarantee",
            "fresh subchecks establish only their individually reported conditional scopes",
        ],
        "budget": {"max_ast_nodes_per_fresh_scan": budget,
                   "max_explicit_uses": MAX_EXPLICIT_USES,
                   "note": "fresh subchecks rescan and rehash the complete AST independently"},
    }
    if type(budget) is not int or not 1 <= budget <= HARD_MAX_AST_NODES:
        result["reason"] = "invalid_ast_node_budget"
        return result
    if (not isinstance(payload, dict) or
            payload.get("schema_version") != "clang-native-captures/v1" or
            payload.get("capture_coverage") !=
            "visited_lambda_initializers_and_bodies_not_exhaustive" or
            payload.get("source_program_checked") is not False or
            payload.get("deployable") is not False or
            not isinstance(payload.get("plugin_build_clang_version"), str) or
            not payload["plugin_build_clang_version"] or
            not isinstance(payload.get("ast_target_triple"), str) or
            not payload["ast_target_triple"] or
            not isinstance(payload.get("ast"), dict) or
            payload["ast"].get("kind") != "TranslationUnitDecl" or
            not isinstance(payload.get("captures"), list) or
            not isinstance(variable_id, str) or not variable_id or
            not isinstance(integer_types, dict) or
            not isinstance(initialization_selection_domains, dict) or
            not isinstance(capture_protocols, dict) or
            any(not isinstance(key, str) or not key or not isinstance(value, dict)
                for key, value in capture_protocols.items())):
        result["reason"] = "invalid_inputs"
        return result
    root = payload["ast"]

    initialization = check_object_initialization(
        payload, variable_id, integer_types, initialization_selection_domains,
        max_ast_nodes=budget)
    result["initialization"] = initialization
    root_hash = (initialization.get("input_sha256") or {}).get("root")
    try:
        result["input_sha256"] = {
            "root": root_hash,
            "variable_id": _hash(variable_id),
            "integer_types": _hash(integer_types),
            "initialization_selection_domains": _hash(initialization_selection_domains),
            "capture_protocols": _hash(capture_protocols),
            "capture_metadata": _hash({
                "schema_version": payload.get("schema_version"),
                "capture_coverage": payload.get("capture_coverage"),
                "plugin_build_clang_version": payload.get("plugin_build_clang_version"),
                "ast_target_triple": payload.get("ast_target_triple"),
                "captures": payload.get("captures"),
            }),
        }
    except (TypeError, ValueError, RecursionError):
        result["reason"] = "input_hash_unsupported"
        return result
    if initialization.get("status") != "checked" or not isinstance(root_hash, str):
        result["reason"] = "fresh_object_initialization_not_checked"
        return result

    try:
        nodes: list[dict[str, Any]] = []
        index: dict[str, list[dict[str, Any]]] = {}
        parents: dict[int, list[dict[str, Any]]] = {}
        pending = [root]
        while pending:
            node = pending.pop()
            if not isinstance(node, dict):
                raise _Unknown("ast_node_not_object")
            nodes.append(node)
            if len(nodes) > budget:
                raise _Unknown("ast_node_budget_exceeded")
            node_id = node.get("id")
            if isinstance(node_id, str) and node_id:
                index.setdefault(node_id, []).append(node)
            children = _children(node)
            for child in children:
                parents.setdefault(id(child), []).append(node)
            pending.extend(children)

        variable_nodes = index.get(variable_id, [])
        if (len(variable_nodes) != 1 or variable_nodes[0].get("kind") != "VarDecl"):
            raise _Unknown("source_variable_not_unique")
        variable = variable_nodes[0]
        owner = variable
        function = None
        while True:
            owners = parents.get(id(owner), [])
            if len(owners) != 1:
                break
            owner = owners[0]
            kind = owner.get("kind")
            if kind == "LambdaExpr" or (isinstance(kind, str) and kind.endswith("TemplateDecl")):
                raise _Unknown("source_variable_scope_unsupported")
            if isinstance(kind, str) and kind.endswith("FunctionDecl"):
                if kind != "FunctionDecl" or _template_marker(owner):
                    raise _Unknown("source_function_not_ordinary_nontemplate_function")
                function = owner
                break
        if function is None:
            raise _Unknown("source_function_not_found")
        function_id = function.get("id")
        result["function_id"] = function_id
        if (not isinstance(function_id, str) or not function_id or
                len(index.get(function_id, [])) != 1 or index[function_id][0] is not function):
            raise _Unknown("source_function_not_unique")

        # Traverse the function's semantic bodies.  Lambda closure records
        # contain a JSON copy of operator(), so skip those record subtrees and
        # visit the direct LambdaExpr body and capture initializers instead.
        semantic_refs: list[tuple[dict[str, Any], tuple[str, ...]]] = []
        semantic_nodes = 0
        semantic_paths = {}
        semantic_ids = {}

        def walk(node: dict[str, Any], lambda_path: tuple[str, ...], ancestors=()) -> None:
            nonlocal semantic_nodes
            semantic_nodes += 1
            if semantic_nodes > budget:
                raise _Unknown("semantic_function_node_budget_exceeded")
            path = ancestors + (node,)
            semantic_paths[id(node)] = path
            if isinstance(node.get("id"), str):
                semantic_ids.setdefault(node["id"], []).append(node)
            kind = node.get("kind")
            if kind in {"GCCAsmStmt", "MSAsmStmt"}:
                raise _Unknown("inline_assembly_in_source_function_unsupported")
            if kind == "DeclRefExpr":
                referenced = node.get("referencedDecl")
                if isinstance(referenced, dict) and referenced.get("id") == variable_id:
                    if (referenced.get("kind") != "VarDecl" or
                            referenced.get("type") != variable.get("type") or
                            not isinstance(node.get("id"), str) or not node["id"]):
                        raise _Unknown("source_declref_binding_or_type_mismatch")
                    semantic_refs.append((node, lambda_path))
                    if len(semantic_refs) > MAX_EXPLICIT_USES:
                        raise _Unknown("explicit_source_use_budget_exceeded")
            children = _children(node, strict=True)
            if kind != "LambdaExpr":
                for child in children:
                    walk(child, lambda_path, path)
                return
            lambda_id = node.get("id")
            if not isinstance(lambda_id, str) or not lambda_id:
                raise _Unknown("lambda_id_missing_in_source_function")
            closures = [child for child in children if child.get("kind") == "CXXRecordDecl"]
            bodies = [child for child in children if child.get("kind") == "CompoundStmt"]
            if len(closures) != 1 or len(bodies) != 1:
                raise _Unknown("lambda_semantic_shape_unsupported")
            for child in children:
                if child is closures[0] or child is bodies[0]:
                    continue
                walk(child, lambda_path, path)  # capture initializers execute outside this closure body
            walk(bodies[0], lambda_path + (lambda_id,), path)

        walk(function, ())
        if not semantic_refs:
            raise _Unknown("source_variable_has_no_explicit_references")

        captures = payload["captures"]
        if len(captures) > budget or any(not isinstance(item, dict) for item in captures):
            raise _Unknown("capture_metadata_shape_or_budget_unsupported")
        source_captures = [item for item in captures
                           if item.get("captured_declaration_id") == variable_id]
        capture_initializer_ids: set[str] = set()
        capture_lambda_ids: set[str] = set()
        capture_summaries: list[dict[str, Any]] = []
        for edge in source_captures:
            initializer_id = edge.get("initializer_expression_id")
            lambda_id = edge.get("lambda_id")
            if (edge.get("support_status") != "observed" or
                    edge.get("unsupported_reason") is not None or
                    edge.get("capture_kind") != "by_reference" or
                    edge.get("is_init_capture") is not False or
                    edge.get("is_this_capture") is not False or
                    edge.get("is_vla_type_capture") is not False or
                    not isinstance(initializer_id, str) or not initializer_id or
                    not isinstance(lambda_id, str) or not lambda_id or
                    initializer_id in capture_initializer_ids or lambda_id in capture_lambda_ids):
                raise _Unknown("source_native_capture_not_unique_plain_by_reference")
            capture_initializer_ids.add(initializer_id)
            capture_lambda_ids.add(lambda_id)
            capture_summaries.append({
                "lambda_id": lambda_id,
                "initializer_expression_id": initializer_id,
                "field_declaration_id": edge.get("field_declaration_id"),
                "closure_declaration_id": edge.get("closure_declaration_id"),
                "capture_kind": "by_reference",
            })

        semantic_by_id: dict[str, tuple[dict[str, Any], tuple[str, ...]]] = {}
        for node, path in semantic_refs:
            node_id = node["id"]
            if node_id in semantic_by_id:
                raise _Unknown("semantic_source_declref_id_duplicate")
            occurrences = index.get(node_id, [])
            if (not occurrences or
                    any(item.get("kind") != "DeclRefExpr" for item in occurrences) or
                    any(not _same_ast(item, occurrences[0]) for item in occurrences[1:])):
                raise _Unknown("source_declref_ast_occurrences_conflict")
            semantic_by_id[node_id] = (node, path)
        if not capture_initializer_ids.issubset(semantic_by_id):
            raise _Unknown("native_capture_initializer_not_in_semantic_source_references")

        direct_copy_ids: set[str] = set()
        captured_copy_ids: set[str] = set()
        copy_paths: dict[str, tuple[str, ...]] = {}
        reference_reports: list[dict[str, Any]] = []
        for reference_id, (reference, lambda_path) in semantic_by_id.items():
            if reference_id in capture_initializer_ids:
                reference_reports.append({
                    "expression_id": reference_id, "role": "native_by_reference_capture_initializer",
                    "lambda_path": list(lambda_path),
                })
                continue
            current = reference
            constructor = None
            while True:
                owners = parents.get(id(current), [])
                if len(owners) != 1:
                    break
                current = owners[0]
                kind = current.get("kind")
                if kind == "CXXConstructExpr":
                    constructor = current
                    break
                if kind in {"DeclStmt", "CompoundStmt", "LambdaExpr", "FunctionDecl"}:
                    break
            if constructor is None or not isinstance(constructor.get("id"), str):
                raise _Unknown("source_reference_not_capture_initializer_or_direct_copy_argument")
            copy_id = constructor["id"]
            if copy_id in copy_paths and copy_paths[copy_id] != lambda_path:
                raise _Unknown("copy_expression_semantic_path_conflict")
            copy_paths[copy_id] = lambda_path
            (captured_copy_ids if lambda_path else direct_copy_ids).add(copy_id)
            reference_reports.append({
                "expression_id": reference_id, "role": "direct_record_copy_argument",
                "copy_expression_id": copy_id, "lambda_path": list(lambda_path),
            })

        if set(capture_protocols) != captured_copy_ids:
            raise _Unknown("capture_protocol_keys_do_not_match_all_captured_copies")

        result.update(
            explicit_source_references=reference_reports,
            capture_initializers=capture_summaries,
            direct_copy_expression_ids=sorted(direct_copy_ids),
            captured_copy_expression_ids=sorted(captured_copy_ids),
            source_reference_count=len(reference_reports),
            capture_count=len(capture_summaries),
            copy_count=len(direct_copy_ids) + len(captured_copy_ids),
        )

        copy_checks: list[dict[str, Any]] = []
        result["copy_checks"] = copy_checks
        for copy_id in sorted(direct_copy_ids):
            report = check_record_copy(root, copy_id, integer_types, max_ast_nodes=budget)
            copy_checks.append(report)
            if (report.get("status") != "checked" or
                    report.get("source_declaration_id") != variable_id):
                raise _Unknown("fresh_direct_record_copy_not_checked")

        capture_checks: list[dict[str, Any]] = []
        result["capture_checks"] = capture_checks
        covered_lambda_ids: set[str] = set()
        for copy_id in sorted(captured_copy_ids):
            report = check_capture_source(
                payload, copy_id, integer_types, capture_protocols[copy_id],
                max_ast_nodes=budget)
            capture_checks.append(report)
            if (report.get("status") != "checked" or
                    report.get("source_declaration_id") != variable_id):
                raise _Unknown("fresh_captured_record_copy_not_checked")
            chain = report.get("capture_chain")
            if not isinstance(chain, list) or not chain:
                raise _Unknown("fresh_capture_chain_missing")
            for edge in chain:
                if (not isinstance(edge, dict) or
                        not isinstance(edge.get("lambda_id"), str) or
                        edge.get("captured_declaration_id") != variable_id):
                    raise _Unknown("fresh_capture_chain_binding_mismatch")
                covered_lambda_ids.add(edge["lambda_id"])
        if covered_lambda_ids != capture_lambda_ids:
            raise _Unknown("source_capture_set_not_exactly_covered_by_all_copy_chains")

        invocation_checks: list[dict[str, Any]] = []
        result["lambda_ids"] = sorted(covered_lambda_ids)
        result["lambda_count"] = len(covered_lambda_ids)
        result["lambda_invocation_checks"] = invocation_checks
        for lambda_id in sorted(covered_lambda_ids):
            report = check_lambda_invocation(root, lambda_id, max_ast_nodes=budget)
            invocation_checks.append(report)
            if report.get("status") != "checked" or report.get("lambda_id") != lambda_id:
                raise _Unknown("fresh_immediate_lambda_invocation_not_checked")

        result.update(
            status="checked",
            source_order=_source_order(variable, semantic_paths, semantic_ids, copy_paths, invocation_checks),
            source_reference_use_effects=_reference_use_effects(
                variable_id, root_hash, copy_paths, copy_checks, capture_checks),
            copy_cleanup_observations=_copy_cleanup_observations(
                payload, root_hash, semantic_paths, semantic_ids, copy_paths, index, budget),
            explicit_source_references=reference_reports,
            capture_initializers=capture_summaries,
            direct_copy_expression_ids=sorted(direct_copy_ids),
            captured_copy_expression_ids=sorted(captured_copy_ids),
            copy_checks=copy_checks, capture_checks=capture_checks,
            lambda_ids=sorted(covered_lambda_ids),
            lambda_invocation_checks=invocation_checks,
            source_reference_count=len(reference_reports),
            capture_count=len(capture_summaries),
            copy_count=len(direct_copy_ids) + len(captured_copy_ids),
            lambda_count=len(covered_lambda_ids),
            counts={
                "explicit_source_references": len(reference_reports),
                "capture_initializers": len(capture_summaries),
                "direct_copies": len(direct_copy_ids),
                "captured_copies": len(captured_copy_ids),
                "lambdas": len(covered_lambda_ids),
            },
            explicit_source_reference_closure={
                "status": "checked",
                "relation": "every_supported_explicit_reference_is_an_exact_native_reference_capture_initializer_or_fresh_checked_direct_copy_argument",
                "function_id": function_id,
            },
        )
    except _Unknown as error:
        result["reason"] = error.reason
    return result
