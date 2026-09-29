"""Rebuild exact softmax launch binding, without inferring configuration values."""

import argparse
import json
from pathlib import Path

from experiments.pytorch_softmax_intake import implementation_hashes, select_entry, sha
from wavebridge.analysis.launch_facts import inspect
from wavebridge.verification.getter_returns import _hash
from wavebridge.verification.launch_binding import check


NATIVE_SHA = "a59c12247f796fe2034ba03ecc43782f77ac3942496b18a140ceacbb24c7ff45"
KERNEL_ID = "0x30d762e0"
HIP_NATIVE_SHA = "46ac52b1c672fadd0e5a66bb3ab380373e0cd69929713d96e7010f375a0cd63e"
HIP_KERNEL_ID = "0x745c579e5490"


def selected_copy_source(binding, position):
    """Select a direct copy source from a freshly bound slot, not its value."""
    slots = [s for s in binding.get("configuration_slots", []) if s.get("position") == position]
    if binding.get("status") != "checked" or len(slots) != 1:
        raise ValueError("configuration_copy_slot_not_unique")
    expression = slots[0].get("expression_ast", {})
    if expression.get("kind") != "CXXConstructExpr" or len(expression.get("inner", [])) != 1:
        raise ValueError("configuration_not_direct_copy_candidate")
    source = expression["inner"][0]
    if source.get("kind") == "ImplicitCastExpr" and source.get("castKind") == "NoOp" and len(source.get("inner", [])) == 1:
        source = source["inner"][0]
    reference = source.get("referencedDecl", {})
    if (source.get("kind") != "DeclRefExpr" or source.get("inner") or
            reference.get("kind") != "VarDecl" or not isinstance(reference.get("id"), str) or not reference["id"]):
        raise ValueError("configuration_copy_source_not_direct_variable")
    return reference["id"]


def check_host_dimensions(root, binding, *, power_input_domain=None):
    """Select sources from the bound object initializer, then independently check."""
    from wavebridge.verification.integer_selection import (
        check_local_minimum_update, check_minimum_to_statement,
        check_minimum_quotient, check_quotient_to_statement)

    result = {"status": "unknown", "reason": None, "selection": None, "checks": {},
              "operand_initializers": [], "power_loop_checks": [], "source_program_checked": False,
              "numeric_domains_established": False, "deployable": False}
    try:
        variable = selected_copy_source(binding, 1)
        index, pending = {}, [(root, None, None)]
        while pending:
            node, owner, parent = pending.pop()
            if node.get("kind") in {"FunctionDecl", "CXXMethodDecl", "LambdaExpr"}:
                owner = node
            index.setdefault(node.get("id"), []).append((node, owner, parent))
            pending.extend((child, owner, node) for child in node.get("inner", []))

        def unique(identifier):
            matches = index.get(identifier, [])
            if not isinstance(identifier, str) or len(matches) != 1:
                raise ValueError("host_selection_identity_not_unique")
            return matches[0]

        declaration, owner, statement = unique(variable)
        if (owner is None or owner.get("kind") != "FunctionDecl" or
                statement is None or statement.get("kind") != "DeclStmt" or
                declaration.get("kind") != "VarDecl" or len(declaration.get("inner", [])) != 1):
            raise ValueError("host_object_declaration_unsupported")
        construct = declaration["inner"][0]
        if construct.get("kind") != "CXXConstructExpr" or len(construct.get("inner", [])) != 3:
            raise ValueError("host_object_initializer_unsupported")

        def reference(node):
            for _ in range(32):
                if node.get("kind") == "ParenExpr" or (node.get("kind") == "ImplicitCastExpr" and
                        node.get("castKind") in {"IntegralCast", "LValueToRValue", "NoOp"}):
                    if len(node.get("inner", [])) != 1:
                        raise ValueError("host_argument_wrapper_unsupported")
                    node = node["inner"][0]
                else:
                    break
            ref = node.get("referencedDecl", {})
            if node.get("kind") != "DeclRefExpr" or ref.get("kind") != "VarDecl" or node.get("inner"):
                raise ValueError("host_argument_not_variable")
            _, ref_owner, _ = unique(ref.get("id"))
            if ref_owner is not owner:
                raise ValueError("host_argument_owner_mismatch")
            return ref["id"]

        minimum_variable, quotient = map(reference, construct["inner"][:2])
        assignments = []
        for occurrences in index.values():
            for node, node_owner, _ in occurrences:
                if (node_owner is owner and node.get("kind") == "BinaryOperator" and
                        node.get("opcode") == "=" and len(node.get("inner", [])) == 2):
                    lhs = node["inner"][0]
                    if lhs.get("kind") == "DeclRefExpr" and lhs.get("referencedDecl", {}).get("id") == minimum_variable:
                        assignments.append(node)
        if len(assignments) != 1:
            raise ValueError("host_minimum_assignment_not_unique")
        assignment = assignments[0]["id"]
        result["selection"] = {"object_declaration_id": variable, "constructor_expression_id": construct["id"],
            "owner_id": owner["id"], "statement_id": statement["id"],
            "minimum_variable_id": minimum_variable, "assignment_id": assignment, "quotient_id": quotient}
        abi = {"int": {"bits": 32, "signed": True}}
        options = {"max_ast_nodes": 10_000_000}
        result["checks"] = {
            "minimum": check_local_minimum_update(root, assignment, abi, **options),
            "minimum_history": check_minimum_to_statement(root, assignment, statement["id"], abi, **options),
            "quotient": check_minimum_quotient(root, assignment, quotient, abi, **options),
            "quotient_history": check_quotient_to_statement(root, assignment, quotient, statement["id"], abi, **options)}
        minimum = result["checks"]["minimum"]
        if minimum.get("status") == "checked":
            from experiments.softmax_host_api_evidence import observe_call
            from wavebridge.analysis.integer_constants import evaluate

            for identifier in minimum["operand_declaration_ids"]:
                operand, operand_owner, _ = unique(identifier)
                if operand_owner is not owner or operand.get("kind") != "VarDecl":
                    raise ValueError("minimum_operand_declaration_mismatch")
                item = {"declaration_id": identifier, "declaration_ast": operand,
                        "constant_evaluation": evaluate(root, identifier, 32),
                        "call_observation": None, "call_observation_reason": None,
                        "initial_value_preserved_to_update": False,
                        "runtime_return_interval": None, "api_effects_established": False}
                result["operand_initializers"].append(item)
                initializers = operand.get("inner", [])
                if len(initializers) == 1 and initializers[0].get("kind") == "CallExpr":
                    call = initializers[0]
                    parts = call.get("inner", [])
                    callee = parts[0] if parts else {}
                    if callee.get("kind") == "ImplicitCastExpr" and len(callee.get("inner", [])) == 1:
                        callee = callee["inner"][0]
                    try:
                        item["call_observation"] = observe_call(root, call["id"],
                            callee.get("referencedDecl", {}).get("id"), identifier)
                    except ValueError as error:
                        item["call_observation_reason"] = str(error)
                if power_input_domain is not None and len(initializers) == 1:
                    expression = initializers[0]
                    if expression.get("kind") == "BinaryOperator" and expression.get("opcode") == "<<":
                        from wavebridge.verification.power_ceiling import check as check_power, check_initialized_shift
                        shift_parts = expression.get("inner", [])
                        if len(shift_parts) != 2:
                            raise ValueError("shift_origin_shape_unsupported")
                        exponent_id = reference(shift_parts[1])
                        exponent_declaration, _, _ = unique(exponent_id)
                        expressions = exponent_declaration.get("inner", [])
                        if len(expressions) != 1 or expressions[0].get("kind") != "CallExpr":
                            raise ValueError("exponent_initializer_not_call")
                        call = expressions[0]
                        parts = call.get("inner", [])
                        if len(parts) != 2:
                            raise ValueError("exponent_call_arity_unsupported")
                        callee = parts[0]
                        if callee.get("kind") != "ImplicitCastExpr" or callee.get("castKind") != "FunctionToPointerDecay" or len(callee.get("inner", [])) != 1:
                            raise ValueError("exponent_callee_shape_unsupported")
                        callee = callee["inner"][0]
                        ref = callee.get("referencedDecl", {})
                        if callee.get("kind") != "DeclRefExpr" or ref.get("kind") != "FunctionDecl":
                            raise ValueError("exponent_callee_not_direct")
                        argument = parts[1]
                        if (argument.get("kind") != "ImplicitCastExpr" or
                                argument.get("castKind") != "LValueToRValue" or len(argument.get("inner", [])) != 1):
                            raise ValueError("power_argument_not_direct_read")
                        argument_reference = argument["inner"][0]
                        if argument_reference.get("kind") != "DeclRefExpr":
                            raise ValueError("power_argument_not_declaration_read")
                        argument_id = argument_reference.get("referencedDecl", {}).get("id")
                        result["power_loop_checks"].append({"call_ast": call,
                            "exponent_declaration_id": exponent_id,
                            "domain_policy": "explicit diagnostic assumption; not established at this call",
                            "call_domain_established": False,
                            "initialized_shift_check": check_initialized_shift(
                                root, exponent_id, identifier, argument_id, *power_input_domain),
                            "check": check_power(root, ref.get("id"), *power_input_domain)})
        result["status"] = "observed"
    except (ValueError, KeyError, TypeError) as error:
        result["reason"] = str(error)
    return result


def run(native, output, *, threads_object=False, host_minimum_update=False, host_minimum_history=False,
        host_minimum_quotient=False, host_quotient_history=False, constructor_argument_effects=False,
        constructor_field_forwarding=False, profile="cuda", host_dimensions=False, power_input_domain=None):
    native, output = Path(native).resolve(), Path(output).resolve()
    if profile not in {"cuda", "hip"}:
        raise ValueError("unsupported_input_profile")
    if power_input_domain is not None and (not host_dimensions or len(power_input_domain) != 2):
        raise ValueError("power_domain_requires_host_dimensions_and_two_bounds")
    if profile == "hip" and any((host_minimum_update, host_minimum_history,
            host_minimum_quotient, host_quotient_history, constructor_argument_effects,
            constructor_field_forwarding)):
        raise ValueError("cuda_only_selection_not_available_in_hip_profile")
    native_sha, kernel_id = ((NATIVE_SHA, KERNEL_ID) if profile == "cuda" else
                             (HIP_NATIVE_SHA, HIP_KERNEL_ID))
    if sha(native) != native_sha or output.exists():
        raise ValueError("native_mismatch_or_output_exists")
    before = implementation_hashes()
    dependencies = {str(path): sha(path) for path in
                    (Path(__file__), Path(__file__).with_name("pytorch_softmax_intake.py"),
                     Path(__file__).with_name("softmax_host_api_evidence.py"))}
    capture = json.loads(native.read_text())
    if capture.get("status") != "collected":
        raise ValueError("native_not_collected")
    root = capture["payload"]["ast"]
    kernel = select_entry(root)
    if kernel["id"] != kernel_id:
        raise ValueError("fixed_kernel_identity_mismatch")
    facts = inspect(root, kernel_id)
    sites = facts["sites"]
    print(json.dumps({"phase": "launch_discovery", "selected_kernel_sites": len(sites),
                      "unresolved_sites": len(facts["unresolved_sites"])}), flush=True)
    selection = None
    checked = {"status": "unknown", "reason": "selected_kernel_launch_not_unique"}
    if len(sites) == 1:
        site = sites[0]
        selection = {"schema_version": "launch-selection/v1", "ast_root_sha256": _hash(root),
                     "kernel_declaration_id": kernel_id, "launch_id": site["launch_id"],
                     "configuration_declaration_id": site["configuration_declaration_id"],
                     "configuration_expression_ids": [arg["id"] for arg in site["configuration_arguments"]]}
        checked = check(root, selection)
    object_report = None
    dimensions_report = (check_host_dimensions(root, checked, power_input_domain=power_input_domain)
                         if host_dimensions and checked.get("status") == "checked" else None)
    if threads_object and checked.get("status") == "checked":
        from wavebridge.verification.object_use_closure import inspect_structure

        # Exact development-input selection, not a constructor-value oracle.
        selected_variable = ("0x30d69b78" if profile == "cuda" else selected_copy_source(checked, 1))
        owners = []
        pending = [(root, None)]
        while pending:
            node, owner = pending.pop()
            if node.get("kind") == "FunctionDecl":
                owner = node
            if node.get("id") == selected_variable:
                owners.append(owner)
            pending.extend((child, owner) for child in node.get("inner", []))
        if len(owners) != 1 or owners[0] is None:
            raise ValueError("threads_owner_not_unique")
        abi = {"int": {"bits": 32, "signed": True},
               "unsigned int": {"bits": 32, "signed": False}}
        object_report = inspect_structure(capture["payload"], selected_variable, abi, {},
                                         instantiated_function_id=owners[0]["id"],
                                         max_ast_nodes=10_000_000)
    minimum_report = None
    if host_minimum_update and checked.get("status") == "checked":
        from wavebridge.verification.integer_selection import check_local_minimum_update

        minimum_report = check_local_minimum_update(
            root, "0x30d69470", {"int": {"bits": 32, "signed": True}},
            max_ast_nodes=10_000_000)
    history_report = None
    if host_minimum_history and checked.get("status") == "checked":
        from wavebridge.verification.integer_selection import check_minimum_to_statement

        statements, pending = [], [(root, None)]
        while pending:
            node, parent = pending.pop()
            if node.get("id") == "0x30d69b78":
                statements.append(parent)
            pending.extend((child, node) for child in node.get("inner", []))
        if len(statements) != 1 or statements[0].get("kind") != "DeclStmt":
            raise ValueError("threads_statement_not_unique")
        history_report = check_minimum_to_statement(
            root, "0x30d69470", statements[0]["id"], {"int": {"bits": 32, "signed": True}},
            max_ast_nodes=10_000_000)
    quotient_report = None
    quotient_history_report = None
    if (host_minimum_quotient or host_quotient_history) and checked.get("status") == "checked":
        from wavebridge.verification.integer_selection import check_minimum_quotient, check_quotient_to_statement

        candidates, targets, pending = [], [], [(root, None, None)]
        while pending:
            node, owner, parent = pending.pop()
            if node.get("kind") == "FunctionDecl":
                owner = node.get("id")
            if (owner == "0x30a41828" and node.get("kind") == "VarDecl" and
                    node.get("name") == "warps_per_block"):
                candidates.append(node)
            if node.get("id") == "0x30d69b78":
                targets.append(parent)
            pending.extend((child, owner, node) for child in node.get("inner", []))
        if len(candidates) != 1:
            raise ValueError("quotient_declaration_not_unique")
        if host_minimum_quotient:
            quotient_report = check_minimum_quotient(
                root, "0x30d69470", candidates[0]["id"], {"int": {"bits": 32, "signed": True}},
                max_ast_nodes=10_000_000)
        if host_quotient_history:
            if len(targets) != 1 or targets[0].get("kind") != "DeclStmt":
                raise ValueError("quotient_history_target_statement_not_unique")
            quotient_history_report = check_quotient_to_statement(
                root, "0x30d69470", candidates[0]["id"], targets[0]["id"],
                {"int": {"bits": 32, "signed": True}}, max_ast_nodes=10_000_000)
    constructor_effects_report = None
    if constructor_argument_effects and checked.get("status") == "checked":
        from wavebridge.verification.constructor_argument_effects import check_scalar_evaluations

        constructor_effects_report = check_scalar_evaluations(
            root, "0x30d69d08", max_ast_nodes=10_000_000)
    forwarding_report = None
    if constructor_field_forwarding and checked.get("status") == "checked":
        from wavebridge.verification.constructor_argument_effects import check_scalar_field_forwarding

        forwarding_report = check_scalar_field_forwarding(
            root, "0x30d69d08", {"int": {"bits": 32, "signed": True},
                                  "unsigned int": {"bits": 32, "signed": False}},
            max_ast_nodes=10_000_000)
    after = implementation_hashes()
    report = {"schema_version": "softmax-native-launch-observation/v1", "check": checked,
              "selection": selection, "launch_discovery": facts, "native_sha256": native_sha,
              "input_profile": profile,
              "threads_object_check": object_report,
              "host_dimensions_diagnostic": dimensions_report,
              "host_minimum_update_check": minimum_report,
              "host_minimum_history_check": history_report,
              "host_minimum_quotient_check": quotient_report,
              "host_quotient_history_check": quotient_history_report,
              "constructor_argument_effects_check": constructor_effects_report,
              "constructor_field_forwarding_check": forwarding_report,
              "implementation_before": before, "implementation_after": after,
              "driver_dependencies": dependencies,
              "inputs_unchanged": before == after and sha(native) == native_sha and
                  all(sha(path) == digest for path, digest in dependencies.items()),
              "configuration_values_established": False, "lane_family_established": False,
              "GPU_executed": False, "source_program_checked": False, "deployable": False}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": checked["status"], "reason": checked.get("reason"),
                      "inputs_unchanged": report["inputs_unchanged"], "sha256": sha(output)}), flush=True)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--profile", choices=("cuda", "hip"), default="cuda")
    parser.add_argument("--threads-object", action="store_true")
    parser.add_argument("--host-dimensions", action="store_true")
    parser.add_argument("--power-input-domain", nargs=2, type=int, metavar=("LOWER", "UPPER"))
    parser.add_argument("--host-minimum-update", action="store_true")
    parser.add_argument("--host-minimum-history", action="store_true")
    parser.add_argument("--host-minimum-quotient", action="store_true")
    parser.add_argument("--host-quotient-history", action="store_true")
    parser.add_argument("--constructor-argument-effects", action="store_true")
    parser.add_argument("--constructor-field-forwarding", action="store_true")
    args = parser.parse_args()
    run(args.native, args.output, threads_object=args.threads_object,
        host_minimum_update=args.host_minimum_update, host_minimum_history=args.host_minimum_history,
        host_minimum_quotient=args.host_minimum_quotient, host_quotient_history=args.host_quotient_history,
        constructor_argument_effects=args.constructor_argument_effects,
        constructor_field_forwarding=args.constructor_field_forwarding, profile=args.profile,
        host_dimensions=args.host_dimensions, power_input_domain=args.power_input_domain)
