"""Recover one narrowly defined two-stage block reduction from Clang AST."""

from __future__ import annotations

from typing import Any

from wavebridge.analysis.integer_constants import evaluate


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


def _unwrap(node: dict[str, Any], casts: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    current = node
    while current.get("kind") in {"ParenExpr", "ImplicitCastExpr"}:
        children = _children(current)
        if len(children) != 1:
            raise _Unknown("ambiguous_wrapper", current.get("range"))
        if current.get("kind") == "ImplicitCastExpr":
            cast_kind = current.get("castKind")
            if cast_kind not in {"LValueToRValue", "FunctionToPointerDecay", "NoOp", "IntegralCast"}:
                raise _Unknown("unsupported_cast", current.get("range"))
            if cast_kind == "IntegralCast" and casts is None:
                raise _Unknown("unrecorded_integral_cast", current.get("range"))
            if casts is not None:
                casts.append({"cast_kind": cast_kind, "source_type": _type(children[0]),
                              "destination_type": _type(current), "range": current.get("range"),
                              "semantic_obligation": "not_discharged"})
        current = children[0]
    return current


def _ref(node: dict[str, Any], kind: str | None = None,
         casts: list[dict[str, Any]] | None = None) -> str:
    current = _unwrap(node, casts)
    referenced = current.get("referencedDecl")
    if current.get("kind") != "DeclRefExpr" or not isinstance(referenced, dict):
        raise _Unknown("expected_exact_declref", current.get("range"))
    if kind is not None and referenced.get("kind") != kind:
        raise _Unknown("unexpected_reference_kind", current.get("range"))
    identifier = referenced.get("id")
    if not isinstance(identifier, str):
        raise _Unknown("reference_id_missing", current.get("range"))
    return identifier


def _literal_int(node: dict[str, Any], expected: int, casts: list[dict[str, Any]] | None = None) -> None:
    current = _unwrap(node, casts)
    try:
        value = int(str(current.get("value")), 0)
    except ValueError:
        raise _Unknown("invalid_integer_literal", current.get("range"))
    if current.get("kind") != "IntegerLiteral" or value != expected:
        raise _Unknown("unexpected_integer_literal", current.get("range"))


def _initializer(declaration: dict[str, Any]) -> dict[str, Any]:
    values = [child for child in _children(declaration)
              if not str(child.get("kind", "")).endswith("Attr")]
    if declaration.get("init") is None or len(values) != 1:
        raise _Unknown("initializer_missing_or_ambiguous", declaration.get("range"))
    return values[0]


def _callee(node: dict[str, Any], target_id: str, casts: list[dict[str, Any]],
            *, allow_builtin: bool) -> dict[str, Any]:
    original = node
    current = node
    callee_casts: list[dict[str, Any]] = []
    while current.get("kind") in {"ParenExpr", "ImplicitCastExpr"}:
        children = _children(current)
        if len(children) != 1:
            raise _Unknown("ambiguous_callee_wrapper", current.get("range"))
        if current.get("kind") == "ImplicitCastExpr":
            cast_kind = current.get("castKind")
            allowed = {"FunctionToPointerDecay", "NoOp"}
            if allow_builtin:
                allowed.add("BuiltinFnToFnPtr")
            if cast_kind not in allowed:
                raise _Unknown("unsupported_callee_cast", current.get("range"))
            evidence = {"cast_kind": cast_kind, "source_type": _type(children[0]),
                        "destination_type": _type(current), "range": current.get("range"),
                        "semantic_obligation": "not_discharged"}
            casts.append(evidence)
            callee_casts.append(evidence)
        current = children[0]
    referenced = current.get("referencedDecl")
    if (current.get("kind") != "DeclRefExpr" or not isinstance(referenced, dict) or
            referenced.get("kind") != "FunctionDecl" or
            not isinstance(referenced.get("id"), str)):
        raise _Unknown("callee_not_exact_function_declref", current.get("range"))
    if referenced["id"] != target_id:
        raise _Unknown("unexpected_call_target", current.get("range"))
    return {"declaration_id": referenced["id"], "callee_ast": original,
            "declref_range": current.get("range"), "casts": callee_casts,
            "builtin_conversion_semantics": "not_established"}


def _call(node: dict[str, Any], target_id: str, argument_ids: list[tuple[str, str]],
          casts: list[dict[str, Any]], *, allow_builtin_callee: bool = False,
          callee_evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    call = _unwrap(node, casts)
    children = _children(call)
    if call.get("kind") != "CallExpr" or len(children) != len(argument_ids) + 1:
        raise _Unknown("unexpected_call_shape", call.get("range"))
    evidence = _callee(children[0], target_id, casts, allow_builtin=allow_builtin_callee)
    if callee_evidence is not None:
        callee_evidence.update(evidence)
    for argument, (identifier, kind) in zip(children[1:], argument_ids):
        if _ref(argument, kind, casts) != identifier:
            raise _Unknown("unexpected_call_argument", argument.get("range"))
    return call


def _assignment(node: dict[str, Any], target_id: str,
                casts: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    current = _unwrap(node, casts)
    children = _children(current)
    if current.get("kind") != "BinaryOperator" or current.get("opcode") != "=" or len(children) != 2:
        raise _Unknown("expected_simple_assignment", current.get("range"))
    if _ref(children[0], "ParmVarDecl", casts) != target_id:
        raise _Unknown("assignment_target_mismatch", children[0].get("range"))
    return current, children[1]


def recover(root: object, function_id: str, reduce_id: str, barrier_id: str,
            int_bits: int) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema_version": "block-reduction-recovery/v1", "status": "unknown", "reason": None,
        "function_id": function_id, "reduce_declaration_id": reduce_id,
        "barrier_declaration_id": barrier_id, "int_bits": int_bits,
        "width": None, "block_threads": None, "writer_lane": None,
        "stage_sequence": [], "ranges": {}, "call_bindings": {},
        "coordinate_asts": {}, "coordinate_equality": "not_established",
        "index_initializers": {},
        "barrier_callee_evidence": None,
        "casts": [], "conversion_semantics": "not_established",
        "reduce_semantics": "not_established", "barrier_semantics": "not_established",
        "coordinate_semantics": "not_established", "checked": False,
        "deployable": False, "relation_recovery": "incomplete",
    }
    if not isinstance(root, dict):
        result["reason"] = "root_not_object"
        return result
    if type(int_bits) is not int or not 2 <= int_bits <= 128:
        result["reason"] = "invalid_int_bits"
        return result
    try:
        body_casts: list[dict[str, Any]] = []
        functions = [node for node in _walk(root) if node.get("kind") in {"FunctionDecl", "CXXMethodDecl"}
                     and node.get("id") == function_id]
        bodies = [(function, child) for function in functions for child in _children(function)
                  if child.get("kind") == "CompoundStmt"]
        if len(bodies) != 1:
            raise _Unknown("function_unique_body_not_found")
        function, body = bodies[0]
        parameters = [child for child in _children(function) if child.get("kind") == "ParmVarDecl"]
        if len(parameters) != 2:
            raise _Unknown("function_not_two_parameters", function.get("range"))
        values = [parameter for parameter in parameters if _type(parameter) == "float"]
        shareds = [parameter for parameter in parameters
                   if isinstance(_type(parameter), str) and _type(parameter).replace(" ", "") == "float*"]
        if len(values) != 1 or len(shareds) != 1:
            raise _Unknown("parameter_types_not_float_and_float_pointer", function.get("range"))
        value_id, shared_id = values[0].get("id"), shareds[0].get("id")
        if not isinstance(value_id, str) or not isinstance(shared_id, str):
            raise _Unknown("parameter_id_missing", function.get("range"))
        statements = _children(body)
        if len(statements) != 7:
            raise _Unknown("body_not_exactly_seven_statements", body.get("range"))

        first_assignment, first_rhs = _assignment(statements[0], value_id, body_casts)
        first_reduce = _call(first_rhs, reduce_id, [(value_id, "ParmVarDecl")], body_casts)

        local_declarations: list[dict[str, Any]] = []
        for statement in statements[1:3]:
            if statement.get("kind") != "DeclStmt":
                raise _Unknown("group_or_lane_not_declstmt", statement.get("range"))
            declarations = [child for child in _children(statement) if child.get("kind") == "VarDecl"]
            if len(declarations) != 1 or _type(declarations[0]) != "const int":
                raise _Unknown("group_or_lane_not_single_const_int", statement.get("range"))
            local_declarations.append(declarations[0])
        group, lane = local_declarations
        group_id, lane_id = group.get("id"), lane.get("id")
        if not isinstance(group_id, str) or not isinstance(lane_id, str):
            raise _Unknown("group_or_lane_id_missing")
        group_expr = _unwrap(_initializer(group), body_casts)
        lane_expr = _unwrap(_initializer(lane), body_casts)
        group_operands, lane_operands = _children(group_expr), _children(lane_expr)
        if group_expr.get("kind") != "BinaryOperator" or group_expr.get("opcode") != "/" or len(group_operands) != 2:
            raise _Unknown("group_initializer_not_coordinate_div_width", group_expr.get("range"))
        if lane_expr.get("kind") != "BinaryOperator" or lane_expr.get("opcode") != "%" or len(lane_operands) != 2:
            raise _Unknown("lane_initializer_not_coordinate_mod_width", lane_expr.get("range"))
        width_id = _ref(group_operands[1], "VarDecl", body_casts)
        if _ref(lane_operands[1], "VarDecl", body_casts) != width_id:
            raise _Unknown("group_lane_width_mismatch", lane_operands[1].get("range"))
        width_result = evaluate(root, width_id, int_bits)
        if width_result.get("status") != "evaluated":
            raise _Unknown("width_constant_unknown", group_operands[1].get("range"))
        width = width_result["value"]
        if type(width) is not int or width <= 0:
            raise _Unknown("width_not_positive", group_operands[1].get("range"))

        if_stmt = statements[3]
        if_children = _children(if_stmt)
        if if_stmt.get("kind") != "IfStmt" or len(if_children) != 2:
            raise _Unknown("writer_not_single_if", if_stmt.get("range"))
        predicate, store = _unwrap(if_children[0], body_casts), _unwrap(if_children[1], body_casts)
        predicate_children = _children(predicate)
        if predicate.get("kind") != "BinaryOperator" or predicate.get("opcode") != "==" or len(predicate_children) != 2:
            raise _Unknown("writer_predicate_not_lane_zero", predicate.get("range"))
        if _ref(predicate_children[0], "VarDecl", body_casts) != lane_id:
            raise _Unknown("writer_predicate_uses_other_lane", predicate_children[0].get("range"))
        _literal_int(predicate_children[1], 0, body_casts)
        store_children = _children(store)
        if store.get("kind") != "BinaryOperator" or store.get("opcode") != "=" or len(store_children) != 2:
            raise _Unknown("writer_body_not_store", store.get("range"))
        subscript = _unwrap(store_children[0], body_casts)
        subscript_children = _children(subscript)
        if subscript.get("kind") != "ArraySubscriptExpr" or len(subscript_children) != 2:
            raise _Unknown("writer_target_not_shared_subscript", subscript.get("range"))
        if (_ref(subscript_children[0], "ParmVarDecl", body_casts) != shared_id or
                _ref(subscript_children[1], "VarDecl", body_casts) != group_id):
            raise _Unknown("writer_shared_or_index_mismatch", subscript.get("range"))
        if _ref(store_children[1], "ParmVarDecl", body_casts) != value_id:
            raise _Unknown("writer_value_mismatch", store_children[1].get("range"))

        barrier_callee_evidence: dict[str, Any] = {}
        barrier = _call(statements[4], barrier_id, [], body_casts,
                        allow_builtin_callee=True,
                        callee_evidence=barrier_callee_evidence)
        second_assignment, select_node = _assignment(statements[5], value_id, body_casts)
        select = _unwrap(select_node, body_casts)
        select_children = _children(select)
        if select.get("kind") != "ConditionalOperator" or len(select_children) != 3:
            raise _Unknown("second_stage_not_conditional", select.get("range"))
        second_predicate, shared_read, zero = (_unwrap(child, body_casts) for child in select_children)
        second_predicate_children = _children(second_predicate)
        if (second_predicate.get("kind") != "BinaryOperator" or second_predicate.get("opcode") != "<" or
                len(second_predicate_children) != 2 or
                _ref(second_predicate_children[0], "VarDecl", body_casts) != lane_id):
            raise _Unknown("second_stage_predicate_not_lane_lt_groups", second_predicate.get("range"))
        group_count = _unwrap(second_predicate_children[1], body_casts)
        group_count_children = _children(group_count)
        if group_count.get("kind") != "BinaryOperator" or group_count.get("opcode") != "/" or len(group_count_children) != 2:
            raise _Unknown("group_count_not_block_div_width", group_count.get("range"))
        block_id = _ref(group_count_children[0], "VarDecl", body_casts)
        if _ref(group_count_children[1], "VarDecl", body_casts) != width_id:
            raise _Unknown("group_count_width_mismatch", group_count_children[1].get("range"))
        block_result = evaluate(root, block_id, int_bits)
        if block_result.get("status") != "evaluated":
            raise _Unknown("block_threads_constant_unknown", group_count_children[0].get("range"))
        block_threads = block_result["value"]
        if (type(block_threads) is not int or block_threads <= 0 or block_threads % width != 0 or
                block_threads // width > width):
            raise _Unknown("invalid_block_width_relationship", group_count.get("range"))
        read_children = _children(shared_read)
        if shared_read.get("kind") != "ArraySubscriptExpr" or len(read_children) != 2:
            raise _Unknown("second_stage_true_not_shared_read", shared_read.get("range"))
        if (_ref(read_children[0], "ParmVarDecl", body_casts) != shared_id or
                _ref(read_children[1], "VarDecl", body_casts) != lane_id):
            raise _Unknown("second_stage_shared_or_index_mismatch", shared_read.get("range"))
        try:
            zero_value = float(str(zero.get("value")))
        except (TypeError, ValueError):
            raise _Unknown("second_stage_false_not_float_zero", zero.get("range"))
        if zero.get("kind") != "FloatingLiteral" or zero_value != 0.0:
            raise _Unknown("second_stage_false_not_float_zero", zero.get("range"))

        if statements[6].get("kind") != "ReturnStmt":
            raise _Unknown("last_statement_not_return", statements[6].get("range"))
        final_reduce = _call(_initializer_like_return(statements[6]), reduce_id,
                             [(value_id, "ParmVarDecl")], body_casts)
        result.update(status="recovered", width=width, block_threads=block_threads, writer_lane=0,
                      stage_sequence=["local_reduce", "group_index", "lane_index", "shared_write",
                                      "barrier", "shared_gather", "final_reduce"],
                      ranges={"function": function.get("range"), "first_reduce": first_reduce.get("range"),
                              "group": group.get("range"), "lane": lane.get("range"),
                              "shared_write": store.get("range"), "barrier": barrier.get("range"),
                              "shared_gather": second_assignment.get("range"),
                              "final_reduce": final_reduce.get("range")},
                      call_bindings={"first_reduce": reduce_id, "barrier": barrier_id,
                                     "final_reduce": reduce_id},
                      barrier_callee_evidence=barrier_callee_evidence,
                      coordinate_asts={"group_coordinate": group_operands[0],
                                       "lane_coordinate": lane_operands[0]},
                      index_initializers={"group": _initializer(group), "lane": _initializer(lane)},
                      casts=body_casts,
                      bindings={"value_parameter_id": value_id, "shared_parameter_id": shared_id,
                                "group_declaration_id": group_id, "lane_declaration_id": lane_id,
                                "width_declaration_id": width_id, "block_declaration_id": block_id})
    except _Unknown as error:
        result["reason"], result["unknown_range"] = error.reason, error.range
    return result


def _initializer_like_return(statement: dict[str, Any]) -> dict[str, Any]:
    children = _children(statement)
    if len(children) != 1:
        raise _Unknown("return_expression_missing_or_ambiguous", statement.get("range"))
    return children[0]
