"""Conservative recovery of simple signed-int column recurrences from Clang AST."""

from __future__ import annotations

from typing import Any

from wavebridge.analysis.integer_constants import evaluate
from wavebridge.analysis.initializer_value import link as link_initializer_value

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


def _declaration_is_reference(declaration: dict[str, Any]) -> bool:
    """Classify declaration types, never the value type of a DeclRefExpr.

    This is intentionally separate from header type matching. Unknown aliases
    cannot establish that storage is an independent scalar.
    """
    info = declaration.get("type")
    if not isinstance(info, dict):
        raise _Unknown("declaration_type_unresolved", declaration.get("range"))
    spelling = info.get("desugaredQualType")
    if not isinstance(spelling, str) or not spelling.strip():
        if info.get("typeAliasDeclId") is not None:
            raise _Unknown("declaration_alias_type_unresolved", declaration.get("range"))
        spelling = info.get("qualType")
    if not isinstance(spelling, str) or not spelling.strip():
        raise _Unknown("declaration_type_unresolved", declaration.get("range"))
    if "&" in spelling:
        return True
    # Restrict non-reference declarations to built-in scalar/pointer/array
    # spellings. A remaining typedef name (including partially desugared names)
    # must not be assumed to denote value storage.
    words = spelling.replace("*", " ").replace("[", " ").replace("]", " ").split()
    builtins = {"const", "volatile", "restrict", "__restrict", "__restrict__",
                "signed", "unsigned", "short", "long", "int", "float", "double",
                "char", "bool", "void", "wchar_t", "char8_t", "char16_t", "char32_t"}
    if not words or any(word not in builtins and not word.isdecimal() for word in words):
        raise _Unknown("declaration_type_unresolved", declaration.get("range"))
    return False


def _storage_target(node: dict[str, Any], protected_ids: set[str]) -> None:
    """Accept only direct scalar storage or a simple array element, never guess aliases."""
    current = node
    while current.get("kind") == "ParenExpr":
        children = _children(current)
        if len(children) != 1:
            raise _Unknown("unsupported_storage_target", current.get("range"))
        current = children[0]
    if current.get("kind") == "DeclRefExpr":
        referenced = current.get("referencedDecl", {})
        if referenced.get("id") in protected_ids:
            raise _Unknown("protected_variable_may_be_modified", current.get("range"))
        if (not isinstance(referenced.get("id"), str) or
                referenced.get("kind") not in {"VarDecl", "ParmVarDecl"} or
                _declaration_is_reference(referenced)):
            raise _Unknown("unsupported_storage_target", current.get("range"))
        return
    if current.get("kind") == "ArraySubscriptExpr":
        children = _children(current)
        if len(children) == 2:
            base = children[0]
            while base.get("kind") in {"ParenExpr", "ImplicitCastExpr"}:
                parts = _children(base)
                if (len(parts) != 1 or (base.get("kind") == "ImplicitCastExpr" and
                        base.get("castKind") not in {"LValueToRValue", "ArrayToPointerDecay", "NoOp"})):
                    raise _Unknown("unsupported_storage_target", current.get("range"))
                base = parts[0]
            # The index is evaluated as a value; the enclosing traversal checks its effects.
            if base.get("kind") == "DeclRefExpr" and not _contains_ref(base, protected_ids):
                return
    raise _Unknown("unsupported_storage_target", current.get("range"))


BODY_KINDS = {
    "CompoundStmt", "DeclStmt", "VarDecl", "NullStmt", "IfStmt",
    "DeclRefExpr", "IntegerLiteral", "FloatingLiteral", "CXXBoolLiteralExpr",
    "ParenExpr", "ImplicitCastExpr", "CXXStaticCastExpr", "CStyleCastExpr",
    "BinaryOperator", "CompoundAssignOperator", "UnaryOperator", "ArraySubscriptExpr",
}


def _check_body(body: dict[str, Any], protected_ids: set[str]) -> None:
    for node in _walk(body):
        kind = node.get("kind")
        if kind in LOOP_KINDS:
            raise _Unknown("nested_loop_in_body", node.get("range"))
        if kind in CONTROL_KINDS:
            raise _Unknown("unsupported_control_flow_in_body", node.get("range"))
        if kind in CALL_KINDS:
            raise _Unknown("call_in_body", node.get("range"))
        # A whitelist is intentional: asm, constructors, statement expressions,
        # opaque builtins and new AST kinds cannot silently be treated as pure.
        if kind not in BODY_KINDS:
            raise _Unknown("unsupported_body_effect", node.get("range"))
        if kind == "UnaryOperator" and node.get("opcode") in {"++", "--", "&"}:
            if _contains_ref(node, protected_ids):
                raise _Unknown("protected_variable_may_be_modified", node.get("range"))
            if node.get("opcode") in {"++", "--"}:
                children = _children(node)
                if len(children) != 1:
                    raise _Unknown("unsupported_storage_target", node.get("range"))
                _storage_target(children[0], protected_ids)
        if kind == "VarDecl" and _declaration_is_reference(node):
            if any(_contains_ref(child, protected_ids) for child in _children(node)):
                raise _Unknown("protected_variable_reference_alias", node.get("range"))
        if kind in {"BinaryOperator", "CompoundAssignOperator"}:
            opcode = node.get("opcode")
            if opcode in ASSIGNMENT_OPCODES:
                children = _children(node)
                if len(children) != 2:
                    raise _Unknown("unsupported_storage_target", node.get("range"))
                _storage_target(children[0], protected_ids)


def _coordinate_header(root: dict[str, Any], induction: dict[str, Any],
                       initializer: dict[str, Any], condition: dict[str, Any],
                       increment: dict[str, Any]) -> dict[str, Any]:
    """Observe one exact CUDA/HIP-style coordinate header without proving values."""
    result: dict[str, Any] = {
        "schema_version": "coordinate-column-header-observation/v1",
        "status": "unknown", "reason": None,
        "start_value_link": None, "step_value_link": None,
        "induction_declaration_id": induction.get("id"),
        "bound_parameter_id": None,
        "recurrence_checked": False, "coordinate_semantics": "not_established",
        "launch_configuration_bound": False, "integer_abi_checked": False,
        "source_program_checked": False, "deployable": False,
        "obligations": [
            "bind the exact start getter and receiver to local x coordinate semantics",
            "bind the exact step getter and receiver to block x dimension semantics",
            "bind one actual launch block dimension and the corresponding local-id domain",
            "check unsigned-to-signed initialization and compound-assignment conversions",
            "check intermediate addition and final increment representability on the declared domain",
        ],
    }
    try:
        induction_id = induction.get("id")
        if not isinstance(induction_id, str) or not induction_id:
            raise _Unknown("coordinate_induction_id_missing")
        init_children = _children(initializer)
        if (initializer.get("kind") != "ImplicitCastExpr" or
                initializer.get("castKind") != "IntegralCast" or
                initializer.get("valueCategory") != "prvalue" or
                _type(initializer) != "int" or len(init_children) != 1 or
                init_children[0].get("kind") != "PseudoObjectExpr" or
                init_children[0].get("valueCategory") != "prvalue" or
                _type(init_children[0]) != "unsigned int"):
            raise _Unknown("coordinate_initializer_shape_unsupported")
        start_link = link_initializer_value(root, initializer)
        result["start_value_link"] = start_link
        conversions = start_link.get("conversions_outer_to_inner")
        if (start_link.get("status") != "recovered" or not isinstance(conversions, list) or
                len(conversions) != 1 or conversions[0].get("cast_kind") != "IntegralCast" or
                conversions[0].get("source_type") != "unsigned int" or
                conversions[0].get("target_type") != "int"):
            raise _Unknown("coordinate_start_value_link_not_recovered")

        condition_children = _children(condition)
        if (condition.get("kind") != "BinaryOperator" or condition.get("opcode") != "<" or
                _type(condition) != "bool" or len(condition_children) != 2):
            raise _Unknown("coordinate_condition_shape_unsupported")
        condition_induction, _ = _declref(condition_children[0])
        bound_id, bound_kind = _declref(condition_children[1])
        if condition_induction != induction_id or bound_kind != "ParmVarDecl":
            raise _Unknown("coordinate_condition_binding_mismatch")
        result["bound_parameter_id"] = bound_id

        increment_children = _children(increment)
        if (increment.get("kind") != "CompoundAssignOperator" or
                increment.get("opcode") != "+=" or _type(increment) != "int" or
                increment.get("valueCategory") != "lvalue" or
                increment.get("computeLHSType") != {"qualType": "unsigned int"} or
                increment.get("computeResultType") != {"qualType": "unsigned int"} or
                len(increment_children) != 2):
            raise _Unknown("coordinate_increment_shape_unsupported")
        increment_induction, _ = _declref(increment_children[0])
        step_expression = increment_children[1]
        if (increment_induction != induction_id or
                step_expression.get("kind") != "PseudoObjectExpr" or
                step_expression.get("valueCategory") != "prvalue" or
                _type(step_expression) != "unsigned int"):
            raise _Unknown("coordinate_increment_binding_mismatch")
        step_link = link_initializer_value(root, step_expression)
        result["step_value_link"] = step_link
        if (step_link.get("status") != "recovered" or
                step_link.get("conversions_outer_to_inner") != []):
            raise _Unknown("coordinate_step_value_link_not_recovered")
        result.update(status="observed", reason=None)
    except _Unknown as error:
        result["reason"] = error.reason
    return result


def _recover_loop(root: dict[str, Any], loop: dict[str, Any], int_bits: int) -> dict[str, Any]:
    item: dict[str, Any] = {
        "status": "unknown", "reason": None, "range": loop.get("range"),
        "induction": None, "start": None, "bound": None, "step": None,
        "step_source": None,
        "initializer_ast": None, "increment_ast": None,
        "coordinate_header_observation": None,
        "header_recurrence_observed": False,
        "body_preserves_induction": "not_established",
        "body_preserves_bound": "not_established",
        "body_effect_reason": None,
        "body_effect_unknown_range": None,
        "condition_ast": None, "assumptions": {
            "signed_recurrence_overflow": "external_precondition_unproven",
            "iteration_domain": "external_precondition_unproven",
            "memory_no_alias": "unproven",
            "source_validity": "external_precondition_unproven",
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
        if (induction.get("storageClass") not in (None, "auto", "register") or
                induction.get("tls") is not None or induction.get("thread_local") is not None):
            raise _Unknown("induction_storage_not_automatic", induction.get("range"))
        induction_id = induction.get("id")
        if not isinstance(induction_id, str):
            raise _Unknown("induction_id_missing", induction.get("range"))
        initializer = _initializer(induction)
        item["initializer_ast"] = initializer
        item["increment_ast"] = increment
        item["coordinate_header_observation"] = _coordinate_header(
            root, induction, initializer, condition, increment)
        coordinate = item["coordinate_header_observation"]
        if coordinate["status"] == "observed":
            protected = {induction_id, coordinate["bound_parameter_id"]}
            for key in ("start_value_link", "step_value_link"):
                protected.add(coordinate[key]["pseudo_object"]["receiver_declaration_id"])
            try:
                # This only establishes the supported body's non-modification
                # premise. Coordinate values, conversions and recurrence remain
                # unknown and must not be inferred from these two flags.
                _check_body(body, protected)
                item.update(body_preserves_induction="established_in_supported_effect_subset",
                            body_preserves_bound="established_in_supported_effect_subset")
            except _Unknown as error:
                item["body_effect_reason"] = error.reason
                item["body_effect_unknown_range"] = error.range
        start_expr = _unwrap_value(initializer)
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
        item["header_recurrence_observed"] = True

        protected = {induction_id, bound_id}
        if start_id is not None:
            protected.add(start_id)
        _check_body(body, protected)
        item.update(body_preserves_induction="established_in_supported_effect_subset",
                    body_preserves_bound="established_in_supported_effect_subset")
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
