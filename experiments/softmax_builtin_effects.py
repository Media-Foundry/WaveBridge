"""Development-only conditional recovery on a pinned native softmax AST.

Automatically select builtin paths, but keep the no-write assumptions explicit
and unverified. This experiment does not establish those external semantics.
"""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path

from experiments.pytorch_softmax_intake import implementation_hashes, select_entry, sha, walk
from wavebridge.analysis.column_loops import recover, recover_with_builtin_effects
from wavebridge.analysis.reduction_discovery import _callee
from wavebridge.verification.getter_returns import _hash
from wavebridge.verification.loop_exit_guards import check_work_preservation

NATIVE_SHA = "317b1a438bc13845cf76b5aa7461db4db2081b402c457a85c4160fdd7257c027"
HIP_NATIVE_SHA = "46ac52b1c672fadd0e5a66bb3ab380373e0cd69929713d96e7010f375a0cd63e"


def run(native_path, output, *, profile="cuda-sm80", guarded_work=False):
    if profile not in {"cuda-sm80", "hip-gfx1100"} or type(guarded_work) is not bool:
        raise ValueError("invalid_profile_or_guarded_work_option")
    expected = NATIVE_SHA if profile == "cuda-sm80" else HIP_NATIVE_SHA
    native_path, output = Path(native_path), Path(output)
    if sha(native_path) != expected:
        raise ValueError("native_input_mismatch")
    if output.exists():
        raise ValueError("output_already_exists")
    before, driver = implementation_hashes(), sha(__file__)
    source = json.loads(native_path.read_text())
    if source.get("status") != "collected":
        raise ValueError("native_input_not_collected")
    payload = source["payload"]
    root, declarations = payload["ast"], defaultdict(list)
    entry = select_entry(root)
    for node in walk(root):
        if node.get("kind") in {"FunctionDecl", "CXXMethodDecl"}:
            declarations[node.get("id")].append(node)
    native = {item["call_expression_id"]: item for item in payload["builtin_calls"]}
    protocols, selected_paths = {}, {}
    envelope_hash = _hash(payload)
    # This selector supplies only identities and explicit assumptions. The
    # recovery entry independently rechecks full call/body/argument structure.
    for call in walk(entry):
        if call.get("kind") != "CallExpr":
            continue
        current, path = call, []
        for _ in range(32):
            path.append(current.get("id"))
            leaf = native.get(current.get("id"))
            if leaf is not None:
                if leaf["builtin_name"] in {"__builtin_huge_valf", "__builtin_nanf"}:
                    protocols[call["id"]] = {
                        "schema_version": "builtin-leaf-effect-assumption/v1",
                        "native_envelope_sha256": envelope_hash,
                        "call_expression_id": current["id"],
                        "callee_declaration_id": leaf["callee_declaration_id"],
                        "builtin_no_memory_write_assumed": True,
                        "valid_call_and_normal_return_assumed": True,
                        "evidence_reference": "development sensitivity assumption; not verified by this experiment",
                    }
                    selected_paths[call["id"]] = path
                break
            target = _callee(current, declarations).get("callee_id")
            matches = declarations.get(target, [])
            if len(matches) != 1:
                break
            bodies = [c for c in matches[0].get("inner", []) if c.get("kind") == "CompoundStmt"]
            if len(bodies) != 1 or len(bodies[0].get("inner", [])) != 1:
                break
            returned = bodies[0]["inner"][0]
            values = returned.get("inner", [])
            if returned.get("kind") != "ReturnStmt" or len(values) != 1 or values[0].get("kind") != "CallExpr":
                break
            current = values[0]
    default = recover(root, entry["id"], 32)
    print(json.dumps({"phase": "default_recovery", "profile": profile}), flush=True)
    conditional = recover_with_builtin_effects(payload, entry["id"], 32, protocols)
    print(json.dumps({"phase": "conditional_recovery", "status": conditional["status"]}), flush=True)
    guarded = []
    if guarded_work:
        # Select original loops containing break syntax, not a successful old
        # report or a per-kernel relation template. Each checker resolves exit
        # ownership, header and effects again from the original full AST.
        for loop in (node for node in walk(entry) if node.get("kind") == "ForStmt"):
            descendants = list(walk(loop))
            if not any(node.get("kind") == "BreakStmt" for node in descendants):
                continue
            call_ids = {node.get("id") for node in descendants if node.get("kind") == "CallExpr"}
            selected = {key: value for key, value in protocols.items() if key in call_ids}
            item = {"loop_id": loop["id"], "range": loop.get("range"), "call_protocols": selected}
            for label, premises in (("without_leaf_assumptions", {}), ("with_leaf_assumptions", selected)):
                item[label] = check_work_preservation(payload, loop["id"], 32, premises,
                    use_static_branches=True, use_nested_loops=True)
                print(json.dumps({"phase": "guarded_work", "loop": loop["id"], "mode": label,
                                  "status": item[label]["status"], "reason": item[label]["reason"]}), flush=True)
            guarded.append(item)
    after = implementation_hashes()
    report = {"schema_version": "softmax-builtin-effects-development/v1",
              "native_sha256": expected, "entry_id": entry["id"], "profile": profile,
              "int_bits": 32, "integer_abi_source": "explicit_external_assumption",
              "source_program_checked": False, "deployable": False, "GPU_executed": False,
              "role": "development_sensitivity_under_unverified_effect_assumptions_not_holdout",
              "driver_sha256": driver, "implementation_before": before, "implementation_after": after,
              "selected_paths": selected_paths, "call_protocols": protocols,
              "default": default, "conditional": conditional,
              "guarded_work_enabled": guarded_work, "guarded_work_checks": guarded,
              "default_loop_counts": dict(Counter(x["status"] for x in default["loops"])),
              "conditional_loop_counts": dict(Counter(x["status"] for x in conditional["recovery"]["loops"])),
              "inputs_unchanged": before == after and sha(native_path) == expected and sha(__file__) == driver}
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"output": str(output), "sha256": sha(output),
                      "default": report["default_loop_counts"], "conditional": report["conditional_loop_counts"],
                      "protocols": len(protocols), "inputs_unchanged": report["inputs_unchanged"]}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--profile", choices=("cuda-sm80", "hip-gfx1100"), default="cuda-sm80")
    parser.add_argument("--guarded-work", action="store_true")
    args = parser.parse_args()
    run(args.native, args.output, profile=args.profile, guarded_work=args.guarded_work)
