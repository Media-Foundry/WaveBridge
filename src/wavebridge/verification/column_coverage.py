"""Exact coverage of same-stride arithmetic progressions, without column expansion."""

import hashlib
import json

from wavebridge.verification.integer_conversion import check_interval as check_conversion


def check_fixed_guarded_loads(payload, declaration_id, outer_loop_id, inner_loop_id,
                              leaf_contract, integer_types, history_call_protocols,
                              work_call_protocols, input_declaration_id, count_parameter_id,
                              count_interval, *, pointer_binding, max_ast_nodes=1_000_000):
    """Bind one guarded float load site to source labels and entry pointer history.

    Count/row/stride domains are explicit external premises. This does not prove
    allocation, immutable input contents, physical participation or GPU execution.
    """
    from wavebridge.analysis.integer_constants import evaluate as constant
    from wavebridge.verification.getter_returns import _hash
    from wavebridge.verification.guarded_stores import _check_entry_pointer_history

    report = {"schema_version": "fixed-guarded-load-relation/v1", "status": "unknown", "reason": None,
              "scope": "one_selected_direct_guarded_load_address_and_destination_at_assignment",
              "labels_check": None, "pointer_history_check": None, "constant_checks": [], "assumptions": [],
              "guarded_load_relation_checked": False, "entry_pointer_history_checked": False,
              "count_domain_checked_under_external_interval": False,
              "count_common_across_lanes_checked": False, "actual_thread_participation_checked": False,
              "memory_load_coverage_checked": False, "input_contents_preserved": False,
              "source_program_checked": False, "deployable": False}
    try:
        labels = check_fixed_guarded_labels(payload, declaration_id, outer_loop_id, inner_loop_id,
                    leaf_contract, integer_types, history_call_protocols, work_call_protocols,
                    max_ast_nodes=max_ast_nodes)
        report["labels_check"] = labels
        report["assumptions"] = list(labels["assumptions"])
        if labels["status"] != "checked" or labels["formal_label_coverage_checked"] is not True:
            raise ValueError("fresh_guarded_labels_not_checked")
        if (not isinstance(count_interval, (list, tuple)) or len(count_interval) != 2 or
                any(type(v) is not int for v in count_interval) or
                not 0 <= count_interval[0] <= count_interval[1] <= labels["capacity"]):
            raise ValueError("invalid_external_count_interval")
        root = payload["ast"]
        index, pending, visited = {}, [root], 0
        while pending:
            node = pending.pop()
            visited += 1
            if visited > max_ast_nodes or not isinstance(node, dict):
                raise ValueError("semantic_ast_budget_or_representation")
            if isinstance(node.get("id"), str):
                index.setdefault(node["id"], []).append(node)
            for key in ("inner", "array_filler"):
                children = node.get(key, [])
                if not isinstance(children, list):
                    raise ValueError("malformed_semantic_children")
                pending.extend(children)

        def unique(identifier):
            nodes = index.get(identifier, [])
            if len(nodes) != 1:
                raise ValueError("load_identity_not_unique")
            return nodes[0]

        def typ(node):
            info = node.get("type", {})
            if "typeAliasDeclId" in info and "desugaredQualType" not in info:
                raise ValueError("unresolved_load_type_alias")
            return info.get("desugaredQualType", info.get("qualType"))

        def plain(node):
            if node.get("array_filler", []) != [] or not isinstance(node.get("inner", []), list):
                raise ValueError("unexpected_load_semantic_slot")
            # Clang may reuse pure literal nodes across template instantiations.
            # Only identical, childless signed-int prvalues may share identity.
            if node.get("kind") == "IntegerLiteral":
                copies = index.get(node.get("id"), [])
                if (not copies or any(n != node for n in copies) or node.get("inner", []) != [] or
                        typ(node) != "int" or node.get("valueCategory") != "prvalue"):
                    raise ValueError("unsupported_shared_integer_literal")
            elif unique(node.get("id")) is not node:
                raise ValueError("load_identity_mismatch")
            return node.get("inner", [])

        def ref(node):
            plain(node)
            target = node.get("referencedDecl", {})
            declaration = unique(target.get("id"))
            if (node.get("kind") != "DeclRefExpr" or node.get("inner", []) != [] or
                    node.get("valueCategory") != "lvalue" or
                    declaration.get("kind") not in {"VarDecl", "ParmVarDecl"} or
                    target.get("kind") != declaration.get("kind") or
                    target.get("type") != declaration.get("type") or node.get("type") != declaration.get("type")):
                raise ValueError("load_reference_declaration_mismatch")
            return declaration

        def cast(node, cast_kind, result_type):
            children = plain(node)
            if (node.get("kind") != "ImplicitCastExpr" or node.get("castKind") != cast_kind or
                    typ(node) != result_type or node.get("valueCategory") != "prvalue" or len(children) != 1):
                raise ValueError("unsupported_load_conversion")
            return children[0]

        def int_atom(node):
            children = plain(node)
            if node.get("kind") == "ParenExpr" and typ(node) in {"int", "const int"} and len(children) == 1:
                return int_atom(children[0])
            if node.get("kind") == "IntegerLiteral":
                value = int(node["value"], 0)
                if not minimum <= value <= maximum:
                    raise ValueError("load_literal_outside_signed_abi")
                return (None, value)
            bare = cast(node, "LValueToRValue", "int")
            declaration = ref(bare)
            if typ(declaration) not in {"int", "const int"}:
                raise ValueError("load_atom_not_signed_int")
            return (declaration["id"], None)

        entry = labels["entry_check"]
        history = entry["history_check"]
        function = unique(history["selection"]["function_id"])
        params = [n for n in function["inner"] if n.get("kind") == "ParmVarDecl"]
        count_param, pointer = unique(count_parameter_id), unique(input_declaration_id)
        if count_param not in params or typ(count_param) != "int" or pointer not in params or typ(pointer) != "const float *":
            raise ValueError("load_parameters_not_supported_same_function_types")
        bits = integer_types["int"]["bits"]
        minimum, maximum = -(1 << (bits - 1)), (1 << (bits - 1)) - 1
        outer = entry["recurrence_check"]
        outer_id = outer["induction"]["declaration_id"]
        inner_id, width, iterations = labels["induction_declaration_id"], labels["width"], labels["iterations"]
        batches = outer["bound"].get("value")
        if (outer["start"].get("kind") != "integer_literal" or outer["start"].get("value") != 0 or
                outer["step"] != 1 or type(batches) is not int or not 1 <= batches <= 4096 or
                len({outer_id, inner_id, count_parameter_id, declaration_id, input_declaration_id}) != 5):
            raise ValueError("unsupported_load_loop_family")

        bound = unique(labels["count_declaration_id"])
        count_mode = "direct_parameter"
        if bound is not count_param:
            initializer, = plain(bound)
            children = plain(initializer)
            if initializer.get("kind") == "ConditionalOperator":
                if typ(initializer) != "int" or initializer.get("valueCategory") != "prvalue" or len(children) != 3:
                    raise ValueError("unsupported_count_conditional")
                predicate = children[0]
                while predicate.get("kind") == "ParenExpr":
                    parts = plain(predicate)
                    if typ(predicate) != "bool" or len(parts) != 1:
                        raise ValueError("unsupported_count_predicate_wrapper")
                    predicate = parts[0]
                operands = plain(predicate)
                if (predicate.get("kind") != "BinaryOperator" or typ(predicate) != "bool" or
                        predicate.get("opcode") not in {"<", "<=", ">", ">=", "==", "!="} or len(operands) != 2):
                    raise ValueError("unsupported_count_predicate")
                for operand in operands:
                    int_atom(operand)
                if set(int_atom(n) for n in children[1:]) != {(None, 0), (count_parameter_id, None)}:
                    raise ValueError("count_not_zero_or_selected_parameter")
                count_mode = "zero_or_parameter_selected_by_source_comparison"
            elif int_atom(initializer) != (count_parameter_id, None):
                raise ValueError("count_not_selected_parameter")
            else:
                count_mode = "parameter_snapshot"

        guard = unique(labels["guard_id"])
        then = guard["inner"][1]
        statements = plain(then)
        if then.get("kind") != "CompoundStmt" or len(statements) != 1:
            raise ValueError("load_guard_arm_not_one_assignment")
        assignment, = statements
        operands = plain(assignment)
        if (assignment.get("kind") != "BinaryOperator" or assignment.get("opcode") != "=" or
                typ(assignment) != "float" or assignment.get("valueCategory") != "lvalue" or len(operands) != 2):
            raise ValueError("load_not_plain_float_assignment")

        def subscript(node, result_type):
            parts = plain(node)
            if node.get("kind") != "ArraySubscriptExpr" or typ(node) != result_type or node.get("valueCategory") != "lvalue" or len(parts) != 2:
                raise ValueError("unsupported_load_subscript")
            return parts

        dest_base, dest_inner = subscript(operands[0], "float")
        row_base, dest_outer = subscript(cast(dest_base, "ArrayToPointerDecay", "float *"), f"float[{iterations}]")
        dest = ref(cast(row_base, "ArrayToPointerDecay", f"float (*)[{iterations}]"))
        plain(dest)
        if (typ(dest) != f"float[{batches}][{iterations}]" or dest.get("kind") != "VarDecl" or
                dest.get("storageClass") not in (None, "auto", "register") or
                any(dest.get(k) is not None for k in ("tls", "tlsKind", "thread_local", "threadLocal")) or
                dest.get("inner", []) != [] or dest.get("init") is not None or
                int_atom(dest_outer) != (outer_id, None) or int_atom(dest_inner) != (inner_id, None)):
            raise ValueError("destination_not_automatic_iteration_array")
        function_body, = [n for n in function["inner"] if n.get("kind") == "CompoundStmt"]
        prefix = function_body["inner"][:history["selection"]["target_statement_index"]]
        if not any(n.get("kind") == "DeclStmt" and plain(n) == [dest] for n in prefix):
            raise ValueError("destination_not_direct_pre_loop_array")
        load = cast(operands[1], "LValueToRValue", "float")
        load_base, load_index = subscript(load, "const float")
        pointer_ref = cast(load_base, "LValueToRValue", "const float *")
        if ref(pointer_ref) is not pointer:
            raise ValueError("load_uses_different_input_pointer")
        pending = [unique(inner_loop_id)]
        input_uses = []
        while pending:
            node = pending.pop()
            if node.get("kind") == "DeclRefExpr" and node.get("referencedDecl", {}).get("id") == input_declaration_id:
                input_uses.append(node)
            pending.extend(node.get("inner", []) + node.get("array_filler", []))
        if len(input_uses) != 1 or input_uses[0] is not pointer_ref:
            raise ValueError("additional_direct_input_use_in_inner_loop")

        domains = {outer_id: (0, batches - 1), inner_id: (0, iterations - 1), count_parameter_id: tuple(count_interval)}

        def polynomial(node, depth=0):
            children = plain(node)
            if depth > 32 or typ(node) not in {"int", "const int"}:
                raise ValueError("unsupported_load_index_type_or_depth")
            if node.get("kind") == "ParenExpr" and len(children) == 1:
                return polynomial(children[0], depth + 1)
            if node.get("kind") != "BinaryOperator":
                identifier, value = int_atom(node)
                if identifier in domains:
                    return {(identifier,): 1}, domains[identifier]
                if identifier is not None:
                    checked = constant(root, identifier, bits)
                    report["constant_checks"].append(checked)
                    if checked["status"] != "evaluated":
                        raise ValueError("load_index_unknown_constant")
                    for source in checked["sources"]:
                        unique(source["declaration_id"])
                    value = checked["value"]
                return ({(): value} if value else {}), (value, value)
            op = node.get("opcode")
            if op not in {"+", "-", "*"} or node.get("valueCategory") != "prvalue" or len(children) != 2:
                raise ValueError("unsupported_load_index_operator")
            a, b = [polynomial(c, depth + 1) for c in children]
            terms = {}
            if op == "*":
                for ka, va in a[0].items():
                    for kb, vb in b[0].items():
                        key = tuple(sorted(ka + kb))
                        if len(key) > 2:
                            raise ValueError("load_index_degree_budget")
                        terms[key] = terms.get(key, 0) + va * vb
                endpoints = [x * y for x in a[1] for y in b[1]]
                interval = min(endpoints), max(endpoints)
            else:
                sign = 1 if op == "+" else -1
                terms = {key: a[0].get(key, 0) + sign * b[0].get(key, 0) for key in a[0].keys() | b[0].keys()}
                interval = ((a[1][0] + b[1][0], a[1][1] + b[1][1]) if sign == 1 else
                            (a[1][0] - b[1][1], a[1][1] - b[1][0]))
            if len(terms) > 64 or interval[0] < minimum or interval[1] > maximum:
                raise ValueError("load_index_budget_or_intermediate_signed_overflow")
            return {k: v for k, v in terms.items() if v}, interval

        terms, interval = polynomial(load_index)
        if terms != {tuple(sorted((outer_id, count_parameter_id))): 1, (inner_id,): width}:
            raise ValueError("load_index_not_row_count_plus_iteration_width")
        relation = {"row_id": outer_id, "count_id": count_parameter_id, "iteration_id": inner_id, "stride": width}
        pointer_check = _check_entry_pointer_history(payload, declaration_id, outer_loop_id,
            entry["result_interval"], history["selection"], integer_types, input_declaration_id,
            pointer_binding, relation, pointer_type="const float *", readonly_parameter_ids=(count_parameter_id,),
            max_ast_nodes=max_ast_nodes)
        report["pointer_history_check"] = pointer_check
        report["assumptions"].extend(pointer_check["assumptions"])
        report["assumptions"].extend([
            "selected count parameter lies in the external interval at function entry",
            "all recorded source-validity, call-effect, no-alias and normal-execution premises hold",
            "address correspondence is at the selected assignment only; input contents and later destination retention are not established"])
        if pointer_check["status"] != "checked" or pointer_check["pointer_history_checked"] is not True:
            raise ValueError("entry_pointer_history_not_checked: " + str(pointer_check["reason"]))
        if pointer_check["input_sha256"]["root"] != labels["input_sha256"]["root"]:
            raise ValueError("load_pointer_root_mismatch")
        report.update(status="checked", guarded_load_relation_checked=True, entry_pointer_history_checked=True,
            count_domain_checked_under_external_interval=True, count_mode=count_mode,
            count_interval=list(count_interval), guard_count_interval=[0 if count_mode.startswith("zero_or") else count_interval[0], count_interval[1]],
            load_expression_id=load["id"], assignment_id=assignment["id"], destination_declaration_id=dest["id"],
            destination_indices=[outer_id, inner_id], relative_index_relation=relation, relative_index_interval=list(interval),
            entry_relative_offset_relation=pointer_check["entry_relative_offset_relation"],
            column_relation="row_at_snapshot*stride_at_snapshot + outer*count + column",
            input_sha256={"root": labels["input_sha256"]["root"], "labels": _hash(labels["input_sha256"]),
                          "pointer_history": _hash(pointer_check["input_sha256"]), "input_id": _hash(input_declaration_id),
                          "count_id": _hash(count_parameter_id), "count_interval": _hash(count_interval),
                          "load": _hash(load), "assignment": _hash(assignment)})
    except (ValueError, TypeError, KeyError, IndexError, AttributeError, RecursionError, StopIteration) as error:
        report["reason"] = str(error)
    return report


def check_fixed_guarded_labels(payload, declaration_id, outer_loop_id, inner_loop_id,
                               leaf_contract, integer_types, history_call_protocols,
                               work_call_protocols, *, max_ast_nodes=1_000_000):
    """Match source labels/guard to a dense formal lane-by-iteration family.

    This is NOT load coverage: actual participation, pointer offsets, allocation,
    loaded values and the guard count's entry domain remain separate obligations.
    """
    from wavebridge.verification.initializer_domain import check_fixed_nested_entry
    from wavebridge.verification.getter_returns import _hash
    from wavebridge.analysis.integer_constants import evaluate as constant
    from wavebridge.analysis.column_loops import _check_body, _Unknown as BodyUnknown

    report = {"schema_version": "fixed-guarded-column-labels/v1", "status": "unknown", "reason": None,
              "scope": "source_guarded_labels_over_explicit_formal_lane_and_iteration_family",
              "entry_check": None, "constant_checks": [], "assumptions": [],
              "formal_label_coverage_checked": False, "actual_thread_participation_checked": False,
              "guard_count_entry_domain_checked": False, "memory_load_coverage_checked": False,
              "pointer_history_checked": False, "source_program_checked": False, "deployable": False}
    try:
        entry = check_fixed_nested_entry(payload, declaration_id, outer_loop_id, inner_loop_id,
                    leaf_contract, integer_types, history_call_protocols, work_call_protocols,
                    max_ast_nodes=max_ast_nodes)
        report["entry_check"] = entry
        report["assumptions"] = list(entry["assumptions"])
        if entry["status"] != "checked" or not entry["value_preserved_to_nested_entry"]:
            raise ValueError("fresh_fixed_nested_entry_not_checked")
        root = payload["ast"]
        index, parents, pending, used = {}, {}, [(root, None)], 0
        while pending:
            node, parent = pending.pop()
            used += 1
            if used > max_ast_nodes:
                raise ValueError("semantic_ast_node_budget_exceeded")
            if not isinstance(node, dict):
                raise ValueError("malformed_ast")
            if isinstance(node.get("id"), str):
                index.setdefault(node["id"], []).append(node)
                parents.setdefault(node["id"], []).append(parent)
            for key in ("inner", "array_filler"):
                children = node.get(key, [])
                if not isinstance(children, list):
                    raise ValueError("malformed_children")
                pending.extend((child, node) for child in children)

        def unique(identifier):
            candidates = index.get(identifier, [])
            if len(candidates) != 1:
                raise ValueError("identity_not_unique")
            return candidates[0]

        def spelling(node):
            info = node.get("type", {})
            if "typeAliasDeclId" in info and "desugaredQualType" not in info:
                raise ValueError("unresolved_type_alias")
            return info.get("desugaredQualType", info.get("qualType"))

        def plain_slots(node):
            # None of the selected scalar expressions or structural nodes has
            # an array filler. Do not ignore synthetic hidden semantic children.
            if node.get("array_filler", []) != []:
                raise ValueError("unexpected_semantic_slot")

        def unwrap(node):
            while node.get("kind") in {"ParenExpr", "ImplicitCastExpr"}:
                plain_slots(node)
                if (spelling(node) not in {"int", "const int"} or len(node.get("inner", [])) != 1 or
                        (node["kind"] == "ImplicitCastExpr" and node.get("castKind") not in {"LValueToRValue", "NoOp"})):
                    raise ValueError("unsupported_integer_wrapper")
                node = node["inner"][0]
            return node

        def reference(node):
            node = unwrap(node)
            ref = node.get("referencedDecl", {})
            if (node.get("kind") != "DeclRefExpr" or spelling(node) not in {"int", "const int"} or
                    node.get("valueCategory") != "lvalue" or node.get("inner", []) != [] or
                    node.get("array_filler", []) != [] or unique(node.get("id")) is not node):
                raise ValueError("expected_plain_integer_reference")
            decl = unique(ref.get("id"))
            if (decl.get("kind") not in {"VarDecl", "ParmVarDecl"} or decl.get("type") != ref.get("type") or
                    decl.get("kind") != ref.get("kind") or spelling(decl) not in {"int", "const int"}):
                raise ValueError("reference_declaration_mismatch")
            return decl

        loop = unique(inner_loop_id)
        body = loop["inner"][-1]
        plain_slots(loop)
        plain_slots(body)
        if body.get("kind") != "CompoundStmt" or len(body.get("inner", [])) != 2:
            raise ValueError("expected_index_declaration_then_guard")
        statement, guard = body["inner"]
        plain_slots(statement)
        plain_slots(guard)
        if statement.get("kind") != "DeclStmt" or len(statement.get("inner", [])) != 1:
            raise ValueError("index_not_single_declaration")
        label = statement["inner"][0]
        plain_slots(label)
        if (label.get("kind") != "VarDecl" or unique(label.get("id")) is not label or spelling(label) != "int" or
                label.get("storageClass") not in (None, "auto", "register") or label.get("tls") is not None or
                label.get("thread_local") is not None or len(label.get("inner", [])) != 1):
            raise ValueError("index_not_automatic_initialized_int")
        if (guard.get("kind") != "IfStmt" or
                any(guard.get(k) for k in ("hasInit", "hasVar", "isConstexpr", "isConsteval")) or
                len(guard.get("inner", [])) != (3 if guard.get("hasElse") else 2)):
            raise ValueError("unsupported_column_guard")
        condition = guard["inner"][0]
        plain_slots(condition)
        if (condition.get("kind") != "BinaryOperator" or condition.get("opcode") != "<" or
                spelling(condition) != "bool" or len(condition.get("inner", [])) != 2 or
                reference(condition["inner"][0])["id"] != label["id"]):
            raise ValueError("guard_not_label_less_than_count")
        bound = reference(condition["inner"][1])
        plain_slots(bound)
        function = unique(entry["history_check"]["selection"]["function_id"])
        if bound not in function.get("inner", []):
            parent, = parents[inner_loop_id]
            statements = parent.get("inner", []) if parent.get("kind") == "CompoundStmt" else []
            position = next(i for i, n in enumerate(statements) if n is loop)
            if (position == 0 or statements[position - 1].get("kind") != "DeclStmt" or
                    statements[position - 1].get("inner") != [bound] or
                    bound.get("storageClass") not in (None, "auto", "register") or
                    bound.get("tls") is not None or bound.get("thread_local") is not None or
                    len(bound.get("inner", [])) != 1):
                raise ValueError("count_not_parameter_or_immediate_outer_local")
        if bound["id"] in {label["id"], declaration_id}:
            raise ValueError("count_role_alias")
        fresh_calls = entry["call_effect_checks"]
        for part in (loop["inner"][0], *loop["inner"][2:]):
            _check_body(part, {bound["id"]},
                        call_callback=lambda call: fresh_calls.get(call.get("id"), {}).get("status") == "checked")

        nested, = [n["check"] for n in entry["nested_checks"] if n["loop_id"] == inner_loop_id]
        recurrence = nested["recurrence"]
        induction = recurrence["induction"]["declaration_id"]
        count = nested["iterations"]
        domain = entry["result_interval"]
        width = domain["upper"] + 1
        if (domain["lower"] != 0 or not 1 <= width <= 1024 or not 1 <= count <= 4096 or
                recurrence["start"].get("value") != 0 or
                recurrence["start"]["kind"] != "integer_literal" or recurrence["step"] != 1 or
                bound["id"] == induction):
            raise ValueError("unsupported_formal_lane_iteration_family")
        bits = integer_types["int"]["bits"]
        minimum, maximum = -(1 << (bits - 1)), (1 << (bits - 1)) - 1
        domains = {declaration_id: (0, width - 1), induction: (0, count - 1)}

        def affine(node, depth=0):
            plain_slots(node)
            if depth > 32 or spelling(node) not in {"int", "const int"}:
                raise ValueError("unsupported_index_expression")
            unique(node.get("id"))
            children = node.get("inner", [])
            if node.get("kind") in {"ParenExpr", "ImplicitCastExpr"}:
                bare = unwrap(node)
                return affine(bare, depth + 1)
            kind = node.get("kind")
            if kind == "DeclRefExpr":
                decl = reference(node)
                identifier = decl["id"]
                if identifier in domains:
                    return ({identifier: 1}, 0, domains[identifier])
                checked = constant(root, identifier, bits)
                report["constant_checks"].append(checked)
                if checked["status"] != "evaluated":
                    raise ValueError("index_read_not_source_constant")
                for source in checked["sources"]:
                    unique(source["declaration_id"])
                value = checked["value"]
                return ({}, value, (value, value))
            if kind == "IntegerLiteral" and not children:
                value = int(node["value"], 0)
                if not minimum <= value <= maximum:
                    raise ValueError("literal_outside_signed_abi")
                return ({}, value, (value, value))
            if kind != "BinaryOperator" or node.get("opcode") not in {"+", "-", "*"} or len(children) != 2:
                raise ValueError("index_expression_not_affine_subset")
            a, b = (affine(c, depth + 1) for c in children)
            op = node["opcode"]
            if op == "*":
                if a[0] and b[0]:
                    raise ValueError("nonlinear_index")
                variable, factor = (a, b) if a[0] else (b, a)
                coefficients = {k: v * factor[1] for k, v in variable[0].items()}
                offset = a[1] * b[1]
                values = [x * y for x in a[2] for y in b[2]]
                interval = min(values), max(values)
            else:
                sign = 1 if op == "+" else -1
                coefficients = {k: a[0].get(k, 0) + sign * b[0].get(k, 0) for k in a[0].keys() | b[0].keys()}
                offset = a[1] + sign * b[1]
                interval = ((a[2][0] + b[2][0], a[2][1] + b[2][1]) if sign == 1 else
                            (a[2][0] - b[2][1], a[2][1] - b[2][0]))
            if interval[0] < minimum or interval[1] > maximum:
                raise ValueError("index_intermediate_signed_overflow")
            return ({k: v for k, v in coefficients.items() if v}, offset, interval)

        coefficients, offset, interval = affine(label["inner"][0])
        if coefficients != {declaration_id: 1, induction: width} or offset != 0 or width * count > maximum:
            raise ValueError("index_not_dense_lane_iteration_layout")
        # Euclidean division gives the unique pair t=c%width, it=c//width.
        # Restricting c<n for any n in [0,width*count] preserves exact prefix coverage.
        report["assumptions"].extend([
            "formal family contains exactly one instance of every coordinate in the entry interval",
            "every formal instance executes the complete recovered inner header sequence normally",
            "for each fixed reached outer iteration (one logical row), all formal lane instances share one n with 0 <= n <= capacity",
            "all inner-loop indirect stores, including through prior or retained aliases, do not alias the selected count storage",
            "stores and external calls respect the recorded no-alias and effect premises"])
        if _hash(root) != entry["input_sha256"]["history"]["root"]:
            raise ValueError("input_changed_between_checks")
        report.update(status="checked", formal_label_coverage_checked=True,
            label_declaration_id=label["id"], guard_id=guard["id"], count_declaration_id=bound["id"],
            induction_declaration_id=induction, width=width, iterations=count, capacity=width * count,
            supported_count_domain={"lower": 0, "upper": width * count}, label_interval=list(interval),
            relation={"coordinate_coefficient": 1, "induction_coefficient": width, "offset": 0},
            count_storage_preserved="conditional_on_recorded_no_alias_and_call_effect_premises",
            input_sha256={"entry": entry["input_sha256"], "root": _hash(root),
                          "label_initializer": _hash(label["inner"][0]), "guard": _hash(condition)})
    except (ValueError, TypeError, KeyError, IndexError, AttributeError, RecursionError, StopIteration, BodyUnknown) as error:
        report["reason"] = str(error)
    return report


def check(columns, starts, stride, *, int_bits=32):
    report = {
        "schema_version": "column-coverage/v1", "status": "unknown", "reason": None,
        "checker": "residue-intervals/v1", "columns": columns, "starts": starts,
        "stride": stride, "int_bits": int_bits, "max_threads": 1024,
        "scope": "same_positive_stride_signed_integer_column_coverage",
        "source_program_checked": False, "deployable": False,
        "assumptions": ["each participating thread uses the supplied start value",
                        "all threads evaluate i < columns and update i += stride",
                        "each iteration contributes exactly once to its column"],
        "floating_point_equivalence": "not_checked",
    }
    if (type(int_bits) is not int or not 2 <= int_bits <= 128 or
            type(columns) is not int or type(stride) is not int or
            not isinstance(starts, list) or not 1 <= len(starts) <= 1024 or
            any(type(start) is not int for start in starts)):
        report["reason"] = "unsupported_input"
        return report
    maximum = (1 << (int_bits - 1)) - 1
    if not 0 <= columns <= maximum or not 1 <= stride <= maximum or any(
            not 0 <= start <= maximum for start in starts):
        report["reason"] = "unsupported_signed_domain"
        return report
    report["input_sha256"] = hashlib.sha256(json.dumps(
        {"columns": columns, "starts": starts, "stride": stride, "int_bits": int_bits},
        sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    # The last loop-body iteration is followed by an increment, even when the
    # next condition is false. Check it rather than assuming no overflow.
    for thread, start in enumerate(starts):
        if start < columns:
            last = start + ((columns - 1 - start) // stride) * stride
            if last + stride > maximum:
                report.update(reason="signed_increment_overflow",
                              counterexample={"thread": thread, "last_column": last})
                return report
    residues = {}
    for thread, start in enumerate(starts):
        if start >= columns:
            continue
        residue = start % stride
        if residue in residues:
            previous = residues[residue]
            report.update(status="rejected", reason="duplicate_column",
                          counterexample={"column": max(start, previous[1]),
                                          "threads": [previous[0], thread]})
            return report
        residues[residue] = (thread, start)
    # Every required residue must begin at the first nonnegative representative.
    # At most len(starts) keys are sorted: cost is independent of columns/stride.
    expected_residue = 0
    for residue in sorted(residues):
        if residue != expected_residue:
            report.update(status="rejected", reason="missing_column",
                          counterexample={"column": expected_residue})
            return report
        if residues[residue][1] != residue:
            report.update(status="rejected", reason="missing_column",
                          counterexample={"column": residue})
            return report
        expected_residue += 1
    if expected_residue != min(stride, columns):
        report.update(status="rejected", reason="missing_column",
                      counterexample={"column": expected_residue})
        return report
    report.update(status="checked", columns_checked=columns, threads_checked=len(starts))
    return report


def check_interval(lower, upper, starts, stride, *, int_bits=32):
    """Lift fixed-column coverage to one closed column-count interval.

    With fixed starts and stride, every thread's contributions for a smaller
    column count are a prefix of those for ``upper``.  Consequently exact
    coverage at the upper endpoint establishes exact coverage throughout the
    interval; the fixed checker also checks the post-body increment at that
    endpoint, which bounds every smaller execution.
    """
    report = {
        "schema_version": "column-coverage-interval/v1", "status": "unknown",
        "reason": None, "lower": lower, "upper": upper, "starts": starts,
        "stride": stride, "int_bits": int_bits, "upper_check": None,
        "scope": "all_column_counts_in_declared_closed_interval",
        "source_program_checked": False, "deployable": False,
        "assumptions": [
            "starts and stride are fixed for every column count in the interval",
            "each participating thread uses the supplied start value",
            "all threads evaluate i < columns and update i += stride",
            "each iteration contributes exactly once to its column",
            "signed integer behavior and the post-body increment follow the fixed-column checker",
        ],
        "method": "check_upper_endpoint_once_using_prefix_monotonicity",
    }
    if (type(lower) is not int or type(upper) is not int or
            type(int_bits) is not int or not 2 <= int_bits <= 128 or
            type(stride) is not int or not isinstance(starts, list) or
            not 1 <= len(starts) <= 1024 or any(type(start) is not int for start in starts)):
        report["reason"] = "unsupported_input"
        return report
    maximum = (1 << (int_bits - 1)) - 1
    if (not 0 <= lower <= upper <= maximum or not 1 <= stride <= maximum or
            any(not 0 <= start <= maximum for start in starts)):
        report["reason"] = "unsupported_signed_domain"
        return report
    report["input_sha256"] = hashlib.sha256(json.dumps(
        {"lower": lower, "upper": upper, "starts": starts,
         "stride": stride, "int_bits": int_bits},
        sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    upper_check = check(upper, starts, stride, int_bits=int_bits)
    report["upper_check"] = upper_check
    report["status"] = upper_check.get("status", "unknown")
    report["reason"] = upper_check.get("reason")
    if report["status"] == "checked":
        iterations = [max(0, (upper - 1 - start) // stride + 1) for start in starts]
        report["interval_checked"] = {"lower": lower, "upper": upper}
        report["threads_checked"] = upper_check.get("threads_checked")
        report["max_iterations_per_thread"] = iterations
        report["max_iterations"] = max(iterations)
    elif report["status"] == "rejected":
        report["counterexample"] = {
            "columns": upper, "upper_counterexample": upper_check.get("counterexample")}
    return report


def check_unsigned_compound_interval(lower, upper, block_threads, *,
                                     int_bits=32, unsigned_bits=32):
    """Conditionally check ``int i`` advanced by unsigned ``i += blockDim.x``.

    The caller supplies the already-bound model: starts are exactly
    ``0..block_threads-1``, the positive step and block dimension are both
    ``block_threads``, and Clang selected unsigned computation followed by an
    assignment to signed int.  This function checks that the resulting machine
    operations preserve the corresponding mathematical recurrence.  It does
    not recover those facts from source.
    """
    report = {
        "schema_version": "unsigned-compound-column-coverage/v1",
        "status": "unknown", "reason": None,
        "lower": lower, "upper": upper, "block_threads": block_threads,
        "int_bits": int_bits, "unsigned_bits": unsigned_bits,
        "starts": None, "stride": block_threads,
        "conversion_checks": [], "coverage": None,
        "scope": "conditional_column_coverage_for_unsigned_compound_assignment_model",
        "source_program_checked": False, "deployable": False,
        "assumptions": [
            "the signed int and unsigned int widths supplied here match the compilation ABI",
            "the start values are exactly local IDs 0 through block_threads minus one",
            "the positive step and runtime block x dimension both equal block_threads",
            "the loop condition is signed int induction less than the supplied signed column count",
            "the compound assignment computes in unsigned int and assigns its result back to signed int",
            "the loop body does not modify induction, column bound, or the fixed coordinate and dimension values",
            "every reached loop body and increment completes normally",
        ],
        "limitations": [
            "does not recover coordinate, launch, ABI or compute-type facts from source",
            "does not establish source equivalence, reachability, body effects or deployment safety",
            "unknown overflow evidence is not asserted to be a reachable runtime counterexample",
        ],
    }
    if (any(type(value) is not int for value in
            (lower, upper, block_threads, int_bits, unsigned_bits)) or
            not 2 <= int_bits <= 128 or not 2 <= unsigned_bits <= 128 or
            int_bits != unsigned_bits or not 1 <= block_threads <= 1024):
        report["reason"] = "unsupported_input_or_integer_abi"
        return report
    signed_maximum = (1 << (int_bits - 1)) - 1
    if not 0 <= lower <= upper <= signed_maximum:
        report["reason"] = "column_interval_not_signed_int_domain"
        return report
    starts = list(range(block_threads))
    report["starts"] = starts
    inputs = {"lower": lower, "upper": upper, "block_threads": block_threads,
              "int_bits": int_bits, "unsigned_bits": unsigned_bits}
    report["input_sha256"] = hashlib.sha256(json.dumps(
        inputs, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def conversion(stage, low, high, source_signed, target_signed):
        evidence = {"stage": stage, "value_interval": {"lower": low, "upper": high},
                    "conversion": check_conversion(low, high, int_bits, source_signed,
                                                   unsigned_bits, target_signed)}
        report["conversion_checks"].append(evidence)
        return evidence["conversion"].get("status") == "checked"

    if not conversion("initial_unsigned_local_id_to_signed_int", 0, block_threads - 1,
                      False, True):
        report["reason"] = "initial_conversion_not_value_preserving"
        return report
    if not conversion("unsigned_step_representability", block_threads, block_threads,
                      False, False):
        report["reason"] = "step_not_representable_in_unsigned_int"
        return report

    if upper > 0:
        # With starts covering every residue 0..B-1, body induction values over
        # all C <= upper are contained in [0, upper-1].  Every executed body is
        # followed by an increment, including the final one after its body.
        if not conversion("signed_induction_to_unsigned_compute_lhs", 0, upper - 1,
                          True, False):
            report["reason"] = "compute_lhs_conversion_not_value_preserving"
            return report
        post_lower, post_upper = block_threads, upper - 1 + block_threads
        # check_interval here checks representability of the mathematical sum;
        # it does not itself model or execute unsigned addition.
        if not conversion("mathematical_unsigned_sum_no_wrap", post_lower, post_upper,
                          False, False):
            report["reason"] = "unsigned_increment_may_wrap"
            return report
        if not conversion("unsigned_compound_result_to_signed_int", post_lower, post_upper,
                          False, True):
            report["reason"] = "final_assignment_not_value_preserving"
            return report

    if upper == 0:
        coverage = {
            "schema_version": "column-coverage-interval/v1",
            "status": "checked", "reason": None,
            "interval_checked": {"lower": 0, "upper": 0},
            "max_iterations_per_thread": [0] * block_threads,
            "max_iterations": 0,
            "method": "zero_column_interval_is_vacuous_after_initialization",
            "source_program_checked": False, "deployable": False,
        }
    else:
        coverage = check_interval(lower, upper, starts, block_threads, int_bits=int_bits)
    report["coverage"] = coverage
    if coverage.get("status") != "checked":
        report["reason"] = "conditional_mathematical_coverage_not_checked"
        return report
    report.update(
        status="checked", reason=None,
        interval_checked={"lower": lower, "upper": upper},
        max_iterations_per_thread=coverage["max_iterations_per_thread"],
        max_iterations=coverage["max_iterations"],
        conclusion="mathematical_recurrence_is_preserved_under_supplied_compound_assignment_model",
    )
    return report
