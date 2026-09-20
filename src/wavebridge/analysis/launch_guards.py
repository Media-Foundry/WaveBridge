"""Recover a narrow class of top-level early-return launch guards."""

from __future__ import annotations

from typing import Any


class _Unknown(Exception):
    def __init__(self, reason: str):
        self.reason = reason


def _children(node: object) -> list[dict[str, Any]]:
    if not isinstance(node, dict) or not isinstance(node.get("inner"), list):
        return []
    return [child for child in node["inner"] if isinstance(child, dict) and child]


def _walk(node: dict[str, Any]):
    yield node
    for child in _children(node):
        yield from _walk(child)


def _qual_type(node: dict[str, Any]) -> str | None:
    value = node.get("type")
    return value.get("qualType") if isinstance(value, dict) else None


def _signed_int(node: dict[str, Any], *, require_const: bool = False) -> bool:
    value = _qual_type(node)
    if not isinstance(value, str):
        return False
    words = value.split()
    if "volatile" in words or "unsigned" in words:
        return False
    base = [word for word in words if word != "const"]
    return base == ["int"] and (not require_const or "const" in words)


def _unwrap_read(node: dict[str, Any]) -> dict[str, Any]:
    current = node
    while current.get("kind") in ("ParenExpr", "ImplicitCastExpr"):
        children = _children(current)
        if len(children) != 1:
            raise _Unknown("ambiguous_comparison_operand")
        if current.get("kind") == "ImplicitCastExpr":
            if current.get("castKind") not in ("LValueToRValue", "NoOp"):
                raise _Unknown("unsupported_comparison_cast")
            if not _signed_int(current) or not _signed_int(children[0]):
                raise _Unknown("comparison_cast_type_not_signed_int")
        current = children[0]
    return current


def _literal(node: dict[str, Any], int_bits: int) -> int:
    leaf = _unwrap_read(node)
    if leaf.get("kind") != "IntegerLiteral" or not _signed_int(leaf):
        raise _Unknown("boundary_not_signed_int_literal")
    try:
        value = int(str(leaf["value"]), 0)
    except (KeyError, TypeError, ValueError):
        raise _Unknown("invalid_boundary_literal")
    minimum, maximum = -(1 << (int_bits - 1)), (1 << (int_bits - 1)) - 1
    if not minimum <= value <= maximum:
        raise _Unknown("boundary_out_of_range")
    return value


def _declref(node: dict[str, Any]) -> str:
    leaf = _unwrap_read(node)
    referenced = leaf.get("referencedDecl")
    if (leaf.get("kind") != "DeclRefExpr" or not _signed_int(leaf) or
            not isinstance(referenced, dict) or referenced.get("kind") != "VarDecl" or
            not isinstance(referenced.get("id"), str) or not referenced["id"]):
        raise _Unknown("comparison_not_exact_local_declref")
    return referenced["id"]


def _terms(node: dict[str, Any]) -> list[dict[str, Any]]:
    if node.get("kind") == "BinaryOperator" and node.get("opcode") == "||":
        children = _children(node)
        if len(children) != 2:
            raise _Unknown("malformed_guard_disjunction")
        return _terms(children[0]) + _terms(children[1])
    return [node]


def _constraint(node: dict[str, Any], int_bits: int) -> tuple[str, int | None, int | None, object]:
    if node.get("kind") != "BinaryOperator" or node.get("opcode") not in ("<", "<=", ">", ">="):
        raise _Unknown("unsupported_guard_term")
    children = _children(node)
    if len(children) != 2:
        raise _Unknown("malformed_guard_comparison")
    opcode = node["opcode"]
    try:
        declaration_id, boundary = _declref(children[0]), _literal(children[1], int_bits)
    except _Unknown:
        boundary, declaration_id = _literal(children[0], int_bits), _declref(children[1])
        opcode = {"<": ">", "<=": ">=", ">": "<", ">=": "<="}[opcode]
    # The guard returns when the comparison is true; recover its integer complement.
    if opcode == "<":
        return declaration_id, boundary, None, node.get("range")
    if opcode == "<=":
        return declaration_id, boundary + 1, None, node.get("range")
    if opcode == ">":
        return declaration_id, None, boundary, node.get("range")
    return declaration_id, None, boundary - 1, node.get("range")


def _return_statement(node: dict[str, Any]) -> bool:
    current = node
    if current.get("kind") == "CompoundStmt":
        children = _children(current)
        if len(children) != 1:
            return False
        current = children[0]
    children = _children(current)
    if current.get("kind") != "ReturnStmt":
        return False
    if not children:  # A void host wrapper may use the same early-return guard shape.
        return True
    if len(children) != 1:
        return False
    try:
        _literal(children[0], 128)
    except _Unknown:
        return False
    return True


def _guard(node: dict[str, Any], int_bits: int) -> list[tuple[str, int | None, int | None, object]]:
    children = _children(node)
    if node.get("kind") != "IfStmt" or node.get("hasElse") is True or len(children) != 2:
        raise _Unknown("unsupported_if_before_launch")
    if not _return_statement(children[1]):
        raise _Unknown("guard_does_not_only_return_integer")
    return [_constraint(term, int_bits) for term in _terms(children[0])]


def _is_launch_statement(statement: dict[str, Any], launch_id: str) -> bool:
    if statement.get("kind") == "CUDAKernelCallExpr":
        return statement.get("id") == launch_id
    if statement.get("kind") != "DoStmt":
        return False
    children = _children(statement)
    if len(children) != 2 or children[0].get("kind") != "CompoundStmt":
        return False
    body = _children(children[0])
    if len(body) != 1 or body[0].get("kind") != "CUDAKernelCallExpr" or body[0].get("id") != launch_id:
        return False
    condition = children[1]
    while condition.get("kind") in ("ParenExpr", "ImplicitCastExpr"):
        wrapped = _children(condition)
        if len(wrapped) != 1:
            return False
        if condition.get("kind") == "ImplicitCastExpr" and condition.get("castKind") != "IntegralToBoolean":
            return False
        condition = wrapped[0]
    return condition.get("kind") == "IntegerLiteral" and str(condition.get("value")) == "0"


def _valid_uses(function: dict[str, Any], declaration_ids: set[str]) -> bool:
    parents: dict[int, list[dict[str, Any]]] = {}
    for parent in _walk(function):
        for child in _children(parent):
            parents.setdefault(id(child), []).append(parent)
    for node in _walk(function):
        if node.get("kind") != "DeclRefExpr":
            continue
        referenced = node.get("referencedDecl")
        if not isinstance(referenced, dict) or referenced.get("id") not in declaration_ids:
            continue
        # Every protected reference must be the sole operand of LValueToRValue.
        node_parents = parents.get(id(node), [])
        if len(node_parents) != 1:
            return False
        parent = node_parents[0]
        if (parent.get("kind") != "ImplicitCastExpr" or
                parent.get("castKind") != "LValueToRValue" or len(_children(parent)) != 1):
            return False
    return True


def _audit_control_flow(function: dict[str, Any], launch_id: str) -> None:
    forbidden = {"GotoStmt", "IndirectGotoStmt", "LabelStmt", "SwitchStmt", "CaseStmt",
                 "DefaultStmt", "GCCAsmStmt", "MSAsmStmt", "CXXTryStmt", "CXXCatchStmt",
                 "CoroutineBodyStmt", "CoreturnStmt", "CoyieldExpr", "LambdaExpr",
                 "CapturedStmt", "SEHTryStmt", "SEHExceptStmt", "SEHFinallyStmt"}
    loops = {"ForStmt", "WhileStmt", "DoStmt", "CXXForRangeStmt"}
    for node in _walk(function):
        kind = node.get("kind")
        if node is not function and kind in ("FunctionDecl", "CXXMethodDecl", "BlockDecl"):
            raise _Unknown("nested_callable_before_launch_unsupported")
        if kind in forbidden:
            raise _Unknown("bypassing_control_flow_unsupported")
        if kind in loops and not (kind == "DoStmt" and _is_launch_statement(node, launch_id)):
            raise _Unknown("unsupported_control_flow_in_host_function")


def _local_declarations(statements: list[dict[str, Any]], stop: int) -> tuple[dict[str, dict[str, Any]], dict[str, int]]:
    declarations: dict[str, dict[str, Any]] = {}
    positions: dict[str, int] = {}
    seen: set[str] = set()
    for statement_index, statement in enumerate(statements[:stop]):
        if statement.get("kind") != "DeclStmt":
            continue
        for declaration in _children(statement):
            if declaration.get("kind") != "VarDecl":
                continue
            declaration_id = declaration.get("id")
            if not isinstance(declaration_id, str) or not declaration_id:
                continue
            if declaration_id in seen:
                declarations.pop(declaration_id, None)
                positions.pop(declaration_id, None)
                continue
            seen.add(declaration_id)
            declarations[declaration_id] = declaration
            positions[declaration_id] = statement_index
    return declarations, positions


def _valid_guard_declaration(declaration: object) -> bool:
    if not isinstance(declaration, dict) or not _signed_int(declaration, require_const=True):
        return False
    if (declaration.get("storageClass") in ("static", "extern") or
            declaration.get("tls") is not None or declaration.get("tlsKind") is not None):
        return False
    initializers = [child for child in _children(declaration)
                    if not str(child.get("kind", "")).endswith("Attr")]
    return declaration.get("init") is not None and len(initializers) == 1


def recover(root: object, launch_id: str, int_bits: int) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema_version": "launch-guards/v1", "status": "unknown", "reason": None,
        "launch_id": launch_id, "int_bits": int_bits, "intervals": [], "guards": [],
        "skipped_guards": [],
        "interpretation": "necessary_conditions_to_pass_supported_early_returns_only",
        "input_protocol": "not_inferred", "source_validity": "not_established",
        "abi_validity": "external_precondition", "launch_reachability": "not_established",
        "checked": False, "deployable": False,
    }
    if not isinstance(root, dict) or not isinstance(launch_id, str) or not launch_id:
        result["reason"] = "invalid_input"
        return result
    if type(int_bits) is not int or not 2 <= int_bits <= 128:
        result["reason"] = "invalid_int_bits"
        return result
    try:
        functions: list[tuple[dict[str, Any], dict[str, Any], int]] = []
        for function in _walk(root):
            if function.get("kind") != "FunctionDecl":
                continue
            bodies = [child for child in _children(function) if child.get("kind") == "CompoundStmt"]
            if len(bodies) != 1:
                continue
            for index, statement in enumerate(_children(bodies[0])):
                if _is_launch_statement(statement, launch_id):
                    functions.append((function, bodies[0], index))
        if len(functions) != 1:
            raise _Unknown("unique_top_level_launch_not_found")
        function, body, launch_index = functions[0]
        _audit_control_flow(function, launch_id)
        statements = _children(body)
        declarations, declaration_positions = _local_declarations(statements, launch_index)
        bounds: dict[str, dict[str, Any]] = {}
        guards: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        for statement_index, statement in enumerate(statements[:launch_index]):
            kind = statement.get("kind")
            if kind == "DeclStmt":
                continue
            if kind != "IfStmt":
                continue
            try:
                constraints = _guard(statement, int_bits)
                for declaration_id, _, _, _ in constraints:
                    if (declaration_positions.get(declaration_id, launch_index) >= statement_index or
                            not _valid_guard_declaration(declarations.get(declaration_id))):
                        raise _Unknown("guard_variable_not_initialized_const_local_signed_int")
            except _Unknown as error:
                skipped.append({"range": statement.get("range"), "reason": error.reason})
                continue
            guards.append({"range": statement.get("range"), "condition_range": _children(statement)[0].get("range"),
                           "constraints": [{"declaration_id": item[0], "lower": item[1], "upper": item[2],
                                            "comparison_range": item[3]}
                                           for item in constraints]})
            for declaration_id, lower, upper, _ in constraints:
                declaration = declarations.get(declaration_id)
                entry = bounds.setdefault(declaration_id, {"declaration_id": declaration_id,
                    "lower": None, "upper": None, "type": declaration.get("type"),
                    "declaration_range": declaration.get("range")})
                if lower is not None:
                    entry["lower"] = lower if entry["lower"] is None else max(entry["lower"], lower)
                if upper is not None:
                    entry["upper"] = upper if entry["upper"] is None else min(entry["upper"], upper)
        result["skipped_guards"] = skipped
        if not guards or not bounds:
            raise _Unknown("no_supported_guard")
        minimum, maximum = -(1 << (int_bits - 1)), (1 << (int_bits - 1)) - 1
        for entry in bounds.values():
            if entry["lower"] is not None and not minimum <= entry["lower"] <= maximum:
                raise _Unknown("complement_boundary_overflow")
            if entry["upper"] is not None and not minimum <= entry["upper"] <= maximum:
                raise _Unknown("complement_boundary_overflow")
            if (entry["lower"] is not None and entry["upper"] is not None and
                    entry["lower"] > entry["upper"]):
                raise _Unknown("empty_guard_complement")
        if not _valid_uses(function, set(bounds)):
            raise _Unknown("guard_variable_has_unsupported_use")
        result.update(status="recovered", guards=guards, skipped_guards=skipped,
                      intervals=list(bounds.values()),
                      function_declaration_id=function.get("id"), launch_statement_index=launch_index)
    except _Unknown as error:
        result["reason"] = error.reason
    return result
