"""Conditionally check protected column-loop declarations in a narrow body subset."""

from __future__ import annotations

from typing import Any

from wavebridge.analysis.column_loops import (
    _Unknown as _BodyUnknown,
    _check_body,
    _children,
    _coordinate_header,
    _initializer,
    _signed_int,
)
from wavebridge.verification.getter_returns import (
    HARD_MAX_AST_NODES,
    MAX_AST_NODES,
    _hash,
    check_property_no_memory_write,
)
from wavebridge.verification.kernel_arguments import _Unknown, _abi_type

MAX_PROPERTIES = 8


def check(root: object, function_id: object, loop_id: object,
          integer_types: object, property_protocols: object, binding: object,
          *, max_ast_nodes: int | None = None) -> dict[str, Any]:
    budget = MAX_AST_NODES if max_ast_nodes is None else max_ast_nodes
    result: dict[str, Any] = {
        "schema_version": "conditional-column-body-check/v1",
        "status": "unknown", "reason": None,
        "function_id": function_id, "loop_id": loop_id,
        "coordinate_header_observation": None,
        "property_checks": {}, "protected_declaration_ids": [],
        "source_program_checked": False, "deployable": False,
        "header_recurrence_checked": False,
        "whole_body_no_memory_write": False,
        "scope": "protected_column_declarations_not_modified_in_supported_body_effect_subset",
        "premises": [
            "the source program is valid for the checked execution context",
            "supported body stores do not alias the protected declarations",
            "each skipped property subtree has a fresh conditional no-write check",
        ],
        "limitations": [
            "does not establish coordinate values, header recurrence or loop coverage",
            "does not prove that the whole body performs no memory writes",
            "does not establish loop reachability, termination or deployment safety",
        ],
        "budget": {"max_ast_nodes_per_fresh_scan": budget,
                   "max_properties": MAX_PROPERTIES},
    }

    def unknown(reason):
        result["reason"] = reason
        return result

    if (not isinstance(root, dict) or not isinstance(function_id, str) or not function_id or
            not isinstance(loop_id, str) or not loop_id or
            not isinstance(integer_types, dict) or
            not isinstance(property_protocols, dict) or not isinstance(binding, dict) or
            type(budget) is not int or not 1 <= budget <= HARD_MAX_AST_NODES):
        return unknown("invalid_inputs_or_budget")
    if (not property_protocols or len(property_protocols) > MAX_PROPERTIES or
            any(not isinstance(key, str) or not key or not isinstance(value, dict)
                for key, value in property_protocols.items())):
        return unknown("invalid_property_protocols")
    try:
        root_sha256 = _hash(root)
        result["input_sha256"] = {
            "root": root_sha256, "function_id": _hash(function_id),
            "loop_id": _hash(loop_id), "integer_types": _hash(integer_types),
            "property_protocols": _hash(property_protocols), "binding": _hash(binding),
        }
    except (TypeError, ValueError, RecursionError):
        return unknown("input_hash_unsupported")
    if (binding.get("schema_version") != "column-body-assumptions/v1" or
            binding.get("root_sha256") != root_sha256 or
            binding.get("function_id") != function_id or
            binding.get("loop_id") != loop_id or
            binding.get("source_validity_assumed") is not True or
            binding.get("no_alias_with_protected_declarations_assumed") is not True or
            not isinstance(binding.get("evidence_reference"), str) or
            not binding["evidence_reference"].strip()):
        return unknown("body_assumptions_not_applicable")

    try:
        pending = [root]
        functions, loops, id_counts, nodes = [], [], {}, 0
        while pending:
            node = pending.pop()
            nodes += 1
            if nodes > budget:
                raise _Unknown("ast_node_budget_exceeded")
            if not isinstance(node, dict) or not isinstance(node.get("inner", []), list):
                raise _Unknown("malformed_ast_node")
            identifier = node.get("id")
            if isinstance(identifier, str) and identifier:
                id_counts[identifier] = id_counts.get(identifier, 0) + 1
            if node.get("kind") in {"FunctionDecl", "CXXMethodDecl"} and identifier == function_id:
                functions.append(node)
            if node.get("kind") == "ForStmt" and identifier == loop_id:
                loops.append(node)
            pending.extend(node.get("inner", []))
        result["ast_nodes_scanned"] = nodes
        if len(functions) != 1 or id_counts.get(function_id) != 1:
            raise _Unknown("function_declaration_not_unique")
        bodies = [child for child in _children(functions[0])
                  if child.get("kind") == "CompoundStmt"]
        if (len(bodies) != 1 or len(loops) != 1 or id_counts.get(loop_id) != 1 or
                not any(child is loops[0] for child in _children(bodies[0]))):
            raise _Unknown("loop_not_unique_direct_function_body_child")
        loop = loops[0]
        parts = loop.get("inner")
        if (not isinstance(parts, list) or len(parts) != 5 or
                not isinstance(parts[1], dict) or parts[1] or
                not all(isinstance(node, dict) and node for node in
                        (parts[0], parts[2], parts[3], parts[4]))):
            raise _Unknown("unsupported_for_header_layout")
        init, _, condition, increment, body = parts
        if init.get("kind") != "DeclStmt" or body.get("kind") != "CompoundStmt":
            raise _Unknown("unsupported_loop_statement_shape")
        variables = [child for child in _children(init) if child.get("kind") == "VarDecl"]
        if len(variables) != 1 or not _signed_int(variables[0]):
            raise _Unknown("initializer_not_single_signed_int")
        induction = variables[0]
        if (induction.get("storageClass") not in (None, "auto", "register") or
                induction.get("tls") is not None or induction.get("thread_local") is not None or
                not isinstance(induction.get("id"), str) or not induction["id"]):
            raise _Unknown("induction_not_unique_automatic_declaration")
        if id_counts.get(induction["id"]) != 1:
            raise _Unknown("induction_declaration_not_unique")

        int_type = _abi_type({"qualType": "int"}, integer_types)
        unsigned_type = _abi_type({"qualType": "unsigned int"}, integer_types)
        if int_type[2] is not True or unsigned_type[2] is not False or int_type[1] != unsigned_type[1]:
            raise _Unknown("coordinate_integer_abi_unsupported")
        header = _coordinate_header(root, induction, _initializer(induction), condition, increment)
        result["coordinate_header_observation"] = header
        if header.get("status") != "observed":
            raise _Unknown("coordinate_header_not_observed")
        protected = {induction["id"], header.get("bound_parameter_id")}
        for key in ("start_value_link", "step_value_link"):
            linked = header.get(key)
            pseudo = linked.get("pseudo_object") if isinstance(linked, dict) else None
            receiver_id = pseudo.get("receiver_declaration_id") if isinstance(pseudo, dict) else None
            if not isinstance(receiver_id, str) or not receiver_id:
                raise _Unknown("coordinate_receiver_binding_missing")
            protected.add(receiver_id)
        if any(not isinstance(identifier, str) or not identifier for identifier in protected):
            raise _Unknown("protected_declaration_binding_missing")
        if any(id_counts.get(identifier) != 1 for identifier in protected):
            raise _Unknown("protected_declaration_not_unique")
        result["protected_declaration_ids"] = sorted(protected)

        used = set()

        def property_callback(expression):
            expression_id = expression.get("id")
            if (not isinstance(expression_id, str) or not expression_id or
                    id_counts.get(expression_id) != 1 or expression_id in used):
                return False
            protocol = property_protocols.get(expression_id)
            if not isinstance(protocol, dict) or set(protocol) != {
                    "leaf_contract", "effect_protocol", "receiver_protocol"}:
                return False
            report = check_property_no_memory_write(
                root, expression_id, protocol["leaf_contract"], integer_types,
                protocol["effect_protocol"], protocol["receiver_protocol"],
                max_ast_nodes=budget)
            result["property_checks"][expression_id] = report
            if (report.get("status") != "checked" or
                    report.get("conclusion", {}).get("property") != "no_memory_write" or
                    report.get("conclusion", {}).get("expression_id") != expression_id):
                return False
            used.add(expression_id)
            return True

        try:
            _check_body(body, protected, property_callback=property_callback)
        except _BodyUnknown as error:
            result["body_effect_reason"] = error.reason
            result["body_effect_unknown_range"] = error.range
            raise _Unknown("body_effect_not_established")
        if used != set(property_protocols):
            raise _Unknown("property_protocol_not_consumed_exactly")
        result.update(
            status="checked",
            conclusion={
                "status": "conditional",
                "property": "protected_declarations_not_modified",
                "protected_declaration_ids": sorted(protected),
                "effect_subset": "supported_column_body_operations_and_fresh_checked_properties",
            },
            assumption_evidence={"reference": binding["evidence_reference"],
                                 "verification_status": "unverified"},
        )
    except _Unknown as error:
        result["reason"] = error.reason
    except _BodyUnknown as error:
        result["reason"] = error.reason
    except (TypeError, ValueError, RecursionError):
        result["reason"] = "input_or_structure_unsupported"
    return result
