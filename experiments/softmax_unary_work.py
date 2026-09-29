"""Fresh guarded-work or entry-recurrence replay under unverified leaf premises.

Prior reports supply only protocol dictionaries, never successful conclusions.
"""
import argparse
import json
from pathlib import Path

from experiments.pytorch_softmax_intake import implementation_hashes, select_entry, sha, walk
from wavebridge.verification.loop_exit_guards import check_work_preservation
from wavebridge.analysis.column_loops import recover_with_call_effects

NATIVE_SHA = "46ac52b1c672fadd0e5a66bb3ab380373e0cd69929713d96e7010f375a0cd63e"
MATH_SHA = "a8af8a027126343d9221d593efdd2a1e709b1ba1588d89ee129fcf21fa9f617b"
ZERO_SHA = "7952d53d103ccbf4c130fc4c775a67b726a039b4c652eddc4b270dc42939de87"


def run(native, math_protocols, zero_protocols, output, *, recurrence=False):
    if type(recurrence) is not bool:
        raise ValueError("invalid_recurrence_option")
    paths = [Path(p).resolve() for p in (native, math_protocols, zero_protocols)]
    expected = [NATIVE_SHA, MATH_SHA, ZERO_SHA]
    if [sha(p) for p in paths] != expected:
        raise ValueError("sealed_input_mismatch")
    output = Path(output).resolve()
    if output.exists():
        raise ValueError("output_already_exists")
    before, driver = implementation_hashes(), sha(__file__)
    source, math, zero = [json.loads(p.read_text()) for p in paths]
    if source.get("status") != "collected":
        raise ValueError("native_not_collected")
    payload = source["payload"]
    entry = select_entry(payload["ast"])
    math = math["external_effect_protocols"]
    protocols = dict(zero["call_protocols"])
    if set(protocols) & set(math):
        raise ValueError("protocol_identity_collision")
    protocols.update(math)
    results = []
    recurrence_checks = {}
    if recurrence:
        for label, enabled in (("default", False), ("unary_enabled", True)):
            print(json.dumps({"phase": "recurrence_" + label, "function_id": entry["id"]}), flush=True)
            checked = recover_with_call_effects(payload, entry["id"], 32, protocols,
                allow_unary_float=enabled, allow_using_shadows=enabled)
            recurrence_checks[label] = checked
            print(json.dumps({"phase": "recurrence_" + label + "_done", "status": checked["status"],
                              "reason": checked["reason"]}), flush=True)
    for node in walk(entry):
        if recurrence:
            break
        if node.get("kind") != "ForStmt":
            continue
        descendants = list(walk(node))
        ids = {n.get("id") for n in descendants}
        if not ids.intersection(math) or not any(n.get("kind") == "BreakStmt" for n in descendants):
            continue
        selected = {k: v for k, v in protocols.items() if k in ids}
        item = {"loop_id": node["id"], "range": node.get("range"), "call_protocols": selected}
        for label, enabled in (("default", False), ("unary_enabled", True)):
            print(json.dumps({"phase": label, "loop_id": node["id"]}), flush=True)
            checked = check_work_preservation(payload, node["id"], 32, selected,
                use_static_branches=False, use_nested_loops=True,
                allow_unary_float=enabled, allow_using_shadows=enabled)
            item[label] = checked
            print(json.dumps({"phase": label + "_done", "status": checked["status"],
                              "reason": checked["reason"]}), flush=True)
        results.append(item)
    after = implementation_hashes()
    stable = before == after and driver == sha(__file__) and [sha(p) for p in paths] == expected
    report = {"schema_version": "softmax-unary-entry-recurrence/v1" if recurrence else "softmax-unary-guarded-work/v1",
        "mode": "entry_recurrence" if recurrence else "guarded_work",
        "status": "observed" if stable else "inputs_changed",
        "inputs_unchanged": stable, "input_files": dict(zip(map(str, paths), expected)),
        "implementation_before": before, "implementation_after": after, "driver_sha256": driver,
        "entry_id": entry["id"], "checks": results, "int_bits": 32,
        "recurrence_enabled": recurrence, "recurrence_checks": recurrence_checks,
        "integer_abi_source": "external int32 assumption; not newly probed",
        "selection": ("fresh full selected-entry recurrence using all sealed protocol dictionaries; no guarded-loop preselection"
                      if recurrence else "syntactic loops containing a selected math call and a break; non-exhaustive"),
        "result_fields": {"checks": "guarded-work-only", "recurrence_checks": "entry-recurrence-only"},
        "static_branches_pruned": False, "external_call_effects_verified": False,
        "source_program_checked": False, "deployable": False, "GPU_executed": False,
        "previous_success_reports_consumed": False}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": report["status"], "output": str(output), "sha256": sha(output)}), flush=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("native", "math-protocols", "zero-protocols", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--recurrence", action="store_true",
                        help="instead replay full selected-function recurrence with default/opt-in call checks")
    args = parser.parse_args()
    result = run(args.native, args.math_protocols, args.zero_protocols, args.output, recurrence=args.recurrence)
    return 0 if result["inputs_unchanged"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
