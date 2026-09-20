"""Recover exact field-to-parameter forwarding in one constructor definition."""

from __future__ import annotations

from typing import Any

ALLOWED_CASTS = {"LValueToRValue", "NoOp"}


class _Unknown(Exception):
    def __init__(self, reason: str, range_value: object = None):
        self.reason, self.range = reason, range_value


def _children(node: dict[str, Any]) -> list[dict[str, Any]]:
    inner = node.get("inner", [])
    return [child for child in inner if isinstance(child, dict) and child] if isinstance(inner, list) else []


def _walk(node: dict[str, Any]):
    yield node
    for child in _children(node):
        yield from _walk(child)


def _type_info(node: dict[str, Any]) -> dict[str, Any] | None:
    return node.get("type") if isinstance(node.get("type"), dict) else None


def _canonical_type(node: dict[str, Any]) -> str | None:
    info = _type_info(node)
    if not info:
        return None
    return info.get("desugaredQualType") or info.get("qualType")


def _contains_id(node: dict[str, Any], identifier: str) -> bool:
    return any(descendant.get("id") == identifier for descendant in _walk(node))


def recover(root: object, constructor_id: str) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema_version": "constructor-fields/v1", "status": "unknown", "reason": None,
        "constructor_declaration_id": constructor_id, "constructor_range": None,
        "record_declaration_id": None, "record_name": None,
        "record_completeness": "not_established", "field_mappings": [], "casts": [],
        "constructor_semantics": "not_established", "field_mapping_semantics": "structural_only",
        "conversion_semantics": "not_established",
        "actual_configuration_values": "not_established", "checked": False,
        "deployable": False, "relation_recovery": "incomplete",
    }
    if not isinstance(root, dict):
        result["reason"] = "root_not_object"
        return result
    try:
        matches = [node for node in _walk(root)
                   if node.get("kind") == "CXXConstructorDecl" and node.get("id") == constructor_id]
        definitions: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for constructor in matches:
            bodies = [child for child in _children(constructor) if child.get("kind") == "CompoundStmt"]
            if len(bodies) == 1:
                definitions.append((constructor, bodies[0]))
            elif len(bodies) > 1:
                raise _Unknown("constructor_has_multiple_bodies", constructor.get("range"))
        if len(definitions) != 1:
            raise _Unknown("constructor_unique_definition_not_found")
        constructor, body = definitions[0]
        result["constructor_range"] = constructor.get("range")
        if _children(body):
            raise _Unknown("constructor_body_not_empty", body.get("range"))
        parameters = [child for child in _children(constructor) if child.get("kind") == "ParmVarDecl"]
        parameter_ids = [parameter.get("id") for parameter in parameters]
        if not all(isinstance(identifier, str) for identifier in parameter_ids) or len(set(parameter_ids)) != len(parameter_ids):
            raise _Unknown("constructor_parameter_ids_missing_or_duplicate", constructor.get("range"))
        parameter_positions = {identifier: position for position, identifier in enumerate(parameter_ids)}
        parameter_nodes = {parameter["id"]: parameter for parameter in parameters}
        initializers = [child for child in _children(constructor) if child.get("kind") == "CXXCtorInitializer"]
        if not initializers:
            raise _Unknown("constructor_has_no_field_initializers", constructor.get("range"))

        mappings: list[dict[str, Any]] = []
        all_casts: list[dict[str, Any]] = []
        field_ids: set[str] = set()
        mapped_parameters: list[str] = []
        for initializer in initializers:
            any_init = initializer.get("anyInit")
            if not isinstance(any_init, dict) or any_init.get("kind") != "FieldDecl":
                raise _Unknown("base_or_delegating_initializer_unsupported", initializer.get("range"))
            field_id = any_init.get("id")
            if not isinstance(field_id, str):
                raise _Unknown("field_id_missing", initializer.get("range"))
            if field_id in field_ids:
                raise _Unknown("duplicate_field_initializer", initializer.get("range"))
            field_ids.add(field_id)
            expressions = _children(initializer)
            if len(expressions) != 1:
                raise _Unknown("field_initializer_expression_missing_or_ambiguous", initializer.get("range"))
            current = expressions[0]
            casts: list[dict[str, Any]] = []
            while current.get("kind") in {"ParenExpr", "ImplicitCastExpr"}:
                wrapped = _children(current)
                if len(wrapped) != 1:
                    raise _Unknown("ambiguous_field_initializer_wrapper", current.get("range"))
                if current.get("kind") == "ImplicitCastExpr":
                    if current.get("castKind") not in ALLOWED_CASTS:
                        raise _Unknown("unsupported_field_initializer_cast", current.get("range"))
                    casts.append({"kind": current.get("kind"), "cast_kind": current.get("castKind"),
                                  "source_type": _type_info(wrapped[0]),
                                  "destination_type": _type_info(current), "range": current.get("range"),
                                  "conversion_semantics": "not_established"})
                current = wrapped[0]
            referenced = current.get("referencedDecl")
            if (current.get("kind") != "DeclRefExpr" or not isinstance(referenced, dict) or
                    referenced.get("kind") != "ParmVarDecl" or
                    not isinstance(referenced.get("id"), str)):
                raise _Unknown("field_initializer_not_exact_parameter_reference", current.get("range"))
            parameter_id = referenced["id"]
            if parameter_id not in parameter_positions:
                raise _Unknown("field_initializer_parameter_not_constructor_parameter", current.get("range"))
            parameter = parameter_nodes[parameter_id]
            field_type, parameter_type = _canonical_type(any_init), _canonical_type(parameter)
            if field_type is None or parameter_type is None or field_type != parameter_type:
                raise _Unknown("field_parameter_desugared_type_mismatch", initializer.get("range"))
            mapped_parameters.append(parameter_id)
            mapping = {"field_id": field_id, "field_name": any_init.get("name"),
                       "field_type": _type_info(any_init), "parameter_id": parameter_id,
                       "parameter_position": parameter_positions[parameter_id],
                       "parameter_type": _type_info(parameter), "initializer_range": initializer.get("range"),
                       "expression_range": expressions[0].get("range"), "casts": casts}
            mappings.append(mapping)
            all_casts.extend(casts)
        if len(mapped_parameters) != len(parameters) or set(mapped_parameters) != set(parameter_ids):
            raise _Unknown("constructor_not_one_to_one_parameter_forwarding", constructor.get("range"))

        records = [node for node in _walk(root) if node.get("kind") in {"CXXRecordDecl", "RecordDecl"}
                   and _contains_id(node, constructor_id)]
        direct_records = [record for record in records
                          if any(child.get("kind") == "CXXConstructorDecl" and child.get("id") == constructor_id
                                 for child in _children(record))]
        if len(direct_records) == 1:
            record = direct_records[0]
            declared_fields = {child.get("id") for child in _children(record)
                               if child.get("kind") == "FieldDecl" and isinstance(child.get("id"), str)}
            if declared_fields != field_ids:
                raise _Unknown("constructor_field_initializers_not_complete_for_record", record.get("range"))
            result.update(record_declaration_id=record.get("id"), record_name=record.get("name"),
                          record_completeness="all_direct_record_fields_initialized")
        else:
            result["record_completeness"] = "record_ownership_not_uniquely_established"
        result.update(status="recovered", field_mappings=mappings, casts=all_casts)
    except _Unknown as error:
        result["reason"], result["unknown_range"] = error.reason, error.range
    return result
