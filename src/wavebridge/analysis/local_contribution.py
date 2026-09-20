"""Recover a narrowly scoped per-column sum-of-squares contribution."""

from __future__ import annotations

from typing import Any

from wavebridge.analysis.column_loops import recover as recover_columns

ALLOWED_CASTS = {"LValueToRValue", "FunctionToPointerDecay", "ArrayToPointerDecay", "NoOp"}
CALL_KINDS = {"CallExpr", "CXXMemberCallExpr", "CXXOperatorCallExpr", "CUDAKernelCallExpr"}
LOOP_KINDS = {"ForStmt", "WhileStmt", "DoStmt", "CXXForRangeStmt"}


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


def _unwrap(node: dict[str, Any]) -> dict[str, Any]:
    current = node
    while current.get("kind") in {"ParenExpr", "ImplicitCastExpr"}:
        children = _children(current)
        if len(children) != 1:
            raise _Unknown("ambiguous_wrapper", current.get("range"))
        if current.get("kind") == "ImplicitCastExpr" and current.get("castKind") not in ALLOWED_CASTS:
            raise _Unknown("unsupported_cast", current.get("range"))
        current = children[0]
    return current


def _ref(node: dict[str, Any], expected_kind: str | None = None) -> str:
    current = _unwrap(node)
    referenced = current.get("referencedDecl")
    if current.get("kind") != "DeclRefExpr" or not isinstance(referenced, dict):
        raise _Unknown("expected_exact_declref", current.get("range"))
    if expected_kind is not None and referenced.get("kind") != expected_kind:
        raise _Unknown("unexpected_reference_kind", current.get("range"))
    identifier = referenced.get("id")
    if not isinstance(identifier, str):
        raise _Unknown("reference_id_missing", current.get("range"))
    return identifier


def _single_var(statement: dict[str, Any], reason: str) -> dict[str, Any]:
    if statement.get("kind") != "DeclStmt":
        raise _Unknown(reason, statement.get("range"))
    declarations = [child for child in _children(statement) if child.get("kind") == "VarDecl"]
    if len(declarations) != 1:
        raise _Unknown(reason, statement.get("range"))
    return declarations[0]


def _initializer(declaration: dict[str, Any]) -> dict[str, Any]:
    values = [child for child in _children(declaration)
              if not str(child.get("kind", "")).endswith("Attr")]
    if declaration.get("init") is None or len(values) != 1:
        raise _Unknown("initializer_missing_or_ambiguous", declaration.get("range"))
    return values[0]


def _float_zero(node: dict[str, Any]) -> bool:
    current = _unwrap(node)
    if current.get("kind") != "FloatingLiteral":
        return False
    try:
        return float(str(current.get("value"))) == 0.0
    except (TypeError, ValueError):
        return False


def _direct_call(call: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    current = _unwrap(call)
    children = _children(current)
    if current.get("kind") != "CallExpr" or not children:
        raise _Unknown("consumer_not_direct_call", current.get("range"))
    callee_id = _ref(children[0], "FunctionDecl")
    return callee_id, children[1:]


def recover(root: object, function_id: str, int_bits: int) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema_version": "local-contribution-recovery/v1", "status": "unknown", "reason": None,
        "function_id": function_id, "int_bits": int_bits, "loop_recurrence": None,
        "loop": None,
        "input_parameter_id": None, "accumulator_declaration_id": None,
        "input_declaration_id": None, "value_declaration_id": None,
        "consumer_declaration_id": None, "consumer": None, "ranges": {},
        "prefix_scope": "not_analyzed", "prefix_statement_ranges": [],
        "operation": "sum_of_squares",
        "preconditions": {"aliasing": "not_established", "coordinate_semantics": "not_established",
                          "floating_point_semantics": "not_established",
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
        matches = [node for node in _walk(root) if node.get("kind") in {"FunctionDecl", "CXXMethodDecl"}
                   and node.get("id") == function_id]
        bodies = [(node, child) for node in matches for child in _children(node)
                  if child.get("kind") == "CompoundStmt"]
        if len(bodies) != 1:
            raise _Unknown("function_unique_body_not_found")
        function, body = bodies[0]
        statements = _children(body)
        if len(statements) < 3:
            raise _Unknown("body_too_short", body.get("range"))
        candidates: list[tuple[int, dict[str, Any]]] = []
        for index in range(len(statements) - 1):
            if statements[index + 1].get("kind") != "ForStmt":
                continue
            try:
                declaration = _single_var(statements[index], "not_candidate")
            except _Unknown:
                continue
            if _type(declaration) == "float":
                candidates.append((index, declaration))
        if len(candidates) != 1:
            raise _Unknown("unique_adjacent_accumulator_loop_candidate_not_found", body.get("range"))
        accumulator_index, accumulator = candidates[0]
        accumulator_id = accumulator.get("id")
        if not isinstance(accumulator_id, str):
            raise _Unknown("accumulator_id_missing", accumulator.get("range"))
        if not _float_zero(_initializer(accumulator)):
            raise _Unknown("accumulator_not_initialized_to_float_zero", accumulator.get("range"))

        loop = statements[accumulator_index + 1]
        columns = recover_columns(root, function_id, int_bits)
        matching_loops = [item for item in columns.get("loops", [])
                          if item.get("range") == loop.get("range") and item.get("status") == "recovered"]
        if len(matching_loops) != 1:
            raise _Unknown("column_recurrence_not_uniquely_recovered", loop.get("range"))
        recurrence = matching_loops[0]
        induction_id = recurrence["induction"]["declaration_id"]
        raw = loop.get("inner")
        if not isinstance(raw, list) or len(raw) != 5 or not isinstance(raw[4], dict):
            raise _Unknown("unsupported_for_layout", loop.get("range"))
        loop_body = raw[4]
        loop_statements = _children(loop_body) if loop_body.get("kind") == "CompoundStmt" else [loop_body]
        if len(loop_statements) != 2:
            raise _Unknown("loop_body_not_exactly_load_and_accumulate", loop_body.get("range"))

        value = _single_var(loop_statements[0], "loop_load_not_single_variable")
        if _type(value) != "const float":
            raise _Unknown("loop_value_not_const_float", value.get("range"))
        value_id = value.get("id")
        if not isinstance(value_id, str):
            raise _Unknown("loop_value_id_missing", value.get("range"))
        load = _unwrap(_initializer(value))
        load_children = _children(load)
        if load.get("kind") != "ArraySubscriptExpr" or len(load_children) != 2:
            raise _Unknown("loop_value_not_array_subscript", load.get("range"))
        input_id = _ref(load_children[0], "ParmVarDecl")
        if _ref(load_children[1], "VarDecl") != induction_id:
            raise _Unknown("load_index_not_induction", load_children[1].get("range"))
        input_parameters = [parameter for parameter in _children(function)
                            if parameter.get("kind") == "ParmVarDecl" and parameter.get("id") == input_id]
        input_type = (_type(input_parameters[0]) or "").replace(" ", "") if input_parameters else ""
        if len(input_parameters) != 1 or input_type not in {"float*", "constfloat*"}:
            raise _Unknown("input_not_float_pointer_parameter", load_children[0].get("range"))

        update = _unwrap(loop_statements[1])
        update_children = _children(update)
        if (update.get("kind") != "CompoundAssignOperator" or update.get("opcode") != "+=" or
                len(update_children) != 2 or _ref(update_children[0], "VarDecl") != accumulator_id):
            raise _Unknown("loop_update_not_accumulator_add", update.get("range"))
        product = _unwrap(update_children[1])
        product_children = _children(product)
        if product.get("kind") != "BinaryOperator" or product.get("opcode") != "*" or len(product_children) != 2:
            raise _Unknown("contribution_not_multiplication", product.get("range"))
        if (_ref(product_children[0], "VarDecl") != value_id or
                _ref(product_children[1], "VarDecl") != value_id):
            raise _Unknown("multiplication_not_same_loaded_value", product.get("range"))

        consumer = None
        for statement in statements[accumulator_index + 2:]:
            call = _consumer_call(statement)
            if call is not None:
                callee_id, arguments = _direct_call(call)
                positions = [index for index, argument in enumerate(arguments)
                             if _is_ref(argument, accumulator_id)]
                if len(positions) != 1:
                    raise _Unknown("consumer_must_use_accumulator_once", call.get("range"))
                for index, argument in enumerate(arguments):
                    if index != positions[0] and not _safe_declref_argument(argument):
                        raise _Unknown("consumer_other_argument_may_have_side_effects", argument.get("range"))
                argument_index = positions[0]
                consumer = {"callee_declaration_id": callee_id, "argument_index": argument_index,
                            "call_range": call.get("range"), "statement_range": statement.get("range")}
                break
            if any(node.get("kind") in CALL_KINDS for node in _walk(statement)):
                raise _Unknown("non_direct_or_nested_call_before_consumer", statement.get("range"))
            shared = _single_var(statement, "statement_before_consumer_not_shared_array_declaration")
            if shared.get("init") is not None or "[" not in (_type(shared) or ""):
                raise _Unknown("statement_before_consumer_not_uninitialized_shared_array", shared.get("range"))
        if consumer is None:
            raise _Unknown("accumulator_consumer_not_found", body.get("range"))
        result.update(status="recovered", loop_recurrence=recurrence, loop=recurrence,
                      input_parameter_id=input_id, input_declaration_id=input_id,
                      accumulator_declaration_id=accumulator_id,
                      value_declaration_id=value_id, consumer=consumer,
                      consumer_declaration_id=consumer["callee_declaration_id"],
                      prefix_statement_ranges=[statement.get("range")
                                               for statement in statements[:accumulator_index]],
                      ranges={"function": function.get("range"), "accumulator": accumulator.get("range"),
                              "loop": loop.get("range"), "load": load.get("range"),
                              "update": update.get("range"), "product": product.get("range")})
    except _Unknown as error:
        result["reason"], result["unknown_range"] = error.reason, error.range
    return result


def _is_ref(node: dict[str, Any], identifier: str) -> bool:
    try:
        return _ref(node) == identifier
    except _Unknown:
        return False


def _safe_declref_argument(node: dict[str, Any]) -> bool:
    try:
        current = _unwrap(node)
        return current.get("kind") == "DeclRefExpr" and isinstance(current.get("referencedDecl"), dict)
    except _Unknown:
        return False


def _consumer_call(statement: dict[str, Any]) -> dict[str, Any] | None:
    current = _unwrap(statement)
    if current.get("kind") == "CallExpr":
        return current
    if current.get("kind") != "DeclStmt":
        return None
    declarations = [child for child in _children(current) if child.get("kind") == "VarDecl"]
    if len(declarations) != 1:
        return None
    try:
        expression = _unwrap(_initializer(declarations[0]))
    except _Unknown:
        return None
    return expression if expression.get("kind") == "CallExpr" else None
