"""Conditional per-work-path stores, relative to the current output pointer.

This is deliberately not a lane-family, pointer-history or output-coverage proof.
All entry and loop evidence is rebuilt from the supplied AST.
"""

from wavebridge.verification import initializer_domain, scalar_expression_effects
from wavebridge.verification.builtin_calls import _Unknown
from wavebridge.verification.getter_returns import _hash


def check(payload, declaration_id, outer_loop_id, inner_loop_id, leaf_contract,
          integer_types, history_call_protocols, work_call_protocols,
          inner_call_protocols, declaration_intervals, output_declaration_id, *,
          max_ast_nodes=None, use_static_branches=False, use_source_constants=False):
    """Check dense relative row indices and exactly one store on each work path."""
    result = {
        "schema_version": "guarded-relative-stores/v1", "status": "unknown", "reason": None,
        "scope": "one_reached_inner_work_path_relative_to_current_output_pointer",
        "guarded_store_relation_checked": False, "store_sites": [], "effect_checks": [],
        "full_output_coverage_established": False, "output_pointer_history_checked": False,
        "lane_family_established": False, "source_program_checked": False, "deployable": False,
        "assumptions": [],
        "limitations": ["no full lane multiset, prior pointer offset, allocation or cross-row coverage",
                        "no floating-point value, communication, machine-code or GPU guarantee",
                        "external domains and valid-execution/no-alias premises remain conditional"],
    }
    try:
        bounds = initializer_domain.check_nested_iteration_bounds(
            payload, declaration_id, outer_loop_id, inner_loop_id, leaf_contract,
            integer_types, history_call_protocols, work_call_protocols, inner_call_protocols,
            declaration_intervals, max_ast_nodes=max_ast_nodes,
            use_static_branches=use_static_branches, use_source_constants=use_source_constants)
        result["bounds_check"] = bounds
        if bounds["status"] != "checked":
            raise _Unknown("nested_bounds_not_checked")
        result["assumptions"].extend(bounds["assumptions"])
        root = payload["ast"]
        index, pending = {}, [root]
        while pending:
            node = pending.pop()
            if node.get("id"):
                index.setdefault(node["id"], []).append(node)
            pending.extend(child for child in node.get("inner", []) if child)

        def unique(identifier):
            nodes = index.get(identifier, [])
            if len(nodes) != 1:
                raise _Unknown("declaration_or_statement_not_unique")
            return nodes[0]

        entry = bounds["entry_check"]
        function = unique(entry["history_check"]["selection"]["function_id"])
        params = {node["id"]: node for node in function.get("inner", [])
                  if node.get("kind") == "ParmVarDecl"}
        if (output_declaration_id not in params or
                scalar_expression_effects._type(params[output_declaration_id]) != "float *"):
            raise _Unknown("output_not_same_function_float_pointer_parameter")
        iteration = bounds["iteration_check"]
        work = iteration["work_check"]
        connection = work["connection_check"]
        outer = entry["work_check"]["connection_check"]
        inner_id, outer_id = (connection["induction_declaration_id"], outer["induction_declaration_id"])
        prefix = connection["prefix_check"]
        partition = prefix["partition_check"]
        guard = prefix["guard_value_expression"]
        if (guard.get("opcode") != "<" or partition["work_when"] is not True or
                len(guard.get("operands", [])) != 2 or guard["operands"][1].get("kind") != "read"):
            raise _Unknown("unsupported_column_guard")
        count_id = guard["operands"][1]["declaration_id"]
        if count_id not in params or scalar_expression_effects._type(params[count_id]) != "int":
            raise _Unknown("column_count_not_int_parameter")
        ranges = dict(iteration.get("effective_declaration_intervals", {
            **declaration_intervals, declaration_id: [bounds["source_interval"]["lower"],
                                                     bounds["source_interval"]["upper"]]}))
        roles = {declaration_id, inner_id, outer_id, count_id}
        constants = {key: value[0] for key, value in ranges.items()
                     if key not in roles and value[0] == value[1]}
        for connected, identifier in ((connection, inner_id), (outer, outer_id)):
            header = connected["header_check"]["header"]
            end = header["bound"].get("value")
            if (header["start"].get("value") != 0 or header["step"] != 1 or
                    type(end) is not int or not 1 <= end <= 1024):
                raise _Unknown("unsupported_zero_based_unit_header")
            ranges[identifier] = [0, end - 1]
        capacity = ranges[inner_id][1] + 1
        bits = integer_types["int"]["bits"]
        minimum, maximum = -(1 << (bits - 1)), (1 << (bits - 1)) - 1

        def arithmetic(opcode, left, right):
            a, b = left
            c, d = right
            if opcode == "+":
                values = (a + c, b + d)
            elif opcode == "-":
                values = (a - d, b - c)
            elif opcode == "*":
                products = (a*c, a*d, b*c, b*d)
                values = (min(products), max(products))
            else:
                raise _Unknown("unsupported_index_operation")
            if values[0] < minimum or values[1] > maximum:
                raise _Unknown("store_index_arithmetic_may_overflow")
            return values

        def combine(opcode, left, right):
            polynomial = {}
            if opcode in {"+", "-"}:
                polynomial.update(left)
                for key, value in right.items():
                    polynomial[key] = polynomial.get(key, 0) + (value if opcode == "+" else -value)
            elif opcode == "*":
                for a, x in left.items():
                    for b, y in right.items():
                        key = tuple(sorted(a + b))
                        if len(key) > 2:
                            raise _Unknown("index_degree_budget")
                        polynomial[key] = polynomial.get(key, 0) + x*y
            else:
                raise _Unknown("unsupported_index_operation")
            if len(polynomial) > 64:
                raise _Unknown("index_term_budget")
            return {key: value for key, value in polynomial.items() if value}

        definitions = {item["declaration_id"]: item["expression"] for item in prefix["prefix_values"]}

        def model(node, depth=0):
            if depth > 32 or node.get("type") != "int":
                raise _Unknown("unsupported_column_expression")
            kind = node.get("kind")
            if kind == "prefix_value":
                return model(definitions[node["declaration_id"]], depth + 1)
            if kind == "read":
                identifier = node["declaration_id"]
                return {(): constants[identifier]} if identifier in constants else {(identifier,): 1}
            if kind == "literal":
                return {(): node["value"]} if node["value"] else {}
            if kind == "binary" and len(node.get("operands", [])) == 2:
                return combine(node["opcode"], *(model(child, depth + 1) for child in node["operands"]))
            raise _Unknown("unsupported_column_expression")

        column = model(guard["operands"][0])
        stride = column.get((inner_id,))
        if (type(stride) is not int or stride <= 0 or
                column != {(declaration_id,): 1, (inner_id,): stride}):
            raise _Unknown("column_not_source_plus_positive_iteration_stride")
        start_lower = bounds["source_interval"]["lower"]
        if start_lower < 0 or ranges[count_id][0] < 0:
            raise _Unknown("nonnegative_column_domain_required")
        if start_lower + capacity * stride < ranges[count_id][1]:
            result["status"] = "rejected"
            raise _Unknown("header_may_truncate_declared_column_domain")
        expected = {tuple(sorted((outer_id, count_id))): 1, (inner_id,): stride}

        def peel(node):
            while node.get("kind") in {"ParenExpr", "ImplicitCastExpr"}:
                children = node.get("inner", [])
                if len(children) != 1 or (node["kind"] == "ImplicitCastExpr" and
                        node.get("castKind") not in {"LValueToRValue", "NoOp"}):
                    raise _Unknown("unsupported_store_cast")
                node = children[0]
            return node

        def expression(node, depth=0):
            if depth > 32 or scalar_expression_effects._type(node) not in {"int", "const int"}:
                raise _Unknown("unsupported_index_type_or_depth")
            if node.get("kind") in {"ParenExpr", "ImplicitCastExpr"}:
                return expression(peel(node), depth + 1)
            kind = node.get("kind")
            if kind == "IntegerLiteral":
                value = int(node["value"])
                if not minimum <= value <= maximum:
                    raise _Unknown("index_literal_not_representable")
                return ({(): value} if value else {}), (value, value)
            if kind == "DeclRefExpr":
                identifier = node["referencedDecl"]["id"]
                # Do not silently cancel unsupported reads, e.g. source-source.
                if identifier not in {outer_id, inner_id, count_id} | set(constants):
                    raise _Unknown("unsupported_store_index_read")
                declared = unique(identifier)
                if scalar_expression_effects._type(declared) not in {"int", "const int"}:
                    raise _Unknown("index_declaration_not_scalar_int")
                return ({(): constants[identifier]} if identifier in constants else {(identifier,): 1}), ranges[identifier]
            children = node.get("inner", [])
            if kind == "BinaryOperator" and len(children) == 2 and node.get("opcode") in {"+", "-", "*"}:
                left, right = (expression(child, depth + 1) for child in children)
                return combine(node["opcode"], left[0], right[0]), arithmetic(node["opcode"], left[1], right[1])
            raise _Unknown("unsupported_store_index_expression")

        decisions = {item["if_id"]: item for item in work.get("static_branch_decisions", [])}

        def pure(node):
            unwrapped = peel(node)
            if unwrapped.get("kind") == "CallExpr":
                report = work["call_effect_checks"].get(unwrapped.get("id"))
                if not report or report["status"] != "checked":
                    raise _Unknown("store_expression_call_not_checked")
            else:
                report = scalar_expression_effects.check_no_memory_write(
                    root, node["id"], max_ast_nodes=max_ast_nodes, allow_integer_to_float=True)
                result["effect_checks"].append(report)
                if report["status"] != "checked":
                    result["failed_effect_expression_id"] = node["id"]
                    raise _Unknown("store_expression_effect_not_checked")
            if unwrapped.get("kind") == "CallExpr":
                result["effect_checks"].append(report)
            result["assumptions"].extend(report.get("assumptions", []))

        def sequence(nodes, depth):
            counts = {0}
            for node in nodes:
                next_counts = paths(node, depth + 1)
                counts = {min(2, a + b) for a in counts for b in next_counts}
            return counts

        def paths(node, depth=0):
            if depth > 64:
                raise _Unknown("store_path_depth_budget")
            children = node.get("inner", [])
            kind = node.get("kind")
            if kind == "CompoundStmt":
                return sequence(children, depth)
            if kind == "NullStmt":
                return {0}
            if kind == "IfStmt":
                if (any(node.get(flag) for flag in ("hasInit", "hasVar", "isConstexpr", "isConsteval")) or
                        len(children) != (3 if node.get("hasElse") else 2)):
                    raise _Unknown("unsupported_store_if")
                decision = decisions.get(node.get("id"))
                if decision:
                    if decision["condition_value"]:
                        return paths(children[1], depth + 1)
                    return paths(children[2], depth + 1) if len(children) == 3 else {0}
                pure(children[0])
                return paths(children[1], depth + 1) | (paths(children[2], depth + 1) if len(children) == 3 else {0})
            if kind != "BinaryOperator" or node.get("opcode") != "=" or len(children) != 2:
                raise _Unknown("unsupported_work_statement_for_store_count")
            lhs, rhs = children
            if lhs.get("kind") != "ArraySubscriptExpr" or len(lhs.get("inner", [])) != 2:
                raise _Unknown("store_not_one_dimensional_subscript")
            base, offset = lhs["inner"]
            base = peel(base)
            if (base.get("kind") != "DeclRefExpr" or
                    base.get("referencedDecl", {}).get("id") != output_declaration_id):
                result["status"] = "rejected"
                raise _Unknown("store_base_not_selected_output")
            if scalar_expression_effects._type(lhs) != "float":
                raise _Unknown("store_element_not_float")
            polynomial, interval = expression(offset)
            if polynomial != expected:
                result["status"] = "rejected"
                raise _Unknown("store_index_not_relative_row_and_iteration")
            pure(rhs)
            result["store_sites"].append({"assignment_id": node["id"], "index_id": offset["id"],
                                           "index_interval": list(interval), "output_declaration_id": output_declaration_id})
            return {1}

        loop = unique(inner_loop_id)
        statements = []
        for binding in partition["work_statement_bindings"]:
            node = loop
            for position in binding["loop_relative_child_path"]:
                node = node["inner"][position]
            if node.get("id") != binding["id"]:
                raise _Unknown("work_statement_binding_changed")
            statements.append(node)
        counts = sequence(statements, 0)
        result["store_count_per_work_path"] = sorted(counts)
        if counts != {1}:
            result["status"] = "rejected"
            raise _Unknown("work_paths_do_not_all_store_exactly_once")
        result.update(status="checked", guarded_store_relation_checked=True,
                      relative_index_relation={"row_id": outer_id, "count_id": count_id,
                                               "iteration_id": inner_id, "stride": stride},
                      header_capacity_checked=True,
                      input_sha256={"bounds": bounds["input_sha256"], "output_id": _hash(output_declaration_id)})
    except _Unknown as error:
        result["reason"] = str(error)
    except (KeyError, TypeError, ValueError, IndexError, RecursionError):
        result["reason"] = "unsupported_input_representation"
    return result
