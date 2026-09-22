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
from wavebridge.verification.object_initialization import check as check_object_initialization


MAX_AST_NODES = 1_000_000
HARD_MAX_AST_NODES = 10_000_000
MAX_EXPLICIT_USES = 256


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

        def walk(node: dict[str, Any], lambda_path: tuple[str, ...]) -> None:
            nonlocal semantic_nodes
            semantic_nodes += 1
            if semantic_nodes > budget:
                raise _Unknown("semantic_function_node_budget_exceeded")
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
                    walk(child, lambda_path)
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
                walk(child, lambda_path)  # capture initializers execute outside this closure body
            walk(bodies[0], lambda_path + (lambda_id,))

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
