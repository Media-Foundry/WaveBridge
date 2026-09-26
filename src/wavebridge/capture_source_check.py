"""Conditionally bind a copied object lvalue through native reference captures.

The native capture envelope is trusted frontend evidence from one ASTContext.
V2 checks the immediate receiver paths conditional on copy evaluation instead
of assuming closure origin. Neither version proves reachability, source value
preservation, or launch semantics.
"""

from __future__ import annotations

from typing import Any

from wavebridge.record_copy_check import check as check_record_copy
from wavebridge.verification.integer_selection import _hash
from wavebridge.verification.kernel_arguments import _Unknown
from wavebridge.verification.lambda_invocation import check as check_lambda_invocation


MAX_AST_NODES = 1_000_000
HARD_MAX_AST_NODES = 10_000_000
MAX_LAMBDA_DEPTH = 32

_PROTOCOL_KEYS = {
    "schema_version", "root_sha256", "copy_expression_id",
    "source_declaration_id", "source_initialized_alive_assumed",
    "closure_instances_from_recorded_lambdas_assumed",
    "source_and_closures_share_recorded_activation_assumed",
    "source_program_valid_assumed", "evidence_reference",
}
_ORIGIN_PREMISE = "closure_instances_from_recorded_lambdas_assumed"


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


def _canonical(index: dict[str, list[dict[str, Any]]], node_id: object,
               kind: str, missing_reason: str, conflict_reason: str) -> dict[str, Any]:
    if not isinstance(node_id, str) or not node_id:
        raise _Unknown(missing_reason)
    matches = index.get(node_id, [])
    if not matches or any(node.get("kind") != kind for node in matches):
        raise _Unknown(missing_reason)
    if any(node != matches[0] for node in matches[1:]):
        raise _Unknown(conflict_reason)
    return matches[0]


def _template_markers(node: dict[str, Any]) -> bool:
    definition = node.get("definitionData")
    children = node.get("inner", [])
    return any(key in node for key in (
        "templateArgs", "templateKind", "specializationKind",
        "instantiatedFrom", "instantiatedFromMemberFunction", "describedFunctionTemplate",
    )) or node.get("isDependent") is True or node.get("isInstantiationDependent") is True or \
        node.get("isGenericLambda") is True or \
        (isinstance(definition, dict) and definition.get("isGenericLambda") is True) or \
        (isinstance(children, list) and any(
            isinstance(child, dict) and child.get("kind") in {
                "TemplateArgument", "TemplateTypeParmDecl", "NonTypeTemplateParmDecl",
                "TemplateTemplateParmDecl",
            } for child in children))


def check(payload: object, copy_expression_id: object, integer_types: object,
          protocol: object, *, max_ast_nodes: int | None = None) -> dict[str, Any]:
    budget = MAX_AST_NODES if max_ast_nodes is None else max_ast_nodes
    source_origin = isinstance(protocol, dict) and protocol.get("schema_version") == "capture-source-assumptions/v2"
    result: dict[str, Any] = {
        "schema_version": "capture-source-check/v2" if source_origin else "capture-source-check/v1",
        "status": "unknown", "reason": None,
        "copy_expression_id": copy_expression_id, "source_declaration_id": None,
        "copy_check": None, "capture_chain": [],
        "source_object_identity": "not_established",
        "source_declaration_binding": "lexical_declref_plus_native_reference_capture_chain",
        "scope": "conditional_source_lvalue_identity_at_the_direct_record_copy_evaluation",
        "source_program_checked": False, "deployable": False,
        "source_object_preservation": "not_established",
        "launch_semantics": "not_established",
        "lambda_invocation": "not_established",
        "capture_metadata_trust": "trusted_frontend_observation_not_independent_verification",
        "assumptions": [
            "the embedded AST and native capture metadata come from the same faithful ASTContext",
            "the explicit integer ABI matches the compilation target",
            "the exact source dynamic object is initialized and alive at copy evaluation",
            "the evaluated closure instances originate from the recorded lambda expressions",
            "the source object and every closure belong to the recorded enclosing activation",
            "the source program is valid",
            "native capture edges do not establish mutation history, invocation, launch, or deployment semantics",
        ],
        "budget": {
            "max_ast_nodes_per_fresh_scan": budget,
            "max_lambda_depth": MAX_LAMBDA_DEPTH,
            "note": "node limits bound individual fresh AST scans, not total execution time",
        },
    }
    if source_origin:
        result["assumptions"].remove("the evaluated closure instances originate from the recorded lambda expressions")
        result["closure_origin"] = {"status": "unknown", "invocation_checks": [],
                                    "scope": "recorded_lambda_receivers_on_copy_evaluation_path"}
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
            not isinstance(copy_expression_id, str) or not copy_expression_id or
            not isinstance(integer_types, dict) or not isinstance(protocol, dict)):
        result["reason"] = "invalid_inputs"
        return result

    root = payload["ast"]
    copy_report = check_record_copy(root, copy_expression_id, integer_types,
                                    max_ast_nodes=budget)
    result["copy_check"] = copy_report
    root_hash = (copy_report.get("input_sha256") or {}).get("root")
    source_id = copy_report.get("source_declaration_id")
    result["source_declaration_id"] = source_id

    metadata = {
        "schema_version": payload.get("schema_version"),
        "capture_coverage": payload.get("capture_coverage"),
        "plugin_build_clang_version": payload.get("plugin_build_clang_version"),
        "ast_target_triple": payload.get("ast_target_triple"),
        "captures": payload.get("captures"),
    }
    try:
        result["input_sha256"] = {
            "root": root_hash,
            "copy_expression_id": _hash(copy_expression_id),
            "integer_types": _hash(integer_types),
            "protocol": _hash(protocol),
            "capture_metadata": _hash(metadata),
        }
    except (TypeError, ValueError, RecursionError):
        result["reason"] = "input_hash_unsupported"
        return result
    if copy_report.get("status") != "checked" or not isinstance(root_hash, str):
        result["reason"] = "fresh_record_copy_check_not_checked"
        return result

    try:
        evidence = protocol.get("evidence_reference")
        expected_keys = _PROTOCOL_KEYS - {_ORIGIN_PREMISE} if source_origin else _PROTOCOL_KEYS
        expected_version = "capture-source-assumptions/v2" if source_origin else "capture-source-assumptions/v1"
        if (set(protocol) != expected_keys or
                protocol.get("schema_version") != expected_version or
                protocol.get("root_sha256") != root_hash or
                protocol.get("copy_expression_id") != copy_expression_id or
                protocol.get("source_declaration_id") != source_id or
                protocol.get("source_initialized_alive_assumed") is not True or
                (not source_origin and protocol.get(_ORIGIN_PREMISE) is not True) or
                protocol.get("source_and_closures_share_recorded_activation_assumed") is not True or
                protocol.get("source_program_valid_assumed") is not True or
                not isinstance(evidence, str) or not evidence.strip()):
            raise _Unknown("capture_source_protocol_invalid_or_not_applicable")

        index: dict[str, list[dict[str, Any]]] = {}
        pending = [root]
        node_count = 0
        while pending:
            node = pending.pop()
            if not isinstance(node, dict):
                raise _Unknown("ast_node_not_object")
            node_count += 1
            if node_count > budget:
                raise _Unknown("ast_node_budget_exceeded")
            node_id = node.get("id")
            if isinstance(node_id, str) and node_id:
                index.setdefault(node_id, []).append(node)
            pending.extend(_children(node))

        # Recover the target's semantic lexical path without traversing a
        # closure record copy of operator(), and without treating a capture
        # initializer as executing inside the lambda it initializes.
        target_occurrences: list[tuple[dict[str, Any], tuple[str, ...], str | None, bool]] = []
        source_occurrences: list[tuple[dict[str, Any], tuple[str, ...], str | None, bool]] = []
        path_nodes = 0
        target_paths = []

        def walk(node: dict[str, Any], lambda_path: tuple[str, ...],
                 function_id: str | None, template_context: bool, ancestors=()) -> None:
            nonlocal path_nodes
            path_nodes += 1
            if path_nodes > budget:
                raise _Unknown("body_path_node_budget_exceeded")
            kind = node.get("kind")
            path = ancestors + (node,)
            here_template = template_context or str(kind).endswith("TemplateDecl") or _template_markers(node)
            here_function = function_id
            if kind in {"FunctionDecl", "CXXMethodDecl", "CXXConstructorDecl",
                        "CXXDestructorDecl"}:
                node_id = node.get("id")
                here_function = node_id if isinstance(node_id, str) else None
            if node.get("id") == copy_expression_id:
                target_occurrences.append((node, lambda_path, here_function, here_template))
                target_paths.append(path)
            if node.get("id") == source_id and kind == "VarDecl":
                source_occurrences.append((node, lambda_path, here_function, here_template))

            children = _children(node)
            if kind != "LambdaExpr":
                for child in children:
                    walk(child, lambda_path, here_function, here_template, path)
                return
            lambda_id = node.get("id")
            if not isinstance(lambda_id, str) or not lambda_id:
                raise _Unknown("lambda_id_missing")
            if len(lambda_path) >= MAX_LAMBDA_DEPTH:
                raise _Unknown("lambda_depth_budget_exceeded")
            closures = [child for child in children if child.get("kind") == "CXXRecordDecl"]
            bodies = [child for child in children if child.get("kind") == "CompoundStmt"]
            if len(closures) != 1 or len(bodies) != 1:
                raise _Unknown("lambda_direct_shape_unsupported")
            for child in children:
                if child is closures[0] or child is bodies[0]:
                    continue
                walk(child, lambda_path, here_function, here_template, path)
            walk(bodies[0], lambda_path + (lambda_id,), here_function, here_template, path)

        walk(root, (), None, False)
        if not target_occurrences:
            raise _Unknown("copy_expression_not_found_in_lambda_body_traversal")
        if any(item[0] != target_occurrences[0][0] or item[1:] != target_occurrences[0][1:]
               for item in target_occurrences[1:]):
            raise _Unknown("copy_expression_body_path_occurrences_conflict")
        target, lambda_path, target_function, target_template = target_occurrences[0]
        if target.get("kind") != "CXXConstructExpr" or not lambda_path:
            raise _Unknown("copy_expression_not_in_supported_lambda_body")
        if target_template:
            raise _Unknown("copy_expression_template_context_unsupported")
        if len(source_occurrences) != 1:
            raise _Unknown("source_declaration_scope_occurrence_not_unique")
        source, source_path, source_function, source_template = source_occurrences[0]
        if source_path or source_function != target_function or source_template:
            raise _Unknown("source_not_outside_all_lambdas_in_same_nontemplate_function")
        enclosing_function = _canonical(index, target_function, "FunctionDecl",
                                        "outer_function_not_ordinary_function",
                                        "outer_function_occurrences_conflict")
        if _template_markers(enclosing_function):
            raise _Unknown("outer_function_template_or_dependent_unsupported")

        source_type = _raw_type(source)
        if ("&" in source_type or "volatile" in source_type.split() or
                source.get("storageClass") is not None or
                source.get("tlsKind") not in (None, "none") or
                source.get("isStaticLocal") is True or source.get("isInitCapture") is True or
                _template_markers(source)):
            raise _Unknown("source_not_plain_automatic_nonreference_variable")

        captures = payload["captures"]
        if len(captures) > budget or any(not isinstance(item, dict) for item in captures):
            raise _Unknown("capture_metadata_shape_or_budget_unsupported")
        chain: list[dict[str, Any]] = []
        for depth, lambda_id in enumerate(lambda_path):
            matching = [item for item in captures
                        if item.get("lambda_id") == lambda_id and
                        item.get("captured_declaration_id") == source_id]
            if len(matching) != 1:
                raise _Unknown("native_capture_edge_missing_or_ambiguous")
            edge = matching[0]
            if (edge.get("support_status") != "observed" or
                    edge.get("unsupported_reason") is not None or
                    edge.get("is_init_capture") is not False or
                    edge.get("is_this_capture") is not False or
                    edge.get("is_vla_type_capture") is not False or
                    type(edge.get("is_implicit")) is not bool or
                    type(edge.get("capture_index")) is not int or edge["capture_index"] < 0 or
                    edge.get("enclosing_lambda_ids") != list(lambda_path[:depth])):
                raise _Unknown("native_capture_edge_unsupported_or_path_mismatch")
            if edge.get("capture_kind") != "by_reference":
                raise _Unknown("capture_chain_contains_nonreference_capture")

            lambda_node = _canonical(index, lambda_id, "LambdaExpr",
                                     "capture_lambda_missing", "capture_lambda_occurrences_conflict")
            lambda_children = _children(lambda_node, strict=True)
            closure_id = edge.get("closure_declaration_id")
            closure = _canonical(index, closure_id, "CXXRecordDecl",
                                 "capture_closure_missing", "capture_closure_occurrences_conflict")
            if (not any(child.get("kind") == "CXXRecordDecl" and
                        child.get("id") == closure_id for child in lambda_children) or
                    closure.get("completeDefinition") is not True or
                    not isinstance(closure.get("definitionData"), dict) or
                    closure["definitionData"].get("isLambda") is not True or
                    any(child.get("kind") == "FunctionTemplateDecl"
                        for child in _children(closure, strict=True)) or
                    _template_markers(closure)):
                raise _Unknown("capture_closure_not_exact_nongeneric_lambda_record")

            field_id = edge.get("field_declaration_id")
            field = _canonical(index, field_id, "FieldDecl",
                               "capture_field_missing", "capture_field_occurrences_conflict")
            if (not any(child.get("kind") == "FieldDecl" and child.get("id") == field_id
                        for child in _children(closure, strict=True)) or
                    _raw_type(field) != f"{source_type} &" or
                    "volatile" in _raw_type(field).split()):
                raise _Unknown("capture_field_not_exact_source_reference_member")

            initializer_id = edge.get("initializer_expression_id")
            initializer = _canonical(index, initializer_id, "DeclRefExpr",
                                     "capture_initializer_missing_or_not_declref",
                                     "capture_initializer_occurrences_conflict")
            referenced = initializer.get("referencedDecl")
            if (initializer.get("valueCategory") != "lvalue" or _children(initializer, strict=True) or
                    not isinstance(referenced, dict) or referenced.get("kind") != "VarDecl" or
                    referenced.get("id") != source_id or referenced.get("type") != source.get("type") or
                    _raw_type(initializer) != source_type or
                    not any(child.get("id") == initializer_id for child in lambda_children)):
                raise _Unknown("capture_initializer_not_exact_source_declref")

            chain.append({
                "lambda_id": lambda_id,
                "enclosing_lambda_ids": list(lambda_path[:depth]),
                "closure_declaration_id": closure_id,
                "captured_declaration_id": source_id,
                "field_declaration_id": field_id,
                "initializer_expression_id": initializer_id,
                "capture_kind": "by_reference",
                "is_implicit": edge["is_implicit"],
                "relation": "conditional_reference_to_same_source_dynamic_object",
            })

        if source_origin:
            if len(target_paths) != 1:
                raise _Unknown("closure_origin_copy_path_not_unique")
            path = target_paths[0]
            previous_body = -1
            for edge in chain:
                invocation = check_lambda_invocation(root, edge["lambda_id"], max_ast_nodes=budget)
                result["closure_origin"]["invocation_checks"].append(invocation)
                if (invocation.get("status") != "checked" or
                        invocation.get("lambda_id") != edge["lambda_id"] or
                        invocation.get("closure_declaration_id") != edge["closure_declaration_id"] or
                        invocation.get("input_sha256", {}).get("root") != root_hash):
                    raise _Unknown("fresh_closure_origin_invocation_not_checked")
                positions = [i for i, node in enumerate(path) if node.get("kind") == "LambdaExpr"
                             and node.get("id") == edge["lambda_id"]]
                if len(positions) != 1:
                    raise _Unknown("closure_origin_lambda_not_on_unique_copy_path")
                position = positions[0]
                calls = [i for i, node in enumerate(path[:position])
                         if node.get("kind") == "CXXOperatorCallExpr" and
                         node.get("id") == invocation.get("call_expression_id")]
                if (len(calls) != 1 or calls[0] <= previous_body or
                        position + 1 >= len(path) or path[position + 1].get("kind") != "CompoundStmt"):
                    raise _Unknown("closure_origin_call_not_on_copy_body_path")
                previous_body = position + 1
            result["closure_origin"]["status"] = "checked"
            result["lambda_invocation"] = "fresh_immediate_receiver_paths_conditioned_on_copy_evaluation"

        result.update(
            status="checked", capture_chain=chain,
            source_object_identity="conditional_same_dynamic_object_at_copy_evaluation",
            identity_completion={
                "status": "conditional",
                "source_declaration_id": source_id,
                "copy_expression_id": copy_expression_id,
                "premises": [
                    "source_initialized_alive_assumed",
                    *([] if source_origin else [_ORIGIN_PREMISE]),
                    "source_and_closures_share_recorded_activation_assumed",
                    "source_program_valid_assumed",
                ],
                "evidence_reference": evidence,
                "external_evidence_verified": False,
            },
        )
    except _Unknown as error:
        result["reason"] = error.reason
    return result
