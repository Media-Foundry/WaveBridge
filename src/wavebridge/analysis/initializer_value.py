"""Link a restricted initializer to its value-producing call, retaining casts.

Clang PseudoObjectExpr::Create takes type/value kind from its result semantic
expression. JSON does not expose that result index. We require a unique matching
semantic expression, not simply the last child, and support only a static MS
property getter with a plain lvalue receiver reference. This does not establish
receiver purity or authorize removing its evaluation.
"""

from typing import Any


class _Unknown(Exception):
    pass


def _children(node):
    children = node.get("inner", [])
    if not isinstance(children, list) or any(not isinstance(c, dict) or not c for c in children):
        raise _Unknown("malformed_children")
    return children


def _type(node):
    info = node.get("type")
    value = info.get("qualType") if isinstance(info, dict) else None
    if not isinstance(value, str) or not value:
        raise _Unknown("missing_expression_type")
    return value


def _id(node):
    value = node.get("id")
    if not isinstance(value, str) or not value:
        raise _Unknown("missing_exact_id")
    return value


def _walk(root):
    pending = [root]
    while pending:
        node = pending.pop()
        if not isinstance(node, dict):
            continue
        yield node
        children = node.get("inner", [])
        if isinstance(children, list):
            pending.extend(children)


def link(root: object, initializer: object) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema_version": "initializer-value-link/v1", "status": "unknown",
        "reason": None, "call_id": None, "callee_declaration_id": None,
        "conversions_outer_to_inner": [], "pseudo_object": None,
        "checked": False, "deployable": False,
        "value_equivalence": "not_established", "coordinate_semantics": "not_established",
        "receiver_purity": "not_established",
        "assumptions": ["input is a faithful well-formed Clang AST in one translation unit",
                        "producer implements Clang PseudoObjectExpr result type/value-kind invariant",
                        "source expression is valid in its execution context"],
    }
    if not isinstance(root, dict) or not isinstance(initializer, dict):
        result["reason"] = "input_not_object"
        return result
    try:
        current = initializer
        wrappers = 0
        while current.get("kind") in {"ParenExpr", "ImplicitCastExpr"}:
            wrappers += 1
            if wrappers > 32:
                raise _Unknown("wrapper_budget_exceeded")
            children = _children(current)
            if len(children) != 1:
                raise _Unknown("ambiguous_initializer_wrapper")
            if current["kind"] == "ParenExpr":
                if (_type(current) != _type(children[0]) or
                        current.get("valueCategory") not in {"prvalue", "lvalue", "xvalue"} or
                        current.get("valueCategory") != children[0].get("valueCategory")):
                    raise _Unknown("parenthesis_type_or_category_mismatch")
            if current["kind"] == "ImplicitCastExpr":
                if (current.get("castKind") != "IntegralCast" or
                        current.get("valueCategory") != "prvalue"):
                    raise _Unknown("unsupported_initializer_cast")
                result["conversions_outer_to_inner"].append({
                    "cast_kind": current["castKind"], "source_type": _type(children[0]),
                    "target_type": _type(current), "range": current.get("range"),
                    "value_preservation": "not_established",
                })
            current = children[0]

        receiver = None
        if current.get("kind") == "PseudoObjectExpr":
            children = _children(current)
            if (len(children) != 3 or children[0].get("kind") != "MSPropertyRefExpr" or
                    children[0].get("valueCategory") != "lvalue"):
                raise _Unknown("unsupported_pseudo_object_shape")
            syntax, receiver, call = children
            if (_type(current) == "void" or current.get("valueCategory") != "prvalue" or
                    receiver.get("kind") != "OpaqueValueExpr" or
                    call.get("kind") != "CallExpr"):
                raise _Unknown("unsupported_pseudo_object_semantics")
            matches = [child for child in children[1:]
                       if _type(child) == _type(current) and
                       child.get("valueCategory") == current["valueCategory"]]
            if len(matches) != 1 or matches[0] is not call:
                raise _Unknown("pseudo_object_result_not_unique_call")
            if _children(syntax) != [receiver]:
                raise _Unknown("property_receiver_mismatch")
            source = _children(receiver)
            if (len(source) != 1 or source[0].get("kind") != "DeclRefExpr" or
                    _children(source[0]) or receiver.get("valueCategory") != "lvalue" or
                    source[0].get("valueCategory") != "lvalue" or
                    _type(receiver) != _type(source[0])):
                raise _Unknown("receiver_not_plain_lvalue_reference")
            reference = source[0].get("referencedDecl")
            if not isinstance(reference, dict) or reference.get("kind") != "VarDecl":
                raise _Unknown("receiver_not_variable")
            if "volatile" in _type(receiver).split():
                raise _Unknown("volatile_receiver")
            result["pseudo_object"] = {
                "expression_id": _id(current), "receiver_id": _id(receiver),
                "receiver_declaration_id": _id(reference),
                "result_selection": "unique_semantic_type_and_value_category_match",
                "expression_type": current.get("type"), "call_type": call.get("type"),
                "receiver_ast": receiver, "range": current.get("range"),
            }
            current = call

        if (current.get("kind") != "CallExpr" or len(_children(current)) != 1 or
                current.get("valueCategory") != "prvalue"):
            raise _Unknown("initializer_not_no_argument_call")
        call = current
        callee = _children(call)[0]
        if receiver is not None and callee.get("kind") != "ImplicitCastExpr":
            raise _Unknown("property_getter_decay_missing")
        if callee.get("kind") == "ImplicitCastExpr":
            if callee.get("castKind") != "FunctionToPointerDecay" or len(_children(callee)) != 1:
                raise _Unknown("unsupported_callee_cast")
            callee = _children(callee)[0]
        if receiver is not None:
            if (callee.get("kind") != "MemberExpr" or callee.get("isArrow") is not False or
                    _children(callee) != [receiver]):
                raise _Unknown("getter_receiver_mismatch")
            target = callee.get("referencedMemberDecl")
            expected_kind = "CXXMethodDecl"
        else:
            if callee.get("kind") != "DeclRefExpr" or _children(callee):
                raise _Unknown("callee_not_direct_free_function")
            reference = callee.get("referencedDecl")
            if not isinstance(reference, dict) or reference.get("kind") != "FunctionDecl":
                raise _Unknown("callee_not_direct_free_function")
            target = _id(reference)
            expected_kind = "FunctionDecl"
        if not isinstance(target, str) or not target:
            raise _Unknown("missing_callee_id")
        declarations = [node for node in _walk(root)
                        if node.get("id") == target and
                        node.get("kind") in {"FunctionDecl", "CXXMethodDecl"}]
        if len(declarations) != 1 or declarations[0].get("kind") != expected_kind:
            raise _Unknown("callee_declaration_not_unique")
        declaration = declarations[0]
        if receiver is not None and declaration.get("storageClass") != "static":
            raise _Unknown("property_getter_not_static")
        if declaration.get("variadic") or any(c.get("kind") == "ParmVarDecl" for c in _children(declaration)):
            raise _Unknown("getter_has_parameters")
        result.update(status="recovered", call_id=_id(call),
                      callee_declaration_id=target, call_type=_type(call),
                      call_range=call.get("range"))
    except _Unknown as error:
        result["reason"] = str(error)
    return result
