"""Check a narrow, effect-free integer constructor declaration shape.

The only permitted writes are the language-level initialization of the
selected object's listed direct integer fields.  Call-site argument
evaluation and every operation outside the selected declaration are out of
scope.
"""

from __future__ import annotations

from typing import Any

from wavebridge.verification.integer_selection import BUILTIN_INTEGER_TYPES, _hash
from wavebridge.verification.kernel_arguments import _Unknown, _abi_type


MAX_AST_NODES = 1_000_000
HARD_MAX_AST_NODES = 10_000_000
MAX_FIELDS = 64
MAX_EXPRESSION_DEPTH = 32
ALLOWED_CONSTRUCTOR_ATTRIBUTES = {"CUDAHostAttr", "CUDADeviceAttr"}
ALLOWED_CASTS = {"LValueToRValue", "NoOp", "IntegralCast"}


def _children(node: object, *, strict: bool = True) -> list[dict[str, Any]]:
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
    return node["type"]


def _raw_type(node: object) -> str:
    info = _type(node)
    value = info.get("desugaredQualType") or info.get("qualType")
    if not isinstance(value, str) or not value:
        raise _Unknown("type_evidence_missing")
    return value


def _integer_type(node: object, integer_types: dict[str, Any], reason: str):
    raw = _raw_type(node)
    if ("volatile" in raw.split() or "&" in raw or "*" in raw or
            "[" in raw or "]" in raw):
        raise _Unknown(reason)
    abi = _abi_type(_type(node), integer_types)
    if abi[0] not in BUILTIN_INTEGER_TYPES:
        raise _Unknown(reason)
    return abi


def _template_or_dependent(node: dict[str, Any]) -> bool:
    if (any(key in node for key in (
            "templateArgs", "templateKind", "specializationKind", "instantiatedFrom",
            "instantiatedFromMemberFunction", "describedFunctionTemplate")) or
            node.get("isDependent") is True or
            node.get("isInstantiationDependent") is True):
        return True
    children = node.get("inner", [])
    return isinstance(children, list) and any(
        isinstance(child, dict) and child.get("kind") in {
            "TemplateArgument", "TemplateTypeParmDecl", "NonTypeTemplateParmDecl",
            "TemplateTemplateParmDecl",
        } for child in children)


def check(root: object, constructor_id: object, integer_types: object,
          *, max_ast_nodes: int | None = None) -> dict[str, Any]:
    budget = MAX_AST_NODES if max_ast_nodes is None else max_ast_nodes
    result: dict[str, Any] = {
        "schema_version": "constructor-effects-check/v1",
        "status": "unknown", "reason": None,
        "constructor_declaration_id": constructor_id,
        "record_declaration_id": None,
        "field_initializers": [],
        "permitted_writes": "not_established",
        "target_address_read": "not_established",
        "target_address_published": "not_established",
        "other_storage_writes": "not_established",
        "scope": "selected_constructor_member_initializers_and_body_only",
        "source_program_checked": False, "deployable": False,
        "normal_return": "assumed_not_proved",
        "call_site_argument_evaluation": "excluded",
        "call_argument_effects": "not_established",
        "post_construction_escape": "not_established",
        "destination_declaration_allocation_and_lifetime": "excluded",
        "cleanup_exception_destructor_and_later_escape": "excluded",
        "invocation_history_and_launch_semantics": "not_established",
        "numeric_values_and_domains": "not_established",
        "assumptions": [
            "the AST is a faithful complete valid single translation unit",
            "the explicit integer ABI matches the compilation target",
            "the selected constructor is entered with valid parameter values and returns normally",
            "parameter default expressions and other call-site argument evaluation occur outside this scope",
            "the implicit language operation of initializing each listed direct field writes that target field",
        ],
        "budget": {
            "max_ast_nodes": budget, "max_fields": MAX_FIELDS,
            "max_expression_depth": MAX_EXPRESSION_DEPTH,
        },
    }
    if type(budget) is not int or not 1 <= budget <= HARD_MAX_AST_NODES:
        result["reason"] = "invalid_ast_node_budget"
        return result
    if (not isinstance(root, dict) or not isinstance(constructor_id, str) or
            not constructor_id or not isinstance(integer_types, dict)):
        result["reason"] = "invalid_inputs"
        return result
    try:
        result["input_sha256"] = {
            "root": _hash(root), "constructor_id": _hash(constructor_id),
            "integer_types": _hash(integer_types),
        }
    except (TypeError, ValueError, RecursionError):
        result["reason"] = "input_hash_unsupported"
        return result

    try:
        nodes: list[dict[str, Any]] = []
        pending = [root]
        while pending:
            node = pending.pop()
            if not isinstance(node, dict):
                raise _Unknown("ast_node_not_object")
            nodes.append(node)
            if len(nodes) > budget:
                raise _Unknown("ast_node_budget_exceeded")
            pending.extend(_children(node, strict=False))

        constructors = [node for node in nodes
                        if node.get("kind") == "CXXConstructorDecl" and
                        node.get("id") == constructor_id]
        if len(constructors) != 1:
            raise _Unknown("constructor_declaration_not_unique")
        constructor = constructors[0]
        if (_template_or_dependent(constructor) or constructor.get("previousDecl") is not None or
                any(node.get("kind") == "CXXConstructorDecl" and
                    node.get("previousDecl") == constructor_id for node in nodes)):
            raise _Unknown("constructor_template_dependent_or_redeclared")

        records = [node for node in nodes if node.get("kind") == "CXXRecordDecl" and
                   any(child.get("kind") == "CXXConstructorDecl" and
                       child.get("id") == constructor_id
                       for child in _children(node, strict=False))]
        if len(records) != 1:
            raise _Unknown("constructor_owning_record_not_unique")
        record = records[0]
        record_id = record.get("id")
        definition = record.get("definitionData")
        if (not isinstance(record_id, str) or not record_id or
                record.get("completeDefinition") is not True or
                record.get("tagUsed") == "union" or record.get("isUnion") is True or
                record.get("bases") not in (None, []) or
                not isinstance(definition, dict) or definition.get("isPolymorphic") is True or
                _template_or_dependent(record)):
            raise _Unknown("constructor_owning_record_shape_unsupported")
        record_occurrences = [node for node in nodes if node.get("id") == record_id and
                              node.get("kind") == "CXXRecordDecl"]
        if len(record_occurrences) != 1 or record_occurrences[0] is not record:
            raise _Unknown("constructor_owning_record_not_unique")
        result["record_declaration_id"] = record_id

        record_children = _children(record)
        if any(str(child.get("kind", "")).endswith("Attr") for child in record_children):
            raise _Unknown("record_attribute_unsupported")
        fields = [child for child in record_children if child.get("kind") == "FieldDecl"]
        if not fields or len(fields) > MAX_FIELDS:
            raise _Unknown("record_field_count_unsupported")
        fields_by_id: dict[str, dict[str, Any]] = {}
        field_types: dict[str, tuple[str, int, bool]] = {}
        for field in fields:
            field_id = field.get("id")
            if (not isinstance(field_id, str) or not field_id or field_id in fields_by_id or
                    field.get("isBitfield") is True or field.get("bitWidthValue") is not None or
                    _children(field)):
                raise _Unknown("record_field_shape_unsupported")
            field_types[field_id] = _integer_type(
                field, integer_types, "record_field_not_plain_builtin_integer")
            occurrences = [node for node in nodes if node.get("kind") == "FieldDecl" and
                           node.get("id") == field_id]
            if len(occurrences) != 1 or occurrences[0] is not field:
                raise _Unknown("record_field_declaration_not_unique")
            fields_by_id[field_id] = field

        constructor_children = _children(constructor)
        parameters = [child for child in constructor_children
                      if child.get("kind") == "ParmVarDecl"]
        initializers = [child for child in constructor_children
                        if child.get("kind") == "CXXCtorInitializer"]
        bodies = [child for child in constructor_children if child.get("kind") == "CompoundStmt"]
        attributes = [child for child in constructor_children
                      if str(child.get("kind", "")).endswith("Attr")]
        allowed_kinds = {"ParmVarDecl", "CXXCtorInitializer", "CompoundStmt",
                         *ALLOWED_CONSTRUCTOR_ATTRIBUTES}
        if (any(child.get("kind") not in allowed_kinds for child in constructor_children) or
                any(attribute.get("kind") not in ALLOWED_CONSTRUCTOR_ATTRIBUTES
                    for attribute in attributes)):
            raise _Unknown("constructor_child_or_attribute_unsupported")
        if len(bodies) != 1 or _children(bodies[0]):
            raise _Unknown("constructor_body_not_unique_and_empty")
        if len(initializers) != len(fields):
            raise _Unknown("constructor_initializers_do_not_cover_all_fields")

        parameters_by_id: dict[str, dict[str, Any]] = {}
        parameter_types: dict[str, tuple[str, int, bool]] = {}
        for parameter in parameters:
            parameter_id = parameter.get("id")
            if (not isinstance(parameter_id, str) or not parameter_id or
                    parameter_id in parameters_by_id or _template_or_dependent(parameter)):
                raise _Unknown("constructor_parameter_shape_unsupported")
            parameter_types[parameter_id] = _integer_type(
                parameter, integer_types, "constructor_parameter_not_plain_builtin_integer")
            if any(str(child.get("kind", "")).endswith("Attr")
                   for child in _children(parameter)):
                raise _Unknown("constructor_parameter_attribute_unsupported")
            occurrences = [node for node in nodes if node.get("kind") == "ParmVarDecl" and
                           node.get("id") == parameter_id]
            if len(occurrences) != 1 or occurrences[0] is not parameter:
                raise _Unknown("constructor_parameter_declaration_not_unique")
            parameters_by_id[parameter_id] = parameter

        def pure_initializer(expression: dict[str, Any], depth: int = 0):
            if depth > MAX_EXPRESSION_DEPTH:
                raise _Unknown("constructor_initializer_expression_depth_exceeded")
            kind = expression.get("kind")
            expression_abi = _integer_type(
                expression, integer_types, "initializer_expression_not_builtin_integer")
            children = _children(expression)
            if kind == "DeclRefExpr":
                referenced = expression.get("referencedDecl")
                if (expression.get("valueCategory") != "lvalue" or children or
                        not isinstance(referenced, dict) or
                        referenced.get("kind") != "ParmVarDecl" or
                        referenced.get("id") not in parameters_by_id):
                    raise _Unknown("initializer_leaf_not_exact_parameter")
                parameter_id = referenced["id"]
                parameter = parameters_by_id[parameter_id]
                if (referenced.get("type") != parameter.get("type") or
                        expression.get("type") != parameter.get("type") or
                        expression_abi != parameter_types[parameter_id]):
                    raise _Unknown("initializer_parameter_type_binding_mismatch")
                return {"source_kind": "parameter", "source_parameter_id": parameter_id}, expression_abi
            if kind == "IntegerLiteral":
                if (expression.get("valueCategory") != "prvalue" or children or
                        not isinstance(expression.get("value"), str)):
                    raise _Unknown("initializer_literal_shape_unsupported")
                return {"source_kind": "integer_literal",
                        "literal_spelling": expression["value"]}, expression_abi
            if kind not in {"ParenExpr", "ImplicitCastExpr"} or len(children) != 1:
                raise _Unknown("constructor_initializer_expression_unsupported")
            source, child_abi = pure_initializer(children[0], depth + 1)
            if kind == "ParenExpr":
                if (expression.get("valueCategory") != children[0].get("valueCategory") or
                        expression_abi != child_abi):
                    raise _Unknown("initializer_parenthesis_type_or_category_discontinuity")
                return source, expression_abi
            cast_kind = expression.get("castKind")
            if cast_kind not in ALLOWED_CASTS or expression.get("valueCategory") != "prvalue":
                raise _Unknown("initializer_cast_kind_or_category_unsupported")
            if cast_kind in {"LValueToRValue", "NoOp"} and expression_abi != child_abi:
                raise _Unknown("initializer_nonconverting_cast_type_discontinuity")
            if cast_kind == "LValueToRValue" and children[0].get("valueCategory") != "lvalue":
                raise _Unknown("initializer_lvalue_to_rvalue_source_not_lvalue")
            if cast_kind in {"NoOp", "IntegralCast"} and children[0].get("valueCategory") != "prvalue":
                raise _Unknown("initializer_value_cast_source_not_prvalue")
            source.setdefault("casts_outer_to_inner", []).insert(0, {
                "cast_kind": cast_kind, "source_type": children[0].get("type"),
                "target_type": expression.get("type"), "range": expression.get("range"),
            })
            return source, expression_abi

        covered: set[str] = set()
        checked_initializers: list[dict[str, Any]] = []
        for initializer in initializers:
            target = initializer.get("anyInit")
            expressions = _children(initializer)
            if (not isinstance(target, dict) or target.get("kind") != "FieldDecl" or
                    not isinstance(target.get("id"), str) or len(expressions) != 1):
                raise _Unknown("base_delegating_or_ambiguous_initializer_unsupported")
            field_id = target["id"]
            if (field_id not in fields_by_id or field_id in covered or
                    target.get("type") != fields_by_id[field_id].get("type")):
                raise _Unknown("initializer_target_field_missing_duplicate_or_misbound")
            source, expression_abi = pure_initializer(expressions[0])
            if expression_abi != field_types[field_id]:
                raise _Unknown("initializer_final_type_does_not_match_field")
            checked_initializers.append({
                "field_id": field_id, "field_name": fields_by_id[field_id].get("name"),
                "field_type": fields_by_id[field_id].get("type"),
                "initializer_range": initializer.get("range"),
                "expression_range": expressions[0].get("range"), **source,
            })
            covered.add(field_id)
        if covered != set(fields_by_id):
            raise _Unknown("constructor_initializers_do_not_exactly_cover_fields")

        result.update(
            status="checked", field_initializers=checked_initializers,
            permitted_writes="selected_object_direct_integer_fields_initialization_only",
            target_address_read="not_observed_in_selected_constructor_member_initializers_or_body",
            target_address_published="not_observed_in_selected_constructor_member_initializers_or_body",
            other_storage_writes="not_observed_in_selected_constructor_member_initializers_or_body",
        )
    except _Unknown as error:
        result["reason"] = error.reason
    return result
