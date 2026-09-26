"""Conditional per-work-path stores, relative to the current output pointer.

This is deliberately not a lane-family, pointer-history or output-coverage proof.
All entry and loop evidence is rebuilt from the supplied AST.
"""

from wavebridge.verification import initializer_domain, scalar_expression_effects
from wavebridge.verification.builtin_calls import _Unknown
from wavebridge.verification.getter_returns import _hash


def check_entry_pointer(payload, declaration_id, outer_loop_id, inner_loop_id, leaf_contract,
                        integer_types, history_call_protocols, work_call_protocols,
                        inner_call_protocols, declaration_intervals, output_declaration_id, *,
                        pointer_binding, max_ast_nodes=None, use_static_branches=False,
                        use_source_constants=False):
    """Bind one entry-relative pointer update to freshly checked guarded stores.

    Row/stride intervals describe values WHEN the offset initializer executes;
    they are external domains, not recovered initialization or launch facts.
    """
    result = {"schema_version": "guarded-entry-pointer-history/v1", "status": "unknown",
              "reason": None, "scope": "conditional_entry_relative_element_offset_at_reached_stores",
              "output_pointer_history_checked": False, "full_output_coverage_established": False,
              "lane_family_established": False, "source_program_checked": False, "deployable": False,
              "assumptions": ["standard abstract-machine execution in one function activation",
                              "no nonlocal control transfer, stack introspection or asynchronous mutation",
                              "pointer update and stores are defined within the same live array object",
                              "row and stride intervals hold when the offset initializer is evaluated"],
              "limitations": ["allocation, pointer representability and dynamic aliasing are not checked",
                              "row/stride domains are external; row getter and launch are not checked",
                              "stride is not assumed equal to the store column-count parameter",
                              "no whole-kernel, floating-point, lane-family or deployment guarantee"]}
    try:
        keys = {"offset_declaration_id", "row_declaration_id", "stride_parameter_id",
                "row_interval", "stride_interval"}
        if not isinstance(pointer_binding, dict) or set(pointer_binding) != keys:
            raise _Unknown("invalid_pointer_binding")
        selected = check(payload, declaration_id, outer_loop_id, inner_loop_id, leaf_contract,
                         integer_types, history_call_protocols, work_call_protocols,
                         inner_call_protocols, declaration_intervals, output_declaration_id,
                         max_ast_nodes=max_ast_nodes, use_static_branches=use_static_branches,
                         use_source_constants=use_source_constants)
        result["store_check"] = selected
        if selected["status"] != "checked":
            raise _Unknown("guarded_stores_not_checked")
        result["assumptions"].extend(selected["assumptions"])
        bounds = selected["bounds_check"]
        history = bounds["entry_check"]["history_check"]
        root = payload["ast"]

        def semantic_children(node):
            # Clang's semantic array initializer slots are not always `inner`.
            children = []
            for key in ("inner", "array_filler"):
                values = node.get(key, [])
                if not isinstance(values, list) or any(not isinstance(value, dict) for value in values):
                    raise _Unknown("unsupported_pointer_history_children")
                children.extend(value for value in values if value)
            return children

        declarations, pending, visited = {}, [root], 0
        budget = scalar_expression_effects.MAX_AST_NODES if max_ast_nodes is None else max_ast_nodes
        while pending:
            node = pending.pop()
            visited += 1
            if visited > budget:
                raise _Unknown("pointer_history_ast_budget_exceeded")
            if isinstance(node.get("id"), str):
                declarations.setdefault(node["id"], []).append(node)
            pending.extend(semantic_children(node))

        def unique(identifier):
            nodes = declarations.get(identifier, []) if isinstance(identifier, str) else []
            if len(nodes) != 1:
                raise _Unknown("pointer_binding_identity_not_unique")
            return nodes[0]

        function = unique(history["selection"]["function_id"])
        bodies = [n for n in function.get("inner", []) if n.get("kind") == "CompoundStmt"]
        if len(bodies) != 1:
            raise _Unknown("function_body_not_unique")
        statements = bodies[0].get("inner", [])
        params = {n["id"]: n for n in function.get("inner", []) if n.get("kind") == "ParmVarDecl"}
        offset_id, row_id, stride_id = (pointer_binding[key] for key in
                                       ("offset_declaration_id", "row_declaration_id", "stride_parameter_id"))
        if (any(not isinstance(x, str) or not x for x in (offset_id, row_id, stride_id)) or
                len({offset_id, row_id, stride_id, declaration_id, output_declaration_id}) != 5):
            raise _Unknown("pointer_binding_roles_not_distinct")
        if stride_id not in params or scalar_expression_effects._type(params[stride_id]) != "int":
            raise _Unknown("stride_not_same_function_int_parameter")

        def automatic(identifier):
            node = unique(identifier)
            if (node.get("kind") != "VarDecl" or scalar_expression_effects._type(node) not in {"int", "const int"} or
                    node.get("storageClass") not in (None, "auto", "register") or
                    any(node.get(k) is not None for k in ("tls", "tlsKind", "thread_local", "threadLocal"))):
                raise _Unknown("pointer_offset_role_not_automatic_int")
            matches = [(i, statement) for i, statement in enumerate(statements)
                       if statement.get("kind") == "DeclStmt" and
                       any(child is node for child in statement.get("inner", []))]
            if len(matches) != 1 or len(matches[0][1].get("inner", [])) != 1:
                raise _Unknown("pointer_offset_declaration_not_direct_single_statement")
            return node, matches[0][0]

        offset, offset_position = automatic(offset_id)
        _, row_position = automatic(row_id)
        _, source_position = automatic(declaration_id)
        outer_position = history["selection"]["target_statement_index"]
        if not source_position < offset_position < outer_position or not row_position < offset_position:
            raise _Unknown("offset_snapshot_order_not_established")

        def peel(node):
            while node.get("kind") in {"ParenExpr", "ImplicitCastExpr"}:
                parts = node.get("inner", [])
                if (len(parts) != 1 or (node["kind"] == "ImplicitCastExpr" and
                        node.get("castKind") not in {"LValueToRValue", "NoOp"})):
                    raise _Unknown("unsupported_pointer_offset_cast")
                node = parts[0]
            return node

        def reference(node, identifier):
            current = peel(node)
            return (current.get("kind") == "DeclRefExpr" and not current.get("inner", []) and
                    current.get("valueCategory") == "lvalue" and
                    current.get("referencedDecl", {}).get("id") == identifier)

        initializers = [n for n in offset.get("inner", []) if not n.get("kind", "").endswith("Attr")]
        if offset.get("init") is None or len(initializers) != 1:
            raise _Unknown("offset_initializer_missing_or_ambiguous")
        expression = peel(initializers[0])
        terms = expression.get("inner", [])
        if expression.get("kind") != "BinaryOperator" or expression.get("opcode") != "+" or len(terms) != 2:
            raise _Unknown("offset_not_row_stride_plus_source")
        product = peel(terms[0])
        factors = product.get("inner", [])
        if (product.get("kind") != "BinaryOperator" or product.get("opcode") != "*" or len(factors) != 2 or
                not reference(factors[0], row_id) or not reference(factors[1], stride_id) or
                not reference(terms[1], declaration_id)):
            raise _Unknown("offset_not_row_stride_plus_source")
        # Shape matching never erases typed machine operations or their order.
        pending = [initializers[0]]
        while pending:
            node = pending.pop()
            if scalar_expression_effects._type(node) not in {"int", "const int"}:
                raise _Unknown("offset_expression_not_signed_int")
            pending.extend(node.get("inner", []))
        bits = integer_types["int"]["bits"]
        maximum = (1 << (bits - 1)) - 1

        def domain(value):
            if (not isinstance(value, (list, tuple)) or len(value) != 2 or
                    any(type(x) is not int for x in value) or not 0 <= value[0] <= value[1] <= maximum):
                raise _Unknown("invalid_pointer_snapshot_domain")
            return value

        row_range, stride_range = (domain(pointer_binding[k]) for k in ("row_interval", "stride_interval"))
        source = bounds["source_interval"]
        product_range = [row_range[0] * stride_range[0], row_range[1] * stride_range[1]]
        offset_range = [product_range[0] + source["lower"], product_range[1] + source["upper"]]
        if product_range[1] > maximum or offset_range[1] > maximum:
            raise _Unknown("pointer_offset_signed_arithmetic_may_overflow")
        updates = []
        for position, statement in enumerate(statements):
            children = statement.get("inner", [])
            if (statement.get("kind") == "CompoundAssignOperator" and statement.get("opcode") == "+=" and
                    len(children) == 2 and reference(children[0], output_declaration_id)):
                updates.append((position, statement))
        if len(updates) != 1:
            raise _Unknown("pointer_update_not_unique_direct_statement")
        update_position, update = updates[0]
        if not offset_position < update_position < outer_position:
            raise _Unknown("pointer_update_order_not_established")
        lhs, rhs = update["inner"]
        if (lhs.get("kind") != "DeclRefExpr" or lhs.get("inner", []) or lhs.get("valueCategory") != "lvalue" or
                scalar_expression_effects._type(lhs) != "float *" or scalar_expression_effects._type(update) != "float *" or
                any(scalar_expression_effects._type({"type": update.get(key)}) != "float *"
                    for key in ("computeLHSType", "computeResultType")) or
                rhs.get("kind") != "ImplicitCastExpr" or rhs.get("castKind") != "LValueToRValue" or
                scalar_expression_effects._type(rhs) != "int" or not reference(rhs, offset_id)):
            raise _Unknown("pointer_update_type_or_operand_not_supported")
        forbidden = {"LambdaExpr", "BlockExpr", "CXXRecordDecl", "RecordDecl", "GCCAsmStmt", "MSAsmStmt",
                     "GotoStmt", "IndirectGotoStmt", "LabelStmt", "SwitchStmt", "CaseStmt", "DefaultStmt",
                     "CXXTryStmt", "CXXCatchStmt", "CXXThrowExpr", "CoroutineBodyStmt", "CoawaitExpr", "CoyieldExpr"}
        pending = [(bodies[0], [])]
        references = []
        while pending:
            node, ancestors = pending.pop()
            if len(ancestors) > 128:
                raise _Unknown("pointer_history_depth_budget_exceeded")
            if node.get("kind") in forbidden:
                raise _Unknown("unsupported_pointer_history_control_or_capture")
            if node.get("kind") == "DeclRefExpr" and node.get("referencedDecl", {}).get("id") in {output_declaration_id, offset_id}:
                if unique(node.get("id")) is not node:
                    raise _Unknown("pointer_reference_occurrence_not_unique")
                if node is lhs:
                    classification = "selected_builtin_update_lhs"
                else:
                    parents = list(ancestors)
                    while parents and parents[-1].get("kind") == "ParenExpr":
                        parents.pop()
                    if (not parents or parents[-1].get("kind") != "ImplicitCastExpr" or
                            parents[-1].get("castKind") != "LValueToRValue"):
                        raise _Unknown("pointer_or_offset_storage_write_or_escape")
                    classification = "value_read_not_storage_escape"
                references.append({"expression_id": node["id"], "classification": classification})
            pending.extend((child, ancestors + [node]) for child in semantic_children(node))
        if sum(item["classification"] == "selected_builtin_update_lhs" for item in references) != 1:
            raise _Unknown("selected_update_lhs_occurrence_not_unique")
        relation = selected["relative_index_relation"]
        result.update(status="checked", output_pointer_history_checked=True,
                      pointer_update_id=update["id"], reference_classifications=references,
                      offset_initializer_id=initializers[0]["id"], offset_interval=offset_range,
                      entry_relative_offset_relation={
                          "row_declaration_id": row_id, "stride_parameter_id": stride_id,
                          "source_declaration_id": declaration_id, "outer_induction_id": relation["row_id"],
                          "count_parameter_id": relation["count_id"], "inner_induction_id": relation["iteration_id"],
                          "inner_stride": relation["stride"],
                          "expression": "row_at_snapshot*stride_at_snapshot + source + outer*count + inner*step",
                          "row_stride_evaluation_point": initializers[0]["id"], "units": "float_elements"},
                      input_sha256={"stores": selected["input_sha256"], "pointer_binding": _hash(pointer_binding)})
    except _Unknown as error:
        result["reason"] = str(error)
    except (KeyError, TypeError, ValueError, IndexError, RecursionError):
        result["reason"] = "unsupported_input_representation"
    return result


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
