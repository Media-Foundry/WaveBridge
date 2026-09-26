"""Restricted signed-int constant evaluation over one real Clang AST root."""

from __future__ import annotations

from typing import Any

WRAPPERS = {"ParenExpr", "ConstantExpr", "ExprWithCleanups", "FullExpr"}
ARITHMETIC = {"+", "-", "*", "/", "%"}
SHIFTS = {"<<", ">>"}
COMPARISONS = {"<", "<=", ">", ">=", "==", "!="}


class _Unknown(Exception):
    def __init__(self, reason: str):
        self.reason = reason


def _children(node: dict[str, Any]) -> list[dict[str, Any]]:
    inner = node.get("inner", [])
    return [child for child in inner if isinstance(child, dict)] if isinstance(inner, list) else []


def _walk(node: dict[str, Any]):
    yield node
    for child in _children(node):
        yield from _walk(child)


def _qual_type(node: dict[str, Any]) -> str | None:
    type_info = node.get("type")
    return type_info.get("qualType") if isinstance(type_info, dict) else None


def _signed_int_type(qual_type: str | None) -> bool:
    if not isinstance(qual_type, str):
        return False
    if "volatile" in qual_type.split():
        return False
    words = qual_type.replace("const", "").split()
    return words == ["int"] and "unsigned" not in qual_type


def _bool_type(qual_type: str | None) -> bool:
    return isinstance(qual_type, str) and qual_type.split() in (["bool"], ["const", "bool"])


def _checked(value: int, int_bits: int) -> int:
    if not -(1 << (int_bits - 1)) <= value <= (1 << (int_bits - 1)) - 1:
        raise _Unknown("signed_overflow")
    return value


def _same_type_wrapper(node: dict[str, Any], child: dict[str, Any]) -> bool:
    parent_type, child_type = _qual_type(node), _qual_type(child)
    return parent_type is None or child_type is None or parent_type == child_type


def _initializer(node: dict[str, Any]) -> dict[str, Any]:
    candidates = [child for child in _children(node)
                  if not str(child.get("kind", "")).endswith("Attr")]
    if node.get("init") is None or len(candidates) != 1:
        raise _Unknown("initializer_missing_or_ambiguous")
    return candidates[0]


def evaluate(root: object, declaration_id: str, int_bits: int) -> dict[str, Any]:
    """Evaluate one exact declaration ID; every unsupported condition yields unknown."""
    result: dict[str, Any] = {
        "schema_version": "signed-int-evaluation/v1", "status": "unknown",
        "declaration_id": declaration_id, "int_bits": int_bits, "value": None,
        "expression_range": None, "sources": [], "checked": False,
        "relation_recovery": "incomplete",
        "selected_branches": [], "template_substitutions": [],
    }
    if not isinstance(root, dict):
        result["reason"] = "root_not_object"
        return result
    if type(int_bits) is not int or not 2 <= int_bits <= 128:
        result["reason"] = "invalid_int_bits"
        return result
    declarations = {node["id"]: node for node in _walk(root)
                    if isinstance(node.get("id"), str) and
                    isinstance(node.get("kind"), str) and node["kind"].endswith("Decl")}
    active: set[str] = set()
    sources: list[dict[str, Any]] = []

    def predicate_value(node: dict[str, Any]) -> bool:
        """Only typed builtin predicates; never execute a call or user conversion."""
        kind, children = node.get("kind"), _children(node)
        if not _bool_type(_qual_type(node)):
            raise _Unknown("unsupported_condition_type")
        if kind == "CXXBoolLiteralExpr" and type(node.get("value")) is bool and not children:
            return node["value"]
        if kind in WRAPPERS and len(children) == 1 and _bool_type(_qual_type(children[0])):
            return predicate_value(children[0])
        if kind == "ImplicitCastExpr" and len(children) == 1:
            if node.get("castKind") == "IntegralToBoolean" and _signed_int_type(_qual_type(children[0])):
                return expression_value(children[0]) != 0
            if node.get("castKind") == "NoOp" and _bool_type(_qual_type(children[0])):
                return predicate_value(children[0])
        if kind == "UnaryOperator" and node.get("opcode") == "!" and len(children) == 1:
            return not predicate_value(children[0])
        if kind == "BinaryOperator" and len(children) == 2:
            opcode = node.get("opcode")
            if opcode in {"&&", "||"}:
                if not all(_bool_type(_qual_type(child)) for child in children):
                    raise _Unknown("unsupported_condition_operand_type")
                left = predicate_value(children[0])
                # Short-circuiting is semantic: the other operand is not evaluated.
                return (left and predicate_value(children[1]) if opcode == "&&"
                        else left or predicate_value(children[1]))
            if opcode in COMPARISONS:
                if not all(_signed_int_type(_qual_type(child)) for child in children):
                    raise _Unknown("unsupported_comparison_operand_type")
                left, right = expression_value(children[0]), expression_value(children[1])
                return {"<": left < right, "<=": left <= right, ">": left > right,
                        ">=": left >= right, "==": left == right, "!=": left != right}[opcode]
        raise _Unknown("unsupported_condition_expression")

    def template_replacement(node: dict[str, Any]) -> int:
        children = _children(node)
        if not _signed_int_type(_qual_type(node)):
            raise _Unknown("unsupported_template_substitution")
        parameter = None
        if len(children) == 2 and children[0].get("kind") == "NonTypeTemplateParmDecl":
            parameter, replacement = children
            if (not _signed_int_type(_qual_type(parameter)) or
                    not isinstance(parameter.get("id"), str) or parameter.get("isParameterPack")):
                raise _Unknown("unsupported_template_parameter")
        elif len(children) == 1:
            # Some Clang versions omit the parameter-declaration child. The
            # trusted typed substitution node still supplies its concrete value;
            # this branch does not claim to independently bind the template arg.
            replacement = children[0]
        else:
            raise _Unknown("unsupported_template_substitution")
        if (replacement.get("kind") != "IntegerLiteral" or
                not _signed_int_type(_qual_type(replacement)) or _children(replacement) or
                replacement.get("valueCategory", "prvalue") != "prvalue"):
            raise _Unknown("nonliteral_template_substitution")
        value = expression_value(replacement)
        result["template_substitutions"].append({
            "range": node.get("range"), "parameter_id": parameter.get("id") if parameter else None,
            "value": value, "origin": "trusted_clang_substitution_literal",
        })
        return value

    def declaration_value(clang_id: str) -> int:
        declaration = declarations.get(clang_id)
        if declaration is None:
            raise _Unknown("missing_declaration")
        if clang_id in active:
            raise _Unknown("cyclic_reference")
        if declaration.get("kind") != "VarDecl":
            raise _Unknown("referenced_declaration_not_variable")
        qual_type = _qual_type(declaration)
        if not _signed_int_type(qual_type):
            raise _Unknown("unsupported_or_unsigned_type")
        if declaration.get("constexpr") is not True and "const" not in qual_type.split():
            raise _Unknown("variable_not_constexpr_or_const")
        expression = _initializer(declaration)
        active.add(clang_id)
        sources.append({"declaration_id": clang_id, "range": declaration.get("range")})
        try:
            return expression_value(expression)
        finally:
            active.remove(clang_id)

    def expression_value(node: dict[str, Any]) -> int:
        kind, children = node.get("kind"), _children(node)
        if kind == "SubstNonTypeTemplateParmExpr":
            return template_replacement(node)
        if kind == "ConditionalOperator":
            if (len(children) != 3 or not _signed_int_type(_qual_type(node)) or
                    not all(_signed_int_type(_qual_type(child)) for child in children[1:])):
                raise _Unknown("unsupported_conditional_type_or_shape")
            selected = 1 if predicate_value(children[0]) else 2
            result["selected_branches"].append({"range": node.get("range"),
                                                "selected_operand": selected})
            return expression_value(children[selected])
        if kind == "IntegerLiteral":
            if not _signed_int_type(_qual_type(node)):
                raise _Unknown("unsupported_or_unsigned_type")
            try:
                return _checked(int(str(node["value"]), 0), int_bits)
            except (KeyError, ValueError):
                raise _Unknown("invalid_integer_literal")
        if kind in WRAPPERS:
            if len(children) != 1 or not _same_type_wrapper(node, children[0]):
                raise _Unknown("type_changing_or_ambiguous_wrapper")
            return expression_value(children[0])
        if kind == "ImplicitCastExpr":
            # LValueToRValue may drop const qualification without changing the signed int value type.
            if (len(children) != 1 or node.get("castKind") not in {"LValueToRValue", "NoOp"} or
                    not _signed_int_type(_qual_type(node)) or
                    not _signed_int_type(_qual_type(children[0]))):
                raise _Unknown("unsupported_cast")
            return expression_value(children[0])
        if kind == "UnaryOperator":
            if (len(children) != 1 or node.get("opcode") not in {"+", "-"} or
                    not _signed_int_type(_qual_type(node))):
                raise _Unknown("unsupported_unary_operator")
            operand = expression_value(children[0])
            return _checked(operand if node["opcode"] == "+" else -operand, int_bits)
        if kind == "BinaryOperator":
            opcode = node.get("opcode")
            if (len(children) != 2 or opcode not in ARITHMETIC | SHIFTS or
                    not _signed_int_type(_qual_type(node))):
                raise _Unknown("unsupported_binary_operator")
            if opcode in SHIFTS and not all(_signed_int_type(_qual_type(child)) for child in children):
                raise _Unknown("unsupported_shift_operand_type")
            left, right = expression_value(children[0]), expression_value(children[1])
            if opcode in SHIFTS:
                if not 0 <= right < int_bits:
                    raise _Unknown("shift_count_out_of_range")
                # Deliberately narrower than C++17: no negative LHS and no
                # signed sign-bit conversion, even where a compiler defines it.
                if left < 0:
                    raise _Unknown("negative_shift_operand_unsupported")
                return _checked(left << right if opcode == "<<" else left >> right, int_bits)
            if opcode == "+": value = left + right
            elif opcode == "-": value = left - right
            elif opcode == "*": value = left * right
            else:
                if right == 0:
                    raise _Unknown("division_by_zero")
                quotient = abs(left) // abs(right)
                if (left < 0) != (right < 0): quotient = -quotient
                _checked(quotient, int_bits)
                value = quotient if opcode == "/" else left - quotient * right
            return _checked(value, int_bits)
        if kind == "DeclRefExpr":
            if not _signed_int_type(_qual_type(node)):
                raise _Unknown("unsupported_or_unsigned_type")
            referenced = node.get("referencedDecl")
            if not isinstance(referenced, dict) or not isinstance(referenced.get("id"), str):
                raise _Unknown("unresolved_declaration_reference")
            return declaration_value(referenced["id"])
        if isinstance(kind, str) and ("CastExpr" in kind or kind == "CallExpr"):
            raise _Unknown("unsupported_cast_or_call")
        raise _Unknown("unsupported_expression_kind")

    declaration = declarations.get(declaration_id)
    if declaration is not None:
        try:
            result["expression_range"] = _initializer(declaration).get("range")
        except _Unknown:
            pass
    try:
        result["value"] = declaration_value(declaration_id)
    except _Unknown as error:
        result["reason"], result["sources"] = error.reason, sources
        return result
    result.update(status="evaluated", reason=None, sources=sources)
    return result
