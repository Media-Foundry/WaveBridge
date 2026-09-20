"""Recover a narrowly defined XOR-add reduction loop from one Clang AST root."""

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


def _unwrap(node: dict[str, Any]) -> dict[str, Any]:
    current = node
    while current.get("kind") in {"ParenExpr", "ImplicitCastExpr"}:
        children = _children(current)
        if len(children) != 1:
            raise _Unknown("ambiguous_wrapper", current.get("range"))
        if current.get("kind") == "ImplicitCastExpr" and current.get("castKind") not in {
                "LValueToRValue", "FunctionToPointerDecay", "NoOp"}:
            raise _Unknown("unsupported_cast", current.get("range"))
        current = children[0]
    return current


def _ref(node: dict[str, Any], expected_kind: str | None = None) -> str:
    current = _unwrap(node)
    referenced = current.get("referencedDecl")
    if current.get("kind") != "DeclRefExpr" or not isinstance(referenced, dict):
        raise _Unknown("expected_exact_declref", current.get("range"))
    if expected_kind is not None and referenced.get("kind") != expected_kind:
        raise _Unknown("unexpected_referenced_declaration_kind", current.get("range"))
    declaration_id = referenced.get("id")
    if not isinstance(declaration_id, str):
        raise _Unknown("referenced_declaration_id_missing", current.get("range"))
    return declaration_id


def _literal(node: dict[str, Any], value: int) -> None:
    current = _unwrap(node)
    try:
        actual = int(str(current.get("value")), 0)
    except ValueError:
        raise _Unknown("invalid_integer_literal", current.get("range"))
    if current.get("kind") != "IntegerLiteral" or actual != value:
        raise _Unknown("unexpected_integer_literal", current.get("range"))


def _full_mask(node: dict[str, Any], int_bits: int) -> dict[str, Any]:
    """Accept only the explicit CUDA logical32 full-participation mask."""
    current = node
    while current.get("kind") == "ParenExpr":
        children = _children(current)
        if len(children) != 1:
            raise _Unknown("ambiguous_mask_wrapper", current.get("range"))
        current = children[0]
    if current.get("kind") != "IntegerLiteral":
        raise _Unknown("shuffle_mask_not_explicit_integer_literal", current.get("range"))
    if _type(current) != "unsigned int":
        raise _Unknown("shuffle_mask_not_unsigned_int", current.get("range"))
    try:
        value = int(str(current.get("value")), 0)
    except (TypeError, ValueError):
        raise _Unknown("invalid_shuffle_mask_literal", current.get("range"))
    if int_bits != 32 or value != 4294967295:
        raise _Unknown("shuffle_mask_not_supported_full_logical32", current.get("range"))
    return {"value": value, "type": current.get("type"), "range": current.get("range"),
            "ast": node, "interpretation": "explicit_full_logical32_mask_literal"}


def _single_child(node: dict[str, Any], reason: str) -> dict[str, Any]:
    children = _children(node)
    if len(children) != 1:
        raise _Unknown(reason, node.get("range"))
    return children[0]


def recover(root: object, function_id: str, shuffle_declaration_id: str,
            int_bits: int = 32) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema_version": "xor-reduction-recovery/v1", "status": "unknown",
        "reason": None, "function_id": function_id,
        "shuffle_declaration_id": shuffle_declaration_id, "int_bits": int_bits,
        "width": None, "offsets": [], "operation": None, "ranges": {},
        "bindings": {}, "mask": None, "shuffle_call_arity": None,
        "external_shuffle_semantics": "not_established",
        "external_mask_semantics": "not_applicable_until_four_argument_form_recovered",
        "conditional_route_check": {
            "models_mask": False, "applicability": "not_established",
            "external_preconditions": []},
        "shuffle_declaration_selection": "external_input",
        "checked": False, "deployable": False, "relation_recovery": "incomplete",
    }
    if not isinstance(root, dict):
        result["reason"] = "root_not_object"
        return result
    if type(int_bits) is not int or not 2 <= int_bits <= 128:
        result["reason"] = "invalid_int_bits"
        return result
    try:
        functions = [node for node in _walk(root) if node.get("kind") in {"FunctionDecl", "CXXMethodDecl"}
                     and node.get("id") == function_id]
        bodies = [(node, child) for node in functions for child in _children(node)
                  if child.get("kind") == "CompoundStmt"]
        if len(bodies) != 1:
            raise _Unknown("function_unique_body_not_found")
        function, body = bodies[0]
        parameters = [child for child in _children(function) if child.get("kind") == "ParmVarDecl"]
        float_parameters = [parameter for parameter in parameters if _type(parameter) == "float"]
        if len(parameters) != 1 or len(float_parameters) != 1:
            raise _Unknown("function_not_single_float_parameter", function.get("range"))
        accumulator = float_parameters[0]
        accumulator_id = accumulator.get("id")
        if not isinstance(accumulator_id, str):
            raise _Unknown("accumulator_id_missing", accumulator.get("range"))

        statements = _children(body)
        if len(statements) != 2 or statements[1].get("kind") != "ReturnStmt":
            raise _Unknown("body_not_loop_then_return", body.get("range"))
        loop_holder = statements[0]
        if loop_holder.get("kind") == "AttributedStmt":
            non_attributes = [child for child in _children(loop_holder)
                              if not str(child.get("kind", "")).endswith("Attr")]
            if len(non_attributes) != 1:
                raise _Unknown("attributed_loop_ambiguous", loop_holder.get("range"))
            loop = non_attributes[0]
        else:
            loop = loop_holder
        if loop.get("kind") != "ForStmt":
            raise _Unknown("first_statement_not_for", loop.get("range"))
        raw = loop.get("inner")
        if not isinstance(raw, list) or len(raw) != 5 or not isinstance(raw[1], dict) or raw[1]:
            raise _Unknown("unsupported_for_header_layout", loop.get("range"))
        init, _, condition, increment, loop_body = raw
        if not all(isinstance(node, dict) and node for node in (init, condition, increment, loop_body)):
            raise _Unknown("incomplete_for_header", loop.get("range"))

        if init.get("kind") != "DeclStmt":
            raise _Unknown("offset_initializer_not_declstmt", init.get("range"))
        declarations = [child for child in _children(init) if child.get("kind") == "VarDecl"]
        if len(declarations) != 1 or _type(declarations[0]) != "int":
            raise _Unknown("offset_not_single_int_variable", init.get("range"))
        offset = declarations[0]
        offset_id = offset.get("id")
        if not isinstance(offset_id, str):
            raise _Unknown("offset_id_missing", offset.get("range"))
        initializer = [child for child in _children(offset)
                       if not str(child.get("kind", "")).endswith("Attr")]
        if offset.get("init") is None or len(initializer) != 1:
            raise _Unknown("offset_initializer_missing_or_ambiguous", offset.get("range"))
        division = _unwrap(initializer[0])
        operands = _children(division)
        if division.get("kind") != "BinaryOperator" or division.get("opcode") != "/" or len(operands) != 2:
            raise _Unknown("offset_initializer_not_width_div_two", division.get("range"))
        width_id = _ref(operands[0], "VarDecl")
        _literal(operands[1], 2)
        width_result = evaluate(root, width_id, int_bits)
        if width_result.get("status") != "evaluated":
            raise _Unknown("width_constant_unknown", operands[0].get("range"))
        width = width_result["value"]
        if type(width) is not int or not 2 <= width <= 64 or width & (width - 1):
            raise _Unknown("width_not_supported_power_of_two", operands[0].get("range"))

        condition_operands = _children(condition)
        if condition.get("kind") != "BinaryOperator" or condition.get("opcode") != ">" or len(condition_operands) != 2:
            raise _Unknown("condition_not_offset_gt_zero", condition.get("range"))
        if _ref(condition_operands[0], "VarDecl") != offset_id:
            raise _Unknown("condition_uses_other_offset", condition_operands[0].get("range"))
        _literal(condition_operands[1], 0)
        increment_operands = _children(increment)
        if (increment.get("kind") != "CompoundAssignOperator" or increment.get("opcode") != ">>=" or
                len(increment_operands) != 2):
            raise _Unknown("increment_not_offset_shift", increment.get("range"))
        if _ref(increment_operands[0], "VarDecl") != offset_id:
            raise _Unknown("increment_uses_other_offset", increment_operands[0].get("range"))
        _literal(increment_operands[1], 1)

        update = _single_child(loop_body, "loop_body_not_single_statement") if loop_body.get("kind") == "CompoundStmt" else loop_body
        update_operands = _children(update)
        if (update.get("kind") != "CompoundAssignOperator" or update.get("opcode") != "+=" or
                len(update_operands) != 2):
            raise _Unknown("loop_body_not_accumulator_add", update.get("range"))
        if _ref(update_operands[0], "ParmVarDecl") != accumulator_id:
            raise _Unknown("update_uses_other_accumulator", update_operands[0].get("range"))
        call = _unwrap(update_operands[1])
        call_children = _children(call)
        if call.get("kind") != "CallExpr" or len(call_children) not in (4, 5):
            raise _Unknown("update_not_supported_three_or_four_argument_call", call.get("range"))
        if _ref(call_children[0], "FunctionDecl") != shuffle_declaration_id:
            raise _Unknown("call_not_selected_shuffle", call_children[0].get("range"))
        mask = None
        argument_start = 1
        if len(call_children) == 5:
            if width != 32:
                raise _Unknown("four_argument_shuffle_requires_logical_width_32",
                               operands[0].get("range"))
            mask = _full_mask(call_children[1], int_bits)
            argument_start = 2
        if _ref(call_children[argument_start], "ParmVarDecl") != accumulator_id:
            raise _Unknown("shuffle_value_not_accumulator", call_children[argument_start].get("range"))
        if _ref(call_children[argument_start + 1], "VarDecl") != offset_id:
            raise _Unknown("shuffle_offset_mismatch", call_children[argument_start + 1].get("range"))
        if _ref(call_children[argument_start + 2], "VarDecl") != width_id:
            raise _Unknown("shuffle_width_mismatch", call_children[argument_start + 2].get("range"))

        returned = _single_child(statements[1], "return_expression_missing_or_ambiguous")
        if _ref(returned, "ParmVarDecl") != accumulator_id:
            raise _Unknown("return_not_accumulator", returned.get("range"))
        offsets, current = [], width // 2
        while current > 0:
            offsets.append(current)
            current >>= 1
        result.update(status="recovered", width=width, offsets=offsets, operation="add",
                      mask=mask, shuffle_call_arity=len(call_children) - 1,
                      external_mask_semantics=(
                          "full_mask_active_and_converged_participation_is_external_precondition"
                          if mask is not None else "implicit_three_argument_form_not_interpreted"),
                      conditional_route_check={
                          "models_mask": False,
                          "applicability": ("applicable_only_under_recorded_full_mask_preconditions"
                                            if mask is not None else
                                            "applicable_under_existing_full_group_precondition"),
                          "external_preconditions": ([
                              "all_32_lanes_named_by_mask_are_active_at_every_shuffle",
                              "all_32_lanes_named_by_mask_are_converged_at_every_shuffle"]
                              if mask is not None else [
                              "all_logical_group_lanes_participate_at_every_shuffle"])},
                      ranges={"function": function.get("range"), "loop": loop.get("range"),
                              "initializer": division.get("range"), "condition": condition.get("range"),
                              "increment": increment.get("range"), "update": update.get("range"),
                              "call": call.get("range"), "return": statements[1].get("range")},
                      bindings={"accumulator_declaration_id": accumulator_id,
                                "offset_declaration_id": offset_id,
                                "width_declaration_id": width_id})
    except _Unknown as error:
        result["reason"], result["unknown_range"] = error.reason, error.range
    return result


def main(argv=None):
    """Persist source extraction and conditional routing evidence separately."""
    import argparse
    import json
    from pathlib import Path
    from wavebridge.frontend.clang_ast import _sha256
    from wavebridge.verification.xor_routes import check

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ast_report", type=Path)
    parser.add_argument("--root-index", type=int, required=True)
    parser.add_argument("--function-id", required=True)
    parser.add_argument("--shuffle-id", required=True)
    parser.add_argument("--int-bits", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists() or args.output.resolve() == args.ast_report.resolve():
        parser.error("output must be a new file")
    with args.ast_report.open(encoding="utf-8") as stream:
        frontend = json.load(stream)
    if (frontend.get("schema_version") != "clang-ast-source/v1" or
            frontend.get("status") != "collected"):
        parser.error("a collected Clang AST report is required")
    roots = frontend.get("ast_roots", [])
    if not 0 <= args.root_index < len(roots):
        parser.error("root index outside collected AST")
    recovered = recover(roots[args.root_index], args.function_id, args.shuffle_id, args.int_bits)
    routes = check(recovered["width"], recovered["offsets"]) if recovered["status"] == "recovered" else None
    report = {"schema_version": "source-xor-evidence/v1",
              "ast_report_sha256": _sha256(args.ast_report), "root_index": args.root_index,
              "recovery": recovered, "conditional_route_check": routes,
              "conditional_route_check_mask_scope": recovered.get("conditional_route_check"),
              "source_program_checked": False, "deployable": False}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"recovery": recovered["status"], "output": str(args.output)}))
    return 0 if recovered["status"] == "recovered" else 2


if __name__ == "__main__":
    raise SystemExit(main())
