"""Recover a strict normalization suffix connected to a local sum-of-squares loop."""

from __future__ import annotations

from typing import Any

from wavebridge.analysis.column_loops import recover as recover_columns
from wavebridge.analysis.local_contribution import recover as recover_local

ALLOWED_CASTS = {"LValueToRValue", "FunctionToPointerDecay", "ArrayToPointerDecay", "NoOp",
                 "IntegralToFloating"}


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


def _unwrap(node: dict[str, Any], casts: list[dict[str, Any]]) -> dict[str, Any]:
    current = node
    while current.get("kind") in {"ParenExpr", "ImplicitCastExpr"}:
        children = _children(current)
        if len(children) != 1:
            raise _Unknown("ambiguous_wrapper", current.get("range"))
        if current.get("kind") == "ImplicitCastExpr":
            cast_kind = current.get("castKind")
            if cast_kind not in ALLOWED_CASTS:
                raise _Unknown("unsupported_cast", current.get("range"))
            casts.append({"cast_kind": cast_kind, "source_type": _type(children[0]),
                          "destination_type": _type(current), "range": current.get("range"),
                          "semantic_obligation": "not_discharged"})
        current = children[0]
    return current


def _ref(node: dict[str, Any], casts: list[dict[str, Any]], kind: str | None = None) -> str:
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


def _single_var(statement: dict[str, Any], qual_type: str, reason: str) -> dict[str, Any]:
    if statement.get("kind") != "DeclStmt":
        raise _Unknown(reason, statement.get("range"))
    variables = [child for child in _children(statement) if child.get("kind") == "VarDecl"]
    if len(variables) != 1 or _type(variables[0]) != qual_type:
        raise _Unknown(reason, statement.get("range"))
    return variables[0]


def _initializer(variable: dict[str, Any]) -> dict[str, Any]:
    values = [child for child in _children(variable)
              if not str(child.get("kind", "")).endswith("Attr")]
    if variable.get("init") is None or len(values) != 1:
        raise _Unknown("initializer_missing_or_ambiguous", variable.get("range"))
    return values[0]


def _direct_call(node: dict[str, Any], casts: list[dict[str, Any]]) -> tuple[dict[str, Any], str, list[dict[str, Any]]]:
    call = _unwrap(node, casts)
    children = _children(call)
    if call.get("kind") != "CallExpr" or not children:
        raise _Unknown("expected_direct_call", call.get("range"))
    callee = _ref(children[0], casts, "FunctionDecl")
    return call, callee, children[1:]


def _same_recurrence(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return (left.get("start", {}).get("kind") == right.get("start", {}).get("kind") and
            left.get("start", {}).get("declaration_id") == right.get("start", {}).get("declaration_id") and
            left.get("start", {}).get("value") == right.get("start", {}).get("value") and
            left.get("bound", {}).get("declaration_id") == right.get("bound", {}).get("declaration_id") and
            left.get("step") == right.get("step"))


def recover(root: object, function_id: str, int_bits: int) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema_version": "normalization-output-recovery/v1", "status": "unknown", "reason": None,
        "function_id": function_id, "int_bits": int_bits, "local_contribution": None,
        "local_loop": None, "output_loop": None, "source_parameter_id": None,
        "output_parameter_id": None, "count_parameter_id": None, "epsilon_parameter_id": None,
        "total_declaration_id": None, "scale_declaration_id": None,
        "consumer_declaration_id": None, "scale_function_id": None,
        "operation": None, "casts": [], "ranges": {},
        "conversion_semantics": "not_established",
        "preconditions": {"prefix_base_address": "not_established", "aliasing": "not_established",
                          "external_scale_function": "not_established",
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
        local = recover_local(root, function_id, int_bits)
        result["local_contribution"] = local
        if local.get("status") != "recovered":
            raise _Unknown("local_contribution_not_recovered")
        matches = [node for node in _walk(root) if node.get("kind") in {"FunctionDecl", "CXXMethodDecl"}
                   and node.get("id") == function_id]
        bodies = [(node, child) for node in matches for child in _children(node)
                  if child.get("kind") == "CompoundStmt"]
        if len(bodies) != 1:
            raise _Unknown("function_unique_body_not_found")
        function, body = bodies[0]
        statements = _children(body)
        consumer_indices: list[int] = []
        for index, statement in enumerate(statements):
            probe_casts: list[dict[str, Any]] = []
            try:
                probe_total = _single_var(statement, "const float", "not_consumer")
                _, probe_callee, probe_args = _direct_call(_initializer(probe_total), probe_casts)
                if (probe_callee == local["consumer_declaration_id"] and len(probe_args) == 2 and
                        _ref(probe_args[0], probe_casts, "VarDecl") == local["accumulator_declaration_id"]):
                    consumer_indices.append(index)
            except _Unknown:
                continue
        if len(consumer_indices) != 1:
            raise _Unknown("local_consumer_statement_not_unique", local["consumer"]["statement_range"])
        consumer_index = consumer_indices[0]
        if consumer_index + 2 >= len(statements):
            raise _Unknown("normalization_suffix_missing", body.get("range"))
        casts: list[dict[str, Any]] = []

        total = _single_var(statements[consumer_index], "const float", "consumer_not_const_float_declaration")
        total_id = total.get("id")
        if not isinstance(total_id, str):
            raise _Unknown("total_id_missing", total.get("range"))
        consumer_call, consumer_id, consumer_args = _direct_call(_initializer(total), casts)
        if consumer_id != local["consumer_declaration_id"] or len(consumer_args) != 2:
            raise _Unknown("consumer_call_shape_mismatch", consumer_call.get("range"))
        if _ref(consumer_args[0], casts, "VarDecl") != local["accumulator_declaration_id"]:
            raise _Unknown("consumer_first_argument_not_accumulator", consumer_args[0].get("range"))
        shared_id = _ref(consumer_args[1], casts, "VarDecl")

        scale = _single_var(statements[consumer_index + 1], "const float", "scale_not_next_const_float_declaration")
        scale_id = scale.get("id")
        if not isinstance(scale_id, str):
            raise _Unknown("scale_id_missing", scale.get("range"))
        scale_call, scale_function_id, scale_args = _direct_call(_initializer(scale), casts)
        if len(scale_args) != 1:
            raise _Unknown("scale_call_not_one_argument", scale_call.get("range"))
        addition = _unwrap(scale_args[0], casts)
        addition_children = _children(addition)
        if addition.get("kind") != "BinaryOperator" or addition.get("opcode") != "+" or len(addition_children) != 2:
            raise _Unknown("scale_argument_not_division_plus_epsilon", addition.get("range"))
        division = _unwrap(addition_children[0], casts)
        division_children = _children(division)
        if division.get("kind") != "BinaryOperator" or division.get("opcode") != "/" or len(division_children) != 2:
            raise _Unknown("scale_argument_not_total_div_count", division.get("range"))
        if _ref(division_children[0], casts, "VarDecl") != total_id:
            raise _Unknown("scale_dividend_not_total", division_children[0].get("range"))
        count_id = _ref(division_children[1], casts, "ParmVarDecl")
        epsilon_id = _ref(addition_children[1], casts, "ParmVarDecl")
        parameters = {node.get("id"): node for node in _children(function) if node.get("kind") == "ParmVarDecl"}
        if _type(parameters.get(count_id, {})) != "int":
            raise _Unknown("count_not_int_parameter", division_children[1].get("range"))
        if _type(parameters.get(epsilon_id, {})) != "float":
            raise _Unknown("epsilon_not_float_parameter", addition_children[1].get("range"))
        local_bound_id = local["loop"]["bound"]["declaration_id"]
        if count_id != local_bound_id:
            raise _Unknown("count_not_local_loop_bound", division_children[1].get("range"))

        output_statement = statements[consumer_index + 2]
        if output_statement.get("kind") != "ForStmt":
            raise _Unknown("output_not_immediate_for", output_statement.get("range"))
        columns = recover_columns(root, function_id, int_bits)
        output_loops = [item for item in columns.get("loops", [])
                        if item.get("range") == output_statement.get("range") and item.get("status") == "recovered"]
        if len(output_loops) != 1:
            raise _Unknown("output_column_recurrence_not_recovered", output_statement.get("range"))
        output_loop = output_loops[0]
        if not _same_recurrence(local["loop"], output_loop):
            raise _Unknown("local_and_output_recurrence_mismatch", output_statement.get("range"))
        raw = output_statement.get("inner")
        if not isinstance(raw, list) or len(raw) != 5 or not isinstance(raw[4], dict):
            raise _Unknown("unsupported_output_for_layout", output_statement.get("range"))
        output_body = raw[4]
        body_statements = _children(output_body) if output_body.get("kind") == "CompoundStmt" else [output_body]
        if len(body_statements) != 1:
            raise _Unknown("output_loop_not_single_write", output_body.get("range"))
        store = _unwrap(body_statements[0], casts)
        store_children = _children(store)
        if store.get("kind") != "BinaryOperator" or store.get("opcode") != "=" or len(store_children) != 2:
            raise _Unknown("output_body_not_assignment", store.get("range"))
        induction_id = output_loop["induction"]["declaration_id"]
        target = _unwrap(store_children[0], casts)
        target_children = _children(target)
        if target.get("kind") != "ArraySubscriptExpr" or len(target_children) != 2:
            raise _Unknown("output_target_not_subscript", target.get("range"))
        output_id = _ref(target_children[0], casts, "ParmVarDecl")
        if _ref(target_children[1], casts, "VarDecl") != induction_id:
            raise _Unknown("output_index_not_induction", target_children[1].get("range"))
        product = _unwrap(store_children[1], casts)
        product_children = _children(product)
        if product.get("kind") != "BinaryOperator" or product.get("opcode") != "*" or len(product_children) != 2:
            raise _Unknown("output_value_not_scale_times_input", product.get("range"))
        if _ref(product_children[0], casts, "VarDecl") != scale_id:
            raise _Unknown("output_multiplier_not_scale", product_children[0].get("range"))
        source = _unwrap(product_children[1], casts)
        source_children = _children(source)
        if source.get("kind") != "ArraySubscriptExpr" or len(source_children) != 2:
            raise _Unknown("output_source_not_subscript", source.get("range"))
        source_id = _ref(source_children[0], casts, "ParmVarDecl")
        if source_id != local["input_declaration_id"]:
            raise _Unknown("output_source_not_local_input", source_children[0].get("range"))
        if _ref(source_children[1], casts, "VarDecl") != induction_id:
            raise _Unknown("source_index_not_output_induction", source_children[1].get("range"))
        output_type = (_type(parameters.get(output_id, {})) or "").replace(" ", "")
        if output_type != "float*":
            raise _Unknown("output_not_float_pointer_parameter", target_children[0].get("range"))
        trailing = statements[consumer_index + 3:]
        if any(statement.get("kind") != "ReturnStmt" or _children(statement) for statement in trailing):
            raise _Unknown("statements_after_output_loop", body.get("range"))

        result.update(status="recovered", local_loop=local["loop"], output_loop=output_loop,
                      source_parameter_id=source_id, output_parameter_id=output_id,
                      count_parameter_id=count_id, epsilon_parameter_id=epsilon_id,
                      total_declaration_id=total_id, scale_declaration_id=scale_id,
                      consumer_declaration_id=consumer_id, scale_function_id=scale_function_id,
                      operation={"local": "sum_of_squares", "scale_argument": "total_div_count_plus_epsilon",
                                 "output": "scale_times_input", "shared_argument_id": shared_id},
                      casts=casts,
                      ranges={"consumer": consumer_call.get("range"), "scale": scale_call.get("range"),
                              "output_loop": output_statement.get("range"), "store": store.get("range")})
    except _Unknown as error:
        result["reason"], result["unknown_range"] = error.reason, error.range
    return result
