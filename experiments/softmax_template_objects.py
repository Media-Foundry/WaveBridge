"""Inspect exact native object/constructor bindings in the fixed softmax specialization."""
import argparse
import json
from pathlib import Path

from experiments.pytorch_softmax_intake import select_entry, sha, walk


def one(items):
    if len(items) != 1:
        raise ValueError("selection_missing_or_ambiguous")
    return items[0]


def run(native, output):
    if output.exists():
        raise ValueError("output_exists")
    digest = sha(native)
    capture = json.loads(native.read_text())
    if capture.get("status") != "collected":
        raise ValueError("native_not_collected")
    payload = capture["payload"]
    root = payload["ast"]
    entry = select_entry(root)
    array = one([n for n in walk(entry) if n.get("kind") == "VarDecl" and n.get("name") == "max_value"])
    calls = []
    for n in walk(entry):
        parts = n.get("inner", [])
        if n.get("kind") == "CallExpr" and len(parts) == 2:
            references = [x for x in walk(parts[1]) if x.get("kind") == "DeclRefExpr"]
            if len(references) == 1 and references[0].get("referencedDecl", {}).get("id") == array["id"]:
                calls.append(n)
    call = one(calls)
    ref = one([n for n in walk(call["inner"][0]) if n.get("kind") == "DeclRefExpr"])
    callee = one([n for n in walk(root) if n.get("id") == ref["referencedDecl"]["id"]])
    local = one([n for n in walk(callee) if n.get("kind") == "VarDecl" and
                 any(c.get("kind") == "CXXConstructExpr" for c in n.get("inner", []))])
    constructor = one([n for n in local["inner"] if n.get("kind") == "CXXConstructExpr"])
    record_observation = one([n for n in payload.get("local_record_objects", [])
                              if n.get("variable_declaration_id") == local["id"]])
    ctor_observation = one([n for n in payload.get("constructor_calls", [])
                            if n.get("expression_id") == constructor["id"]])
    record = one([n for n in walk(root) if n.get("id") == record_observation["record_declaration_id"]])
    declaration = one([n for n in record.get("inner", [])
                       if n.get("id") == ctor_observation["constructor_declaration_id"]])
    if (ctor_observation["record_declaration_id"] != record["id"] or
            declaration.get("kind") != "CXXConstructorDecl"):
        raise ValueError("constructor_record_binding_mismatch")
    report = {"schema_version": "softmax-template-object-observation/v1", "status": "observed",
              "native_sha256": digest, "entry_id": entry["id"], "call_id": call["id"],
              "callee_id": callee["id"], "local_record_observation": record_observation,
              "constructor_observation": ctor_observation, "record_definition_data": record.get("definitionData"),
              "constructor_declaration": declaration, "source_program_checked": False,
              "lifecycle_effects_checked": False, "deployable": False, "GPU_executed": False,
              "driver_sha256": sha(__file__), "selector_sha256": sha(Path(__file__).with_name("pytorch_softmax_intake.py")),
              "inputs_unchanged": sha(native) == digest}
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": report["status"], "local": record_observation,
                      "constructor": ctor_observation, "sha256": sha(output),
                      "inputs_unchanged": report["inputs_unchanged"]}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    run(args.native, args.output)
