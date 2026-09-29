"""Check a bounded integer doubling-exponent loop, not arbitrary log helpers."""
from wavebridge.verification.getter_returns import _hash


def check_initialized_shift(root, exponent_id, power_id, argument_id, lower, upper,
                            *, int_bits=32, max_ast_nodes=1_000_000):
    """Bind adjacent local initializers under an argument-at-read domain premise."""
    from wavebridge.verification.launch_binding import _direct_callee

    result = {"schema_version": "power-ceiling-initialized-shift/v1", "status": "unknown", "reason": None,
        "scope": "adjacent_local_initializations_under_argument_domain_at_read",
        "checks": {}, "result_interval": None, "argument_domain_verified": False,
        "source_program_checked": False, "deployable": False,
        "later_value_history": "not_established", "linker_resolution": "not_established",
        "assumptions": ["faithful valid AST, matching integer ABI and ordinary sequential execution",
            "the exact argument declaration holds a value in the supplied interval at the call read",
            "the selected source function is the actual invoked implementation"]}
    try:
        if (not isinstance(root, dict) or root.get("kind") != "TranslationUnitDecl" or
                type(max_ast_nodes) is not int or not 1 <= max_ast_nodes <= 10_000_000 or
                any(not isinstance(i, str) or not i for i in (exponent_id, power_id, argument_id)) or
                len({exponent_id, power_id, argument_id}) != 3):
            raise ValueError("invalid_selection_or_budget")
        index, parents, pending, count = {}, {}, [(root, None)], 0
        while pending:
            node, parent = pending.pop(); count += 1
            if count > max_ast_nodes:
                raise ValueError("ast_node_budget_exceeded")
            if not isinstance(node, dict) or not isinstance(node.get("inner", []), list):
                raise ValueError("malformed_ast")
            index.setdefault(node.get("id"), []).append(node)
            parents[id(node)] = parent
            pending.extend((child, node) for child in node.get("inner", []))

        def unique(identifier):
            matches = index.get(identifier, [])
            if not isinstance(identifier, str) or len(matches) != 1:
                raise ValueError("selected_identity_not_unique")
            return matches[0]

        def children(node, kind, count, *, identical_literal=False):
            matches = index.get(node.get("id"), [])
            identity_ok = (bool(matches) and all(n == node for n in matches)
                           if identical_literal and kind == "IntegerLiteral" else
                           len(matches) == 1 and matches[0] is node)
            if (node.get("kind") != kind or not isinstance(node.get("id"), str) or
                    not identity_ok or len(node.get("inner", [])) != count):
                raise ValueError("selected_shape_unsupported")
            return node.get("inner", [])

        def typed(node, spelling, category=None):
            if node.get("type") != {"qualType": spelling} or (category and node.get("valueCategory") != category):
                raise ValueError("selected_type_unsupported")

        def local(identifier):
            declaration = unique(identifier)
            initializer, = children(declaration, "VarDecl", 1)
            if (declaration.get("type") not in ({"qualType": "int"}, {"qualType": "const int"}) or
                    declaration.get("init") != "c" or declaration.get("storageClass") not in (None, "auto", "register") or
                    any(declaration.get(k) is not None for k in ("tls", "tlsKind", "thread_local", "threadLocal"))):
                raise ValueError("local_storage_or_type_unsupported")
            statement = parents[id(declaration)]
            if not isinstance(statement, dict) or children(statement, "DeclStmt", 1)[0] is not declaration:
                raise ValueError("local_declaration_statement_unsupported")
            return declaration, initializer, statement

        exponent, call, first = local(exponent_id)
        power, shift, second = local(power_id)
        typed(exponent, "int")
        block = parents[id(first)]
        if not isinstance(block, dict) or block.get("kind") != "CompoundStmt" or parents[id(second)] is not block:
            raise ValueError("initializers_not_in_same_block")
        statements = block.get("inner", [])
        position = next(i for i, n in enumerate(statements) if n is first)
        if position + 1 >= len(statements) or statements[position + 1] is not second:
            raise ValueError("initializers_not_adjacent")
        callee, argument = children(call, "CallExpr", 2); typed(call, "int", "prvalue")
        direct = callee
        while direct.get("kind") in {"ImplicitCastExpr", "ParenExpr"} and len(direct.get("inner", [])) == 1:
            direct = direct["inner"][0]
        function = unique(direct.get("referencedDecl", {}).get("id"))
        if not _direct_callee(callee, function):
            raise ValueError("callee_binding_unsupported")

        def read(node, identifier):
            inner, = children(node, "ImplicitCastExpr", 1); typed(node, "int", "prvalue")
            if node.get("castKind") != "LValueToRValue":
                raise ValueError("argument_conversion_unsupported")
            children(inner, "DeclRefExpr", 0); typed(inner, "int", "lvalue")
            declaration = unique(identifier); typed(declaration, "int")
            ref = inner.get("referencedDecl", {})
            if (declaration.get("kind") not in {"VarDecl", "ParmVarDecl"} or ref.get("id") != identifier or
                    ref.get("kind") != declaration["kind"] or ref.get("type") != declaration["type"]):
                raise ValueError("read_declaration_mismatch")

        read(argument, argument_id)
        base, amount = children(shift, "BinaryOperator", 2); typed(shift, "int", "prvalue")
        if shift.get("opcode") != "<<":
            raise ValueError("subsequent_shift_operation_mismatch")
        children(base, "IntegerLiteral", 0, identical_literal=True); typed(base, "int", "prvalue")
        if base.get("value") != "1":
            raise ValueError("subsequent_shift_base_not_one")
        read(amount, exponent_id)
        body = check(root, function["id"], lower, upper, int_bits=int_bits, max_ast_nodes=max_ast_nodes)
        result["checks"]["function_body"] = body
        if body["status"] != "checked":
            raise ValueError("fresh_function_body_not_checked")
        domain = body["result_interval"]
        result.update(status="checked", exponent_declaration_id=exponent_id, power_declaration_id=power_id,
            argument_declaration_id=argument_id, call_id=call["id"], function_id=function["id"],
            exponent_interval=domain, result_interval={"lower": 1 << domain["lower"], "upper": 1 << domain["upper"]},
            exponent_preserved_to_shift=True, subsequent_shift_checked=True,
            base_literal_identity={"policy": "identical_childless_integer_literal_occurrences_only",
                "expression_id": base["id"], "occurrences": len(index[base["id"]])},
            input_sha256={"root": _hash(root), "selection_and_domain": _hash(
                [exponent_id, power_id, argument_id, lower, upper, int_bits])})
    except (ValueError, KeyError, TypeError, IndexError, StopIteration, RecursionError) as error:
        result["reason"] = str(error)
    return result


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
