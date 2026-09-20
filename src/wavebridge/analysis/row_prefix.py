"""Recover a strict row-offset prefix without interpreting coordinate getters."""

from __future__ import annotations

from typing import Any

from wavebridge.analysis.initializer_evidence import inspect
from wavebridge.analysis.normalization_output import recover as recover_normalization

IMPLICIT_CASTS = {"LValueToRValue", "IntegralCast", "NoOp", "ArrayToPointerDecay"}


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


def _type(node: dict[str, Any]) -> str | None:
    info = node.get("type")
    return info.get("qualType") if isinstance(info, dict) else None


def _record_cast(node: dict[str, Any], child: dict[str, Any], casts: list[dict[str, Any]]) -> None:
    casts.append({"kind": node.get("kind"), "cast_kind": node.get("castKind"),
                  "source_type": _type(child), "destination_type": _type(node),
                  "range": node.get("range"), "semantic_obligation": "not_discharged"})


def _unwrap_implicit(node: dict[str, Any], casts: list[dict[str, Any]]) -> dict[str, Any]:
    current = node
    while current.get("kind") in {"ParenExpr", "ImplicitCastExpr"}:
        children = _children(current)
        if len(children) != 1:
            raise _Unknown("ambiguous_wrapper", current.get("range"))
        if current.get("kind") == "ImplicitCastExpr":
            if current.get("castKind") not in IMPLICIT_CASTS:
                raise _Unknown("unsupported_implicit_cast", current.get("range"))
            _record_cast(current, children[0], casts)
        current = children[0]
    return current


def _ref(node: dict[str, Any], casts: list[dict[str, Any]], kind: str | None = None) -> str:
    current = _unwrap_implicit(node, casts)
    referenced = current.get("referencedDecl")
    if current.get("kind") != "DeclRefExpr" or not isinstance(referenced, dict):
        raise _Unknown("expected_exact_declref", current.get("range"))
    if kind is not None and referenced.get("kind") != kind:
        raise _Unknown("unexpected_reference_kind", current.get("range"))
    identifier = referenced.get("id")
    if not isinstance(identifier, str):
        raise _Unknown("reference_id_missing", current.get("range"))
    return identifier


def _single_const_int(statement: dict[str, Any], reason: str) -> dict[str, Any]:
    if statement.get("kind") != "DeclStmt":
        raise _Unknown(reason, statement.get("range"))
    variables = [child for child in _children(statement) if child.get("kind") == "VarDecl"]
    if len(variables) != 1 or _type(variables[0]) != "const int":
        raise _Unknown(reason, statement.get("range"))
    return variables[0]


def _initializer(variable: dict[str, Any]) -> dict[str, Any]:
    values = [child for child in _children(variable)
              if not str(child.get("kind", "")).endswith("Attr")]
    if variable.get("init") is None or len(values) != 1:
        raise _Unknown("initializer_missing_or_ambiguous", variable.get("range"))
    return values[0]


def _cast_signature(casts: list[dict[str, Any]]) -> list[tuple[object, object, object, object]]:
    return [(cast["kind"], cast["cast_kind"], cast["source_type"], cast["destination_type"])
            for cast in casts]


def _offset(statement: dict[str, Any], pointer_id: str, row_id: str, count_id: str,
            all_casts: list[dict[str, Any]]) -> dict[str, Any]:
    statement_casts: list[dict[str, Any]] = []
    update = _unwrap_implicit(statement, statement_casts)
    children = _children(update)
    if update.get("kind") != "CompoundAssignOperator" or update.get("opcode") != "+=" or len(children) != 2:
        raise _Unknown("prefix_pointer_update_not_plus_equal", update.get("range"))
    if _ref(children[0], statement_casts, "ParmVarDecl") != pointer_id:
        raise _Unknown("prefix_pointer_update_target_mismatch", children[0].get("range"))
    product = _unwrap_implicit(children[1], statement_casts)
    operands = _children(product)
    if product.get("kind") != "BinaryOperator" or product.get("opcode") != "*" or len(operands) != 2:
        raise _Unknown("prefix_offset_not_row_times_count", product.get("range"))

    row_casts: list[dict[str, Any]] = []
    explicit = _unwrap_implicit(operands[0], row_casts)
    explicit_children = _children(explicit)
    if (explicit.get("kind") != "CXXStaticCastExpr" or explicit.get("castKind") not in {"IntegralCast", "NoOp"} or
            len(explicit_children) != 1 or _type(explicit) not in {"int64_t", "long", "long long"}):
        raise _Unknown("row_not_explicit_int64_static_cast", explicit.get("range"))
    _record_cast(explicit, explicit_children[0], row_casts)
    if _ref(explicit_children[0], row_casts, "VarDecl") != row_id:
        raise _Unknown("offset_uses_other_row", explicit_children[0].get("range"))

    count_casts: list[dict[str, Any]] = []
    if _ref(operands[1], count_casts, "ParmVarDecl") != count_id:
        raise _Unknown("offset_uses_other_count", operands[1].get("range"))
    all_casts.extend(statement_casts)
    all_casts.extend(row_casts)
    all_casts.extend(count_casts)
    return {"range": update.get("range"), "product_range": product.get("range"),
            "offset_ast": children[1], "update_ast": statement,
            "statement_cast_signature": _cast_signature(statement_casts),
            "row_cast_signature": _cast_signature(row_casts),
            "count_cast_signature": _cast_signature(count_casts),
            "product_type": _type(product)}


def recover(root: object, function_id: str, int_bits: int) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema_version": "row-prefix-recovery/v1", "status": "unknown", "reason": None,
        "function_id": function_id, "int_bits": int_bits, "normalization_output": None,
        "row_declaration_id": None, "start_declaration_id": None,
        "row_initializer_ast": None, "start_initializer_ast": None,
        "row_initializer_evidence": None, "start_initializer_evidence": None,
        "source_parameter_id": None, "output_parameter_id": None, "count_parameter_id": None,
        "source_offset": None, "output_offset": None, "casts": [], "ranges": {},
        "conversion_semantics": "not_established",
        "offset_integer_width": "not_established",
        "coordinate_semantics": "not_established",
        "preconditions": {"prefix_coordinate_meaning": "not_established",
                          "pointer_arithmetic_bounds": "not_established",
                          "offset_integer_abi_width": "not_established",
                          "aliasing": "not_established", "floating_point_semantics": "not_established",
                          "complete_source_validity": "not_established"},
        "checked": False, "deployable": False, "relation_recovery": "incomplete",
    }
    if not isinstance(root, dict):
        result["reason"] = "root_not_object"
        return result
    if type(int_bits) is not int or not 2 <= int_bits <= 128:
        result["reason"] = "invalid_int_bits"
        return result
    try:
        normalization = recover_normalization(root, function_id, int_bits)
        result["normalization_output"] = normalization
        if normalization.get("status") != "recovered":
            raise _Unknown("normalization_output_not_recovered")
        matches = [node for node in _walk(root) if node.get("kind") in {"FunctionDecl", "CXXMethodDecl"}
                   and node.get("id") == function_id]
        bodies = [(node, child) for node in matches for child in _children(node)
                  if child.get("kind") == "CompoundStmt"]
        if len(bodies) != 1:
            raise _Unknown("function_unique_body_not_found")
        _, body = bodies[0]
        statements = _children(body)
        accumulator_id = normalization["local_contribution"]["accumulator_declaration_id"]
        accumulator_indices = [index for index, statement in enumerate(statements)
                               if any(child.get("kind") == "VarDecl" and child.get("id") == accumulator_id
                                      for child in _children(statement))]
        if len(accumulator_indices) != 1:
            raise _Unknown("accumulator_statement_not_unique", body.get("range"))
        prefix = statements[:accumulator_indices[0]]
        if len(prefix) != 4:
            raise _Unknown("prefix_not_exactly_four_statements", body.get("range"))
        row = _single_const_int(prefix[0], "row_not_first_const_int")
        start = _single_const_int(prefix[1], "start_not_second_const_int")
        row_id, start_id = row.get("id"), start.get("id")
        if not isinstance(row_id, str) or not isinstance(start_id, str):
            raise _Unknown("row_or_start_id_missing")
        row_initializer, start_initializer = _initializer(row), _initializer(start)
        loop_start = normalization["local_loop"].get("start", {})
        if loop_start.get("kind") != "declaration_reference" or loop_start.get("declaration_id") != start_id:
            raise _Unknown("start_not_local_loop_start", start.get("range"))
        if normalization["output_loop"].get("start", {}).get("declaration_id") != start_id:
            raise _Unknown("start_not_output_loop_start", start.get("range"))
        source_id = normalization["source_parameter_id"]
        output_id = normalization["output_parameter_id"]
        count_id = normalization["count_parameter_id"]
        casts: list[dict[str, Any]] = []
        source_offset = _offset(prefix[2], source_id, row_id, count_id, casts)
        output_offset = _offset(prefix[3], output_id, row_id, count_id, casts)
        if (source_offset["statement_cast_signature"] != output_offset["statement_cast_signature"] or
                source_offset["row_cast_signature"] != output_offset["row_cast_signature"] or
                source_offset["count_cast_signature"] != output_offset["count_cast_signature"] or
                source_offset["product_type"] != output_offset["product_type"]):
            raise _Unknown("source_output_offset_cast_structure_mismatch", prefix[3].get("range"))
        result.update(status="recovered", row_declaration_id=row_id, start_declaration_id=start_id,
                      row_initializer_ast=row_initializer, start_initializer_ast=start_initializer,
                      row_initializer_evidence=inspect(root, row_id),
                      start_initializer_evidence=inspect(root, start_id),
                      source_parameter_id=source_id, output_parameter_id=output_id,
                      count_parameter_id=count_id, source_offset=source_offset,
                      output_offset=output_offset, casts=casts,
                      ranges={"prefix": [statement.get("range") for statement in prefix],
                              "row": row.get("range"), "start": start.get("range")})
    except _Unknown as error:
        result["reason"], result["unknown_range"] = error.reason, error.range
    return result
