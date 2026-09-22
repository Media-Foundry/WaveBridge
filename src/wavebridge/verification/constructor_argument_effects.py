"""Check effects of a narrow set of direct constructor arguments."""

from __future__ import annotations

from typing import Any

from wavebridge.constructor_source_check import check as check_constructor_source
from wavebridge.verification.integer_selection import _hash
from wavebridge.verification.kernel_arguments import _Unknown


MAX_AST_NODES = 1_000_000
HARD_MAX_AST_NODES = 10_000_000
ALLOWED_CALLEE_ATTRIBUTES = {
    "CUDAHostAttr", "CUDADeviceAttr", "ConstAttr", "PureAttr",
    "AlwaysInlineAttr", "NoInlineAttr", "EnableIfAttr",
}


def _children(node: object, *, strict: bool = False) -> list[dict[str, Any]]:
    if not isinstance(node, dict):
        raise _Unknown("ast_node_not_object")
    children = node.get("inner", [])
    if not isinstance(children, list) or any(not isinstance(child, dict) for child in children):
        raise _Unknown("ast_children_not_list_of_objects")
    if strict and any(not child for child in children):
        raise _Unknown("selected_ast_contains_empty_placeholder")
    return [child for child in children if child]


def _raw_type(node: object) -> str:
    if not isinstance(node, dict) or not isinstance(node.get("type"), dict):
        raise _Unknown("type_evidence_missing")
    info = node["type"]
    value = info.get("desugaredQualType") or info.get("qualType")
    if not isinstance(value, str) or not value:
        raise _Unknown("type_evidence_missing")
    return value


def _template_marker(node: dict[str, Any]) -> bool:
    if (any(key in node for key in (
            "templateArgs", "templateKind", "specializationKind", "instantiatedFrom",
            "instantiatedFromMemberFunction", "describedFunctionTemplate")) or
            node.get("isDependent") is True or node.get("isInstantiationDependent") is True):
        return True
    children = node.get("inner", [])
    return isinstance(children, list) and any(
        isinstance(child, dict) and child.get("kind") in {
            "TemplateArgument", "TemplateTypeParmDecl", "NonTypeTemplateParmDecl",
            "TemplateTemplateParmDecl",
        } for child in children)


def _declrefs_have_no_children(node: dict[str, Any]) -> None:
    pending = [node]
    while pending:
        current = pending.pop()
        children = _children(current, strict=True)
        if current.get("kind") == "DeclRefExpr" and children:
            raise _Unknown("selected_declref_contains_hidden_children")
        pending.extend(children)


def check(root: object, constructor_expression_id: object, integer_types: object,
          selection_domains: object, *, max_ast_nodes: int | None = None) -> dict[str, Any]:
    budget = MAX_AST_NODES if max_ast_nodes is None else max_ast_nodes
    result: dict[str, Any] = {
        "schema_version": "constructor-argument-effects-check/v1",
        "status": "unknown", "reason": None,
        "constructor_expression_id": constructor_expression_id,
        "constructor_source": None, "argument_effects": [],
        "scope": "selected_direct_constructor_argument_evaluations_only",
        "external_storage_writes": "not_established",
        "address_escape_beyond_the_call": "not_established",
        "permitted_internal_operations": [],
        "source_program_checked": False, "deployable": False,
        "constructor_member_initializers_and_body": "excluded_from_this_conclusion",
        "destination_declaration_allocation_and_lifetime": "excluded",
        "outer_cleanup_exception_unwinding_and_destructor": "excluded",
        "post_construction_escape": "not_established",
        "prior_operand_initialization_history": "excluded",
        "invocation_history_and_launch_semantics": "not_established",
        "assumptions": [
            "the AST is a faithful complete valid single translation unit",
            "the explicit integer ABI matches the compilation target",
            "the supported operand declarations denote initialized objects visible at this use",
            "the exact minimum calls and selected constructor return normally",
            "earlier automatic-variable initialization effects are outside this evaluation scope",
        ],
        "budget": {"max_ast_nodes_per_fresh_scan": budget,
                   "note": "the limit is not a total execution-time budget"},
    }
    if type(budget) is not int or not 1 <= budget <= HARD_MAX_AST_NODES:
        result["reason"] = "invalid_ast_node_budget"
        return result
    if (not isinstance(root, dict) or
            not isinstance(constructor_expression_id, str) or
            not constructor_expression_id or not isinstance(integer_types, dict) or
            not isinstance(selection_domains, dict)):
        result["reason"] = "invalid_inputs"
        return result

    source = check_constructor_source(
        root, constructor_expression_id, integer_types, selection_domains,
        max_ast_nodes=budget)
    result["constructor_source"] = source
    root_hash = (source.get("input_sha256") or {}).get("root")
    try:
        result["input_sha256"] = {
            "root": root_hash,
            "constructor_expression_id": _hash(constructor_expression_id),
            "integer_types": _hash(integer_types),
            "selection_domains": _hash(selection_domains),
        }
    except (TypeError, ValueError, RecursionError):
        result["reason"] = "input_hash_unsupported"
        return result
    if source.get("status") != "checked" or not isinstance(root_hash, str):
        result["reason"] = "fresh_constructor_source_check_not_checked"
        return result

    try:
        nodes: list[dict[str, Any]] = []
        index: dict[str, list[dict[str, Any]]] = {}
        pending = [root]
        while pending:
            node = pending.pop()
            if not isinstance(node, dict):
                raise _Unknown("ast_node_not_object")
            nodes.append(node)
            if len(nodes) > budget:
                raise _Unknown("ast_node_budget_exceeded")
            node_id = node.get("id")
            if isinstance(node_id, str) and node_id:
                index.setdefault(node_id, []).append(node)
            pending.extend(_children(node))

        expression_matches = index.get(constructor_expression_id, [])
        if len(expression_matches) != 1 or expression_matches[0].get("kind") != "CXXConstructExpr":
            raise _Unknown("constructor_expression_not_unique_direct_construct")
        expression = expression_matches[0]

        domain_ids: set[str] = set()
        for value in selection_domains.values():
            if not isinstance(value, list):
                raise _Unknown("selection_domains_shape_unsupported")
            for item in value:
                identifier = item.get("declaration_id") if isinstance(item, dict) else None
                if not isinstance(identifier, str) or not identifier:
                    raise _Unknown("selection_operand_declaration_id_invalid")
                domain_ids.add(identifier)

        wanted = domain_ids | {constructor_expression_id}
        locations: dict[str, list[dict[str, Any]]] = {identifier: [] for identifier in wanted}
        path_nodes = 0

        def walk(node: dict[str, Any], function: dict[str, Any] | None,
                 lambda_depth: int, template_depth: int,
                 compounds: tuple[str, ...], parents: tuple[tuple[str, str | None], ...],
                 destination_vars: tuple[str, ...]) -> None:
            nonlocal path_nodes
            path_nodes += 1
            if path_nodes > budget:
                raise _Unknown("scope_path_node_budget_exceeded")
            kind = node.get("kind")
            here_template = template_depth + int(str(kind).endswith("TemplateDecl"))
            here_function = function
            if kind in {"FunctionDecl", "CXXMethodDecl", "CXXConstructorDecl",
                        "CXXDestructorDecl"}:
                here_function = node
            here_lambda = lambda_depth + int(kind == "LambdaExpr")
            here_compounds = compounds
            if kind == "CompoundStmt":
                compound_id = node.get("id")
                if not isinstance(compound_id, str) or not compound_id:
                    raise _Unknown("compound_scope_id_missing")
                here_compounds = compounds + (compound_id,)
            here_destinations = destination_vars
            if kind == "VarDecl" and isinstance(node.get("id"), str):
                here_destinations = destination_vars + (node["id"],)
            node_id = node.get("id")
            if node_id in locations:
                locations[node_id].append({
                    "node": node, "function": here_function,
                    "lambda_depth": here_lambda, "template_depth": here_template,
                    "compounds": here_compounds, "parents": parents,
                    "destination_vars": destination_vars,
                })
            next_parents = parents + ((str(kind), node_id if isinstance(node_id, str) else None),)
            for child in _children(node):
                walk(child, here_function, here_lambda, here_template,
                     here_compounds, next_parents, here_destinations)

        walk(root, None, 0, 0, (), (), ())
        target_locations = locations[constructor_expression_id]
        if len(target_locations) != 1:
            raise _Unknown("constructor_expression_scope_path_not_unique")
        target_location = target_locations[0]
        caller = target_location["function"]
        if (not isinstance(caller, dict) or caller.get("kind") != "FunctionDecl" or
                target_location["lambda_depth"] != 0 or
                target_location["template_depth"] != 0 or _template_marker(caller)):
            raise _Unknown("constructor_call_not_in_ordinary_nontemplate_function")
        if not target_location["compounds"]:
            raise _Unknown("constructor_call_not_in_function_compound_body")
        caller_id = caller.get("id")
        if not isinstance(caller_id, str) or not caller_id:
            raise _Unknown("constructor_caller_id_missing")

        destination_ids = set(target_location["destination_vars"])
        operand_records: dict[str, dict[str, Any]] = {}
        for identifier in domain_ids:
            operand_locations = locations[identifier]
            if len(operand_locations) != 1:
                raise _Unknown("selection_operand_declaration_scope_not_unique")
            location = operand_locations[0]
            declaration = location["node"]
            kind = declaration.get("kind")
            raw = _raw_type(declaration)
            if (kind not in {"VarDecl", "ParmVarDecl"} or
                    "volatile" in raw.split() or "&" in raw or "*" in raw or
                    identifier in destination_ids or location["lambda_depth"] != 0 or
                    location["template_depth"] != 0 or
                    not isinstance(location["function"], dict) or
                    location["function"].get("id") != caller_id or
                    declaration.get("isInitCapture") is True or
                    declaration.get("initCapture") is True):
                raise _Unknown("selection_operand_not_plain_same_function_object")
            if (declaration.get("storageClass") not in {None, "auto", "register"} or
                    declaration.get("tls") not in (None, "none") or
                    declaration.get("tlsKind") not in (None, "none")):
                raise _Unknown("selection_operand_storage_duration_unsupported")
            declaration_children = _children(declaration, strict=True)
            if any(str(child.get("kind", "")).endswith("Attr")
                   for child in declaration_children):
                raise _Unknown("selection_operand_attribute_unsupported")
            parents = location["parents"]
            if kind == "ParmVarDecl":
                if not parents or parents[-1] != ("FunctionDecl", caller_id):
                    raise _Unknown("selection_operand_parameter_not_direct_caller_parameter")
            else:
                if (len(parents) < 2 or parents[-1][0] != "DeclStmt" or
                        parents[-2][0] != "CompoundStmt" or
                        not location["compounds"] or
                        location["compounds"][-1] != parents[-2][1] or
                        tuple(target_location["compounds"][:len(location["compounds"])]) !=
                        location["compounds"]):
                    raise _Unknown("selection_operand_local_scope_not_supported_at_call")
            operand_records[identifier] = {
                "declaration_id": identifier, "declaration_kind": kind,
                "type": declaration.get("type"),
                "storage": "caller_parameter" if kind == "ParmVarDecl" else "automatic_local",
                "prior_initializer_effects": "excluded" if kind == "VarDecl" else "not_applicable",
            }

        selection_items = source.get("selection_checks")
        arguments_report = (source.get("constructor_arguments") or {}).get("arguments")
        if not isinstance(selection_items, list) or not isinstance(arguments_report, list):
            raise _Unknown("fresh_argument_reports_missing")
        selections_by_position: dict[int, dict[str, Any]] = {}
        checked_arguments: list[dict[str, Any]] = []
        for item in selection_items:
            if (not isinstance(item, dict) or type(item.get("position")) is not int or
                    not isinstance(item.get("report"), dict)):
                raise _Unknown("fresh_selection_report_shape_invalid")
            position, report = item["position"], item["report"]
            if position in selections_by_position or report.get("status") != "checked":
                raise _Unknown("fresh_selection_report_not_unique_checked")
            selections_by_position[position] = report

            argument_id = report.get("expression_id")
            argument_matches = index.get(argument_id, [])
            if len(argument_matches) != 1:
                raise _Unknown("selection_argument_expression_not_unique")
            argument_expression = argument_matches[0]
            _declrefs_have_no_children(argument_expression)

            callee_id = report.get("callee_declaration_id")
            callee_matches = [node for node in index.get(callee_id, [])
                              if node.get("kind") == "FunctionDecl"]
            if len(callee_matches) != 1:
                raise _Unknown("selection_effect_callee_not_unique")
            callee = callee_matches[0]
            callee_children = _children(callee, strict=True)
            attributes = [child for child in callee_children
                          if str(child.get("kind", "")).endswith("Attr")]
            if any(attribute.get("kind") not in ALLOWED_CALLEE_ATTRIBUTES
                   for attribute in attributes):
                raise _Unknown("selection_effect_callee_attribute_unsupported")
            for attribute in attributes:
                if attribute.get("kind") != "EnableIfAttr":
                    if _children(attribute, strict=True):
                        raise _Unknown("selection_effect_callee_attribute_payload_unsupported")
                    continue
                # Clang specifies enable_if's condition as unevaluated.  Keep
                # the accepted evidence narrower still: the exact condition
                # emitted for the real header is a childless literal true.
                attribute_children = _children(attribute, strict=True)
                if (len(attribute_children) != 1 or
                        attribute_children[0].get("kind") != "CXXBoolLiteralExpr" or
                        attribute_children[0].get("value") is not True or
                        attribute_children[0].get("valueCategory") != "prvalue" or
                        attribute_children[0].get("type") != {"qualType": "bool"} or
                        _children(attribute_children[0], strict=True)):
                    raise _Unknown("selection_effect_enable_if_attribute_unsupported")
            parameters = [child for child in callee_children
                          if child.get("kind") == "ParmVarDecl"]
            if len(parameters) != 2:
                raise _Unknown("selection_effect_callee_parameters_missing")
            for parameter in parameters:
                parameter_children = _children(parameter, strict=True)
                if any(str(child.get("kind", "")).endswith("Attr")
                       for child in parameter_children):
                    raise _Unknown("selection_effect_parameter_attribute_unsupported")
            _declrefs_have_no_children(callee)

            domain = selection_domains.get(argument_id)
            if not isinstance(domain, list) or any(not isinstance(entry, dict) for entry in domain):
                raise _Unknown("selection_effect_domain_binding_invalid")
            bound_ids = [entry.get("declaration_id") for entry in domain]
            if (len(bound_ids) != len(set(bound_ids)) or
                    any(identifier not in operand_records for identifier in bound_ids)):
                raise _Unknown("selection_effect_operand_not_validated")
            checked_arguments.append({
                "position": position, "argument_expression_id": argument_id,
                "kind": "exact_two_operand_integer_minimum",
                "callee_declaration_id": callee_id,
                "operand_declarations": [operand_records[identifier]
                                         for identifier in bound_ids],
                "effects": "no_external_storage_write_or_address_escape_beyond_call",
                "internal_reference_binding": "permitted",
            })

        positions = {item.get("position") for item in arguments_report
                     if isinstance(item, dict)}
        if positions != set(range(len(arguments_report))):
            raise _Unknown("constructor_argument_positions_not_exact")
        for argument in arguments_report:
            position = argument["position"]
            if position in selections_by_position:
                continue
            argument_ast = argument.get("argument_ast")
            if not isinstance(argument_ast, dict) or not isinstance(argument_ast.get("id"), str):
                raise _Unknown("literal_argument_ast_id_missing")
            checked_arguments.append({
                "position": position, "argument_expression_id": argument_ast["id"],
                "kind": "builtin_integer_literal_or_default_literal",
                "effects": "only_builtin_value_computation_and_optional_scalar_temporary_materialization",
                "temporary_storage_write": "permitted_if_materialized",
                "address_escape_beyond_call": "not_observed",
            })
        checked_arguments.sort(key=lambda item: item["position"])
        if len(checked_arguments) != len(arguments_report):
            raise _Unknown("constructor_arguments_not_exactly_effect_checked")

        result.update(
            status="checked", argument_effects=checked_arguments,
            external_storage_writes="not_observed_for_selected_argument_evaluations",
            address_escape_beyond_the_call="not_observed_for_selected_argument_evaluations",
            permitted_internal_operations=[
                "temporary_const_reference_binding_inside_exact_minimum_calls",
                "builtin_integer_value_computation",
                "scalar_literal_temporary_materialization_and_its_own_storage_write",
            ],
        )
    except _Unknown as error:
        result["reason"] = error.reason
    return result
