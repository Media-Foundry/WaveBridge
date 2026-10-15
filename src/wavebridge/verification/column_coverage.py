"""Exact coverage of same-stride arithmetic progressions, without column expansion."""

import hashlib
import json

from wavebridge.verification.integer_conversion import check_interval as check_conversion


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
