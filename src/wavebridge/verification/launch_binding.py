"""Bind one kernel/launch pair and its configuration slots, never their values."""

from wavebridge.analysis.launch_facts import inspect
from wavebridge.verification.getter_returns import _hash


def _direct_callee(node, declaration):
    """Narrow ordinary function-to-pointer chain; no type-name heuristics."""
    signature = declaration.get("type")
    if not isinstance(signature, dict) or not isinstance(signature.get("qualType"), str):
        return False
    spelling = signature["qualType"]
    if " (" not in spelling or "(*" in spelling or declaration.get("variadic"):
        return False
    pointer = {"qualType": spelling.replace(" (", " (*)(", 1)}
    while node.get("kind") in {"ParenExpr", "ImplicitCastExpr"}:
        children = node.get("inner", [])
        if len(children) != 1:
            return False
        child = children[0]
        if node["kind"] == "ImplicitCastExpr":
            cast = node.get("castKind")
            if cast == "FunctionToPointerDecay":
                if node.get("type") != pointer or child.get("type") != signature:
                    return False
            elif cast != "NoOp" or node.get("type") != child.get("type"):
                return False
        elif node.get("type") != child.get("type"):
            return False
        node = child
    reference = node.get("referencedDecl", {})
    return (node.get("kind") == "DeclRefExpr" and not node.get("inner") and
            node.get("type") == signature and reference.get("type") == signature and
            reference.get("kind") == "FunctionDecl" and reference.get("id") == declaration.get("id"))


def check(root, selection, *, max_ast_nodes=1_000_000):
    result = {
        "schema_version": "kernel-launch-binding/v1", "status": "unknown", "reason": None,
        "scope": "exact_syntactic_kernel_launch_and_positional_arguments_in_one_AST",
        "source_program_checked": False, "deployable": False,
        "configuration_values": "not_established", "source_object_preservation": "not_established",
        "host_reachability": "not_established", "launch_API_semantics": "not_established",
        "assumptions": ["faithful well-formed single-TU Clang AST"],
        "configuration_slots": [], "parameter_bindings": [],
    }

    def unknown(reason):
        result["reason"] = reason
        return result

    if (not isinstance(root, dict) or root.get("kind") != "TranslationUnitDecl" or
            not isinstance(selection, dict)):
        return unknown("complete_translation_unit_and_selection_required")
    if type(max_ast_nodes) is not int or not 1 <= max_ast_nodes <= 10_000_000:
        return unknown("invalid_ast_node_budget")
    if selection.get("schema_version") != "launch-selection/v1":
        return unknown("unsupported_selection_schema")
    kernel, launch = selection.get("kernel_declaration_id"), selection.get("launch_id")
    configuration = selection.get("configuration_declaration_id")
    slots = selection.get("configuration_expression_ids")
    if (any(not isinstance(v, str) or not v for v in (kernel, launch, configuration)) or
            not isinstance(slots, list) or len(slots) != 4 or
            any(not isinstance(v, str) or not v for v in slots) or len(set(slots)) != 4):
        return unknown("invalid_selected_ids")
    # Check the input tree before handing it to recursive recovery. This is not
    # a completeness proof: the faithful complete TU remains a frontend premise.
    nodes, pending = [], [root]
    while pending:
        node = pending.pop()
        if not isinstance(node, dict):
            return unknown("malformed_AST_node")
        nodes.append(node)
        if len(nodes) > max_ast_nodes:
            return unknown("ast_node_budget_exceeded")
        children = node.get("inner", [])
        if not isinstance(children, list):
            return unknown("malformed_AST_children")
        pending.extend(children)
    try:
        root_hash = _hash(root)
        result["input_sha256"] = {"root": root_hash, "selection": _hash(selection)}
        if selection.get("ast_root_sha256") != root_hash:
            return unknown("selection_root_mismatch")
        facts = inspect(root, kernel)
    except (TypeError, ValueError, RecursionError):
        return unknown("unsupported_AST_or_hash")
    result["launch_discovery"] = {
        "scope": "all_syntactic_launch_occurrences_in_supplied_TU",
        "unresolved_sites": facts["unresolved_sites"],
        "normalization": facts["normalization"],
        "complete_launch_resolution": "not_established" if facts["unresolved_sites"] else "all_observed_sites_resolved",
    }
    # Binding one exact site does not require resolving every dependent launch
    # in this TU. Identity conflicts remain global errors; missing identities
    # cannot be silently classified as a distinct, unselected site.
    if facts["normalization"]["conflicts"]:
        return unknown("conflicting_launch_id_occurrences")
    if any(not isinstance(node.get("id"), str) or not node["id"]
           for node in nodes if node.get("kind") == "CUDAKernelCallExpr"):
        return unknown("launch_occurrence_identity_missing")
    matches = [site for site in facts["sites"] if site.get("launch_id") == launch]
    if len(matches) != 1:
        return unknown("selected_launch_not_uniquely_bound_to_kernel")
    site = matches[0]
    if site["parameter_binding_status"] != "bound_by_position":
        return unknown(site["parameter_binding_reason"])
    definitions = [node for node in nodes if node.get("kind") == "FunctionDecl" and
                   node.get("id") == kernel and
                   any(child.get("kind") == "CompoundStmt" for child in node.get("inner", []))]
    if len(definitions) != 1:
        return unknown("unique_kernel_definition_required")
    definition = definitions[0]
    if not any(child.get("kind") == "CUDAGlobalAttr" for child in definition.get("inner", [])):
        return unknown("kernel_global_attribute_missing")
    if definition.get("variadic"):
        return unknown("variadic_kernel_unsupported")
    declarations = [node for node in nodes if node.get("id") == configuration]
    if (not declarations or any(node != declarations[0] for node in declarations) or
            declarations[0].get("kind") != "FunctionDecl" or
            len([n for n in declarations[0].get("inner", []) if n.get("kind") == "ParmVarDecl"]) != 4):
        return unknown("configuration_declaration_not_unique_four_parameter_function")
    if (site["configuration_declaration_id"] != configuration or
            not _direct_callee(site["kernel_callee_ast"], definition) or
            not _direct_callee(site["configuration_ast"]["inner"][0], declarations[0])):
        return unknown("callee_declaration_or_type_mismatch")
    parameters = [row["parameter_declaration_id"] for row in site["parameter_bindings"]]
    if any(not value for value in parameters) or len(set(parameters)) != len(parameters):
        return unknown("kernel_parameter_ids_not_unique")
    if any(not isinstance(arg.get("id"), str) or not arg["id"] or not arg.get("kind")
           for arg in site["kernel_arguments"]):
        return unknown("kernel_argument_identity_missing")
    arguments = site["configuration_arguments"]
    if [arg.get("id") for arg in arguments] != slots:
        return unknown("configuration_expression_position_mismatch")
    # Check selected identities across the whole TU, not just the recovered
    # launch subtree. Embedded referencedDecl summaries are not AST occurrences.
    selected = [(kernel, definition),
                *[(node["id"], node) for node in definition["inner"] if node.get("kind") == "ParmVarDecl"],
                (launch, next(node for node in nodes if node.get("kind") == "CUDAKernelCallExpr"
                              and node.get("id") == launch)), *zip(slots, arguments),
                *[(arg["id"], arg) for arg in site["kernel_arguments"]]]
    for identifier, expected in selected:
        if any(node != expected for node in nodes if node.get("id") == identifier):
            return unknown("selected_expression_id_conflict")
    result.update(
        status="checked", kernel_declaration_id=kernel, launch_id=launch,
        kernel_definition_sha256=_hash(definition),
        configuration_declaration_id=site["configuration_declaration_id"],
        configuration_declaration_sha256=_hash(declarations[0]),
        configuration_declaration_occurrences=len(declarations),
        identity_normalization="only_full_node_identical_occurrences_with_same_id",
        launch_ast_occurrences=site["ast_occurrences"],
        configuration_slots=[{"position": position, "expression_id": arg["id"],
                              "expression_sha256": _hash(arg), "expression_ast": arg}
                             for position, arg in enumerate(arguments)],
        parameter_bindings=site["parameter_bindings"],
    )
    return result
