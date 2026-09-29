"""Exhaustive finite-domain check of a read-only prefix to a statement entry.

This is not a general C++ interpreter: only plain int comparisons, Boolean
conditions, compounds, if and a single-pass do statement are supported.
Unexecuted branches are not interpreted. Reached calls or writes stay unknown.
"""
from wavebridge.verification.getter_returns import _hash


def check_guarded_argument(root, function_id, local_id, guard_id, call_id, callee_id,
                           argument_position, *, int_bits=32, max_ast_nodes=1_000_000):
    """Necessary discrete argument domain at a reached call, not call safety.

    Recognize a const local and a dominating `if (x != a && x != b) return K`,
    also nested under Boolean OR. Inventory every local reference to exclude
    address/reference escape. Other calls are not asserted to be pure.
    """
    from wavebridge.verification.launch_binding import _direct_callee
    result = {"schema_version": "guarded-const-argument/v1", "status": "unknown", "reason": None,
              "scope": "necessary_argument_values_if_selected_call_is_normally_reached",
              "argument_values": None, "call_reachability_proved": False,
              "other_argument_effects_checked": False, "runtime_input_binding_verified": False,
              "source_program_checked": False, "deployable": False,
              "assumptions": ["faithful valid C++ AST and matching signed-int ABI",
                  "ordinary sequential execution without nonlocal jumps or asynchronous interference",
                  "source validity and local object lifetime without replacement hold on the selected execution",
                  "the selected declaration denotes the actual invoked callee"],
              "limitations": ["not an effect or validity check of other arguments or intervening calls",
                  "no guarantee that the call executes, returns, or is safe"]}
    try:
        ids = (function_id, local_id, guard_id, call_id, callee_id)
        if (not isinstance(root, dict) or root.get("kind") != "TranslationUnitDecl" or
                any(not isinstance(i, str) or not i for i in ids) or len(set(ids)) != 5 or
                type(argument_position) is not int or argument_position < 0 or
                type(int_bits) is not int or not 2 <= int_bits <= 64 or
                type(max_ast_nodes) is not int or not 1 <= max_ast_nodes <= 10_000_000):
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
            pending.extend((c, node) for c in node.get("inner", []))

        def unique(identifier):
            values = index.get(identifier, [])
            if len(values) != 1:
                raise ValueError("selected_identity_not_unique")
            return values[0]

        def children(node, kind, size=None):
            if node.get("kind") != kind or unique(node.get("id")) is not node:
                raise ValueError("selected_shape_or_identity_unsupported")
            values = node.get("inner", [])
            if size is not None and len(values) != size:
                raise ValueError("selected_arity_unsupported")
            return values

        function, local, guard, call, callee = map(unique, ids)
        members = children(function, "FunctionDecl")
        initializer, = children(local, "VarDecl", 1)
        if (local.get("type") != {"qualType": "const int"} or local.get("init") is None or
                local.get("storageClass") not in (None, "auto", "register") or
                any(local.get(k) is not None for k in ("tls", "tlsKind", "thread_local", "threadLocal"))):
            raise ValueError("local_not_automatic_const_int")
        declaration = parents[id(local)]
        children(declaration, "DeclStmt")
        block = parents[id(declaration)]
        statements = children(block, "CompoundStmt")
        if (block not in members or parents[id(guard)] is not block or parents[id(call)] is not block or
                not statements.index(declaration) < statements.index(guard) < statements.index(call)):
            raise ValueError("guard_not_dominating_same_body_call")
        condition, returned = children(guard, "IfStmt", 2)
        if any(guard.get(k) for k in ("hasInit", "hasVar", "isConstexpr", "isConsteval", "hasElse")):
            raise ValueError("guard_form_unsupported")
        if returned.get("kind") == "CompoundStmt":
            returned, = children(returned, "CompoundStmt", 1)
        return_value, = children(returned, "ReturnStmt", 1)
        children(return_value, "IntegerLiteral", 0)
        if return_value.get("type") != {"qualType": "int"}:
            raise ValueError("return_value_unsupported")

        def read(node):
            leaf, = children(node, "ImplicitCastExpr", 1)
            children(leaf, "DeclRefExpr", 0)
            ref = leaf.get("referencedDecl", {})
            if (node.get("castKind") != "LValueToRValue" or node.get("type") != {"qualType": "int"} or
                    node.get("valueCategory") != "prvalue" or leaf.get("valueCategory") != "lvalue" or
                    leaf.get("type") != local["type"] or ref.get("id") != local_id or
                    ref.get("kind") != "VarDecl" or ref.get("type") != local["type"]):
                raise ValueError("argument_not_plain_selected_const_read")

        forbidden = {"GotoStmt", "IndirectGotoStmt", "LabelStmt", "AddrLabelExpr", "LambdaExpr", "BlockExpr",
                     "CoroutineBodyStmt", "CXXTryStmt", "GCCAsmStmt", "MSAsmStmt", "CXXNewExpr",
                     "SwitchStmt", "CaseStmt", "DefaultStmt", "SEHTryStmt", "SEHExceptStmt",
                     "CXXPseudoDestructorExpr", "StmtExpr"}
        pending, references = [function], []
        while pending:
            node = pending.pop()
            if node.get("kind") in forbidden:
                raise ValueError("caller_control_or_lifetime_unsupported")
            if node.get("kind") == "DeclRefExpr" and node.get("referencedDecl", {}).get("id") == local_id:
                read(parents[id(node)])
                references.append(node["id"])
            pending.extend(node.get("inner", []))

        def unwrap(node):
            while node.get("kind") == "ParenExpr":
                child, = children(node, "ParenExpr", 1)
                if child.get("type") != node.get("type"):
                    raise ValueError("paren_type_mismatch")
                node = child
            return node

        def forbidden_values(node):
            node = unwrap(node)
            if node.get("kind") != "BinaryOperator" or node.get("type") != {"qualType": "bool"}:
                return None
            left, right = children(node, "BinaryOperator", 2)
            if node.get("opcode") == "&&":
                a, b = forbidden_values(left), forbidden_values(right)
                return a | b if a is not None and b is not None else None
            if node.get("opcode") != "!=":
                return None
            for variable, literal in ((left, right), (right, left)):
                if literal.get("kind") != "IntegerLiteral" or literal.get("type") != {"qualType": "int"}:
                    continue
                try:
                    read(variable)
                except ValueError:
                    continue
                children(literal, "IntegerLiteral", 0)
                value = int(literal["value"])
                if not -(1 << (int_bits - 1)) <= value < (1 << (int_bits - 1)):
                    raise ValueError("literal_outside_abi")
                return {value}
            return None

        # A false OR implies each operand false. An unrelated subtree supplies
        # no constraint; a full conjunction of != tests supplies a finite set.
        def required_values(node):
            node = unwrap(node)
            values = forbidden_values(node)
            if values is not None:
                return values
            if (node.get("kind") == "BinaryOperator" and node.get("opcode") == "||" and
                    node.get("type") == {"qualType": "bool"}):
                left, right = children(node, "BinaryOperator", 2)
                a, b = required_values(left), required_values(right)
                return b if a is None else a if b is None else a & b
            return None

        values = required_values(condition)
        if not values:
            raise ValueError("finite_nonempty_guard_domain_not_established")
        arguments = children(call, "CallExpr")
        parameters = [n for n in children(callee, "FunctionDecl") if n.get("kind") == "ParmVarDecl"]
        if (len(arguments) != len(parameters) + 1 or argument_position >= len(parameters) or
                not _direct_callee(arguments[0], callee)):
            raise ValueError("direct_positional_call_binding_unsupported")
        parameter = parameters[argument_position]
        if unique(parameter.get("id")) is not parameter or parameter.get("type") != {"qualType": "int"}:
            raise ValueError("selected_parameter_not_plain_int")
        read(arguments[argument_position + 1])
        result.update(status="checked", argument_values=sorted(values),
                      parameter_id=parameter["id"], local_reference_ids=sorted(references),
                      local_address_escape=False,
                      input_sha256={"root": _hash(root), "selection": _hash([*ids, argument_position, int_bits])})
    except (ValueError, KeyError, TypeError, IndexError, RecursionError) as error:
        result["reason"] = str(error)
    return result


def check(root, function_id, parameter_id, statement_id, lower, upper, *,
          int_bits=32, max_ast_nodes=1_000_000, max_steps=100_000):
    result = {"schema_version": "parameter-entry/v1", "status": "unknown", "reason": None,
              "scope": "function_entry_to_first_selected_statement_entry_under_external_finite_domain",
              "entry_domain_verified": False, "parameter_preserved": False,
              "target_statement_evaluated": False, "source_program_checked": False,
              "deployable": False, "result_interval": None,
              "assumptions": ["faithful valid AST and matching signed-int ABI",
                  "ordinary sequential function invocation without asynchronous interference",
                  "selected parameter at function entry belongs to the supplied interval"],
              "limitations": ["no runtime input protocol binding or invocation reachability proof",
                  "no effects of the target statement or later execution are checked"]}
    try:
        if (not isinstance(root, dict) or root.get("kind") != "TranslationUnitDecl" or
                any(not isinstance(i, str) or not i for i in (function_id, parameter_id, statement_id)) or
                any(type(v) is not int for v in (lower, upper, int_bits, max_ast_nodes, max_steps)) or
                not 2 <= int_bits <= 64 or not 1 <= max_ast_nodes <= 10_000_000 or
                not 1 <= max_steps <= 1_000_000 or not 0 <= upper - lower < 4096 or
                not -(1 << (int_bits - 1)) <= lower <= upper < (1 << (int_bits - 1))):
            raise ValueError("invalid_selection_domain_or_budget")
        index, pending, parents, count = {}, [(root, None)], {}, 0
        while pending:
            node, parent = pending.pop(); count += 1
            if count > max_ast_nodes:
                raise ValueError("ast_node_budget_exceeded")
            if not isinstance(node, dict) or not isinstance(node.get("inner", []), list):
                raise ValueError("malformed_ast")
            index.setdefault(node.get("id"), []).append(node)
            parents[id(node)] = parent
            pending.extend((c, node) for c in node.get("inner", []))

        def unique(identifier):
            nodes = index.get(identifier, [])
            if len(nodes) != 1:
                raise ValueError("selected_identity_not_unique")
            return nodes[0]

        function, parameter, target = map(unique, (function_id, parameter_id, statement_id))
        if (function.get("kind") != "FunctionDecl" or parameter.get("kind") != "ParmVarDecl" or
                parameter.get("type") != {"qualType": "int"} or parameter.get("inner", []) or
                parents[id(parameter)] is not function or target.get("kind") != "DeclStmt"):
            raise ValueError("function_parameter_or_target_unsupported")
        bodies = [n for n in function.get("inner", []) if n.get("kind") == "CompoundStmt"]
        if len(bodies) != 1:
            raise ValueError("function_body_not_unique")
        ancestor = target
        while ancestor is not function and ancestor is not None:
            ancestor = parents[id(ancestor)]
        if ancestor is not function:
            raise ValueError("target_not_in_selected_function")
        steps, visited, skipped = 0, set(), set()

        def prepare(node):
            nonlocal steps
            steps += 1
            if steps > max_steps:
                raise ValueError("execution_budget_exceeded")
            matches = index.get(node.get("id"), [])
            # Clang may share constant leaves between template and instance.
            shared = (node.get("kind") == "IntegerLiteral" and not node.get("inner", []) and
                      matches and all(n == node for n in matches))
            if not isinstance(node.get("id"), str) or (not shared and unique(node["id"]) is not node):
                raise ValueError("prefix_identity_conflict")
            visited.add(node["id"])
            return node.get("inner", [])

        def expression(node, value):
            children = prepare(node)
            kind, typ = node.get("kind"), node.get("type")
            if typ not in ({"qualType": "int"}, {"qualType": "bool"}) or node.get("valueCategory") != "prvalue":
                raise ValueError("condition_type_unsupported")
            if kind == "IntegerLiteral" and not children and typ == {"qualType": "int"}:
                number = int(node["value"])
                if not -(1 << (int_bits - 1)) <= number < (1 << (int_bits - 1)):
                    raise ValueError("literal_outside_abi")
                return number
            if kind == "ParenExpr" and len(children) == 1 and children[0].get("type") == typ:
                return expression(children[0], value)
            if kind == "ImplicitCastExpr" and len(children) == 1:
                child = children[0]
                if node.get("castKind") == "IntegralToBoolean" and typ == {"qualType": "bool"}:
                    return bool(expression(child, value))
                if node.get("castKind") == "LValueToRValue" and typ == {"qualType": "int"}:
                    if (prepare(child) or child.get("kind") != "DeclRefExpr" or
                            child.get("type") != parameter["type"] or child.get("valueCategory") != "lvalue" or
                            child.get("referencedDecl", {}).get("id") != parameter_id or
                            child.get("referencedDecl", {}).get("kind") != "ParmVarDecl" or
                            child.get("referencedDecl", {}).get("type") != parameter["type"]):
                        raise ValueError("condition_not_selected_parameter_read")
                    return value
            if kind == "UnaryOperator" and node.get("opcode") == "!" and len(children) == 1 and typ == {"qualType": "bool"}:
                return not expression(children[0], value)
            if kind == "BinaryOperator" and len(children) == 2 and typ == {"qualType": "bool"}:
                op = node.get("opcode")
                left = expression(children[0], value)
                if op == "&&" and not left:
                    skipped.add(children[1]["id"]); return False
                if op == "||" and left:
                    skipped.add(children[1]["id"]); return True
                right = expression(children[1], value)
                if op in ("&&", "||"):
                    return bool(right)
                comparisons = {"==": left == right, "!=": left != right, "<": left < right,
                               "<=": left <= right, ">": left > right, ">=": left >= right}
                if op in comparisons and children[0].get("type") == children[1].get("type"):
                    return comparisons[op]
            raise ValueError("condition_expression_unsupported")

        def execute(node, value):
            children = prepare(node)
            if node is target:
                return "reached"
            kind = node.get("kind")
            if kind == "CompoundStmt":
                for child in children:
                    outcome = execute(child, value)
                    if outcome != "continue":
                        return outcome
                return "continue"
            if kind == "IfStmt" and len(children) in (2, 3) and not any(
                    node.get(k) for k in ("hasInit", "hasVar", "isConstexpr", "isConsteval")):
                yes = bool(expression(children[0], value))
                selected = 1 if yes else 2
                other = 2 if yes else 1
                if other < len(children):
                    skipped.add(children[other]["id"])
                return execute(children[selected], value) if selected < len(children) else "continue"
            if kind == "DoStmt" and len(children) == 2:
                outcome = execute(children[0], value)
                if outcome != "continue":
                    return outcome
                if expression(children[1], value):
                    raise ValueError("repeating_do_loop_unsupported")
                return "continue"
            if kind == "NullStmt" and not children:
                return "continue"
            raise ValueError("reached_statement_effect_unsupported")

        for value in range(lower, upper + 1):
            if execute(bodies[0], value) != "reached":
                raise ValueError("target_not_reached_for_full_domain")
        result.update(status="checked", parameter_preserved=True,
                      result_interval={"lower": lower, "upper": upper},
                      domain_values_exhaustively_checked=upper - lower + 1, evaluation_steps=steps,
                      visited_node_ids=sorted(visited),
                      branch_ids_skipped_in_at_least_one_domain_execution=sorted(skipped),
                      input_sha256={"root": _hash(root), "selection_domain_abi": _hash(
                          [function_id, parameter_id, statement_id, lower, upper, int_bits])})
    except (ValueError, TypeError, KeyError, IndexError, RecursionError) as error:
        result["reason"] = str(error)
    return result
