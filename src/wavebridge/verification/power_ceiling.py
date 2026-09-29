"""Check a bounded integer doubling-exponent loop, not arbitrary log helpers."""
from wavebridge.verification.getter_returns import _hash


def check(root, function_id, lower, upper, *, int_bits=32, max_ast_nodes=1_000_000):
    """Recognize by exact storage/dataflow, never by function or variable names.

    Supported input stays positive and below the largest nonnegative signed
    power of two. This is deliberately not a model of shifts into the sign bit.
    """
    result = {"schema_version": "power-ceiling-loop/v1", "status": "unknown", "reason": None,
        "function_id": function_id, "input_interval": {"lower": lower, "upper": upper},
        "int_bits": int_bits, "result_interval": None,
        "scope": "selected_function_body_under_explicit_positive_input_domain",
        "input_domain_established_at_call": False, "source_program_checked": False,
        "deployable": False, "linker_resolution": "not_established",
        "assumptions": ["faithful valid single-TU AST and matching signed-int ABI",
            "the selected function is invoked with its argument in the supplied interval",
            "ordinary sequential execution without asynchronous interference"],
        "limitations": ["not call argument binding, reaching values, later shifts or launch domains"]}
    try:
        if (not isinstance(root, dict) or root.get("kind") != "TranslationUnitDecl" or
                not isinstance(function_id, str) or not function_id or
                type(int_bits) is not int or not 2 <= int_bits <= 64 or
                type(max_ast_nodes) is not int or not 1 <= max_ast_nodes <= 10_000_000 or
                type(lower) is not int or type(upper) is not int or lower > upper):
            raise ValueError("invalid_inputs_or_budget")
        if not 1 <= lower <= upper <= (1 << (int_bits - 2)):
            raise ValueError("domain_outside_supported_nonnegative_signed_shifts")
        index, pending, count = {}, [root], 0
        while pending:
            node = pending.pop(); count += 1
            if count > max_ast_nodes:
                raise ValueError("ast_node_budget_exceeded")
            if not isinstance(node, dict) or not isinstance(node.get("inner", []), list):
                raise ValueError("malformed_ast")
            index.setdefault(node.get("id"), []).append(node)
            pending.extend(node.get("inner", []))

        def children(node, kind, size=None):
            if (node.get("kind") != kind or not isinstance(node.get("id"), str) or
                    len(index.get(node["id"], [])) != 1):
                raise ValueError("selected_shape_or_identity_unsupported")
            parts = node.get("inner", [])
            if size is not None and len(parts) != size:
                raise ValueError("selected_child_count_unsupported")
            return parts

        def typed(node, spelling, category=None):
            if node.get("type") != {"qualType": spelling} or (
                    category is not None and node.get("valueCategory") != category):
                raise ValueError("selected_type_or_value_category_unsupported")

        matches = index.get(function_id, [])
        if len(matches) != 1:
            raise ValueError("function_not_unique")
        function = matches[0]
        parts = children(function, "FunctionDecl", 2)
        typed(function, "int (int)")
        if (function.get("variadic") or function.get("previousDecl") or
                any(n.get("previousDecl") == function_id for nodes in index.values() for n in nodes)):
            raise ValueError("function_redeclaration_or_variadic_unsupported")
        parameter, body = parts
        children(parameter, "ParmVarDecl", 0); typed(parameter, "int")
        declaration_statement, loop, returned = children(body, "CompoundStmt", 3)
        declaration, = children(declaration_statement, "DeclStmt", 1)
        initial, = children(declaration, "VarDecl", 1); typed(declaration, "int")
        if (declaration.get("init") != "c" or declaration.get("storageClass") not in (None, "auto", "register") or
                any(declaration.get(k) is not None for k in ("tls", "tlsKind", "thread_local", "threadLocal"))):
            raise ValueError("counter_not_plain_automatic_initialization")

        def literal(node, value):
            children(node, "IntegerLiteral", 0); typed(node, "int", "prvalue")
            if node.get("value") != str(value):
                raise ValueError("literal_value_mismatch")

        def reference(node, target, load):
            if load:
                inner, = children(node, "ImplicitCastExpr", 1)
                typed(node, "int", "prvalue")
                if node.get("castKind") != "LValueToRValue":
                    raise ValueError("reference_cast_unsupported")
                node = inner
            children(node, "DeclRefExpr", 0); typed(node, "int", "lvalue")
            ref = node.get("referencedDecl", {})
            if (ref.get("id") != target["id"] or ref.get("kind") != target["kind"] or
                    ref.get("type") != target["type"]):
                raise ValueError("reference_declaration_mismatch")

        literal(initial, 0)
        condition, step = children(loop, "WhileStmt", 2)
        lhs, rhs = children(condition, "BinaryOperator", 2); typed(condition, "bool", "prvalue")
        if condition.get("opcode") != "<":
            raise ValueError("comparison_not_strict_less")
        reference(rhs, parameter, True)
        if lhs.get("kind") == "ParenExpr":
            typed(lhs, "int", "prvalue")
            lhs, = children(lhs, "ParenExpr", 1)
        base, exponent = children(lhs, "BinaryOperator", 2); typed(lhs, "int", "prvalue")
        if lhs.get("opcode") != "<<":
            raise ValueError("shift_operation_mismatch")
        literal(base, 1); reference(exponent, declaration, True)
        if step.get("kind") == "CompoundStmt":
            step, = children(step, "CompoundStmt", 1)
        operand, = children(step, "UnaryOperator", 1); typed(step, "int")
        if step.get("opcode") != "++" or type(step.get("isPostfix")) is not bool:
            raise ValueError("increment_shape_unsupported")
        reference(operand, declaration, False)
        value, = children(returned, "ReturnStmt", 1)
        reference(value, declaration, True)
        result.update(status="checked", parameter_id=parameter["id"], counter_id=declaration["id"],
            result_interval={"lower": (lower - 1).bit_length(), "upper": (upper - 1).bit_length()},
            relation="return is the least nonnegative k such that 2**k >= argument",
            maximum_iterations=(upper - 1).bit_length(),
            invariant="counter starts at zero, increases by one, and is tested against the same unchanged parameter",
            input_sha256={"root": _hash(root), "function_id": _hash(function_id),
                "domain_and_abi": _hash([lower, upper, int_bits])})
    except (ValueError, KeyError, TypeError, IndexError, RecursionError) as error:
        result["reason"] = str(error)
    return result
