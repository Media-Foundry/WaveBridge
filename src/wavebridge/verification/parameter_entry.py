"""Exhaustive finite-domain check of a read-only prefix to a statement entry.

This is not a general C++ interpreter: only plain int comparisons, Boolean
conditions, compounds, if and a single-pass do statement are supported.
Unexecuted branches are not interpreted. Reached calls or writes stay unknown.
"""
from wavebridge.verification.getter_returns import _hash


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
