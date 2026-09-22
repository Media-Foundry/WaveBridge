"""Check the narrow syntax binding of an immediately invoked lambda.

This checker deliberately says nothing about reachability, execution count, or
the effects of the lambda body.  It only relates one original ``LambdaExpr``
closure temporary to the exact ``operator()`` selected by its direct call.
"""

from __future__ import annotations

from typing import Any

from wavebridge.verification.integer_selection import _hash
from wavebridge.verification.kernel_arguments import _Unknown


MAX_AST_NODES = 1_000_000
HARD_MAX_AST_NODES = 10_000_000
MAX_RECEIVER_WRAPPERS = 8

_METHOD_ATTRS = {
    "AlwaysInlineAttr", "CUDADeviceAttr", "CUDAHostAttr", "NoInlineAttr",
}


def _children(node: object, *, strict: bool = False) -> list[dict[str, Any]]:
    if not isinstance(node, dict):
        raise _Unknown("ast_node_not_object")
    children = node.get("inner", [])
    if not isinstance(children, list) or any(not isinstance(child, dict) for child in children):
        raise _Unknown("ast_children_not_list_of_objects")
    if strict and any(not child for child in children):
        raise _Unknown("selected_ast_contains_empty_placeholder")
    return [child for child in children if child]


def _type(node: object) -> dict[str, Any]:
    if not isinstance(node, dict) or not isinstance(node.get("type"), dict):
        raise _Unknown("type_evidence_missing")
    info = node["type"]
    value = info.get("desugaredQualType") or info.get("qualType")
    if not isinstance(value, str) or not value:
        raise _Unknown("type_evidence_missing")
    return info


def _raw_type(node: object) -> str:
    info = _type(node)
    return info.get("desugaredQualType") or info["qualType"]


def _template_marker(node: dict[str, Any]) -> bool:
    definition = node.get("definitionData")
    children = node.get("inner", [])
    return (any(key in node for key in (
        "templateArgs", "templateKind", "specializationKind", "instantiatedFrom",
        "instantiatedFromMemberFunction", "describedFunctionTemplate",
    )) or node.get("isDependent") is True or
        node.get("isInstantiationDependent") is True or
        node.get("isGenericLambda") is True or
        (isinstance(definition, dict) and definition.get("isGenericLambda") is True) or
        (isinstance(children, list) and any(
            isinstance(child, dict) and child.get("kind") in {
                "TemplateArgument", "TemplateTypeParmDecl", "NonTypeTemplateParmDecl",
                "TemplateTemplateParmDecl", "FunctionTemplateDecl",
            } for child in children)))


def _function_pointer_type(signature: str) -> str:
    marker = signature.find(" (")
    if marker <= 0 or not signature[marker + 1:].startswith("("):
        raise _Unknown("lambda_call_operator_signature_unsupported")
    return signature[:marker] + " (*)" + signature[marker + 1:]


def _const_call_signature(signature: str) -> bool:
    """Recognize Clang's ordinary and trailing-return const spellings."""
    if signature.endswith(" const"):
        return True
    pieces = signature.split(" -> ")
    return len(pieces) == 2 and pieces[0].endswith("() const") and bool(pieces[1])


def check(root: object, lambda_id: object, *, max_ast_nodes: int | None = None) -> dict[str, Any]:
    budget = MAX_AST_NODES if max_ast_nodes is None else max_ast_nodes
    result: dict[str, Any] = {
        "schema_version": "lambda-immediate-invocation-check/v1",
        "status": "unknown", "reason": None,
        "lambda_id": lambda_id, "closure_declaration_id": None,
        "call_expression_id": None, "call_operator_declaration_id": None,
        "receiver_wrappers": [],
        "receiver_identity": "not_established",
        "scope": "selected_lambda_temporary_as_direct_operator_call_receiver",
        "source_program_checked": False, "deployable": False,
        "reachability": "not_established", "execution_count": "not_established",
        "normal_return": "not_established", "body_effects": "not_established",
        "capture_or_value_preservation": "not_established",
        "closure_escape_from_body": "not_established",
        "assumptions": [
            "the AST is a faithful complete single translation unit",
            "the source program is valid",
            "the selected call expression is evaluated",
            "syntax binding does not establish reachability, execution count, body effects, or value preservation",
        ],
        "budget": {"max_ast_nodes": budget,
                   "max_receiver_wrappers": MAX_RECEIVER_WRAPPERS},
    }
    if type(budget) is not int or not 1 <= budget <= HARD_MAX_AST_NODES:
        result["reason"] = "invalid_ast_node_budget"
        return result
    if (not isinstance(root, dict) or root.get("kind") != "TranslationUnitDecl" or
            not isinstance(lambda_id, str) or not lambda_id):
        result["reason"] = "invalid_inputs"
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

        try:
            result["input_sha256"] = {"root": _hash(root), "lambda_id": _hash(lambda_id)}
        except (TypeError, ValueError, RecursionError):
            raise _Unknown("input_hash_unsupported")

        lambda_occurrences = index.get(lambda_id, [])
        if (not lambda_occurrences or
                any(node.get("kind") != "LambdaExpr" for node in lambda_occurrences) or
                any(node != lambda_occurrences[0] for node in lambda_occurrences[1:])):
            raise _Unknown("original_lambda_expression_not_unique")
        # JSON repeats lambda bodies under the closure's operator method.  Walk
        # the semantic expression/body view while skipping that record copy;
        # this selects the one original expression path without weakening the
        # full-index conflict check above.
        semantic_occurrences: list[dict[str, Any]] = []
        semantic_pending = [root]
        semantic_count = 0
        while semantic_pending:
            node = semantic_pending.pop()
            semantic_count += 1
            if semantic_count > budget:
                raise _Unknown("semantic_ast_node_budget_exceeded")
            if node.get("id") == lambda_id and node.get("kind") == "LambdaExpr":
                semantic_occurrences.append(node)
            children = _children(node)
            if node.get("kind") == "LambdaExpr":
                children = [child for child in children if child.get("kind") != "CXXRecordDecl"]
            semantic_pending.extend(children)
        if len(semantic_occurrences) != 1:
            raise _Unknown("original_lambda_semantic_path_not_unique")
        expression = semantic_occurrences[0]
        if (expression.get("valueCategory") != "prvalue" or _template_marker(expression)):
            raise _Unknown("lambda_expression_generic_or_shape_unsupported")
        closure_type = _raw_type(expression)
        lambda_children = _children(expression, strict=True)
        closures = [child for child in lambda_children if child.get("kind") == "CXXRecordDecl"]
        bodies = [child for child in lambda_children if child.get("kind") == "CompoundStmt"]
        if len(closures) != 1 or len(bodies) != 1:
            raise _Unknown("lambda_closure_or_body_not_unique")
        closure, lambda_body = closures[0], bodies[0]
        closure_id = closure.get("id")
        result["closure_declaration_id"] = closure_id
        if (not isinstance(closure_id, str) or not closure_id or
                closure.get("completeDefinition") is not True or
                not isinstance(closure.get("definitionData"), dict) or
                closure["definitionData"].get("isLambda") is not True or
                _template_marker(closure)):
            raise _Unknown("lambda_closure_record_unsupported")
        closure_occurrences = index.get(closure_id, [])
        if (not closure_occurrences or
                any(node.get("kind") != "CXXRecordDecl" for node in closure_occurrences) or
                any(node != closure_occurrences[0] for node in closure_occurrences[1:])):
            raise _Unknown("lambda_closure_declaration_not_unique")

        methods = [child for child in _children(closure, strict=True)
                   if child.get("kind") == "CXXMethodDecl" and child.get("name") == "operator()"]
        if len(methods) != 1:
            raise _Unknown("lambda_call_operator_not_unique_in_closure")
        method = methods[0]
        method_id = method.get("id")
        result["call_operator_declaration_id"] = method_id
        method_occurrences = index.get(method_id, []) if isinstance(method_id, str) else []
        if (not isinstance(method_id, str) or not method_id or not method_occurrences or
                any(node.get("kind") != "CXXMethodDecl" for node in method_occurrences) or
                any(node != method_occurrences[0] for node in method_occurrences[1:]) or
                method.get("storageClass") is not None or method.get("isStatic") is True or
                method.get("previousDecl") is not None or _template_marker(method)):
            raise _Unknown("lambda_call_operator_declaration_unsupported")
        method_children = _children(method, strict=True)
        parameters = [child for child in method_children if child.get("kind") == "ParmVarDecl"]
        method_bodies = [child for child in method_children if child.get("kind") == "CompoundStmt"]
        attributes = [child for child in method_children
                      if str(child.get("kind", "")).endswith("Attr")]
        if (parameters or len(method_bodies) != 1 or method_bodies[0] != lambda_body or
                any(child.get("kind") not in {"CompoundStmt", *_METHOD_ATTRS}
                    for child in method_children) or
                any(child.get("kind") not in _METHOD_ATTRS or _children(child, strict=True)
                    for child in attributes)):
            raise _Unknown("lambda_call_operator_body_parameters_or_attributes_unsupported")

        # The original LambdaExpr itself must flow only through the narrow
        # receiver wrappers to the second child of one direct operator call.
        current = expression
        wrappers: list[dict[str, Any]] = []
        materializations = 0
        no_op_casts = 0
        while True:
            owners = parents.get(id(current), [])
            if len(owners) != 1:
                raise _Unknown("lambda_receiver_parent_path_not_unique")
            owner = owners[0]
            kind = owner.get("kind")
            if kind == "CXXOperatorCallExpr":
                call = owner
                break
            if len(wrappers) >= MAX_RECEIVER_WRAPPERS or kind not in {
                    "ParenExpr", "MaterializeTemporaryExpr", "ImplicitCastExpr"}:
                raise _Unknown("lambda_not_direct_temporary_receiver")
            if _children(owner, strict=True) != [current]:
                raise _Unknown("lambda_receiver_wrapper_not_single_child")
            if kind == "ParenExpr":
                if (owner.get("valueCategory") != current.get("valueCategory") or
                        _type(owner) != _type(current)):
                    raise _Unknown("lambda_receiver_paren_type_mismatch")
            elif kind == "MaterializeTemporaryExpr":
                materializations += 1
                if (materializations != 1 or owner.get("valueCategory") != "lvalue" or
                        owner.get("storageDuration") != "full expression" or
                        owner.get("boundToLValueRef") is not True or
                        _raw_type(owner) != closure_type):
                    raise _Unknown("lambda_receiver_materialization_unsupported")
            else:
                no_op_casts += 1
                if (no_op_casts != 1 or owner.get("castKind") != "NoOp" or
                        owner.get("valueCategory") != "lvalue" or
                        _raw_type(owner) != f"const {closure_type}"):
                    raise _Unknown("lambda_receiver_cast_unsupported")
            wrappers.append({"id": owner.get("id"), "kind": kind,
                             "type": owner.get("type"),
                             "value_category": owner.get("valueCategory")})
            current = owner
        method_signature = _raw_type(method)
        if (materializations != 1 or no_op_casts not in {0, 1} or
                (no_op_casts == 1) != _const_call_signature(method_signature)):
            raise _Unknown("lambda_receiver_required_wrappers_missing")

        call_children = _children(call, strict=True)
        call_id = call.get("id")
        result["call_expression_id"] = call_id
        call_occurrences = index.get(call_id, []) if isinstance(call_id, str) else []
        if (not isinstance(call_id, str) or not call_id or not call_occurrences or
                any(node.get("kind") != "CXXOperatorCallExpr" for node in call_occurrences) or
                any(node != call_occurrences[0] for node in call_occurrences[1:]) or
                call.get("valueCategory") != "prvalue" or len(call_children) != 2 or
                call_children[1] is not current):
            raise _Unknown("lambda_operator_call_shape_or_identity_unsupported")
        callee = call_children[0]
        callee_children = _children(callee, strict=True)
        if (callee.get("kind") != "ImplicitCastExpr" or
                callee.get("castKind") != "FunctionToPointerDecay" or
                callee.get("valueCategory") != "prvalue" or len(callee_children) != 1):
            raise _Unknown("lambda_operator_callee_cast_unsupported")
        reference = callee_children[0]
        referenced = reference.get("referencedDecl")
        if (reference.get("kind") != "DeclRefExpr" or
                reference.get("valueCategory") != "lvalue" or _children(reference, strict=True) or
                not isinstance(referenced, dict) or
                referenced.get("kind") != "CXXMethodDecl" or
                referenced.get("id") != method_id or
                referenced.get("name") != "operator()" or
                referenced.get("type") != method.get("type") or
                _raw_type(reference) != method_signature or
                _raw_type(callee) != _function_pointer_type(method_signature)):
            raise _Unknown("lambda_operator_callee_not_exact_closure_method")

        result.update(
            status="checked", receiver_wrappers=wrappers,
            receiver_identity="selected_original_lambda_temporary_is_direct_call_receiver",
            completion={
                "status": "conditional",
                "condition": "the_selected_call_expression_is_evaluated",
                "established": [
                    "exact_original_lambda_expression_to_closure_record_binding",
                    "exact_temporary_receiver_to_nonstatic_zero_argument_operator_call_binding",
                    "operator_method_body_matches_the_lambda_expression_body",
                ],
            },
        )
    except _Unknown as error:
        result["reason"] = error.reason
    return result
