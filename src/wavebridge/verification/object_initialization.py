"""Conditionally check one direct automatic object's initialization."""

from __future__ import annotations

from typing import Any

from wavebridge.verification.constructor_argument_effects import (
    check as check_constructor_argument_effects,
)
from wavebridge.verification.integer_selection import _hash
from wavebridge.verification.kernel_arguments import _Unknown


MAX_AST_NODES = 1_000_000
HARD_MAX_AST_NODES = 10_000_000
CLEANUP_COVERAGE = "visited_expressions_not_exhaustive"
CLEANUP_COUNT_SEMANTICS = "clang_cleanup_objects_not_destructor_event_count"


def _children(node: object, *, strict: bool = False) -> list[dict[str, Any]]:
    if not isinstance(node, dict):
        raise _Unknown("ast_node_not_object")
    children = node.get("inner", [])
    if not isinstance(children, list) or any(not isinstance(child, dict) for child in children):
        raise _Unknown("ast_children_not_list_of_objects")
    if strict and any(not child for child in children):
        raise _Unknown("selected_ast_contains_empty_placeholder")
    return [child for child in children if child]


def _raw_type(node: object) -> str:
    if not isinstance(node, dict) or not isinstance(node.get("type"), dict):
        raise _Unknown("type_evidence_missing")
    info = node["type"]
    value = info.get("desugaredQualType") or info.get("qualType")
    if not isinstance(value, str) or not value:
        raise _Unknown("type_evidence_missing")
    return value


def _template_marker(node: dict[str, Any]) -> bool:
    if (any(key in node for key in (
            "templateArgs", "templateKind", "specializationKind", "instantiatedFrom",
            "instantiatedFromMemberFunction", "describedFunctionTemplate")) or
            node.get("isDependent") is True or node.get("isInstantiationDependent") is True):
        return True
    children = node.get("inner", [])
    return isinstance(children, list) and any(
        isinstance(child, dict) and child.get("kind") in {
            "TemplateArgument", "TemplateTypeParmDecl", "NonTypeTemplateParmDecl",
            "TemplateTemplateParmDecl",
        } for child in children)


def check(payload: object, variable_id: object, integer_types: object,
          selection_domains: object, *, max_ast_nodes: int | None = None) -> dict[str, Any]:
    budget = MAX_AST_NODES if max_ast_nodes is None else max_ast_nodes
    result: dict[str, Any] = {
        "schema_version": "object-initialization-check/v1",
        "status": "unknown", "reason": None,
        "variable_id": variable_id, "constructor_expression_id": None,
        "cleanup_wrapper_id": None, "cleanup_observation": None,
        "constructor_argument_effects": None, "fields": [],
        "scope": "selected_automatic_object_direct_initialization_on_normal_completion",
        "source_program_checked": False, "deployable": False,
        "target_address_published": "not_established",
        "prior_aliases": "not_established",
        "post_initialization_value_preservation": "not_established",
        "post_initialization_escape": "not_established",
        "destructor_and_lifetime_end_effects": "not_established",
        "exception_and_unwinding_effects": "not_established",
        "invocation_history_and_launch_semantics": "not_established",
        "assumptions": [
            "the embedded AST and cleanup metadata are faithful outputs of the same Clang ASTContext",
            "the explicit integer ABI matches the compilation target",
            "the source program is valid and the selected constructor returns normally",
            "a false Clang cleanupsHaveSideEffects flag is trusted frontend evidence rather than an independent proof",
            "cleanup getNumObjects counts Clang cleanup objects and is not a destructor-event count",
        ],
        "budget": {"max_ast_nodes_per_fresh_scan": budget,
                   "note": "the limit is not a total execution-time budget"},
    }
    if type(budget) is not int or not 1 <= budget <= HARD_MAX_AST_NODES:
        result["reason"] = "invalid_ast_node_budget"
        return result
    if (not isinstance(payload, dict) or
            payload.get("schema_version") != "clang-native-captures/v1" or
            not isinstance(payload.get("ast"), dict) or
            payload["ast"].get("kind") != "TranslationUnitDecl" or
            not isinstance(variable_id, str) or not variable_id or
            not isinstance(integer_types, dict) or not isinstance(selection_domains, dict)):
        result["reason"] = "invalid_inputs"
        return result
    root = payload["ast"]

    try:
        nodes: list[dict[str, Any]] = []
        parent: dict[int, dict[str, Any]] = {}
        index: dict[str, list[dict[str, Any]]] = {}
        pending: list[tuple[dict[str, Any], dict[str, Any] | None]] = [(root, None)]
        while pending:
            node, owner = pending.pop()
            if not isinstance(node, dict):
                raise _Unknown("ast_node_not_object")
            nodes.append(node)
            if len(nodes) > budget:
                raise _Unknown("ast_node_budget_exceeded")
            if owner is not None:
                parent[id(node)] = owner
            node_id = node.get("id")
            if isinstance(node_id, str) and node_id:
                index.setdefault(node_id, []).append(node)
            pending.extend((child, node) for child in _children(node))

        variable_nodes = index.get(variable_id, [])
        variables = [node for node in variable_nodes if node.get("kind") == "VarDecl"]
        if len(variable_nodes) != 1 or len(variables) != 1:
            raise _Unknown("target_variable_not_unique")
        variable = variables[0]
        raw_variable_type = _raw_type(variable)
        if (variable.get("storageClass") not in {None, "auto", "register"} or
                variable.get("tls") not in (None, "none") or
                variable.get("tlsKind") not in (None, "none") or
                "volatile" in raw_variable_type.split() or "&" in raw_variable_type or
                variable.get("isInitCapture") is True or variable.get("initCapture") is True):
            raise _Unknown("target_not_plain_automatic_nonreference_variable")

        variable_children = _children(variable, strict=True)
        if (len(variable_children) != 1 or
                str(variable_children[0].get("kind", "")).endswith("Attr")):
            raise _Unknown("target_variable_declaration_children_unsupported")
        initializer = variable_children[0]
        wrapper = None
        if initializer.get("kind") == "ExprWithCleanups":
            wrapper = initializer
            wrapper_children = _children(wrapper, strict=True)
            if len(wrapper_children) != 1 or wrapper_children[0].get("kind") != "CXXConstructExpr":
                raise _Unknown("cleanup_wrapper_not_single_direct_constructor")
            constructor = wrapper_children[0]
        elif initializer.get("kind") == "CXXConstructExpr":
            constructor = initializer
        else:
            raise _Unknown("target_initializer_not_direct_constructor")
        constructor_id = constructor.get("id")
        if not isinstance(constructor_id, str) or not constructor_id:
            raise _Unknown("target_constructor_expression_id_missing")
        result["constructor_expression_id"] = constructor_id

        if (variable.get("type") != initializer.get("type") or
                variable.get("type") != constructor.get("type")):
            raise _Unknown("target_initializer_type_binding_mismatch")
        if len(index.get(constructor_id, [])) != 1 or index[constructor_id][0] is not constructor:
            raise _Unknown("target_constructor_expression_not_unique")

        decl_stmt = parent.get(id(variable))
        compound = parent.get(id(decl_stmt)) if decl_stmt is not None else None
        if (not isinstance(decl_stmt, dict) or decl_stmt.get("kind") != "DeclStmt" or
                _children(decl_stmt, strict=True) != [variable] or
                not isinstance(compound, dict) or compound.get("kind") != "CompoundStmt"):
            raise _Unknown("target_not_direct_local_of_ordinary_nontemplate_function")
        ancestor = parent.get(id(compound))
        function = None
        while ancestor is not None:
            kind = ancestor.get("kind")
            if (kind == "LambdaExpr" or
                    (isinstance(kind, str) and kind.endswith("TemplateDecl"))):
                raise _Unknown("target_not_direct_local_of_ordinary_nontemplate_function")
            if isinstance(kind, str) and kind.endswith("FunctionDecl"):
                if kind != "FunctionDecl" or _template_marker(ancestor):
                    raise _Unknown("target_not_direct_local_of_ordinary_nontemplate_function")
                function = ancestor
                break
            ancestor = parent.get(id(ancestor))
        if function is None:
            raise _Unknown("target_not_direct_local_of_ordinary_nontemplate_function")
        function_id = function.get("id")
        if (not isinstance(function_id, str) or not function_id or
                len(index.get(function_id, [])) != 1 or index[function_id][0] is not function):
            raise _Unknown("target_function_not_unique")

        cleanup_observation: dict[str, Any]
        if wrapper is not None:
            wrapper_id = wrapper.get("id")
            if (not isinstance(wrapper_id, str) or not wrapper_id or
                    len(index.get(wrapper_id, [])) != 1 or index[wrapper_id][0] is not wrapper):
                raise _Unknown("cleanup_wrapper_id_missing_or_not_unique")
            result["cleanup_wrapper_id"] = wrapper_id
            metadata = payload.get("expression_cleanups")
            if (payload.get("cleanup_coverage") != CLEANUP_COVERAGE or
                    payload.get("cleanup_object_count_semantics") != CLEANUP_COUNT_SEMANTICS or
                    not isinstance(metadata, list) or
                    any(not isinstance(item, dict) for item in metadata)):
                raise _Unknown("cleanup_metadata_missing_or_wrong_schema")
            metadata_ids = [item.get("expression_id") for item in metadata]
            if (any(not isinstance(identifier, str) or not identifier
                    for identifier in metadata_ids) or
                    len(metadata_ids) != len(set(metadata_ids))):
                raise _Unknown("cleanup_metadata_ids_missing_or_duplicate")
            matches = [item for item in metadata if item.get("expression_id") == wrapper_id]
            if len(matches) != 1:
                raise _Unknown("cleanup_metadata_binding_missing_or_ambiguous")
            observed = matches[0]
            num_objects = observed.get("num_objects")
            side_effects = observed.get("cleanups_have_side_effects")
            if (observed.get("subexpression_id") != constructor_id or
                    type(num_objects) is not int or num_objects != 0 or
                    type(side_effects) is not bool or side_effects is not False):
                raise _Unknown("cleanup_metadata_not_supported_side_effect_free_shape")
            json_side_effects = wrapper.get("cleanupsHaveSideEffects")
            if (json_side_effects is not None and
                    (type(json_side_effects) is not bool or
                     json_side_effects is not False or
                     json_side_effects != side_effects)):
                raise _Unknown("cleanup_ast_and_native_flag_conflict")
            subtree = [constructor]
            while subtree:
                node = subtree.pop()
                if node is not constructor and node.get("kind") in {
                        "ExprWithCleanups", "CXXBindTemporaryExpr"}:
                    raise _Unknown("wrapped_constructor_contains_nested_cleanup_node")
                subtree.extend(_children(node, strict=True))
            cleanup_observation = {
                "status": "observed",
                "expression_id": wrapper_id,
                "subexpression_id": constructor_id,
                "num_objects": num_objects,
                "cleanups_have_side_effects": side_effects,
                "coverage": CLEANUP_COVERAGE,
                "count_semantics": CLEANUP_COUNT_SEMANTICS,
                "interpretation": "trusted_clang_flag_for_this_wrapper_not_independent_effect_proof",
            }
        else:
            forbidden = {"ExprWithCleanups", "CXXBindTemporaryExpr", "MaterializeTemporaryExpr"}
            subtree = [constructor]
            while subtree:
                node = subtree.pop()
                if node is not constructor and node.get("kind") in forbidden:
                    raise _Unknown("unwrapped_constructor_contains_cleanup_or_temporary_node")
                subtree.extend(_children(node, strict=True))
            cleanup_observation = {
                "status": "not_present_and_no_cleanup_nodes_in_construct_subtree",
                "metadata_required": False,
            }
        result["cleanup_observation"] = cleanup_observation

        argument_effects = check_constructor_argument_effects(
            root, constructor_id, integer_types, selection_domains,
            max_ast_nodes=budget)
        result["constructor_argument_effects"] = argument_effects
        source = argument_effects.get("constructor_source")
        constructor_effects = source.get("constructor_effects") if isinstance(source, dict) else None
        if (argument_effects.get("status") != "checked" or
                argument_effects.get("constructor_expression_id") != constructor_id or
                not isinstance(source, dict) or source.get("status") != "checked" or
                source.get("expression_id") != constructor_id or
                not isinstance(constructor_effects, dict) or
                constructor_effects.get("status") != "checked" or
                argument_effects.get("external_storage_writes") !=
                "not_observed_for_selected_argument_evaluations" or
                argument_effects.get("address_escape_beyond_the_call") !=
                "not_observed_for_selected_argument_evaluations" or
                constructor_effects.get("target_address_published") !=
                "not_observed_in_selected_constructor_member_initializers_or_body" or
                constructor_effects.get("other_storage_writes") !=
                "not_observed_in_selected_constructor_member_initializers_or_body"):
            raise _Unknown("fresh_constructor_value_or_effect_chain_not_checked")
        fields = source.get("fields")
        if not isinstance(fields, list) or not fields:
            raise _Unknown("fresh_constructor_field_domains_missing")

        metadata_for_hash = {
            "cleanup_coverage": payload.get("cleanup_coverage"),
            "cleanup_object_count_semantics": payload.get("cleanup_object_count_semantics"),
            "expression_cleanups": payload.get("expression_cleanups"),
        }
        root_hash = (source.get("input_sha256") or {}).get("root")
        if not isinstance(root_hash, str) or not root_hash:
            raise _Unknown("fresh_constructor_root_hash_missing")
        try:
            result["input_sha256"] = {
                "root": root_hash, "variable_id": _hash(variable_id),
                "integer_types": _hash(integer_types),
                "selection_domains": _hash(selection_domains),
                "cleanup_metadata": _hash(metadata_for_hash),
            }
        except (TypeError, ValueError, RecursionError):
            raise _Unknown("input_hash_unsupported")

        result.update(
            status="checked", fields=fields,
            target_address_published="not_observed_during_selected_initialization",
            completion={
                "status": "conditional",
                "condition": "the_valid_selected_constructor_evaluation_returns_normally",
                "established": [
                    "recorded_integer_field_domains_at_initialization_completion",
                    "no_target_address_publication_observed_during_selected_initialization",
                ],
            },
        )
    except _Unknown as error:
        result["reason"] = error.reason
    return result
