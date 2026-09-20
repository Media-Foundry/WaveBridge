"""Conservative recovery of simple signed-int column recurrences from Clang AST."""

from __future__ import annotations

from typing import Any

from wavebridge.analysis.integer_constants import evaluate

FUNCTION_KINDS = {"FunctionDecl", "CXXMethodDecl"}
LOOP_KINDS = {"ForStmt", "WhileStmt", "DoStmt", "CXXForRangeStmt"}
CONTROL_KINDS = {"BreakStmt", "ContinueStmt", "GotoStmt", "ReturnStmt"}
CALL_KINDS = {"CallExpr", "CXXMemberCallExpr", "CXXOperatorCallExpr", "CUDAKernelCallExpr"}
VALUE_WRAPPERS = {"ParenExpr", "ImplicitCastExpr"}
ASSIGNMENT_OPCODES = {"=", "+=", "-=", "*=", "/=", "%=", "<<=", ">>=", "&=", "|=", "^="}


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


def _signed_int(node: dict[str, Any]) -> bool:
    qual = _type(node)
    if not isinstance(qual, str) or "volatile" in qual.split() or "unsigned" in qual.split():
        return False
    return qual.replace("const", "").split() == ["int"]


def _unwrap_value(node: dict[str, Any]) -> dict[str, Any]:
    current = node
    while current.get("kind") in VALUE_WRAPPERS:
        children = _children(current)
        if len(children) != 1 or not _signed_int(current) or not _signed_int(children[0]):
            raise _Unknown("unsupported_value_wrapper", current.get("range"))
        if (current.get("kind") == "ImplicitCastExpr" and
                current.get("castKind") not in {"LValueToRValue", "NoOp"}):
            raise _Unknown("unsupported_value_cast", current.get("range"))
        current = children[0]
    return current


def _declref(node: dict[str, Any]) -> tuple[str, str | None]:
    current = _unwrap_value(node)
    referenced = current.get("referencedDecl")
    if (current.get("kind") != "DeclRefExpr" or not _signed_int(current) or
            not isinstance(referenced, dict) or not isinstance(referenced.get("id"), str)):
        raise _Unknown("expected_exact_signed_int_declref", current.get("range"))
    return referenced["id"], referenced.get("kind")


def _initializer(var: dict[str, Any]) -> dict[str, Any]:
    values = [child for child in _children(var) if not str(child.get("kind", "")).endswith("Attr")]
    if var.get("init") is None or len(values) != 1:
        raise _Unknown("initializer_missing_or_ambiguous", var.get("range"))
    return values[0]


def _contains_ref(node: dict[str, Any], declaration_ids: set[str]) -> bool:
    for descendant in _walk(node):
        referenced = descendant.get("referencedDecl")
        if (descendant.get("kind") == "DeclRefExpr" and isinstance(referenced, dict) and
                referenced.get("id") in declaration_ids):
            return True
    return False


def _direct_ref_id(node: dict[str, Any]) -> str | None:
    current = node
    while current.get("kind") in {"ParenExpr", "ImplicitCastExpr"}:
        children = _children(current)
        if len(children) != 1:
            return None
        current = children[0]
    referenced = current.get("referencedDecl")
    if current.get("kind") == "DeclRefExpr" and isinstance(referenced, dict):
        return referenced.get("id") if isinstance(referenced.get("id"), str) else None
    return None


def _check_body(body: dict[str, Any], protected_ids: set[str]) -> None:
    for node in _walk(body):
        kind = node.get("kind")
        if kind in LOOP_KINDS:
            raise _Unknown("nested_loop_in_body", node.get("range"))
        if kind in CONTROL_KINDS:
            raise _Unknown("unsupported_control_flow_in_body", node.get("range"))
        if kind in CALL_KINDS:
            raise _Unknown("call_in_body", node.get("range"))
        if kind == "UnaryOperator" and node.get("opcode") in {"++", "--", "&"}:
            if _contains_ref(node, protected_ids):
                raise _Unknown("protected_variable_may_be_modified", node.get("range"))
        if kind == "VarDecl" and "&" in (_type(node) or ""):
            if any(_contains_ref(child, protected_ids) for child in _children(node)):
                raise _Unknown("protected_variable_reference_alias", node.get("range"))
        if kind in {"BinaryOperator", "CompoundAssignOperator"}:
            opcode = node.get("opcode")
            if opcode in ASSIGNMENT_OPCODES:
                children = _children(node)
                # Writing output[index] reads index; it does not write the index variable.
                # Only an exact protected DeclRef lvalue is a supported definite mutation.
                if children and _direct_ref_id(children[0]) in protected_ids:
                    raise _Unknown("protected_variable_may_be_modified", node.get("range"))


def _recover_loop(root: dict[str, Any], loop: dict[str, Any], int_bits: int) -> dict[str, Any]:
    item: dict[str, Any] = {
        "status": "unknown", "reason": None, "range": loop.get("range"),
        "induction": None, "start": None, "bound": None, "step": None,
        "step_source": None,
        "condition_ast": None, "assumptions": {
            "signed_recurrence_overflow": "external_precondition_unproven",
            "iteration_domain": "external_precondition_unproven",
            "memory_no_alias": "unproven",
        },
    }
    try:
        raw_inner = loop.get("inner")
        if not isinstance(raw_inner, list) or len(raw_inner) != 5:
            raise _Unknown("unsupported_for_header_layout", loop.get("range"))
        init, empty_slot, condition, increment, body = raw_inner
        if not isinstance(empty_slot, dict) or empty_slot:
            raise _Unknown("unsupported_for_header_slot", loop.get("range"))
        if not all(isinstance(node, dict) and node for node in (init, condition, increment, body)):
            raise _Unknown("incomplete_for_header", loop.get("range"))
        if init.get("kind") != "DeclStmt":
            raise _Unknown("initializer_not_declaration", init.get("range"))
        variables = [child for child in _children(init) if child.get("kind") == "VarDecl"]
        if len(variables) != 1 or not _signed_int(variables[0]):
            raise _Unknown("initializer_not_single_signed_int", init.get("range"))
        induction = variables[0]
        induction_id = induction.get("id")
        if not isinstance(induction_id, str):
            raise _Unknown("induction_id_missing", induction.get("range"))
        start_expr = _unwrap_value(_initializer(induction))
        if start_expr.get("kind") == "IntegerLiteral" and _signed_int(start_expr):
            try:
                start_value = int(str(start_expr["value"]), 0)
                if not -(1 << (int_bits - 1)) <= start_value <= (1 << (int_bits - 1)) - 1:
                    raise _Unknown("start_literal_out_of_range", start_expr.get("range"))
                start = {"kind": "integer_literal", "value": start_value,
                         "range": start_expr.get("range")}
            except (KeyError, ValueError):
                raise _Unknown("invalid_start_literal", start_expr.get("range"))
            start_id = None
        else:
            start_id, _ = _declref(start_expr)
            start = {"kind": "declaration_reference", "declaration_id": start_id,
                     "range": start_expr.get("range")}

        if condition.get("kind") != "BinaryOperator" or condition.get("opcode") != "<":
            raise _Unknown("condition_not_strict_less_than", condition.get("range"))
        condition_children = _children(condition)
        if len(condition_children) != 2:
            raise _Unknown("condition_operands_ambiguous", condition.get("range"))
        condition_induction, _ = _declref(condition_children[0])
        if condition_induction != induction_id:
            raise _Unknown("condition_uses_other_induction", condition_children[0].get("range"))
        bound_id, bound_kind = _declref(condition_children[1])
        if bound_kind == "ParmVarDecl":
            bound = {"kind": "parameter", "declaration_id": bound_id,
                     "range": condition_children[1].get("range")}
        else:
            constant = evaluate(root, bound_id, int_bits)
            if constant.get("status") != "evaluated":
                raise _Unknown("bound_not_parameter_or_resolved_const", condition_children[1].get("range"))
            bound = {"kind": "constant_declaration", "declaration_id": bound_id,
                     "value": constant["value"], "range": condition_children[1].get("range")}

        if increment.get("kind") != "CompoundAssignOperator" or increment.get("opcode") != "+=":
            raise _Unknown("increment_not_plus_equal", increment.get("range"))
        increment_children = _children(increment)
        if len(increment_children) != 2:
            raise _Unknown("increment_operands_ambiguous", increment.get("range"))
        increment_induction, _ = _declref(increment_children[0])
        if increment_induction != induction_id:
            raise _Unknown("increment_uses_other_induction", increment_children[0].get("range"))
        step_expr = _unwrap_value(increment_children[1])
        step_source: dict[str, Any]
        if step_expr.get("kind") == "IntegerLiteral" and _signed_int(step_expr):
            try:
                step_value = int(str(step_expr["value"]), 0)
                if not -(1 << (int_bits - 1)) <= step_value <= (1 << (int_bits - 1)) - 1:
                    raise _Unknown("step_literal_out_of_range", step_expr.get("range"))
            except (KeyError, ValueError):
                raise _Unknown("invalid_step_literal", step_expr.get("range"))
            step_source = {"kind": "integer_literal", "range": step_expr.get("range")}
        else:
            step_id, _ = _declref(step_expr)
            constant = evaluate(root, step_id, int_bits)
            if constant.get("status") != "evaluated":
                raise _Unknown("step_not_resolved_signed_int_constant", step_expr.get("range"))
            step_value = constant["value"]
            step_source = {"kind": "constant_declaration", "declaration_id": step_id,
                           "range": step_expr.get("range")}
        if type(step_value) is not int or step_value <= 0:
            raise _Unknown("step_not_positive", step_expr.get("range"))
        step_source["value"] = step_value

        protected = {induction_id, bound_id}
        if start_id is not None:
            protected.add(start_id)
        _check_body(body, protected)
        item.update(status="recovered", induction={"declaration_id": induction_id,
                    "range": induction.get("range")}, start=start, bound=bound,
                    step=step_value, step_source=step_source, condition_ast=condition)
    except _Unknown as error:
        item["reason"], item["unknown_range"] = error.reason, error.range
    return item


def recover(root: object, function_id: str, int_bits: int) -> dict[str, Any]:
    """Recover only the supported ForStmt recurrence subset in one AST root."""
    result: dict[str, Any] = {
        "schema_version": "column-loop-recovery/v1", "status": "unknown",
        "function_id": function_id, "int_bits": int_bits, "loops": [],
        "reason": None, "checked": False, "deployable": False,
        "relation_recovery": "incomplete",
    }
    if not isinstance(root, dict):
        result["reason"] = "root_not_object"
        return result
    if type(int_bits) is not int or not 2 <= int_bits <= 128:
        result["reason"] = "invalid_int_bits"
        return result
    matches = [node for node in _walk(root) if node.get("kind") in FUNCTION_KINDS and
               node.get("id") == function_id]
    bodies = [(node, child) for node in matches for child in _children(node)
              if child.get("kind") == "CompoundStmt"]
    if len(bodies) != 1:
        result["reason"] = "function_unique_body_not_found"
        return result
    _, body = bodies[0]
    loops = [node for node in _walk(body) if node.get("kind") == "ForStmt"]
    if not loops:
        result["reason"] = "no_for_loop"
        return result
    result["loops"] = [_recover_loop(root, loop, int_bits) for loop in loops]
    result["status"] = "recovered" if all(loop["status"] == "recovered" for loop in result["loops"]) else "unknown"
    if result["status"] == "unknown":
        result["reason"] = "one_or_more_loops_unknown"
    return result
