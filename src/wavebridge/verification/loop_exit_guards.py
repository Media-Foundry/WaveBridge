"""Direct loop-exit partitions, not full iteration-domain or body-effect proofs."""
from wavebridge.verification.builtin_calls import _children, _typed, _Unknown
from wavebridge.verification.getter_returns import _hash
from wavebridge.verification.scalar_expression_effects import (
    check_no_memory_write, _type, MAX_AST_NODES, HARD_MAX_AST_NODES)

BREAK_OWNERS = {"ForStmt", "WhileStmt", "DoStmt", "CXXForRangeStmt", "SwitchStmt"}
UNSUPPORTED_JUMPS = {"ContinueStmt", "ReturnStmt", "GotoStmt", "IndirectGotoStmt",
                     "CXXThrowExpr", "CoreturnStmt", "CoawaitExpr", "CoyieldExpr"}
FUNCTION_SCOPES = {"LambdaExpr", "FunctionDecl", "CXXMethodDecl", "CXXConstructorDecl", "CXXDestructorDecl"}


def inspect_structure(root, loop_id, *, max_ast_nodes=None):
    budget = MAX_AST_NODES if max_ast_nodes is None else max_ast_nodes
    result = {"schema_version": "loop-exit-guard-partition/v1", "status": "unknown", "reason": None,
              "scope": "direct_loop_exit_guard_partition", "source_program_checked": False,
              "deployable": False, "full_iteration_domain_established": False,
              "loop_header_checked": False, "body_effects_checked": False,
              "guard_operand_checks": [],
              "assumptions": ["AST faithfully describes one valid translation unit",
                              "evaluation reaches the selected guard and completes normally"],
              "limitations": ["prefix and work effects, initialization history and header are not checked",
                              "guard values and their stability across iterations are not established",
                              "no loop coverage, effective bound, output equivalence or GPU guarantee"],
              "budget": {"max_ast_nodes_per_scan": budget}}
    try:
        if (not isinstance(root, dict) or root.get("kind") != "TranslationUnitDecl" or
                not isinstance(loop_id, str) or not loop_id or
                type(budget) is not int or not 1 <= budget <= HARD_MAX_AST_NODES):
            raise _Unknown("invalid_inputs_or_budget")
        index, pending, count = {}, [root], 0
        while pending:
            node = pending.pop()
            count += 1
            if count > budget:
                raise _Unknown("ast_node_budget_exceeded")
            if not isinstance(node, dict) or not isinstance(node.get("inner", []), list):
                raise _Unknown("malformed_ast")
            identifier = node.get("id")
            if isinstance(identifier, str) and identifier:
                index.setdefault(identifier, []).append(node)
            pending.extend(node.get("inner", []))

        def exact(node):
            identifier = node.get("id")
            if (not isinstance(identifier, str) or not identifier or len(index.get(identifier, [])) != 1
                    or index[identifier][0] is not node):
                result["unknown_identity"] = {"id": identifier, "kind": node.get("kind"),
                                              "occurrences": len(index.get(identifier, [])) if isinstance(identifier, str) else 0}
                raise _Unknown("selected_identity_not_unique")
            return identifier

        candidates = index.get(loop_id, [])
        if len(candidates) != 1:
            raise _Unknown("loop_identity_not_unique")
        loop = candidates[0]
        parts = loop.get("inner", [])
        if (loop.get("kind") != "ForStmt" or len(parts) != 5 or parts[1] != {} or
                parts[-1].get("kind") != "CompoundStmt"):
            raise _Unknown("unsupported_loop_body_layout")
        body = parts[-1]
        statements = _children(body)
        if not statements:
            raise _Unknown("empty_loop_body")
        # Non-dependent template statements (notably BreakStmt) can be shared
        # across instantiated AST dumps. Bind statement occurrences by the
        # unique selected loop plus its exact child path, not a global Stmt ID.
        paths, pending = {}, [(loop, [])]
        while pending:
            node, path = pending.pop()
            paths.setdefault(id(node), []).append(path)
            pending.extend((child, path + [position]) for position, child in
                           enumerate(node.get("inner", [])) if child)

        def occurrence(node):
            selected_paths = paths.get(id(node), [])
            identifier = node.get("id")
            if len(selected_paths) != 1 or not isinstance(identifier, str) or not identifier:
                raise _Unknown("statement_occurrence_not_unique")
            return {"id": identifier, "loop_relative_child_path": selected_paths[0]}
        # break belongs to the nearest loop OR switch. Never promote a nested
        # break into an exit of the selected loop.
        owned, pending = [], [(body, loop_id)]
        while pending:
            node, owner = pending.pop()
            kind = node.get("kind")
            if kind in FUNCTION_SCOPES:
                raise _Unknown("nested_function_scope_unsupported")
            if kind in UNSUPPORTED_JUMPS:
                raise _Unknown("other_control_transfer_unsupported")
            if kind in BREAK_OWNERS:
                owner = exact(node)
            if kind == "BreakStmt" and owner == loop_id:
                if _children(node):
                    raise _Unknown("break_has_operands")
                owned.append(node)
            # Full-AST traversal permits Clang's empty optional slots (e.g.
            # nested ForStmt headers). Selected partition shapes remain strict.
            pending.extend((child, owner) for child in node.get("inner", []) if child)
        if len(owned) != 1:
            raise _Unknown("not_one_selected_loop_break")
        selected_break = owned[0]

        def is_break(node):
            if node.get("kind") == "CompoundStmt":
                children = _children(node)
                return len(children) == 1 and children[0] is selected_break
            return node is selected_break

        def branch_parts(node):
            if (node.get("kind") != "IfStmt" or node.get("hasInit") or node.get("hasVar") or
                    node.get("isConstexpr") or node.get("isConsteval")):
                return None
            children = _children(node)
            if len(children) != (3 if node.get("hasElse") else 2):
                return None
            return children

        first, last = branch_parts(statements[0]), branch_parts(statements[-1])
        if first and len(first) == 2 and is_break(first[1]) and len(statements) > 1:
            guard, branch = first[0], statements[0]
            prefix, work, pattern, break_when = [], statements[1:], "leading_break_guard", True
        elif last and len(last) == 3 and is_break(last[2]) and last[1].get("kind") == "CompoundStmt":
            guard, branch = last[0], statements[-1]
            prefix, work, pattern, break_when = statements[:-1], _children(last[1]), "trailing_else_break", False
        else:
            raise _Unknown("unsupported_break_partition")
        _typed(guard, "BinaryOperator", "bool", "prvalue")
        operands = _children(guard)
        if guard.get("opcode") not in {"<", "<=", ">", ">=", "==", "!="} or len(operands) != 2:
            raise _Unknown("guard_not_integer_comparison")
        for operand in operands:
            checked = check_no_memory_write(root, exact(operand), max_ast_nodes=budget)
            result["guard_operand_checks"].append(checked)
            if checked["status"] != "checked" or checked.get("result_type") != "int":
                raise _Unknown("guard_operand_not_checked_int")
            result["assumptions"].extend(checked["assumptions"])
        branch_binding, break_binding = occurrence(branch), occurrence(selected_break)
        prefix_bindings, work_bindings = [occurrence(node) for node in prefix], [occurrence(node) for node in work]
        result.update(status="checked", loop_id=loop_id, branch_id=branch_binding["id"],
                      break_id=break_binding["id"], branch_binding=branch_binding, break_binding=break_binding,
                      guard_id=exact(guard), guard_ast=guard,
                      pattern=pattern, break_when=break_when, work_when=not break_when,
                      prefix_statement_ids=[item["id"] for item in prefix_bindings],
                      work_statement_ids=[item["id"] for item in work_bindings],
                      prefix_statement_bindings=prefix_bindings, work_statement_bindings=work_bindings,
                      prefix_evaluated_before_guard=True,
                      input_sha256={"root": _hash(root), "loop_id": _hash(loop_id)})
    except _Unknown as error:
        result["reason"] = str(error)
    except (TypeError, ValueError, KeyError, RecursionError):
        result["reason"] = "unsupported_input_representation"
    return result


def check_iteration_bounds(payload, loop_id, int_bits, call_protocols, declaration_intervals, *,
                           max_ast_nodes=None, use_static_branches=False, use_nested_loops=False,
                           use_source_constants=False):
    """Conservative work-count bounds; check each evaluated prefix/guard operation.

    External declaration intervals are assumptions at entry, not inferred launch
    facts. Work preservation is rebuilt, never supplied as a trusted report.
    """
    work = check_work_preservation(payload, loop_id, int_bits, call_protocols,
                                  max_ast_nodes=max_ast_nodes,
                                  use_static_branches=use_static_branches, use_nested_loops=use_nested_loops)
    result = {"schema_version": "guarded-loop-iteration-bounds/v1", "status": "unknown", "reason": None,
              "scope": "selected_loop_work_count_bounds_and_prefix_guard_integer_safety",
              "work_check": work, "source_program_checked": False, "deployable": False,
              "full_iteration_domain_established": False, "iteration_bounds_established": False,
              "iterations": [], "budget": {"max_header_iterations": 1024, "max_expression_depth": 64},
              "assumptions": ["declared integer intervals hold at entry for these exact declarations",
                              "integer ABI, AST fidelity and every work-check premise apply"],
              "limitations": ["bounds may be conservative; no per-input exact trip count or output coverage",
                              "nested-loop arithmetic and work-body arithmetic are not checked here",
                              "input ranges are external assumptions, not established launch or initialization facts"]}
    if work["status"] != "checked":
        result["reason"] = "work_preservation_not_checked"
        return result
    try:
        if type(use_source_constants) is not bool or not isinstance(declaration_intervals, dict):
            raise _Unknown("invalid_declaration_intervals")
        connection = work["connection_check"]
        header, prefix = connection["header_check"]["header"], connection["prefix_check"]
        induction = connection["induction_declaration_id"]
        required = set(prefix["external_read_declaration_ids"]) - {induction}
        derived = {}
        if use_source_constants:
            from wavebridge.analysis.integer_constants import evaluate as constant_value

            result["schema_version"] = "guarded-loop-iteration-bounds-source-constants/v1"
            result["source_constant_checks"] = {}
            result["derived_constant_intervals"] = derived
            result["budget"]["max_constant_domain_reads"] = 64
            if len(required) > 64:
                raise _Unknown("constant_domain_read_budget_exceeded")
            # Work checking already bounded/validated the full TU. Do not let
            # the constant evaluator's declaration map hide duplicate IDs.
            index, pending = {}, [payload["ast"]]
            while pending:
                node = pending.pop()
                if isinstance(node.get("id"), str):
                    index.setdefault(node["id"], []).append(node)
                pending.extend(node.get("inner", []))
            for identifier in sorted(required):
                declarations = index.get(identifier, [])
                if len(declarations) != 1:
                    raise _Unknown("domain_declaration_not_unique")
                declaration = declarations[0]
                if (declaration.get("kind") != "VarDecl" or
                        _type(declaration) != "const int"):
                    continue
                checked = constant_value(payload["ast"], identifier, int_bits)
                result["source_constant_checks"][identifier] = checked
                if any(len(index.get(source["declaration_id"], [])) != 1 for source in checked["sources"]):
                    raise _Unknown("constant_domain_dependency_not_unique")
                if checked["status"] == "evaluated":
                    derived[identifier] = [checked["value"], checked["value"]]
        if set(declaration_intervals) != required - set(derived):
            raise _Unknown("declaration_interval_keys_mismatch")
        effective = {**declaration_intervals, **derived}
        if use_source_constants:
            result["effective_declaration_intervals"] = effective
            result["limitations"].append("source-derived constant values do not establish the remaining external input ranges")
        minimum, maximum = -(1 << (int_bits - 1)), (1 << (int_bits - 1)) - 1

        def representable(bounds):
            if bounds[0] < minimum or bounds[1] > maximum:
                raise _Unknown("signed_arithmetic_may_overflow")
            return bounds

        ranges = {}
        for identifier, interval in effective.items():
            if (not isinstance(interval, (list, tuple)) or len(interval) != 2 or
                    any(type(value) is not int for value in interval) or interval[0] > interval[1]):
                raise _Unknown("invalid_declaration_interval")
            ranges[identifier] = representable(tuple(interval))
        start, bound, step = header["start"].get("value"), header["bound"].get("value"), header["step"]
        if any(type(value) is not int for value in (start, bound, step)) or step <= 0:
            raise _Unknown("constant_header_domain_required")
        representable((start, start))
        representable((bound, bound))
        count = max(0, (bound - start + step - 1) // step)
        if count > 1024:
            raise _Unknown("header_iteration_budget_exceeded")

        def evaluate(node, values, definitions, depth=0):
            if depth > 64 or node.get("type") != "int":
                raise _Unknown("interval_expression_type_or_depth")
            kind = node.get("kind")
            if kind == "read":
                return values[node["declaration_id"]]
            if kind == "prefix_value":
                return definitions[node["declaration_id"]]
            if kind == "literal":
                return representable((node["value"], node["value"]))
            operands = [evaluate(child, values, definitions, depth + 1) for child in node.get("operands", [])]
            opcode = node.get("opcode")
            if kind == "unary" and len(operands) == 1 and opcode in {"+", "-"}:
                a, b = operands[0]
                return representable((a, b) if opcode == "+" else (-b, -a))
            if kind == "binary" and len(operands) == 2:
                (a, b), (c, d) = operands
                if opcode == "+":
                    return representable((a + c, b + d))
                if opcode == "-":
                    return representable((a - d, b - c))
                if opcode == "*":
                    products = (a*c, a*d, b*c, b*d)
                    return representable((min(products), max(products)))
            raise _Unknown("interval_operation_unsupported")

        def comparison(opcode, left, right):
            a, b = left
            c, d = right
            if opcode == ">":
                return comparison("<", right, left)
            if opcode == ">=":
                return comparison("<=", right, left)
            if opcode == "<":
                return True if b < c else False if a >= d else None
            if opcode == "<=":
                return True if b <= c else False if a > d else None
            if opcode in {"==", "!="}:
                equal = True if a == b == c == d else False if b < c or d < a else None
                return equal if opcode == "==" or equal is None else not equal
            raise _Unknown("interval_comparison_unsupported")

        lower, upper, guaranteed_reachable = 0, 0, True
        guard = prefix["guard_value_expression"]
        for index in range(count):
            value = start + index * step
            values, definitions = {**ranges, induction: (value, value)}, {}
            item = {"induction_value": value, "prefix_intervals": {}}
            result["iterations"].append(item)
            for definition in prefix["prefix_values"]:
                interval = evaluate(definition["expression"], values, definitions)
                definitions[definition["declaration_id"]] = interval
                item["prefix_intervals"][definition["declaration_id"]] = list(interval)
            operands = [evaluate(node, values, definitions) for node in guard["operands"]]
            truth = comparison(guard["opcode"], *operands)
            continues = None if truth is None else truth == prefix["partition_check"]["work_when"]
            item.update(guard_operand_intervals=operands, guard_truth=truth, work_executes=continues)
            if continues is False:
                break
            upper += 1
            if guaranteed_reachable and continues is True:
                lower += 1
            else:
                guaranteed_reachable = False
            # Possible work implies a possible increment, even on the final
            # header iteration. A definite break does not execute increment.
            representable((value + step, value + step))
        result.update(status="checked", iteration_bounds_established=True,
                      work_count_bounds=[lower, upper], original_header_iteration_count=count,
                      declaration_intervals=declaration_intervals,
                      input_sha256={**work["input_sha256"], "declaration_intervals": _hash(declaration_intervals)})
        result["assumptions"].extend(work["assumptions"])
    except _Unknown as error:
        result["reason"] = str(error)
    except (TypeError, ValueError, KeyError, IndexError, RecursionError):
        result["reason"] = "unsupported_input_representation"
    return result


def check_prefix_values(root, loop_id, *, max_ast_nodes=None):
    """Connect pure scalar prefix initializers to guard values, without a loop proof."""
    partition = inspect_structure(root, loop_id, max_ast_nodes=max_ast_nodes)
    result = {"schema_version": "loop-exit-prefix-values/v1", "status": "unknown", "reason": None,
              "scope": "exit_guard_values_after_restricted_prefix", "partition_check": partition,
              "prefix_values": [], "prefix_preserves_existing_objects": "not_established",
              "source_program_checked": False, "deployable": False,
              "full_iteration_domain_established": False, "loop_header_checked": False,
              "work_effects_checked": False, "cross_iteration_stability_checked": False,
              "assumptions": list(partition["assumptions"]),
              "limitations": ["typed expression DAG preserves operation order; it is not unbounded-integer algebra",
                              "external reads are values at prefix entry, not proven constant across iterations",
                              "prefix executes even on a break iteration; header, work and overflow domains remain unproved"],
              "budget": {"max_prefix_declarations": 64, "max_expression_depth": 64}}
    if partition["status"] != "checked":
        result["reason"] = "exit_partition_not_checked"
        return result
    try:
        # The fresh partition already bounded and validated this entire AST.
        index, pending = {}, [root]
        while pending:
            node = pending.pop()
            if isinstance(node.get("id"), str):
                index.setdefault(node["id"], []).append(node)
            pending.extend(node.get("inner", []))
        loop = index[loop_id][0]

        def unique(node):
            identifier = node.get("id")
            if not isinstance(identifier, str) or len(index.get(identifier, [])) != 1 or index[identifier][0] is not node:
                raise _Unknown("prefix_identity_not_unique")
            return identifier

        declarations = []
        for binding in partition["prefix_statement_bindings"]:
            node = loop
            for position in binding["loop_relative_child_path"]:
                node = node["inner"][position]
            if node.get("kind") != "DeclStmt" or len(_children(node)) != 1:
                raise _Unknown("prefix_not_single_declaration_statement")
            variable = _children(node)[0]
            if (variable.get("kind") != "VarDecl" or _type(variable) not in {"int", "const int"}
                    or variable.get("storageClass") not in (None, "auto", "register")
                    or variable.get("tls") is not None or variable.get("thread_local") is not None
                    or variable.get("init") is None or len(_children(variable)) != 1):
                raise _Unknown("prefix_not_automatic_initialized_int")
            unique(variable)
            declarations.append(variable)
        if len(declarations) > 64:
            raise _Unknown("prefix_declaration_budget_exceeded")
        prefix_ids = {node["id"] for node in declarations}
        available, external_reads = set(), set()

        def term(node, depth=0):
            if depth > 64:
                raise _Unknown("prefix_expression_depth_exceeded")
            children = _children(node)
            kind = node.get("kind")
            if kind == "ParenExpr" and len(children) == 1:
                return term(children[0], depth + 1)
            if (kind == "ImplicitCastExpr" and node.get("castKind") == "LValueToRValue"
                    and len(children) == 1):
                value = children[0]
                while value.get("kind") == "ParenExpr" and len(_children(value)) == 1:
                    value = _children(value)[0]
                if value.get("kind") != "DeclRefExpr" or _children(value):
                    raise _Unknown("prefix_value_read_not_scalar_declaration")
                identifier = value["referencedDecl"]["id"]
                if identifier in prefix_ids:
                    if identifier not in available:
                        raise _Unknown("prefix_reads_self_or_later_declaration")
                    return {"kind": "prefix_value", "type": "int", "declaration_id": identifier}
                external_reads.add(identifier)
                return {"kind": "read", "type": "int", "declaration_id": identifier}
            if kind == "IntegerLiteral" and not children:
                return {"kind": "literal", "type": "int", "value": int(node["value"])}
            if kind == "BinaryOperator" and node.get("opcode") in {"+", "-", "*", "/", "%"} and len(children) == 2:
                return {"kind": "binary", "type": "int", "opcode": node["opcode"],
                        "operands": [term(child, depth + 1) for child in children]}
            if kind == "UnaryOperator" and node.get("opcode") in {"+", "-"} and len(children) == 1:
                return {"kind": "unary", "type": "int", "opcode": node["opcode"],
                        "operands": [term(children[0], depth + 1)]}
            raise _Unknown("prefix_value_expression_unsupported")

        for variable in declarations:
            initializer = _children(variable)[0]
            checked = check_no_memory_write(root, unique(initializer), max_ast_nodes=max_ast_nodes)
            item = {"declaration_id": variable["id"], "initializer_id": initializer["id"], "initializer_check": checked}
            result["prefix_values"].append(item)
            if checked["status"] != "checked" or checked.get("result_type") != "int":
                raise _Unknown("prefix_initializer_not_checked_int")
            item["expression"] = term(initializer)
            result["assumptions"].extend(checked["assumptions"])
            available.add(variable["id"])
        guard = partition["guard_ast"]
        expression = {"opcode": guard["opcode"], "operands": [term(node) for node in _children(guard)]}
        result.update(status="checked", guard_value_expression=expression,
                      prefix_preserves_existing_objects="conditional", external_read_declaration_ids=sorted(external_reads),
                      input_sha256=partition["input_sha256"], break_when=partition["break_when"],
                      work_when=partition["work_when"])
    except _Unknown as error:
        result["reason"] = str(error)
    except (TypeError, ValueError, KeyError, RecursionError, IndexError):
        result["reason"] = "unsupported_input_representation"
    return result


def check_header_connection(root, loop_id, int_bits, *, max_ast_nodes=None):
    """Bind original header induction to the guard DAG, not to its full domain."""
    from wavebridge.analysis.column_loops import observe_header

    header = observe_header(root, loop_id, int_bits, max_ast_nodes=max_ast_nodes)
    result = {"schema_version": "loop-exit-header-connection/v1", "status": "unknown", "reason": None,
              "scope": "header_induction_to_exit_guard", "header_check": header, "prefix_check": None,
              "induction_guard_references": [], "source_program_checked": False, "deployable": False,
              "full_iteration_domain_established": False, "work_effects_checked": False,
              "cross_iteration_stability_checked": False,
              "limitations": ["dependency identity alone does not imply monotonicity or an effective bound",
                              "guard and header bound may be different objects",
                              "body preservation, overflow and guarded iteration domain remain unproved"]}
    if header["status"] != "observed":
        result["reason"] = "header_not_observed"
        return result
    prefix = check_prefix_values(root, loop_id, max_ast_nodes=max_ast_nodes)
    result["prefix_check"] = prefix
    if prefix["status"] != "checked":
        result["reason"] = "prefix_values_not_checked"
        return result
    if header["input_sha256"]["root"] != prefix["input_sha256"]["root"]:
        result["reason"] = "input_changed_between_checks"
        return result
    induction = header["header"]["induction"]["declaration_id"]
    definitions = {item["declaration_id"]: item["expression"] for item in prefix["prefix_values"]}
    visited, pending = set(), [(prefix["guard_value_expression"], "guard", [])]
    while pending:
        node, owner, path = pending.pop()
        if node.get("kind") == "read" and node["declaration_id"] == induction:
            result["induction_guard_references"].append({"declaration_id": induction, "definition": owner,
                                                       "operand_path": path})
        if node.get("kind") == "prefix_value":
            identifier = node["declaration_id"]
            if identifier not in visited:
                visited.add(identifier)
                pending.append((definitions[identifier], identifier, []))
        pending.extend((child, owner, path + [position]) for position, child in enumerate(node.get("operands", [])))
    if not result["induction_guard_references"]:
        result["reason"] = "guard_does_not_depend_on_induction"
        return result
    result.update(status="checked", induction_declaration_id=induction,
                  input_sha256=header["input_sha256"],
                  assumptions=header["assumptions"] + prefix["assumptions"])
    return result


def check_work_preservation(payload, loop_id, int_bits, call_protocols, *, max_ast_nodes=None,
                            use_static_branches=False, use_nested_loops=False):
    """Check all selected work statements, not just successfully checked calls."""
    from wavebridge.analysis.column_loops import _check_body, _static_bool_value, _Unknown as BodyUnknown
    from wavebridge.verification.builtin_calls import check_call_no_memory_write
    from wavebridge.verification.scalar_call_effects import check_no_memory_write as check_scalar_call

    result = {"schema_version": "loop-exit-work-preservation/v1", "status": "unknown", "reason": None,
              "scope": "guarded_work_preserves_dependency_storage", "connection_check": None,
              "protected_declaration_ids": [], "call_effect_checks": {},
              "work_preserves_protected": "not_established", "external_call_effects_verified": False,
              "source_program_checked": False, "deployable": False, "full_iteration_domain_established": False,
              "assumptions": ["source is valid and asynchronous interference is excluded",
                              "memory stores do not alias any protected declaration storage"],
              "limitations": ["not a complete recurrence, integer overflow or iteration-domain proof",
                              "nested loops are not accepted by this work checker",
                              "external leaf effects remain unverified; all consumed call premises apply"],
              "budget": {"max_call_protocols": 64}}
    if (type(use_static_branches) is not bool or type(use_nested_loops) is not bool or
            not isinstance(payload, dict) or not isinstance(payload.get("ast"), dict) or
            not isinstance(call_protocols, dict) or len(call_protocols) > 64 or
            any(not isinstance(key, str) or not key or not isinstance(value, dict)
                for key, value in call_protocols.items())):
        result["reason"] = "invalid_inputs_or_protocols"
        return result
    if use_static_branches:
        result["schema_version"] = "loop-exit-work-preservation-with-static-branches/v1"
        result["static_branch_decisions"] = []
    if use_nested_loops:
        result["schema_version"] = "loop-exit-work-preservation-with-nested-loops/v1"
        result["static_branches_enabled"] = use_static_branches
        result["nested_loop_checks"] = []
        result["budget"].update(max_nested_loops=16, max_nested_depth=8)
        result["limitations"][1] = "only freshly checked guarded ForStmt nests are supported; termination is not proved"
    root = payload["ast"]
    connection = check_header_connection(root, loop_id, int_bits, max_ast_nodes=max_ast_nodes)
    result["connection_check"] = connection
    if connection["status"] != "checked":
        result["reason"] = "header_connection_not_checked"
        return result
    try:
        def dependencies(checked):
            header = checked["header_check"]["header"]
            protected = set(checked["prefix_check"]["external_read_declaration_ids"])
            protected.add(checked["induction_declaration_id"])
            for source in (header["start"], header["bound"]):
                if "declaration_id" in source:
                    protected.add(source["declaration_id"])
            return protected

        prefix = connection["prefix_check"]
        protected = dependencies(connection)
        result["protected_declaration_ids"] = sorted(protected)
        loops, pending = [], [root]
        while pending:
            node = pending.pop()
            if node.get("id") == loop_id:
                loops.append(node)
            pending.extend(node.get("inner", []))
        if len(loops) != 1:
            raise _Unknown("loop_identity_changed")
        paths, pending = {}, [(loops[0], [])]
        while pending:
            node, path = pending.pop()
            paths.setdefault(id(node), []).append(path)
            pending.extend((child, path + [position]) for position, child in
                           enumerate(node.get("inner", [])) if child)

        def choose_branch(node):
            if any(node.get(flag) for flag in ("hasInit", "hasVar", "isConstexpr", "isConsteval")):
                return None
            children = _children(node)
            if len(children) != (3 if node.get("hasElse") else 2):
                return None
            try:
                value = _static_bool_value(children[0])
            except BodyUnknown:
                return None  # Unknown never means false: ordinary traversal checks both arms.
            locations = paths.get(id(node), [])
            if len(locations) != 1 or not isinstance(node.get("id"), str):
                raise _Unknown("static_branch_occurrence_not_unique")
            selected = [children[1]] if value else children[2:]
            result["static_branch_decisions"].append({
                "if_id": node["id"], "loop_relative_child_path": locations[0],
                "condition_ast": children[0], "condition_value": value,
                "selected_arm": "then" if value else "else" if selected else "none",
                "guard_evaluation": "checked_literal_boolean_no_memory_write"})
            return selected

        def check_call(node):
            identifier = node.get("id")
            if identifier not in call_protocols:
                return False
            reports = result["call_effect_checks"]
            if identifier not in reports:
                protocol = call_protocols[identifier]
                if protocol.get("schema_version") == "scalar-leaf-effect-assumption/v1":
                    reports[identifier] = check_scalar_call(root, identifier, protocol, max_ast_nodes=max_ast_nodes)
                else:
                    reports[identifier] = check_call_no_memory_write(payload, identifier, protocol, max_ast_nodes=max_ast_nodes)
            return reports[identifier]["status"] == "checked"

        def bound_statement(loop, binding):
            statement = loop
            for position in binding["loop_relative_child_path"]:
                statement = statement["inner"][position]
            if statement.get("id") != binding["id"]:
                raise _Unknown("work_binding_changed")
            return statement

        def scan(statement, protected_ids, depth):
            _check_body(statement, protected_ids, call_callback=check_call,
                        nested_callback=(lambda node: nested(node, protected_ids, depth + 1))
                        if use_nested_loops else None,
                        branch_callback=choose_branch if use_static_branches else None)

        def nested(node, ancestors, depth):
            reports = result["nested_loop_checks"]
            if depth > 8 or len(reports) >= 16:
                raise _Unknown("nested_loop_budget_exceeded")
            locations = paths.get(id(node), [])
            if len(locations) != 1:
                raise _Unknown("nested_loop_occurrence_not_unique")
            report = {"loop_id": node.get("id"), "loop_relative_child_path": locations[0],
                      "status": "unknown", "ancestor_protected_declaration_ids": sorted(ancestors),
                      "header_preserves_ancestors": "not_established",
                      "body_preserves_combined_dependencies": "not_established"}
            reports.append(report)
            child = check_header_connection(root, node.get("id"), int_bits, max_ast_nodes=max_ast_nodes)
            report["connection_check"] = child
            if child["status"] != "checked":
                raise _Unknown("nested_header_connection_not_checked")
            if child["input_sha256"]["root"] != connection["input_sha256"]["root"]:
                raise _Unknown("input_changed_between_checks")
            # Inspect the ORIGINAL init, condition and increment. Only the fresh
            # nested induction may change; no ancestor storage may be touched.
            parts = node["inner"]
            for expression in (parts[0], parts[2], parts[3]):
                scan(expression, ancestors, depth)
            report["header_preserves_ancestors"] = "conditional"
            combined = ancestors | dependencies(child)
            report["combined_protected_declaration_ids"] = sorted(combined)
            partition = child["prefix_check"]["partition_check"]
            # Include the prefix and complete guard on the breaking iteration.
            # Only the structurally owned BreakStmt itself is omitted.
            for binding in partition["prefix_statement_bindings"]:
                scan(bound_statement(node, binding), combined, depth)
            scan(partition["guard_ast"], combined, depth)
            for binding in partition["work_statement_bindings"]:
                scan(bound_statement(node, binding), combined, depth)
            report.update(status="checked", body_preserves_combined_dependencies="conditional")
            result["assumptions"].extend(child["assumptions"])

        for binding in prefix["partition_check"]["work_statement_bindings"]:
            scan(bound_statement(loops[0], binding), protected, 0)
        unused = sorted(set(call_protocols) - set(result["call_effect_checks"]))
        result["unused_call_protocol_ids"] = unused
        if unused:
            raise _Unknown("unused_call_protocols")
        result.update(status="checked", work_preserves_protected="conditional",
                      input_sha256={**connection["input_sha256"], "call_protocols": _hash(call_protocols)})
        result["assumptions"].extend(connection["assumptions"])
    except BodyUnknown as error:
        result["reason"], result["unknown_range"] = error.reason, error.range
    except _Unknown as error:
        result["reason"] = str(error)
    except (TypeError, ValueError, KeyError, IndexError, RecursionError):
        result["reason"] = "unsupported_input_representation"
    return result
