"""Inspect the first remaining call blocker in the pinned softmax native AST."""
import argparse
from collections import defaultdict
import json
from pathlib import Path

from experiments.pytorch_softmax_intake import implementation_hashes, select_entry, sha, walk
from wavebridge.analysis.reduction_discovery import _callee
from wavebridge.verification.scalar_forwarding import inspect_structure

NATIVE_SHA = "317b1a438bc13845cf76b5aa7461db4db2081b402c457a85c4160fdd7257c027"
RECOVERY_SHA = "4b209cf805ca46d40293a595b9d3c65a891a394e3a5111467c70f0e56b777ce7"


def run(native, recovery, output):
    if sha(native) != NATIVE_SHA or sha(recovery) != RECOVERY_SHA:
        raise ValueError("fixed_input_mismatch")
    if output.exists():
        raise ValueError("output_exists")
    before = implementation_hashes()
    helpers = {str(path): sha(path) for path in (Path(__file__), Path(__file__).with_name("pytorch_softmax_intake.py"))}
    frontend = json.loads(native.read_text())
    if frontend.get("status") != "collected":
        raise ValueError("native_not_collected")
    root = frontend["payload"]["ast"]
    old = json.loads(recovery.read_text())
    if old["native_sha256"] != NATIVE_SHA:
        raise ValueError("recovery_binding_mismatch")
    blocker = next(loop for loop in old["conditional"]["recovery"]["loops"]
                   if loop.get("reason") == "call_effect_not_checked")
    entry = select_entry(root)
    calls = [n for n in walk(entry) if n.get("kind") == "CallExpr" and n.get("range") == blocker["unknown_range"]]
    if len(calls) != 1:
        raise ValueError("blocker_not_unique")
    declarations = defaultdict(list)
    for node in walk(root):
        if node.get("kind") == "FunctionDecl":
            declarations[node.get("id")].append(node)
    first = _callee(calls[0], declarations).get("callee_id")
    current, path = first, []
    for _ in range(33):
        matches = declarations.get(current, [])
        if len(matches) != 1:
            raise ValueError("selector_declaration_not_unique")
        declaration = matches[0]
        path.append({k: declaration.get(k) for k in ("id", "name", "type", "range")})
        bodies = [c for c in declaration.get("inner", []) if c.get("kind") == "CompoundStmt"]
        if not bodies:
            break
        if len(bodies) != 1 or len(bodies[0].get("inner", [])) != 1:
            raise ValueError("selector_not_single_body_statement")
        statement = bodies[0]["inner"][0]
        if statement.get("kind") != "ReturnStmt" or len(statement.get("inner", [])) != 1:
            raise ValueError("selector_not_single_return")
        current = _callee(statement["inner"][0], declarations).get("callee_id")
    else:
        raise ValueError("selector_depth_budget")
    checked = inspect_structure(root, first, current)
    after = implementation_hashes()
    report = {"schema_version": "softmax-scalar-forwarding-development/v1",
              "native_sha256": NATIVE_SHA, "recovery_sha256": RECOVERY_SHA,
              "selected_call_ast": calls[0], "selected_path": path, "structure": checked,
              "caller_argument_effects": "not_established", "effect_semantics": "not_established",
              "GPU_executed": False, "source_program_checked": False, "deployable": False,
              "implementation_before": before, "implementation_after": after, "driver_dependencies": helpers,
              "inputs_unchanged": before == after and sha(native) == NATIVE_SHA and sha(recovery) == RECOVERY_SHA
              and all(sha(path) == digest for path, digest in helpers.items())}
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": checked["status"], "reason": checked["reason"], "sha256": sha(output),
                      "path": [item["name"] for item in path], "inputs_unchanged": report["inputs_unchanged"]}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native", type=Path, required=True)
    parser.add_argument("--recovery", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.native, args.recovery, args.output)
