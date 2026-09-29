"""Conservative recovery of simple signed-int column recurrences from Clang AST."""

from __future__ import annotations

import re
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
    """Recognize builtin storage paths; index effects are checked by the body walk."""
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
        subscripts = []
        while current.get("kind") == "ArraySubscriptExpr":
            subscripts.append(current)
            children = current.get("inner")
            if (len(subscripts) > 8 or not isinstance(children, list) or len(children) != 2 or
                    any(not isinstance(child, dict) or not child for child in children)):
                raise _Unknown("unsupported_storage_target", current.get("range"))
            base = children[0]
            while base.get("kind") in {"ParenExpr", "ImplicitCastExpr"}:
                parts = _children(base)
                if (len(parts) != 1 or (base.get("kind") == "ImplicitCastExpr" and
                        base.get("castKind") not in {"LValueToRValue", "ArrayToPointerDecay", "NoOp"})):
                    raise _Unknown("unsupported_storage_target", current.get("range"))
                base = parts[0]
            current = base
        if current.get("kind") == "DeclRefExpr" and not _contains_ref(current, protected_ids):
            if len(subscripts) > 1:
                declaration = current.get("referencedDecl", {})
                if (not isinstance(declaration.get("id"), str) or
                        declaration.get("kind") not in {"VarDecl", "ParmVarDecl"} or
                        any(part.get("valueCategory") != "lvalue" or
                            not isinstance(_type(part), str) for part in subscripts)):
                    raise _Unknown("unsupported_storage_target", node.get("range"))
                # A plain pointer-to-array declarator needs parentheses. Normalize
                # only that spelling for the existing conservative type classifier;
                # do not erase reference syntax or expand unresolved aliases.
                info = declaration.get("type", {})
                if not isinstance(info, dict):
                    raise _Unknown("declaration_type_unresolved", node.get("range"))
                spelling = info.get("desugaredQualType", info.get("qualType"))
                if (isinstance(spelling, str) and
                        (info.get("typeAliasDeclId") is None or "desugaredQualType" in info) and
                        re.search(r"\(\s*\*\s*\)\s*\[", spelling)):
                    normalized = re.sub(r"\(\s*\*\s*\)(?=\s*\[)", "*", spelling)
                    declaration = {**declaration, "type": {**info, "desugaredQualType": normalized}}
                if _declaration_is_reference(declaration):
                    raise _Unknown("unsupported_storage_target", node.get("range"))
            # Every index and wrapper remains in the enclosing effect traversal.
            return
    raise _Unknown("unsupported_storage_target", current.get("range"))


BODY_KINDS = {
    "CompoundStmt", "DeclStmt", "VarDecl", "NullStmt", "IfStmt",
    "DeclRefExpr", "IntegerLiteral", "FloatingLiteral", "CXXBoolLiteralExpr",
    "ParenExpr", "ImplicitCastExpr", "CXXStaticCastExpr", "CStyleCastExpr",
    "BinaryOperator", "CompoundAssignOperator", "UnaryOperator", "ArraySubscriptExpr",
    "ConditionalOperator",
}


def _check_literal_float_array_init(node: dict[str, Any]) -> None:
    """Check all semantic initializer slots, including Clang's array_filler.

    This intentionally excludes expression/record/reference initialization.
    array_filler is not an ordinary `inner` child and must never be ignored.
    """
    def unsupported():
        raise _Unknown("unsupported_array_initializer_effect", node.get("range"))

    spelling = _type(node)
    if not isinstance(spelling, str):
        unsupported()
    match = re.fullmatch(r"float\s*\[([1-9][0-9]*)\]", spelling)
    if not match or int(match.group(1)) > 4096 or node.get("valueCategory") != "prvalue":
        unsupported()
    count = int(match.group(1))
    if "array_filler" in node:
        slots = node["array_filler"]
        if (node.get("inner", []) != [] or not isinstance(slots, list) or
                not 1 <= len(slots) <= count + 1 or
                not isinstance(slots[0], dict) or slots[0].get("kind") != "ImplicitValueInitExpr"):
            unsupported()
    else:
        slots = node.get("inner")
        if not isinstance(slots, list) or len(slots) != count:
            unsupported()
    for slot in slots:
        if (not isinstance(slot, dict) or slot.get("kind") not in {"FloatingLiteral", "ImplicitValueInitExpr"} or
                _type(slot) != "float" or slot.get("valueCategory") != "prvalue" or
                slot.get("inner", []) != [] or "array_filler" in slot):
            unsupported()


def _check_bool_substitution(node: dict[str, Any]) -> None:
    """Trust only Clang's concrete bool-literal replacement, not an arbitrary child."""
    children = node.get("inner")
    if (_type(node) != "bool" or node.get("valueCategory") != "prvalue" or
            not isinstance(children, list) or len(children) not in (1, 2) or
            any(not isinstance(child, dict) or not child for child in children)):
        raise _Unknown("unsupported_body_template_substitution", node.get("range"))
    if len(children) == 2:
        parameter = children[0]
        if (parameter.get("kind") != "NonTypeTemplateParmDecl" or _type(parameter) != "bool" or
                not isinstance(parameter.get("id"), str) or not parameter["id"] or
                parameter.get("isParameterPack") or parameter.get("inner", []) != []):
            raise _Unknown("unsupported_body_template_parameter", node.get("range"))
    literal = children[-1]
    if (literal.get("kind") != "CXXBoolLiteralExpr" or _type(literal) != "bool" or
            literal.get("valueCategory") != "prvalue" or type(literal.get("value")) is not bool or
            literal.get("inner", []) != []):
        raise _Unknown("nonliteral_body_template_substitution", node.get("range"))


def _hinted_loop(node: dict[str, Any]) -> dict[str, Any]:
    """Expose the original loop, never the effect of an optimized/unrolled program."""
    children = node.get("inner")
    if (not isinstance(children, list) or not 2 <= len(children) <= 9 or
            any(not isinstance(child, dict) or not child for child in children) or
            children[-1].get("kind") != "ForStmt"):
        raise _Unknown("unsupported_body_attribute_wrapper", node.get("range"))
    for attribute in children[:-1]:
        expressions = attribute.get("inner", [])
        if (attribute.get("kind") != "LoopHintAttr" or not isinstance(expressions, list) or
                any(expression != {} for expression in expressions)):
            raise _Unknown("unsupported_body_loop_hint", attribute.get("range"))
    return children[-1]


def _static_bool_value(node: dict[str, Any], depth=0) -> bool:
    """Only literal/compiler-substituted bools and side-effect-free wrappers."""
    if depth > 32 or _type(node) != "bool" or node.get("valueCategory") != "prvalue":
        raise _Unknown("static_bool_type_or_depth_unsupported", node.get("range"))
    children = node.get("inner", [])
    if not isinstance(children, list) or any(not isinstance(child, dict) or not child for child in children):
        raise _Unknown("static_bool_children_unsupported", node.get("range"))
    kind = node.get("kind")
    if kind == "CXXBoolLiteralExpr" and type(node.get("value")) is bool and not children:
        return node["value"]
    if kind == "SubstNonTypeTemplateParmExpr":
        _check_bool_substitution(node)
        return children[-1]["value"]
    if kind == "ParenExpr" and len(children) == 1:
        return _static_bool_value(children[0], depth + 1)
    if kind == "UnaryOperator" and node.get("opcode") == "!" and len(children) == 1:
        return not _static_bool_value(children[0], depth + 1)
    raise _Unknown("static_bool_not_established", node.get("range"))


def _check_body(body: dict[str, Any], protected_ids: set[str],
                property_callback=None, nested_callback=None, call_callback=None, branch_callback=None) -> None:
    pending = [body]
    while pending:
        node = pending.pop()
        kind = node.get("kind")
        if kind == "IfStmt" and branch_callback is not None:
            selected = branch_callback(node)
            if selected is not None:
                pending.extend(reversed(selected))
                continue  # Callback checked full guard evaluation and selected branch.
        if kind == "SubstNonTypeTemplateParmExpr":
            _check_bool_substitution(node)
            continue  # Only the validated literal has runtime expression meaning.
        if kind == "AttributedStmt":
            pending.append(_hinted_loop(node))
            continue  # The loop still undergoes exactly the ordinary checks below.
        if kind == "PseudoObjectExpr" and property_callback is not None:
            if property_callback(node) is True:
                # The callback is responsible for a fresh conditional effect
                # check. Only then may its semantic call subtree be skipped.
                continue
            raise _Unknown("property_effect_not_checked", node.get("range"))
        if kind == "ForStmt" and nested_callback is not None:
            nested_callback(node)
            continue
        if kind in LOOP_KINDS:
            raise _Unknown("nested_loop_in_body", node.get("range"))
        if kind in CONTROL_KINDS:
            raise _Unknown("unsupported_control_flow_in_body", node.get("range"))
        if kind in CALL_KINDS:
            if kind == "CallExpr" and call_callback is not None:
                if call_callback(node) is True:
                    continue  # Fresh check covers the COMPLETE call evaluation.
                raise _Unknown("call_effect_not_checked", node.get("range"))
            raise _Unknown("call_in_body", node.get("range"))
        if kind == "InitListExpr":
            _check_literal_float_array_init(node)
            continue  # Every semantic slot was checked, not just `inner`.
        # A whitelist is intentional: asm, constructors, statement expressions,
        # opaque builtins and new AST kinds cannot silently be treated as pure.
        if kind not in BODY_KINDS:
            raise _Unknown("unsupported_body_effect", node.get("range"))
        if kind == "ConditionalOperator":
            operands = node.get("inner")
            if (not isinstance(operands, list) or len(operands) != 3 or
                    any(not isinstance(child, dict) or not child for child in operands)):
                raise _Unknown("conditional_body_operands_ambiguous", node.get("range"))
            # Effect analysis visits the condition AND BOTH result branches.
            # Unlike constant evaluation, it never erases a branch on a guessed
            # value. A conditional lvalue is still not a supported write target.
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
        pending.extend(reversed(_children(node)))


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


def _check_nested_loop(root: dict[str, Any], loop: dict[str, Any], int_bits: int,
                       protected_ids: set[str], call_callback=None) -> dict[str, Any]:
    """One nested level, constant finite recurrence, and enclosing storage preservation.

    This is conditional on the same valid-execution/no-alias premises as the
    parent. A finite header recurrence alone does not prove body completion.
    """
    nested = _recover_loop(root, loop, int_bits, allow_nested=False, call_callback=call_callback)
    if nested["status"] != "recovered":
        raise _Unknown(nested["reason"], nested.get("unknown_range"))
    start, bound, step = nested["start"], nested["bound"], nested["step"]
    if (start["kind"] != "integer_literal" or bound["kind"] != "constant_declaration" or
            start["value"] < 0 or bound["value"] < 0):
        raise _Unknown("nested_domain_not_nonnegative_constants", loop.get("range"))
    first, limit = start["value"], bound["value"]
    iterations = max(0, (limit - first + step - 1) // step)
    final = first + iterations * step
    if final > (1 << (int_bits - 1)) - 1:
        raise _Unknown("nested_signed_increment_overflow", loop.get("range"))
    if nested["induction"]["declaration_id"] in protected_ids:
        raise _Unknown("nested_induction_conflicts_with_enclosing", loop.get("range"))
    # The inner check protects its own recurrence. Independently recheck ALL
    # executable components against the enclosing loop's protected declarations.
    init, _, condition, increment, body = loop["inner"]
    for component in (init, condition, increment, body):
        _check_body(component, protected_ids, call_callback=call_callback)
    return {
        "range": loop.get("range"), "recurrence": nested,
        "iterations": iterations, "final_induction": final,
        "enclosing_storage_preserved": "established_in_supported_effect_subset",
        "completion": "conditional_on_valid_body_execution",
        "checked": False, "deployable": False,
    }


def _recover_loop(root: dict[str, Any], loop: dict[str, Any], int_bits: int,
                  *, allow_nested: bool = True, call_callback=None, header_only=False) -> dict[str, Any]:
    item: dict[str, Any] = {
        "status": "unknown", "reason": None, "range": loop.get("range"),
        "induction": None, "start": None, "bound": None, "step": None,
        "step_source": None,
        "nested_loops": [],
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
        if coordinate["status"] == "observed" and not header_only:
            protected = {induction_id, coordinate["bound_parameter_id"]}
            for key in ("start_value_link", "step_value_link"):
                protected.add(coordinate[key]["pseudo_object"]["receiver_declaration_id"])
            try:
                # This only establishes the supported body's non-modification
                # premise. Coordinate values, conversions and recurrence remain
                # unknown and must not be inferred from these two flags.
                _check_body(body, protected, call_callback=call_callback)
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

        builtin_increment = (increment.get("kind") == "UnaryOperator" and
                             increment.get("opcode") == "++")
        if builtin_increment:
            postfix = increment.get("isPostfix")
            expected_category = "prvalue" if postfix is True else "lvalue"
            if (type(postfix) is not bool or _type(induction) != "int" or _type(increment) != "int" or
                    increment.get("valueCategory") != expected_category):
                raise _Unknown("builtin_increment_type_or_category", increment.get("range"))
            operands = _children(increment)
            if len(operands) != 1:
                raise _Unknown("increment_operands_ambiguous", increment.get("range"))
            target = operands[0]
            while target.get("kind") == "ParenExpr":
                children = _children(target)
                if (len(children) != 1 or _type(target) != "int" or
                        target.get("valueCategory") != "lvalue"):
                    raise _Unknown("builtin_increment_target_unsupported", target.get("range"))
                target = children[0]
            declaration = target.get("referencedDecl", {})
            if (target.get("kind") != "DeclRefExpr" or _type(target) != "int" or
                    target.get("valueCategory") != "lvalue" or
                    declaration.get("kind") != "VarDecl" or _type(declaration) != "int"):
                raise _Unknown("builtin_increment_target_unsupported", target.get("range"))
            if declaration.get("id") != induction_id:
                raise _Unknown("increment_uses_other_induction", target.get("range"))
            step_value = 1
            step_source = {"kind": "builtin_increment", "postfix": postfix,
                           "range": increment.get("range")}
        elif increment.get("kind") != "CompoundAssignOperator" or increment.get("opcode") != "+=":
            raise _Unknown("increment_not_plus_equal", increment.get("range"))
        increment_children = _children(increment) if not builtin_increment else []
        if not builtin_increment and len(increment_children) != 2:
            raise _Unknown("increment_operands_ambiguous", increment.get("range"))
        increment_induction = induction_id
        if not builtin_increment:
            increment_induction, _ = _declref(increment_children[0])
        if increment_induction != induction_id:
            raise _Unknown("increment_uses_other_induction", increment_children[0].get("range"))
        step_expr = increment if builtin_increment else _unwrap_value(increment_children[1])
        step_source: dict[str, Any]
        if builtin_increment:
            pass  # Preserve the observed unary AST; no synthetic += expression.
        elif step_expr.get("kind") == "IntegerLiteral" and _signed_int(step_expr):
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

        if header_only:
            item.update(status="observed", induction={"declaration_id": induction_id,
                        "range": induction.get("range")}, start=start, bound=bound,
                        step=step_value, step_source=step_source, condition_ast=condition)
            return item

        protected = {induction_id, bound_id}
        if start_id is not None:
            protected.add(start_id)
        def check_nested(node):
            item["nested_loops"].append(_check_nested_loop(root, node, int_bits, protected, call_callback))

        _check_body(body, protected, nested_callback=check_nested if allow_nested else None,
                    call_callback=call_callback)
        item.update(body_preserves_induction="established_in_supported_effect_subset",
                    body_preserves_bound="established_in_supported_effect_subset")
        item.update(status="recovered", induction={"declaration_id": induction_id,
                    "range": induction.get("range")}, start=start, bound=bound,
                    step=step_value, step_source=step_source, condition_ast=condition)
    except _Unknown as error:
        item["reason"], item["unknown_range"] = error.reason, error.range
    return item


def _recover(root: object, function_id: str, int_bits: int, call_callback=None) -> dict[str, Any]:
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
    loops = []
    pending = [(body, 0)]
    while pending:
        node, depth = pending.pop()
        if node.get("kind") == "ForStmt":
            loops.append((node, depth))
        child_depth = depth + int(node.get("kind") in LOOP_KINDS)
        pending.extend((child, child_depth) for child in reversed(_children(node)))
    if not loops:
        result["reason"] = "no_for_loop"
        return result
    result["loops"] = [dict(_recover_loop(root, loop, int_bits, allow_nested=depth == 0,
                                         call_callback=call_callback),
                            lexical_loop_depth=depth) for loop, depth in loops]
    result["status"] = "recovered" if all(loop["status"] == "recovered" for loop in result["loops"]) else "unknown"
    if result["status"] == "unknown":
        result["reason"] = "one_or_more_loops_unknown"
    return result


def recover(root: object, function_id: str, int_bits: int) -> dict[str, Any]:
    """Default recovery has no external-call effect assumptions."""
    return _recover(root, function_id, int_bits)


def observe_header(root, loop_id, int_bits, *, max_ast_nodes=None):
    """Observe an exact original loop header, never an edited/break-free loop."""
    from wavebridge.verification.getter_returns import _hash

    budget = 1_000_000 if max_ast_nodes is None else max_ast_nodes
    result = {"schema_version": "column-loop-header-observation/v1", "status": "unknown", "reason": None,
              "scope": "original_for_header_only", "header": None, "constant_checks": [],
              "source_program_checked": False, "deployable": False, "full_iteration_domain_established": False,
              "body_effects_checked": False, "int_bits": int_bits,
              "assumptions": ["faithful valid translation unit", "int_bits is an externally supplied signed-int ABI"],
              "limitations": ["body effects, exits, overflow domain and complete recurrence are not checked"],
              "budget": {"max_ast_nodes": budget}}
    if (not isinstance(root, dict) or root.get("kind") != "TranslationUnitDecl" or
            not isinstance(loop_id, str) or not loop_id or type(int_bits) is not int or not 2 <= int_bits <= 128 or
            type(budget) is not int or not 1 <= budget <= 10_000_000):
        result["reason"] = "invalid_inputs_or_budget"
        return result
    try:
        index, pending, count = {}, [root], 0
        while pending:
            node = pending.pop()
            count += 1
            if count > budget:
                raise _Unknown("ast_node_budget_exceeded")
            if not isinstance(node, dict) or not isinstance(node.get("inner", []), list):
                raise _Unknown("malformed_ast")
            if isinstance(node.get("id"), str):
                index.setdefault(node["id"], []).append(node)
            pending.extend(node.get("inner", []))
        matches = index.get(loop_id, [])
        if len(matches) != 1 or matches[0].get("kind") != "ForStmt":
            raise _Unknown("loop_identity_not_unique")
        loop = matches[0]
        # All declaration lookups in the observed header must be unambiguous.
        for component in loop.get("inner", [])[:-1]:
            for node in _walk(component):
                if node.get("kind") == "DeclRefExpr":
                    reference = node.get("referencedDecl", {})
                    definitions = index.get(reference.get("id"), [])
                    if (len(definitions) != 1 or definitions[0].get("kind") != reference.get("kind")
                            or definitions[0].get("type") != reference.get("type")):
                        raise _Unknown("header_declaration_not_unique_or_mismatched")
        header = _recover_loop(root, loop, int_bits, header_only=True)
        result["header"] = header
        if header["status"] != "observed":
            raise _Unknown("unsupported_header:" + str(header["reason"]))
        for source in (header["bound"], header["step_source"]):
            if source.get("kind") != "constant_declaration":
                continue
            checked = evaluate(root, source["declaration_id"], int_bits)
            result["constant_checks"].append(checked)
            if checked["status"] != "evaluated" or checked["value"] != source["value"]:
                raise _Unknown("header_constant_not_rechecked")
            if any(len(index.get(item["declaration_id"], [])) != 1 for item in checked["sources"]):
                raise _Unknown("header_constant_dependency_not_unique")
        result.update(status="observed", loop_id=loop_id,
                      input_sha256={"root": _hash(root), "loop_id": _hash(loop_id), "int_bits": _hash(int_bits)})
    except _Unknown as error:
        result["reason"] = error.reason
    except (TypeError, ValueError, KeyError, RecursionError):
        result["reason"] = "malformed_or_too_deep_input"
    return result


def recover_with_builtin_effects(payload, function_id, int_bits, call_protocols, *, max_ast_nodes=None):
    """Separate conditional path; never accepts caller-supplied success reports."""
    return _recover_with_call_effects(payload, function_id, int_bits, call_protocols,
                                      max_ast_nodes=max_ast_nodes, allow_scalar=False)


def recover_with_call_effects(payload, function_id, int_bits, call_protocols, *, max_ast_nodes=None,
                              allow_unary_float=False, allow_using_shadows=False):
    """Fresh builtin or scalar call checks, with explicit unverified leaf premises."""
    return _recover_with_call_effects(payload, function_id, int_bits, call_protocols,
                                      max_ast_nodes=max_ast_nodes, allow_scalar=True,
                                      allow_unary_float=allow_unary_float, allow_using_shadows=allow_using_shadows)


def _recover_with_call_effects(payload, function_id, int_bits, call_protocols, *, max_ast_nodes, allow_scalar,
                               allow_unary_float=False, allow_using_shadows=False):
    from wavebridge.verification.builtin_calls import (
        check_call_no_memory_write, MAX_AST_NODES, HARD_MAX_AST_NODES)
    from wavebridge.verification.scalar_call_effects import check_no_memory_write as check_scalar_call
    from wavebridge.verification.getter_returns import _hash

    budget = MAX_AST_NODES if max_ast_nodes is None else max_ast_nodes
    result = {"schema_version": "column-loop-builtin-effects/v1", "status": "unknown",
              "reason": None, "recovery": None, "call_effect_checks": {},
              "checked": False, "source_program_checked": False, "deployable": False,
              "external_call_effects_verified": False,
              "scope": "restricted_loop_recurrence_under_explicit_builtin_effect_assumptions",
              "limitations": ["not a source-program, FP-value or deployment guarantee",
                              "source validity, memory non-aliasing and recurrence domain remain external",
                              "partial successful calls never upgrade an unknown loop"],
              "budget": {"max_ast_nodes_per_scan": budget, "max_call_protocols": 64}}
    result["builtin_call_policy"] = {"schema_version": "builtin-callsite-policy/v1",
                                    "allow_unary_float": allow_unary_float,
                                    "allow_using_shadows": allow_using_shadows}
    if allow_scalar:
        result["schema_version"] = "column-loop-call-effects/v1"
        result["scope"] = "restricted_loop_recurrence_under_explicit_call_effect_assumptions"
    if (not isinstance(payload, dict) or not isinstance(payload.get("ast"), dict) or
            payload["ast"].get("kind") != "TranslationUnitDecl" or
            not isinstance(function_id, str) or not function_id or
            not isinstance(call_protocols, dict) or len(call_protocols) > 64 or
            any(not isinstance(k, str) or not k or not isinstance(v, dict) for k, v in call_protocols.items()) or
            type(budget) is not int or not 1 <= budget <= HARD_MAX_AST_NODES or
            type(allow_unary_float) is not bool or type(allow_using_shadows) is not bool):
        result["reason"] = "invalid_inputs_or_budget"
        return result
    try:
        # Bound and validate the traversal before using the legacy recursive
        # walker. Do not silently reinterpret a malformed new-path input.
        pending, count = [payload["ast"]], 0
        while pending:
            node = pending.pop()
            count += 1
            if count > budget:
                result["reason"] = "ast_node_budget_exceeded"
                return result
            if not isinstance(node, dict) or not isinstance(node.get("inner", []), list):
                result["reason"] = "malformed_ast"
                return result
            pending.extend(node.get("inner", []))
        result["input_sha256"] = {"native_envelope": _hash(payload), "function_id": _hash(function_id),
                                  "int_bits": _hash(int_bits), "call_protocols": _hash(call_protocols),
                                  "builtin_call_policy": _hash(result["builtin_call_policy"])}

        def check_call(node):
            identifier = node.get("id")
            if not isinstance(identifier, str) or identifier not in call_protocols:
                return False
            reports = result["call_effect_checks"]
            if identifier not in reports:
                protocol = call_protocols[identifier]
                if allow_scalar and protocol.get("schema_version") == "scalar-leaf-effect-assumption/v1":
                    reports[identifier] = check_scalar_call(
                        payload["ast"], identifier, protocol, max_ast_nodes=budget)
                else:
                    reports[identifier] = check_call_no_memory_write(
                        payload, identifier, protocol, max_ast_nodes=budget,
                        allow_unary_float=allow_unary_float, allow_using_shadows=allow_using_shadows)
            return reports[identifier]["status"] == "checked"

        recovery = _recover(payload["ast"], function_id, int_bits, call_callback=check_call)
        result["recovery"] = recovery
        # This child must not masquerade as the default effect-subset result in
        # existing combination checkers which do not consume the new premises.
        recovery["schema_version"] = "column-loop-recovery-with-external-calls/v1"
        if allow_scalar:
            recovery["schema_version"] = "column-loop-recovery-with-call-effects/v1"
        recovery["external_call_effects_verified"] = False
        pending = list(recovery["loops"])
        while pending:
            loop = pending.pop()
            assumption_key = "external_call_effects" if allow_scalar else "builtin_call_effects"
            loop["assumptions"][assumption_key] = "explicit_external_protocols_unverified"
            for flag in ("body_preserves_induction", "body_preserves_bound"):
                if loop.get(flag) == "established_in_supported_effect_subset":
                    loop[flag] = "established_under_external_call_effect_assumptions"
            for nested in loop.get("nested_loops", []):
                nested["enclosing_storage_preserved"] = "established_under_external_call_effect_assumptions"
                pending.append(nested["recurrence"])
        result["status"], result["reason"] = recovery["status"], recovery["reason"]
        result["unused_call_protocol_ids"] = sorted(set(call_protocols) - set(result["call_effect_checks"]))
        if result["status"] == "recovered" and result["unused_call_protocol_ids"]:
            result["status"], result["reason"] = "unknown", "unused_call_protocols"
    except (TypeError, ValueError, RecursionError, KeyError):
        result["status"], result["reason"] = "unknown", "malformed_or_too_deep_input"
    return result
