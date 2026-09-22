"""Check exact per-field integer copying for one direct record construction."""

from __future__ import annotations

from typing import Any

from wavebridge.analysis.constructor_arguments import inspect as inspect_constructor
from wavebridge.verification.integer_selection import BUILTIN_INTEGER_TYPES, _hash
from wavebridge.verification.kernel_arguments import _Unknown, _abi_type

MAX_AST_NODES = 1_000_000
HARD_MAX_AST_NODES = 10_000_000
MAX_FIELDS = 64


class _Rejected(Exception):
    def __init__(self, reason: str, detail: object = None):
        self.reason, self.detail = reason, detail


def _children(node: object, *, strict: bool = True) -> list[dict[str, Any]]:
    if not isinstance(node, dict):
        raise _Unknown("ast_node_not_object")
    children = node.get("inner", [])
    if not isinstance(children, list) or any(not isinstance(child, dict) for child in children):
        raise _Unknown("ast_children_not_list_of_objects")
    if strict and any(not child for child in children):
        raise _Unknown("selected_ast_contains_empty_placeholder")
    return [child for child in children if child]


def _type(node: dict[str, Any]) -> dict[str, Any]:
    value = node.get("type")
    if not isinstance(value, dict):
        raise _Unknown("type_evidence_missing")
    return value


def _raw_type(node: dict[str, Any]) -> str:
    info = _type(node)
    value = info.get("desugaredQualType") or info.get("qualType")
    if not isinstance(value, str) or not value:
        raise _Unknown("type_evidence_missing")
    return value


def _local_effects(record, declaration, parameter, fields, mappings):
    """Classify AST-role accesses, not aliasing or lifetime-wide preservation."""
    result = {
        "schema_version": "record-copy-local-effects/v1",
        "status": "unknown", "reason": "declaration_effect_subset_unsupported",
        "scope": "selected_constructor_argument_binding_initializers_and_body_only",
        "source_parameter_accesses": "not_established",
        "destination_accesses": "not_established",
        "additional_address_publication": "not_established",
        "field_ids": [],
        "source_program_checked": False, "deployable": False,
        "assumptions": [
            "the parent value check and its input hashes bind this local classification",
            "the AST faithfully describes a valid source program under the declared integer ABI",
            "source fields are initialized and readable through the live evaluated argument",
            "the selected constructor returns normally",
        ],
        "source_destination_nonoverlap": "not_established",
        "concurrent_or_prior_alias_effects": "not_established",
        "surrounding_cleanup_and_destructor_effects": "not_established",
        "source_object_preservation": "not_established",
        "target_allocation_and_lifetime": "not_established",
        "interpretation": "accesses_by_AST_source_parameter_and_destination_roles_not_dynamic_storage_disjointness",
    }
    # Record attributes can affect layout/semantics; do not interpret them by
    # spelling or inherit the value checker's broader attribute tolerance.
    if any(str(child.get("kind", "")).endswith("Attr") for child in _children(record)):
        return result
    if any(declaration.get(flag) is True for flag in (
            "isDeleted", "explicitlyDeleted", "isInvalid", "isInvalidDecl", "isVariadic")):
        return result
    if any(parameter.get(flag) is True for flag in (
            "isParameterPack", "isPackExpansion", "isInvalid", "isInvalidDecl")):
        return result
    if any(field.get(flag) is True for field in fields for flag in ("isInvalid", "isInvalidDecl")):
        return result
    for child in _children(declaration):
        if child.get("kind") in {"ParmVarDecl", "CXXCtorInitializer", "CompoundStmt"}:
            continue  # exact count and full expressions were checked above
        if child.get("kind") not in {"CUDAHostAttr", "CUDADeviceAttr"} or _children(child):
            return result
    if (_children(parameter) or parameter.get("init") is not None or
            parameter.get("hasInheritedDefaultArg") is True or
            parameter.get("hasDefaultArg") is True or
            parameter.get("hasUninstantiatedDefaultArg") is True or
            parameter.get("hasUnparsedDefaultArg") is True or
            any(_children(field) or field.get("hasInClassInitializer") is True
                for field in fields)):
        return result
    result.update(
        status="checked", reason=None,
        source_parameter_accesses="direct_integer_field_reads_only",
        destination_accesses="direct_field_initializations_only",
        additional_address_publication="not_observed_beyond_selected_const_reference_binding",
        field_ids=[mapping["target_field_id"] for mapping in mappings],
    )
    return result


def check(root: object, expression_id: object, integer_types: object,
          *, max_ast_nodes: int | None = None) -> dict[str, Any]:
    budget = MAX_AST_NODES if max_ast_nodes is None else max_ast_nodes
    result: dict[str, Any] = {
        "schema_version": "record-copy-check/v1", "status": "unknown", "reason": None,
        "expression_id": expression_id, "constructor_declaration_id": None,
        "expression_ast_occurrences": 0,
        "record_declaration_id": None, "source_declaration_id": None,
        "source_declaration_binding": "lexical_declref_only",
        "source_object_identity": "not_established",
        "constructor_arguments": None, "field_mappings": [],
        "local_copy_effects": {"status": "unknown", "reason": "copy_value_relation_not_checked"},
        "scope": "evaluated_copy_argument_per_field_integer_value_equality_at_direct_construction",
        "source_program_checked": False, "deployable": False,
        "source_object_preservation": "not_established",
        "source_initialization_relation": "not_established",
        "launch_semantics": "not_established",
        "assumptions": [
            "the AST is a faithful complete single translation unit",
            "the explicit integer ABI matches the compilation target",
            "the source object is alive and valid while the constructor reads its fields",
            "the copied integer fields are initialized and each field read has a defined value",
            "the source program is valid",
            "the constructor call returns normally",
            "the recorded source declaration ID is only the lexical DeclRef binding",
            "lambda capture resolution and the runtime origin or identity of the evaluated copy argument are not established",
        ],
        "budget": {"max_ast_nodes": budget, "max_fields": MAX_FIELDS},
    }
    if type(budget) is not int or not 1 <= budget <= HARD_MAX_AST_NODES:
        result["reason"] = "invalid_ast_node_budget"
        return result
    if (not isinstance(root, dict) or not isinstance(expression_id, str) or not expression_id or
            not isinstance(integer_types, dict)):
        result["reason"] = "invalid_inputs"
        return result
    try:
        result["input_sha256"] = {
            "root": _hash(root), "expression_id": _hash(expression_id),
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
        expressions = [node for node in nodes if node.get("id") == expression_id]
        result["expression_ast_occurrences"] = len(expressions)
        if not expressions:
            raise _Unknown("copy_expression_id_missing")
        if any(node != expressions[0] for node in expressions[1:]):
            raise _Unknown("copy_expression_occurrences_conflict")
        expression = expressions[0]
        if expression.get("kind") != "CXXConstructExpr":
            raise _Unknown("copy_expression_not_direct_constructor")

        int_abi = _abi_type({"qualType": "int"}, integer_types)
        arguments = inspect_constructor(root, expression, int_abi[1], max_ast_nodes=budget)
        result["constructor_arguments"] = arguments
        if arguments.get("status") != "inspected":
            raise _Unknown("copy_constructor_argument_recovery_unsupported")
        identity = arguments.get("constructor_identity")
        if (not isinstance(identity, dict) or identity.get("mode") !=
                "exact_alias_record_and_unique_selected_constructor_type"):
            raise _Unknown("copy_constructor_identity_not_exact_direct_record")
        constructor_id = arguments.get("constructor_declaration_id")
        record_id = identity.get("record_declaration_id")
        result.update(constructor_declaration_id=constructor_id,
                      record_declaration_id=record_id)
        if (not isinstance(constructor_id, str) or not constructor_id or
                not isinstance(record_id, str) or not record_id):
            raise _Unknown("copy_constructor_or_record_id_missing")

        declaration = arguments.get("default_constructor_declaration_ast")
        if (not isinstance(declaration, dict) or declaration.get("kind") != "CXXConstructorDecl" or
                declaration.get("id") != constructor_id):
            raise _Unknown("copy_constructor_declaration_ast_missing")
        constructor_occurrences = [node for node in nodes if node.get("id") == constructor_id]
        if len(constructor_occurrences) != 1 or constructor_occurrences[0] is not declaration:
            raise _Unknown("copy_constructor_declaration_not_unique")
        if declaration.get("previousDecl") is not None or any(
                node.get("kind") == "CXXConstructorDecl" and
                node.get("previousDecl") == constructor_id for node in nodes):
            raise _Unknown("copy_constructor_redeclaration_unsupported")

        records = [node for node in nodes if node.get("kind") == "CXXRecordDecl" and
                   node.get("id") == record_id]
        if len(records) != 1:
            raise _Unknown("copy_record_declaration_not_unique")
        record = records[0]
        definition_data = record.get("definitionData")
        if (record.get("completeDefinition") is not True or record.get("bases") or
                record.get("tagUsed") == "union" or record.get("isUnion") is True):
            raise _Unknown("copy_record_shape_unsupported")
        if isinstance(definition_data, dict) and definition_data.get("isPolymorphic") is True:
            raise _Unknown("copy_polymorphic_record_unsupported")
        record_type = _raw_type(expression)
        expression_type = _type(expression)
        record_spelling = expression_type.get("qualType")
        alias_id = expression_type.get("typeAliasDeclId")
        if (not isinstance(record_spelling, str) or not record_spelling or
                not isinstance(alias_id, str) or not alias_id or
                alias_id != identity.get("alias_declaration_id")):
            raise _Unknown("copy_record_alias_binding_missing")

        fields = [child for child in _children(record) if child.get("kind") == "FieldDecl"]
        if not fields or len(fields) > MAX_FIELDS:
            raise _Unknown("copy_record_field_count_unsupported")
        field_ids: list[str] = []
        field_abis: dict[str, tuple[str, int, bool]] = {}
        for field in fields:
            field_id = field.get("id")
            if (not isinstance(field_id, str) or not field_id or field_id in field_ids or
                    field.get("isBitfield") is True or field.get("bitWidthValue") is not None or
                    any(not str(child.get("kind", "")).endswith("Attr")
                        for child in _children(field))):
                raise _Unknown("copy_record_field_shape_unsupported")
            raw = _raw_type(field)
            if "volatile" in raw.split() or "&" in raw or "*" in raw or "[" in raw:
                raise _Unknown("copy_record_field_type_unsupported")
            abi = _abi_type(_type(field), integer_types)
            if abi[0] not in BUILTIN_INTEGER_TYPES:
                raise _Unknown("copy_record_field_not_builtin_integer")
            field_ids.append(field_id)
            field_abis[field_id] = abi
            occurrences = [node for node in nodes if node.get("id") == field_id]
            if len(occurrences) != 1 or occurrences[0] is not field:
                raise _Unknown("copy_field_declaration_not_unique")

        declaration_children = _children(declaration)
        parameters = [child for child in declaration_children if child.get("kind") == "ParmVarDecl"]
        initializers = [child for child in declaration_children if child.get("kind") == "CXXCtorInitializer"]
        bodies = [child for child in declaration_children if child.get("kind") == "CompoundStmt"]
        if (len(parameters) != 1 or len(initializers) != len(fields) or len(bodies) != 1 or
                _children(bodies[0]) or any(not (child.get("kind") in {
                    "ParmVarDecl", "CXXCtorInitializer", "CompoundStmt"} or
                    str(child.get("kind", "")).endswith("Attr"))
                    for child in declaration_children)):
            raise _Unknown("copy_constructor_body_or_member_shape_unsupported")
        parameter = parameters[0]
        parameter_id = parameter.get("id")
        if not isinstance(parameter_id, str) or not parameter_id:
            raise _Unknown("copy_parameter_id_missing")
        parameter_occurrences = [node for node in nodes if node.get("id") == parameter_id]
        if len(parameter_occurrences) != 1 or parameter_occurrences[0] is not parameter:
            raise _Unknown("copy_parameter_declaration_not_unique")
        parameter_type = _raw_type(parameter)
        if parameter_type != f"const {record_spelling} &":
            raise _Unknown("copy_parameter_not_exact_const_record_reference")
        signature = _raw_type(declaration)
        if signature not in {f"void ({parameter_type})", f"void ({parameter_type}) noexcept"}:
            raise _Unknown("copy_constructor_signature_unsupported")

        argument_items = arguments.get("arguments")
        expression_arguments = _children(expression)
        if (not isinstance(argument_items, list) or len(argument_items) != 1 or
                len(expression_arguments) != 1 or
                argument_items[0].get("argument_ast") != expression_arguments[0]):
            raise _Unknown("copy_source_argument_shape_unsupported")
        argument = expression_arguments[0]
        argument_children = _children(argument)
        if (argument.get("kind") != "ImplicitCastExpr" or argument.get("castKind") != "NoOp" or
                argument.get("valueCategory") != "lvalue" or len(argument_children) != 1 or
                _raw_type(argument) != f"const {record_spelling}"):
            raise _Unknown("copy_source_const_binding_unsupported")
        source_ref = argument_children[0]
        referenced_source = source_ref.get("referencedDecl")
        if (source_ref.get("kind") != "DeclRefExpr" or source_ref.get("valueCategory") != "lvalue" or
                _children(source_ref) or
                not isinstance(referenced_source, dict) or
                referenced_source.get("kind") not in {"VarDecl", "ParmVarDecl"} or
                not isinstance(referenced_source.get("id"), str)):
            raise _Unknown("copy_source_not_direct_object_declaration")
        if (_raw_type(source_ref) != record_type or _raw_type(referenced_source) != record_type or
                _type(source_ref).get("typeAliasDeclId") != alias_id or
                _type(referenced_source).get("typeAliasDeclId") != alias_id):
            raise _Unknown("copy_source_record_type_or_alias_mismatch")
        source_id = referenced_source["id"]
        source_matches = [node for node in nodes if node.get("id") == source_id and
                          node.get("kind") == referenced_source.get("kind")]
        if len(source_matches) != 1:
            raise _Unknown("copy_source_declaration_not_unique")
        source = source_matches[0]
        if (_raw_type(source) != record_type or _type(source).get("typeAliasDeclId") != alias_id or
                _type(source) != _type(referenced_source)):
            raise _Unknown("copy_source_declaration_type_mismatch")
        result["source_declaration_id"] = source_id

        mappings: list[dict[str, Any]] = []
        target_ids: set[str] = set()
        for initializer in initializers:
            target = initializer.get("anyInit")
            expressions = _children(initializer)
            if (not isinstance(target, dict) or target.get("kind") != "FieldDecl" or
                    not isinstance(target.get("id"), str) or len(expressions) != 1):
                raise _Unknown("copy_field_initializer_shape_unsupported")
            target_id = target["id"]
            if target_id not in field_abis or target_id in target_ids:
                raise _Rejected("copy_target_field_missing_or_duplicate", target_id)
            target_field = fields[field_ids.index(target_id)]
            if target.get("type") != target_field.get("type"):
                raise _Rejected("copy_target_field_type_mismatch", target_id)
            read = expressions[0]
            read_children = _children(read)
            if (read.get("kind") != "ImplicitCastExpr" or
                    read.get("castKind") != "LValueToRValue" or
                    read.get("valueCategory") != "prvalue" or len(read_children) != 1 or
                    _abi_type(_type(read), integer_types) != field_abis[target_id]):
                raise _Unknown("copy_field_read_shape_or_type_unsupported")
            member = read_children[0]
            member_children = _children(member)
            source_field_id = member.get("referencedMemberDecl")
            if (member.get("kind") != "MemberExpr" or member.get("isArrow") is not False or
                    member.get("valueCategory") != "lvalue" or len(member_children) != 1 or
                    not isinstance(source_field_id, str) or
                    _abi_type(_type(member), integer_types) != field_abis[target_id]):
                raise _Unknown("copy_source_member_shape_or_type_unsupported")
            base = member_children[0]
            referenced_parameter = base.get("referencedDecl")
            if (base.get("kind") != "DeclRefExpr" or base.get("valueCategory") != "lvalue" or
                    _children(base) or
                    not isinstance(referenced_parameter, dict) or
                    referenced_parameter.get("kind") != "ParmVarDecl" or
                    referenced_parameter.get("id") != parameter_id or
                    _raw_type(referenced_parameter) != parameter_type or
                    _raw_type(base) != f"const {record_spelling}"):
                raise _Unknown("copy_source_member_base_not_exact_parameter")
            if source_field_id != target_id:
                raise _Rejected("copy_source_field_does_not_match_target",
                                {"target_field_id": target_id,
                                 "source_field_id": source_field_id})
            target_ids.add(target_id)
            mappings.append({
                "target_field_id": target_id, "source_field_id": source_field_id,
                "field_name": target_field.get("name"),
                "field_type": target_field.get("type"),
                "parameter_id": parameter_id,
                "initializer_range": initializer.get("range"),
                "read_range": read.get("range"),
                "relation": "integer_value_equal_at_copy_evaluation",
            })
        if target_ids != set(field_ids):
            raise _Rejected("copy_fields_not_exactly_covered")
        result.update(status="checked", field_mappings=mappings)
        result["local_copy_effects"] = _local_effects(
            record, declaration, parameter, fields, mappings)
    except _Rejected as error:
        result.update(status="rejected", reason=error.reason)
        if error.detail is not None:
            result["diagnostic"] = error.detail
    except _Unknown as error:
        result["reason"] = error.reason
    return result
