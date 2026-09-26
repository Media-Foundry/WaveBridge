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


def driver_dependencies():
    return {name: sha(Path(__file__).with_name(name)) for name in
            ("softmax_call_audit.py", "pytorch_softmax_intake.py", "softmax_constant_followup.py")}


def inventory(root, entry_id, max_functions=64):
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
        functions.append({"id": identifier, "declaration_count": len(matches),
                          "definition_count": len(definitions),
                          "declarations": [{key: node.get(key) for key in
                              ("kind", "name", "mangledName", "type", "storageClass", "virtual", "range")}
                                           for node in matches],
                          "body_ast": _body(definitions[0]) if len(definitions) == 1 else None})
        if len(definitions) != 1:
            continue
        for call in _walk_function_body(_body(definitions[0])):
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ast", type=Path, required=True)
    parser.add_argument("--previous-report", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    return 0 if run(args.ast, args.previous_report, args.output_dir)["inputs_unchanged"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
