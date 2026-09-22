"""Retain syntactic launch sites without interpreting their configuration values."""


def _walk(node):
    yield node
    children = node.get("inner", [])
    if not isinstance(children, list):
        return
    for child in children:
        if isinstance(child, dict):
            yield from _walk(child)


def _target(node):
    current = node
    while current.get("kind") in {"ParenExpr", "ImplicitCastExpr"}:
        children = current.get("inner", [])
        if not isinstance(children, list) or len(children) != 1 or not isinstance(children[0], dict):
            return None
        if current.get("kind") == "ImplicitCastExpr" and current.get("castKind") not in {
                "NoOp", "FunctionToPointerDecay"}:
            return None
        current = children[0]
    declaration = current.get("referencedDecl", {})
    if (current.get("kind") == "DeclRefExpr" and isinstance(declaration, dict) and
            declaration.get("kind") == "FunctionDecl" and isinstance(declaration.get("id"), str)):
        return declaration["id"]
    return None


def inspect(root, kernel_id):
    report = {
        "schema_version": "launch-facts/v1", "status": "unknown", "reason": None,
        "kernel_declaration_id": kernel_id, "sites": [], "unresolved_sites": [],
        "other_kernel_sites": 0, "scope": "syntactic_launch_sites_in_one_ast_root",
        "configuration_semantics": "not_established", "host_reachability": "not_checked",
        "checked": False, "deployable": False,
        "normalization": {
            "scope": "CUDAKernelCallExpr_occurrences_within_one_supplied_AST_root",
            "rule": "collapse_only_full-node-identical_occurrences_with_the_same_nonempty_string_id",
            "missing_id_policy": "retain_each_occurrence_without_merging",
            "different_id_policy": "never_merge_even_when_other_content_matches",
            "raw_occurrences": 0, "normalized_occurrences": 0,
            "identical_duplicate_groups": [], "conflicts": [],
        },
    }
    if not isinstance(root, dict) or not isinstance(kernel_id, str):
        report["reason"] = "invalid_input"
        return report
    launch_occurrences = [node for node in _walk(root)
                          if node.get("kind") == "CUDAKernelCallExpr"]
    report["normalization"]["raw_occurrences"] = len(launch_occurrences)
    by_id = {}
    without_id = []
    for node in launch_occurrences:
        identifier = node.get("id")
        if isinstance(identifier, str) and identifier:
            by_id.setdefault(identifier, []).append(node)
        else:
            without_id.append((node, 1))
    normalized = []
    for identifier, occurrences in by_id.items():
        first = occurrences[0]
        if any(node != first for node in occurrences[1:]):
            conflict = {"reason": "conflicting_launch_occurrences_for_same_id",
                        "launch_id": identifier, "ast_occurrences": len(occurrences),
                        "ranges": [node.get("range") for node in occurrences]}
            report["normalization"]["conflicts"].append(conflict)
            report["unresolved_sites"].append(conflict)
        else:
            normalized.append((first, len(occurrences)))
            if len(occurrences) > 1:
                report["normalization"]["identical_duplicate_groups"].append({
                    "launch_id": identifier, "ast_occurrences": len(occurrences)})
    normalized.extend(without_id)
    report["normalization"]["normalized_occurrences"] = len(normalized)
    if report["normalization"]["conflicts"]:
        report["reason"] = "conflicting_launch_id_occurrences"
        return report

    definitions = [node for node in _walk(root) if node.get("kind") == "FunctionDecl" and
                   node.get("id") == kernel_id and isinstance(node.get("inner"), list) and
                   any(isinstance(child, dict) and child.get("kind") == "CompoundStmt"
                       for child in node["inner"])]
    parameters = ([child for child in definitions[0]["inner"] if isinstance(child, dict) and
                   child.get("kind") == "ParmVarDecl"] if len(definitions) == 1 else None)
    for node, ast_occurrences in normalized:
        children = node.get("inner", [])
        if not isinstance(children, list) or len(children) < 2 or not all(isinstance(child, dict) for child in children):
            report["unresolved_sites"].append({"reason": "unsupported_launch_layout",
                                               "range": node.get("range"),
                                               "ast_occurrences": ast_occurrences})
            continue
        target = _target(children[0])
        if target is None:
            report["unresolved_sites"].append({"reason": "kernel_not_exact_declref",
                                               "range": node.get("range"),
                                               "ast_occurrences": ast_occurrences})
            continue
        if target != kernel_id:
            report["other_kernel_sites"] += ast_occurrences
            continue
        configuration = children[1]
        config_children = configuration.get("inner", [])
        configuration_target = (_target(config_children[0]) if isinstance(config_children, list) and config_children and
                                isinstance(config_children[0], dict) else None)
        if (configuration.get("kind") != "CallExpr" or not isinstance(config_children, list) or len(config_children) != 5 or
                not all(isinstance(child, dict) for child in config_children) or
                configuration_target is None):
            report["unresolved_sites"].append({"reason": "unsupported_configuration_call",
                                               "range": node.get("range"),
                                               "ast_occurrences": ast_occurrences})
            continue
        site = {
            "launch_id": node.get("id"), "range": node.get("range"),
            "ast_occurrences": ast_occurrences,
            "kernel_declaration_id": target, "kernel_callee_ast": children[0],
            "configuration_declaration_id": configuration_target,
            "configuration_ast": configuration,
            "configuration_arguments": config_children[1:],
            "kernel_arguments": children[2:],
            "argument_values": "not_evaluated",
            "parameter_binding_status": "unknown", "parameter_binding_reason": None,
            "parameter_bindings": [],
        }
        if parameters is None:
            site["parameter_binding_reason"] = "unique_kernel_definition_not_found"
        elif len(parameters) != len(children) - 2:
            site["parameter_binding_reason"] = "kernel_argument_count_mismatch"
        elif any(not isinstance(parameter.get("id"), str) for parameter in parameters):
            site["parameter_binding_reason"] = "parameter_id_missing"
        else:
            site["parameter_binding_status"] = "bound_by_position"
            site["parameter_bindings"] = [
                {"position": index, "parameter_declaration_id": parameter["id"],
                 "parameter_type": parameter.get("type"), "parameter_range": parameter.get("range"),
                 "argument_ast": argument, "argument_value_semantics": "not_established"}
                for index, (parameter, argument) in enumerate(zip(parameters, children[2:]))]
        report["sites"].append(site)
    report["status"] = "evidence" if report["sites"] else "unknown"
    if not report["sites"]:
        report["reason"] = "no_supported_matching_launch"
    return report
