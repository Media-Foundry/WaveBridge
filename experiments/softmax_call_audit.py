"""Development call inventory on a sealed AST; not a purity or dispatch checker."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from experiments.pytorch_softmax_intake import implementation_hashes, select_entry, sha, walk
from experiments.softmax_constant_followup import AST_SHA
from wavebridge.analysis.reduction_discovery import _body, _callee, _walk_function_body

PREVIOUS_SHA = "3c01b98b7727f042a5fdb279cffe2e37a370bde6ab893752e57cecd6fb5763e9"
CALLS = {"CallExpr", "CXXMemberCallExpr", "CXXOperatorCallExpr", "CUDAKernelCallExpr"}
HIP_NATIVE_SHA = "46ac52b1c672fadd0e5a66bb3ab380373e0cd69929713d96e7010f375a0cd63e"


def driver_dependencies():
    return {name: sha(Path(__file__).with_name(name)) for name in
            ("softmax_call_audit.py", "pytorch_softmax_intake.py", "softmax_constant_followup.py")}


def inventory(root, entry_id, max_functions=64, *, observe_identical_repeats=False):
    declarations = {}
    for node in walk(root):
        if node.get("kind") in {"FunctionDecl", "CXXMethodDecl"} and isinstance(node.get("id"), str):
            declarations.setdefault(node["id"], []).append(node)
    queue, visited, functions, edges = [entry_id], set(), [], []
    while queue and len(visited) < max_functions:
        identifier = queue.pop(0)
        if identifier in visited:
            continue
        visited.add(identifier)
        matches = declarations.get(identifier, [])
        definitions = [node for node in matches if _body(node) is not None]
        # Diagnostic traversal only: retain multiplicity and require equality of
        # the entire declaration, not just a name, body, or selected fields.
        identical = bool(matches) and all(node == matches[0] for node in matches)
        selected = (definitions[0] if len(definitions) == 1 else
                    definitions[0] if observe_identical_repeats and definitions and identical else None)
        functions.append({"id": identifier, "declaration_count": len(matches),
                          "definition_count": len(definitions),
                          "all_declaration_occurrences_identical": identical,
                          "repeated_definition_traversed": selected is not None and len(definitions) > 1,
                          "declarations": [{key: node.get(key) for key in
                              ("kind", "name", "mangledName", "type", "storageClass", "virtual", "range")}
                                           for node in matches],
                          "body_ast": _body(selected) if selected is not None else None})
        if selected is None:
            continue
        for call in _walk_function_body(_body(selected)):
            if call.get("kind") not in CALLS:
                continue
            resolution = _callee(call, declarations)
            current = next(iter(call.get("inner", [])), {})
            wrappers = []
            while isinstance(current, dict) and current.get("kind") in {"ParenExpr", "ImplicitCastExpr"}:
                wrappers.append({key: current.get(key) for key in ("kind", "castKind", "type", "range")})
                children = current.get("inner", [])
                if len(children) != 1:
                    break
                current = children[0]
            # Observe only one direct callee expression, never an argument's ref.
            # This is deliberately separate from the production resolver result.
            reference = current.get("referencedDecl", {}) if isinstance(current, dict) else {}
            observed = None
            if (isinstance(current, dict) and current.get("kind") == "DeclRefExpr" and
                    reference.get("kind") in {"FunctionDecl", "CXXMethodDecl"} and
                    isinstance(reference.get("id"), str)):
                observed = reference["id"]
            target = observed or resolution.get("callee_id")
            edges.append({"caller_id": identifier, "call_id": call.get("id"),
                          "call_kind": call.get("kind"), "call_range": call.get("range"),
                          "production_resolution": resolution, "callee_wrappers": wrappers,
                          "observed_reference_id": observed,
                          "inventory_target_id": target, "call_ast": call,
                          "dispatch_checked": False, "effects_checked": False})
            if target and target not in visited and target not in queue:
                queue.append(target)
    return {"functions": functions, "edges": edges, "pending_ids": queue,
            "observe_identical_repeats": observe_identical_repeats,
            "budget_exhausted": bool(queue), "max_functions": max_functions,
            "scope": "syntactic_direct_reference_inventory_not_dynamic_reachability",
            "source_program_checked": False, "deployable": False}


def run(ast_path, previous_path, output_dir):
    ast_path, previous_path = Path(ast_path).resolve(), Path(previous_path).resolve()
    if sha(ast_path) != AST_SHA or sha(previous_path) != PREVIOUS_SHA:
        raise ValueError("sealed_input_hash_mismatch")
    previous = json.loads(previous_path.read_text())
    if previous.get("ast_sha256") != AST_SHA:
        raise ValueError("previous_ast_binding_mismatch")
    directory = Path(output_dir).resolve()
    directory.mkdir(parents=True, exist_ok=False)
    before, driver = implementation_hashes(), sha(__file__)
    dependencies = driver_dependencies()
    frontend = json.loads(ast_path.read_text())
    if frontend.get("status") != "collected" or len(frontend.get("ast_roots", [])) != 1:
        raise ValueError("unique_collected_root_required")
    root = frontend["ast_roots"][0]
    entry = select_entry(root)
    report = {"schema_version": "softmax-call-audit/v1", "command": sys.argv,
              "ast_sha256": AST_SHA, "previous_sha256": PREVIOUS_SHA,
              "entry_id": entry["id"], "implementation_before": before,
              "driver_sha256": driver, "evaluation_role": "development_not_holdout",
              "driver_dependencies_before": dependencies,
              "inventory": inventory(root, entry["id"]),
              "frontend_reexecuted": False, "GPU_executed": False,
              "source_program_checked": False, "deployable": False}
    report["implementation_after"] = implementation_hashes()
    report["driver_dependencies_after"] = driver_dependencies()
    stable = (before == report["implementation_after"] and driver == sha(__file__) and
              dependencies == report["driver_dependencies_after"] and
              sha(ast_path) == AST_SHA and sha(previous_path) == PREVIOUS_SHA)
    report.update(status="observed" if stable else "inputs_changed", inputs_unchanged=stable)
    path = directory / "report.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": report["status"], "report": str(path), "sha256": sha(path)}))
    return report


def run_native(native_path, output_dir, *, using_shadows=False, unary_float=False, unary_forwarding=False,
               outer_calls=False, assume_unary_effects=False):
    """Observe HIP call paths without deduplicating or modifying checker input."""
    from wavebridge.verification.builtin_calls import inspect_structure
    from wavebridge.verification.using_shadow_identity import UsingShadowIndex, IdentityUnknown
    from wavebridge.verification.getter_returns import _hash
    from wavebridge.verification.scalar_forwarding import inspect_builtin_structure
    from wavebridge.verification.scalar_call_effects import inspect_native_call
    from wavebridge.verification.builtin_calls import check_call_no_memory_write
    if (any(type(option) is not bool for option in
            (using_shadows, unary_float, unary_forwarding, outer_calls, assume_unary_effects)) or
            unary_forwarding and not (using_shadows and unary_float) or outer_calls and not unary_forwarding or
            assume_unary_effects and not outer_calls):
        raise ValueError("invalid_using_shadows_option")
    native_path = Path(native_path).resolve()
    if sha(native_path) != HIP_NATIVE_SHA:
        raise ValueError("sealed_native_input_hash_mismatch")
    source = json.loads(native_path.read_text())
    if source.get("status") != "collected":
        raise ValueError("native_input_not_collected")
    payload = source["payload"]
    root = payload["ast"]
    entry = select_entry(root)
    directory = Path(output_dir).resolve()
    directory.mkdir(parents=True, exist_ok=False)
    before, helpers = implementation_hashes(), driver_dependencies()
    observed = inventory(root, entry["id"], observe_identical_repeats=True)
    call_ids = {edge["call_id"] for edge in observed["edges"]}
    repeated_ids = {item["id"] for item in observed["functions"] if item["declaration_count"] > 1}
    occurrences = []
    pending = [(root, [])]
    while pending:
        node, parents = pending.pop()
        if node.get("kind") in {"FunctionDecl", "CXXMethodDecl"} and node.get("id") in repeated_ids:
            occurrences.append({"declaration_id": node["id"], "parent_path": parents,
                                "declaration_ast": node})
            # Observe each occurrence separately even when their contents differ;
            # this does not authorize a graph edge through the ambiguous node.
            call_ids.update(child.get("id") for child in walk(node) if child.get("kind") in CALLS)
        pending.extend((child, parents + [{"kind": node.get("kind"), "id": node.get("id"),
                                           "name": node.get("name"), "child_index": index}])
                       for index, child in enumerate(node.get("inner", [])))
    # Record native unary math leaves and ask the unchanged builtin checker.
    # Naming here selects diagnostic subjects; it establishes no semantics.
    leaves = [record for record in payload["builtin_calls"]
              if record.get("call_expression_id") in call_ids and
              record.get("builtin_name") in {"__builtin_expf", "__builtin_logf"}]
    checks = [{"native_observation": record,
               "structure_check": inspect_structure(payload, record["call_expression_id"],
                   allow_unary_float=unary_float, allow_using_shadows=using_shadows)}
              for record in leaves]
    identities, identity_checks = None, []
    if using_shadows:
        identities = UsingShadowIndex(root, 1_000_000)
        for identifier in sorted(repeated_ids):
            item = {"declaration_id": identifier, "status": "unknown", "reason": None,
                    "scope": "ordinary_identity_and_using_reference_representation_only",
                    "source_program_checked": False, "deployable": False}
            try:
                declaration = identities.unique(identifier)
                item.update(status="checked", ordinary_declaration_sha256=_hash(declaration))
            except IdentityUnknown as error:
                item["reason"] = str(error)
            identity_checks.append(item)
    forwarding_checks, outer_checks, effect_checks, effect_protocols = [], [], [], {}
    envelope_hash = _hash(payload) if assume_unary_effects else None
    if unary_forwarding:
        # Select syntactic routes only; the checker rebuilds every body and
        # parameter edge. No function name is a relation template or oracle.
        native_ids = {record["call_expression_id"] for record in leaves}
        routes = {}
        for outer in (node for node in walk(entry) if node.get("kind") == "CallExpr"):
            current, first, seen = outer, None, set()
            for _ in range(32):
                if current.get("id") in native_ids:
                    if first is not None:
                        routes.setdefault((first, current["id"]), []).append(outer["id"])
                    break
                parts = current.get("inner", [])
                if not parts:
                    break
                reference = parts[0]
                while reference.get("kind") in {"ImplicitCastExpr", "ParenExpr"} and len(reference.get("inner", [])) == 1:
                    reference = reference["inner"][0]
                target = reference.get("referencedDecl", {})
                if reference.get("kind") != "DeclRefExpr" or target.get("kind") != "FunctionDecl":
                    break
                identifier = target.get("id")
                if identifier in seen:
                    break
                seen.add(identifier)
                try:
                    declaration = identities.unique(identifier)
                except IdentityUnknown:
                    break
                first = identifier if first is None else first
                body = _body(declaration)
                statements = body.get("inner", []) if body else []
                if (len(statements) != 1 or statements[0].get("kind") != "ReturnStmt" or
                        len(statements[0].get("inner", [])) != 1 or
                        statements[0]["inner"][0].get("kind") != "CallExpr"):
                    break
                current = statements[0]["inner"][0]
        for (start, terminal), outer_ids in sorted(routes.items()):
            checked = inspect_builtin_structure(payload, start, terminal, allow_using_shadows=True)
            forwarding_checks.append({"start_declaration_id": start, "native_leaf_call_id": terminal,
                "syntactic_outer_call_ids": outer_ids, "check": checked})
            print(json.dumps({"phase": "native_forwarding", "start": start,
                              "status": checked["status"], "reason": checked["reason"]}), flush=True)
            if outer_calls:
                for outer_id in outer_ids:
                    print(json.dumps({"phase": "outer_call_start", "call": outer_id}), flush=True)
                    if assume_unary_effects:
                        record = next(r for r in leaves if r["call_expression_id"] == terminal)
                        protocol = {"schema_version": "builtin-leaf-effect-assumption/v1",
                            "native_envelope_sha256": envelope_hash, "call_expression_id": terminal,
                            "callee_declaration_id": record["callee_declaration_id"],
                            "builtin_no_memory_write_assumed": True,
                            "valid_call_and_normal_return_assumed": True,
                            "evidence_reference": "development sensitivity assumption; not verified by this experiment"}
                        effect_protocols[outer_id] = protocol
                        effect = check_call_no_memory_write(payload, outer_id, protocol,
                            allow_unary_float=True, allow_using_shadows=True)
                        effect_checks.append({"call_expression_id": outer_id, "check": effect})
                        outer_check = effect.get("native_call_structure") or {
                            "status": "unknown", "reason": "no_native_structure_report"}
                    else:
                        outer_check = inspect_native_call(payload, outer_id, terminal, allow_using_shadows=True)
                    outer_checks.append({"call_expression_id": outer_id, "native_leaf_call_id": terminal,
                                         "check": outer_check})
                    print(json.dumps({"phase": "outer_call_done", "call": outer_id,
                                      "status": outer_check["status"], "reason": outer_check["reason"],
                                      "conditional_effect_status": effect["status"] if assume_unary_effects else None}), flush=True)
    report = {"schema_version": "softmax-native-call-audit/v1",
              "command": sys.argv, "native_sha256": HIP_NATIVE_SHA,
              "entry_id": entry["id"], "inventory": observed,
              "repeated_declaration_occurrences": occurrences,
              "math_leaf_selection_scope": "inventory_edges_or_individual_repeated_declaration_occurrences_not_proven_paths",
              "math_builtin_checks": checks, "implementation_before": before,
              "using_shadows_enabled": using_shadows,
              "unary_float_enabled": unary_float,
              "unary_forwarding_enabled": unary_forwarding,
              "unary_forwarding_checks": forwarding_checks,
              "outer_calls_enabled": outer_calls, "outer_call_checks": outer_checks,
              "assume_unary_effects": assume_unary_effects, "conditional_effect_checks": effect_checks,
              "outer_call_inventory_complete": False, "external_effects_verified": False,
              "using_shadow_identity_checks": identity_checks,
              "using_shadow_observations": identities.observations if identities else [],
              "driver_dependencies_before": helpers,
              "frontend_reexecuted": False, "GPU_executed": False,
              "source_program_checked": False, "deployable": False,
              "ast_modified": False, "external_effect_protocols": effect_protocols}
    report["implementation_after"] = implementation_hashes()
    report["driver_dependencies_after"] = driver_dependencies()
    stable = (before == report["implementation_after"] and
              helpers == report["driver_dependencies_after"] and sha(native_path) == HIP_NATIVE_SHA)
    report.update(status="observed" if stable else "inputs_changed", inputs_unchanged=stable)
    path = directory / "report.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": report["status"], "report": str(path), "sha256": sha(path)}))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--ast", type=Path)
    inputs.add_argument("--native", type=Path)
    parser.add_argument("--previous-report", type=Path)
    parser.add_argument("--using-shadows", action="store_true")
    parser.add_argument("--unary-float", action="store_true")
    parser.add_argument("--unary-forwarding", action="store_true")
    parser.add_argument("--outer-calls", action="store_true")
    parser.add_argument("--assume-unary-effects", action="store_true",
                        help="sensitivity run under UNVERIFIED leaf no-write/normal-return assumptions")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.native:
        if args.previous_report:
            parser.error("--previous-report is not used with --native")
        result = run_native(args.native, args.output_dir, using_shadows=args.using_shadows,
                            unary_float=args.unary_float, unary_forwarding=args.unary_forwarding,
                            outer_calls=args.outer_calls, assume_unary_effects=args.assume_unary_effects)
    else:
        if not args.previous_report:
            parser.error("--ast requires --previous-report")
        if args.using_shadows or args.unary_float or args.unary_forwarding or args.outer_calls or args.assume_unary_effects:
            parser.error("--using-shadows and --unary-float require --native")
        result = run(args.ast, args.previous_report, args.output_dir)
    return 0 if result["inputs_unchanged"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
