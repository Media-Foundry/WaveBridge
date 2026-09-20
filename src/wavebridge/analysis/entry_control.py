"""Recover entry-to-first-call control obligations, not collective convergence."""

from wavebridge.frontend.clang_ast import _walk


MAX_NODES = 10000
MAX_DEPTH = 64
EXPRESSION_KINDS = {
    "DeclStmt", "VarDecl", "DeclRefExpr", "IntegerLiteral", "FloatingLiteral",
    "ImplicitCastExpr", "ParenExpr", "BinaryOperator", "CompoundAssignOperator",
    "UnaryOperator", "ArraySubscriptExpr", "CallExpr", "MemberExpr",
    "CXXStaticCastExpr", "PseudoObjectExpr", "MSPropertyRefExpr", "OpaqueValueExpr",
    "CUDASharedAttr", "CompoundStmt", "NullStmt",
}


class _Unknown(Exception):
    def __init__(self, reason):
        self.reason = reason


def _children(node):
    children = node.get("inner", [])
    if not isinstance(children, list) or any(not isinstance(child, dict) for child in children):
        raise _Unknown("malformed_ast_children")
    return [child for child in children if child]


def _unwrap(node):
    depth = 0
    while node.get("kind") in ("ParenExpr", "ImplicitCastExpr"):
        depth += 1
        children = _children(node)
        if depth > MAX_DEPTH or len(children) != 1:
            raise _Unknown("unsupported_call_wrapper")
        node = children[0]
    return node


def _callee(call):
    children = _children(call)
    if call.get("kind") != "CallExpr" or not children:
        raise _Unknown("unsupported_call")
    target = _unwrap(children[0])
    if target.get("kind") == "DeclRefExpr":
        ref = target.get("referencedDecl")
        identifier = ref.get("id") if isinstance(ref, dict) and ref.get("kind") == "FunctionDecl" else None
    elif target.get("kind") == "MemberExpr":
        # This records a target obligation only; dispatch/receiver semantics are unproved.
        identifier = target.get("referencedMemberDecl")
    else:
        identifier = None
    if not isinstance(identifier, str) or not identifier:
        raise _Unknown("call_target_not_exact_declaration")
    return identifier


def _statement_call(statement):
    current = _unwrap(statement)
    if current.get("kind") == "DeclStmt":
        declarations = _children(current)
        if len(declarations) != 1 or declarations[0].get("kind") != "VarDecl":
            raise _Unknown("target_statement_not_single_variable")
        values = _children(declarations[0])
        if declarations[0].get("init") is None or len(values) != 1:
            raise _Unknown("target_initializer_not_unique")
        current = _unwrap(values[0])
    return current


def recover(root, function_id, callee_id, call_range):
    result = {
        "schema_version": "entry-control-obligations/v1", "status": "unknown", "reason": None,
        "function_id": function_id, "callee_id": callee_id, "call_range": call_range,
        "checked": False, "deployable": False, "source_program_checked": False,
        "participation": "not_established", "call_obligations": [], "loop_obligations": [],
        "scope": "entry_to_first_target_invocation_only",
        "remaining_obligations": ["prefix calls return normally for every modeled thread",
                                  "prefix loops terminate normally for every modeled thread",
                                  "prefix memory accesses and arithmetic are valid",
                                  "all modeled threads enter this kernel invocation"],
        "budget": {"max_prefix_nodes": MAX_NODES, "max_depth": MAX_DEPTH, "nodes_used": 0},
    }
    if (not isinstance(root, dict) or not isinstance(call_range, dict) or not call_range or
            any(not isinstance(value, str) or not value for value in (function_id, callee_id))):
        result["reason"] = "invalid_inputs"
        return result
    try:
        functions = [node for node in _walk(root)
                     if node.get("kind") == "FunctionDecl" and node.get("id") == function_id]
        if len(functions) != 1:
            raise _Unknown("function_not_unique")
        bodies = [child for child in _children(functions[0]) if child.get("kind") == "CompoundStmt"]
        if len(bodies) != 1:
            raise _Unknown("function_body_not_unique")
        calls = [node for node in _walk(bodies[0])
                 if node.get("kind") == "CallExpr" and node.get("range") == call_range]
        if len(calls) != 1 or _callee(calls[0]) != callee_id:
            raise _Unknown("target_call_not_unique_or_bound")
        target = calls[0]
        statements = _children(bodies[0])
        positions = [i for i, statement in enumerate(statements)
                     if any(node is target for node in _walk(statement))]
        if len(positions) != 1:
            raise _Unknown("target_statement_not_unique")
        position = positions[0]
        if _statement_call(statements[position]) is not target:
            raise _Unknown("target_not_direct_top_level_call")
        nodes = 0

        def scan(node, depth=0, top_loop=False):
            nonlocal nodes
            nodes += 1
            result["budget"]["nodes_used"] = nodes
            if nodes > MAX_NODES or depth > MAX_DEPTH:
                raise _Unknown("prefix_traversal_budget_exceeded")
            kind = node.get("kind")
            if kind == "ForStmt":
                if not top_loop or not isinstance(node.get("range"), dict):
                    raise _Unknown("prefix_loop_not_direct_or_located")
                result["loop_obligations"].append({"range": node["range"], "termination": "not_established"})
            elif not isinstance(kind, str) or kind not in EXPRESSION_KINDS:
                raise _Unknown("unsupported_prefix_control_or_expression")
            if kind == "BinaryOperator" and node.get("opcode") in ("&&", "||"):
                raise _Unknown("short_circuit_prefix_unsupported")
            if kind == "CallExpr":
                result["call_obligations"].append({"declaration_id": _callee(node),
                                                  "range": node.get("range"),
                                                  "normal_return": "not_established"})
            for child in _children(node):
                scan(child, depth + 1)

        for statement in statements[:position]:
            scan(statement, top_loop=statement.get("kind") == "ForStmt")
        # Arguments/callee evaluation precede the invocation; do not assume they are pure.
        for child in _children(target):
            scan(child)
        result.update(status="recovered", target_statement_index=position,
                      prefix_statement_ranges=[statement.get("range") for statement in statements[:position]])
    except (_Unknown, RecursionError) as error:
        result["reason"] = error.reason if isinstance(error, _Unknown) else "ast_recursion_limit"
    return result
