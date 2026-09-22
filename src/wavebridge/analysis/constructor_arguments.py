"""Inspect constructor argument evidence without assigning field or launch semantics."""

from __future__ import annotations

from typing import Any

from wavebridge.analysis.integer_constants import evaluate

ARG_CASTS = {"LValueToRValue", "IntegralCast", "NoOp"}
DEFAULT_SOURCE_CASTS = {"IntegralCast", "NoOp"}
BUILTIN_INTEGER_TYPES = {
    "bool", "char", "signed char", "unsigned char", "wchar_t", "char8_t",
    "char16_t", "char32_t", "short", "short int", "signed short",
    "signed short int", "unsigned short", "unsigned short int", "int",
    "signed", "signed int", "unsigned", "unsigned int", "long", "long int",
    "signed long", "signed long int", "unsigned long", "unsigned long int",
    "long long", "long long int", "signed long long", "signed long long int",
    "unsigned long long", "unsigned long long int", "__int128",
    "signed __int128", "unsigned __int128",
}
MAX_AST_NODES = 1_000_000
HARD_MAX_AST_NODES = 10_000_000


class _Unknown(Exception):
    def __init__(self, reason: str, range_value: object = None):
        self.reason, self.range = reason, range_value


def _children(node: dict[str, Any]) -> list[dict[str, Any]]:
    inner = node.get("inner", [])
    return [child for child in inner if isinstance(child, dict) and child] if isinstance(inner, list) else []


def _type(node: dict[str, Any]) -> object:
    return node.get("type") if isinstance(node.get("type"), dict) else None


def _record_cast(node: dict[str, Any], child: dict[str, Any]) -> dict[str, Any]:
    return {"kind": node.get("kind"), "cast_kind": node.get("castKind"),
            "source_type": _type(child), "destination_type": _type(node),
            "range": node.get("range"), "conversion_semantics": "not_established"}


def _unwrap_parens(node: dict[str, Any]) -> dict[str, Any]:
    current = node
    while current.get("kind") == "ParenExpr":
        children = _children(current)
        if len(children) != 1:
            raise _Unknown("ambiguous_parentheses", current.get("range"))
        current = children[0]
    return current


def _unique_node(root, identifier, budget):
    pending, matches, count = [root], [], 0
    while pending:
        node = pending.pop()
        count += 1
        if count > budget:
            raise _Unknown("constructor_identity_ast_budget_exceeded")
        if not isinstance(node, dict) or not isinstance(node.get("inner", []), list):
            raise _Unknown("constructor_identity_malformed_ast")
        if node.get("id") == identifier:
            matches.append(node)
        pending.extend(node.get("inner", []))
    if len(matches) != 1:
        raise _Unknown("constructor_identity_declaration_not_unique")
    return matches[0]


def _walk_bounded(root: dict[str, Any], budget: int) -> list[dict[str, Any]]:
    pending, nodes = [root], []
    while pending:
        node = pending.pop()
        if not isinstance(node, dict) or not isinstance(node.get("inner", []), list):
            raise _Unknown("constructor_identity_malformed_ast")
        nodes.append(node)
        if len(nodes) > budget:
            raise _Unknown("constructor_identity_ast_budget_exceeded")
        pending.extend(node.get("inner", []))
    return nodes


def _canonical_type(node: dict[str, Any]) -> str | None:
    info = _type(node)
    if not isinstance(info, dict):
        return None
    value = info.get("desugaredQualType", info.get("qualType"))
    return value if isinstance(value, str) and value else None


def _supported_default_type(node: dict[str, Any]) -> bool:
    value = _canonical_type(node)
    if value is None or "&" in value or "volatile" in value.split():
        return False
    words = [word for word in value.split() if word not in {"const", "restrict"}]
    return " ".join(words) in BUILTIN_INTEGER_TYPES


def _default_expression_shape(node: dict[str, Any]) -> bool:
    current = node
    while current.get("kind") in {"ParenExpr", "ImplicitCastExpr"}:
        if (current.get("kind") == "ImplicitCastExpr" and
                current.get("castKind") not in DEFAULT_SOURCE_CASTS):
            return False
        children = _children(current)
        if len(children) != 1:
            return False
        current = children[0]
    return current.get("kind") == "IntegerLiteral" and not _children(current)


def _recover_default_source(root: dict[str, Any], constructor: dict[str, Any],
                            parameters: list[dict[str, Any]], position: int,
                            callpoint: dict[str, Any], budget: int
                            ) -> tuple[dict[str, Any], dict[str, Any]]:
    """Recover only a declaration-local literal default hidden by JSON dumping."""
    if constructor.get("isImplicit") is True or constructor.get("inheritedConstructor"):
        raise _Unknown("default_source_inherited_or_implicit_constructor_unsupported")
    if any(constructor.get(key) for key in
           ("previousDecl", "firstRedecl", "describedFunctionTemplate", "templateKind")):
        raise _Unknown("default_source_constructor_redeclaration_or_template_unsupported")
    nodes = _walk_bounded(root, budget)
    constructor_id = constructor.get("id")
    constructors = [node for node in nodes if node.get("kind") == "CXXConstructorDecl"]
    # A later declaration can inherit the selected declaration's default. JSON
    # copies the expression but does not expose CXXDefaultArgExpr::getParam().
    previous = {node.get("previousDecl") for node in constructors
                if isinstance(node.get("previousDecl"), str)}
    if constructor_id in previous:
        raise _Unknown("default_source_constructor_redeclaration_or_template_unsupported")
    if not 0 <= position < len(parameters):
        raise _Unknown("default_source_parameter_position_missing")
    parameter = parameters[position]
    parameter_id = parameter.get("id")
    if not isinstance(parameter_id, str) or not parameter_id:
        raise _Unknown("default_source_parameter_id_missing")
    occurrences = [node for node in nodes if node.get("id") == parameter_id]
    full_parameters = [node for node in occurrences
                       if node.get("kind") == "ParmVarDecl" and
                       isinstance(node.get("range"), dict) and node.get("range")]
    if (len(full_parameters) != 1 or full_parameters[0] is not parameter or
            any(node.get("kind") != "ParmVarDecl" for node in occurrences)):
        raise _Unknown("default_source_parameter_id_ambiguous")
    if parameter.get("init") != "c":
        raise _Unknown("default_source_parameter_has_no_local_initializer")
    sources = [child for child in _children(parameter)
               if not str(child.get("kind", "")).endswith("Attr")]
    if len(sources) != 1:
        raise _Unknown("default_source_parameter_initializer_ambiguous")
    source = sources[0]
    if not _default_expression_shape(source):
        raise _Unknown("default_source_expression_unsupported")
    source_nodes = []
    pending = [source]
    while pending:
        current = pending.pop()
        source_nodes.append(current)
        pending.extend(_children(current))
    for current in source_nodes:
        identifier = current.get("id")
        if (not isinstance(identifier, str) or not identifier or
                sum(node.get("id") == identifier for node in nodes) != 1):
            raise _Unknown("default_source_expression_id_ambiguous")
        if not _supported_default_type(current):
            raise _Unknown("default_source_type_unsupported")
    if (not _supported_default_type(parameter) or not _supported_default_type(source) or
            not _supported_default_type(callpoint)):
        raise _Unknown("default_source_type_unsupported")
    expected = _canonical_type(parameter)
    if _canonical_type(source) != expected or _canonical_type(callpoint) != expected:
        raise _Unknown("default_source_type_mismatch")
    return source, {
        "schema_version": "constructor-default-source/v1",
        "constructor_declaration_id": constructor_id,
        "parameter_id": parameter_id,
        "parameter_position": position,
    }


def _direct_constructor(root, expression, budget):
    """Resolve selected ctorType only inside an exactly typedef-anchored record.

    Clang's ctorType is emitted from CE->getConstructor()->getType(). Never
    search globally by class name, infer overload selection, or infer copy effects.
    """
    if expression.get("constructionKind") != "complete":
        raise _Unknown("direct_constructor_not_complete_object")
    info = _type(expression) or {}
    alias_id = info.get("typeAliasDeclId")
    if not isinstance(alias_id, str) or not alias_id:
        raise _Unknown("direct_constructor_type_anchor_missing")
    alias = _unique_node(root, alias_id, budget)
    if alias.get("kind") not in {"TypedefDecl", "TypeAliasDecl"}:
        raise _Unknown("direct_constructor_type_anchor_not_alias")
    types = _children(alias)
    if len(types) != 1:
        raise _Unknown("direct_constructor_alias_shape_unsupported")
    record_type = types[0]
    if record_type.get("kind") == "ElaboratedType":
        types = _children(record_type)
        if len(types) != 1:
            raise _Unknown("direct_constructor_alias_shape_unsupported")
        record_type = types[0]
    reference = record_type.get("decl", {})
    if (record_type.get("kind") != "RecordType" or not isinstance(reference, dict) or
            reference.get("kind") != "CXXRecordDecl" or
            not isinstance(reference.get("id"), str) or not reference["id"]):
        raise _Unknown("direct_constructor_alias_not_exact_record")
    # Upstream Clang omits desugaredQualType when its printed spelling equals
    # qualType. The exact alias -> record ID anchor above remains mandatory;
    # this fallback does not resolve an alias by its name.
    actual_type = info.get("desugaredQualType", info.get("qualType"))
    if (not isinstance(actual_type, str) or not actual_type or
            actual_type != (_type(record_type) or {}).get("qualType")):
        raise _Unknown("direct_constructor_record_type_mismatch")
    record = _unique_node(root, reference["id"], budget)
    if record.get("kind") != "CXXRecordDecl" or record.get("completeDefinition") is not True:
        raise _Unknown("direct_constructor_record_not_complete")
    members = _children(record)
    if record.get("bases") or any(member.get("kind") in {
            "FunctionTemplateDecl", "UsingDecl", "UsingShadowDecl"} for member in members):
        raise _Unknown("direct_constructor_record_selection_unsupported")
    ctor_info = expression.get("ctorType")
    ctor_type = ctor_info.get("qualType") if isinstance(ctor_info, dict) else None
    if not isinstance(ctor_type, str) or not ctor_type:
        raise _Unknown("direct_constructor_signature_missing")
    candidates = [member for member in members if member.get("kind") == "CXXConstructorDecl"
                  and (_type(member) or {}).get("qualType") == ctor_type]
    if len(candidates) != 1:
        raise _Unknown("direct_constructor_signature_not_unique_in_record")
    constructor = candidates[0]
    identifier = constructor.get("id")
    if not isinstance(identifier, str) or not identifier:
        raise _Unknown("constructor_declaration_reference_missing")
    if _unique_node(root, identifier, budget) is not constructor:
        raise _Unknown("constructor_identity_declaration_not_unique")
    parameters = [member for member in _children(constructor) if member.get("kind") == "ParmVarDecl"]
    if constructor.get("variadic") or len(parameters) != len(_children(expression)):
        raise _Unknown("direct_constructor_parameter_count_mismatch")
    return {"id": identifier, "kind": "CXXConstructorDecl", "type": _type(constructor)}, {
        "mode": "exact_alias_record_and_unique_selected_constructor_type",
        "alias_declaration_id": alias_id, "record_declaration_id": reference["id"],
        "constructor_declaration_id": identifier, "selected_constructor_type": ctor_type,
        "max_ast_nodes_per_scan": budget,
        "premise": "faithful single-TU Clang AST with ctorType from selected constructor",
        "copy_or_move_semantics": "not_established",
    }, constructor, parameters


def _argument(root: dict[str, Any], node: dict[str, Any], position: int,
              int_bits: int, *, constructor: dict[str, Any] | None = None,
              parameters: list[dict[str, Any]] | None = None,
              budget: int = MAX_AST_NODES) -> dict[str, Any]:
    item: dict[str, Any] = {
        "position": position, "status": "unknown", "reason": None,
        "argument_ast": node, "default_argument": False, "default_source_ast": None,
        "default_source_binding": None, "default_source_reason": None,
        "leaf_kind": None, "declaration_id": None, "casts": [],
        "pre_conversion_constant": None, "range": node.get("range"),
        "conversion_semantics": "not_established",
    }
    current = node
    if current.get("kind") == "CXXDefaultArgExpr":
        item["default_argument"] = True
        children = _children(current)
        if len(children) == 0 and constructor is not None and parameters is not None:
            try:
                source, binding = _recover_default_source(
                    root, constructor, parameters, position, current, budget)
                item["default_source_ast"] = source
                item["default_source_binding"] = binding
                current = source
            except _Unknown as error:
                item["default_source_reason"] = error.reason
                item["reason"] = "default_argument_source_missing_or_ambiguous"
                return item
        elif len(children) != 1:
            item["default_source_reason"] = "default_source_callpoint_shape_unsupported"
            item["reason"] = "default_argument_source_missing_or_ambiguous"
            return item
        else:
            item["default_source_ast"] = children[0]
            current = children[0]
    current = _unwrap_parens(current)
    while current.get("kind") == "ImplicitCastExpr":
        children = _children(current)
        if len(children) != 1:
            item["reason"] = "ambiguous_argument_cast"
            return item
        if current.get("castKind") not in ARG_CASTS:
            item["reason"] = "unsupported_argument_cast"
            return item
        item["casts"].append(_record_cast(current, children[0]))
        current = _unwrap_parens(children[0])
    item["leaf_kind"] = current.get("kind")
    if current.get("kind") == "IntegerLiteral":
        try:
            value = int(str(current.get("value")), 0)
        except (TypeError, ValueError):
            item["reason"] = "invalid_integer_literal"
            return item
        if not -(1 << (int_bits - 1)) <= value <= (1 << (int_bits - 1)) - 1:
            item["reason"] = "pre_conversion_signed_integer_out_of_range"
            return item
        item["pre_conversion_constant"] = {"status": "evaluated", "value": value,
                                            "source": "integer_literal",
                                            "range": current.get("range")}
        item["status"] = "evidence"
        return item
    if current.get("kind") == "DeclRefExpr":
        referenced = current.get("referencedDecl")
        if not isinstance(referenced, dict) or referenced.get("kind") not in {"VarDecl", "ParmVarDecl"}:
            item["reason"] = "argument_reference_not_variable_or_parameter"
            return item
        declaration_id = referenced.get("id")
        if not isinstance(declaration_id, str):
            item["reason"] = "argument_declaration_id_missing"
            return item
        item["declaration_id"] = declaration_id
        if referenced.get("kind") == "VarDecl":
            constant = evaluate(root, declaration_id, int_bits)
            if constant.get("status") == "evaluated":
                item["pre_conversion_constant"] = {"status": "evaluated",
                    "value": constant["value"], "source": "signed_int_declaration",
                    "declaration_id": declaration_id, "evaluation": constant}
                item["status"] = "evidence"
                return item
            item["constant_evaluation"] = constant
        item["status"] = "symbolic"
        return item
    item["reason"] = "unsupported_argument_expression"
    return item


def inspect(root: object, expression: object, int_bits: int,
            *, max_ast_nodes: int | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema_version": "constructor-arguments/v1", "status": "unknown", "reason": None,
        "int_bits": int_bits, "expression_ast": expression if isinstance(expression, dict) else None,
        "expression_type": None, "constructor_declaration_id": None,
        "default_constructor_declaration_ast": None,
        "constructor_reference": None, "constructor_expression_ast": None,
        "constructor_identity": None,
        "constructor_type": None, "casts": [], "arguments": [],
        "constructor_semantics": "not_established", "field_mapping": "not_established",
        "actual_configuration_values": "not_established",
        "conversion_semantics": "not_established", "checked": False,
        "deployable": False, "relation_recovery": "incomplete",
    }
    if not isinstance(root, dict):
        result["reason"] = "root_not_object"
        return result
    if not isinstance(expression, dict):
        result["reason"] = "expression_not_object"
        return result
    if type(int_bits) is not int or not 2 <= int_bits <= 128:
        result["reason"] = "invalid_int_bits"
        return result
    budget = MAX_AST_NODES if max_ast_nodes is None else max_ast_nodes
    if type(budget) is not int or not 1 <= budget <= HARD_MAX_AST_NODES:
        result["reason"] = "invalid_constructor_identity_budget"
        return result
    try:
        outer = _unwrap_parens(expression)
        result["expression_type"] = _type(outer)
        if outer.get("kind") == "CXXConstructExpr":
            constructor = outer
            conversion, identity, default_constructor, parameters = _direct_constructor(
                root, constructor, budget)
            result["constructor_identity"] = identity
            result["default_constructor_declaration_ast"] = default_constructor
        elif outer.get("kind") == "CXXFunctionalCastExpr" and outer.get("castKind") == "ConstructorConversion":
            conversion = outer.get("conversionFunc")
            if (not isinstance(conversion, dict) or conversion.get("kind") != "CXXConstructorDecl" or
                    not isinstance(conversion.get("id"), str)):
                raise _Unknown("constructor_declaration_reference_missing", outer.get("range"))
            constructed = _children(outer)
            if len(constructed) != 1 or constructed[0].get("kind") != "CXXConstructExpr":
                raise _Unknown("constructor_target_missing_or_ambiguous", outer.get("range"))
            constructor = constructed[0]
            default_constructor, parameters = None, None
            result["constructor_identity"] = {"mode": "explicit_conversion_function_reference"}
        else:
            raise _Unknown("not_constructor_functional_cast", outer.get("range"))
        arguments = [_argument(root, argument, position, int_bits,
                               constructor=default_constructor, parameters=parameters,
                               budget=budget)
                     for position, argument in enumerate(_children(constructor))]
        result.update(constructor_declaration_id=conversion["id"], constructor_reference=conversion,
                      constructor_expression_ast=constructor,
                      constructor_type=constructor.get("ctorType") or _type(constructor),
                      arguments=arguments,
                      casts=[cast for argument in arguments for cast in argument["casts"]])
        unknown = [argument for argument in arguments if argument["status"] == "unknown"]
        if unknown:
            result["reason"] = "one_or_more_arguments_unknown"
            return result
        result["status"] = "inspected"
    except _Unknown as error:
        result["reason"], result["unknown_range"] = error.reason, error.range
    return result
