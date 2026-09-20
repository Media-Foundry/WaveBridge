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
    }
    if not isinstance(root, dict) or not isinstance(kernel_id, str):
        report["reason"] = "invalid_input"
        return report
    definitions = [node for node in _walk(root) if node.get("kind") == "FunctionDecl" and
                   node.get("id") == kernel_id and isinstance(node.get("inner"), list) and
                   any(isinstance(child, dict) and child.get("kind") == "CompoundStmt"
                       for child in node["inner"])]
    parameters = ([child for child in definitions[0]["inner"] if isinstance(child, dict) and
                   child.get("kind") == "ParmVarDecl"] if len(definitions) == 1 else None)
    for node in _walk(root):
        if node.get("kind") != "CUDAKernelCallExpr":
            continue
        children = node.get("inner", [])
        if not isinstance(children, list) or len(children) < 2 or not all(isinstance(child, dict) for child in children):
            report["unresolved_sites"].append({"reason": "unsupported_launch_layout", "range": node.get("range")})
            continue
        target = _target(children[0])
        if target is None:
            report["unresolved_sites"].append({"reason": "kernel_not_exact_declref", "range": node.get("range")})
            continue
        if target != kernel_id:
            report["other_kernel_sites"] += 1
            continue
        configuration = children[1]
        config_children = configuration.get("inner", [])
        configuration_target = (_target(config_children[0]) if isinstance(config_children, list) and config_children and
                                isinstance(config_children[0], dict) else None)
        if (configuration.get("kind") != "CallExpr" or not isinstance(config_children, list) or len(config_children) != 5 or
                not all(isinstance(child, dict) for child in config_children) or
                configuration_target is None):
            report["unresolved_sites"].append({"reason": "unsupported_configuration_call",
                                               "range": node.get("range")})
            continue
        site = {
            "launch_id": node.get("id"), "range": node.get("range"),
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
