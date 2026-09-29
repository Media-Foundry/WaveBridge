"""Pinned HIP initializer diagnostic; no lane/launch range is guessed."""
import argparse
import json
from pathlib import Path

from experiments.pytorch_softmax_intake import implementation_hashes, sha, walk
from wavebridge.verification.initializer_domain import check_source

NATIVE_SHA = "46ac52b1c672fadd0e5a66bb3ab380373e0cd69929713d96e7010f375a0cd63e"
DECLARATION_ID = "0x745c579bb0c0"
ABI = {"int": {"bits": 32, "signed": True}, "unsigned int": {"bits": 32, "signed": False},
       "unsigned long": {"bits": 64, "signed": False}}


def literal_arguments(call):
    """Select only literal candidates; the getter checker rechecks conversions."""
    values = []
    for argument in call.get("inner", [])[1:]:
        node = argument
        for _ in range(32):
            if node.get("kind") == "ParenExpr" or (
                    node.get("kind") == "ImplicitCastExpr" and
                    node.get("castKind") in {"IntegralCast", "NoOp"}):
                if len(node.get("inner", [])) != 1:
                    raise ValueError("diagnostic_argument_not_literal")
                node = node["inner"][0]
            else:
                break
        if node.get("kind") != "IntegerLiteral":
            raise ValueError("diagnostic_argument_not_literal")
        value = int(node["value"])
        if not 0 <= value < (1 << 128):
            raise ValueError("diagnostic_argument_out_of_range")
        values.append(value)
    return values


def run(native, output):
    native, output = Path(native).resolve(), Path(output).resolve()
    if sha(native) != NATIVE_SHA or output.exists():
        raise ValueError("fixed_input_mismatch_or_output_exists")
    before = implementation_hashes()
    dependencies = {str(p): sha(p) for p in (Path(__file__).resolve(),
        Path(__file__).with_name("pytorch_softmax_intake.py").resolve())}
    captured = json.loads(native.read_text())
    if captured.get("status") != "collected":
        raise ValueError("native_not_collected")
    payload = captured["payload"]
    root = payload["ast"]
    initial = check_source(root, DECLARATION_ID, {}, ABI)
    result = {"schema_version": "hip-initializer-full-type-diagnostic/v1",
        "native_sha256": NATIVE_SHA, "declaration_id": DECLARATION_ID,
        "without_leaf_domain": initial, "full_type_domain_check": None,
        "observed_path": [], "diagnostic_reason": None, "integer_types": ABI,
        "integer_abi_source": "explicit external integer ABI; not newly measured",
        "scope": "one fixed source initializer, not value history or launch semantics",
        "source_program_checked": False, "deployable": False, "GPU_executed": False,
        "lane_range_established": False, "leaf_value_semantics_verified": False}
    try:
        link = initial.get("checks", {}).get("value_link", {})
        if link.get("status") != "recovered":
            raise ValueError("initializer_link_not_recovered")
        index = {}
        for node in walk(root):
            if node.get("kind") in {"FunctionDecl", "CXXMethodDecl"}:
                index.setdefault(node.get("id"), []).append(node)
        current, visited = link["callee_declaration_id"], set()
        for _ in range(32):
            if current in visited or len(index.get(current, [])) != 1:
                raise ValueError("diagnostic_declaration_not_unique_or_cycle")
            visited.add(current)
            declaration = index[current][0]
            bodies = [n for n in declaration.get("inner", []) if n.get("kind") == "CompoundStmt"]
            if len(bodies) != 1:
                raise ValueError("diagnostic_body_not_unique")
            calls = [n for n in walk(bodies[0]) if n.get("kind") == "CallExpr"]
            if len(calls) != 1:
                raise ValueError("diagnostic_not_one_call")
            call = calls[0]
            callee = call["inner"][0]
            while callee.get("kind") in {"ImplicitCastExpr", "ParenExpr"} and len(callee.get("inner", [])) == 1:
                callee = callee["inner"][0]
            ref = callee.get("referencedDecl", {})
            if callee.get("kind") != "DeclRefExpr" or ref.get("kind") != "FunctionDecl":
                raise ValueError("diagnostic_not_direct_reference")
            result["observed_path"].append({"caller": current, "call_id": call["id"], "callee": ref["id"]})
            records = [r for r in payload["builtin_calls"] if r["call_expression_id"] == call["id"]]
            declarations = index.get(ref["id"], [])
            external = (len(declarations) == 1 and not any(
                n.get("kind") == "CompoundStmt" for n in declarations[0].get("inner", [])))
            if records or external:
                arguments = literal_arguments(call)
                type_evidence = call.get("type", {})
                spelling = type_evidence.get("desugaredQualType") or type_evidence.get("qualType")
                if spelling not in ABI or ABI[spelling]["signed"]:
                    raise ValueError("diagnostic_leaf_type_or_arity_unsupported")
                if records and (len(records) != 1 or records[0]["callee_declaration_id"] != ref["id"]):
                    raise ValueError("diagnostic_native_record_conflict")
                if records and arguments:
                    raise ValueError("diagnostic_native_arity_unsupported")
                contract = {"schema_version": "getter-leaf-domain/v1", "declaration_id": ref["id"],
                    "arguments": arguments, "return_type": type_evidence, "lower": 0, "upper": (1 << ABI[spelling]["bits"]) - 1}
                result.update(native_leaf_observation=records[0] if records else None,
                    external_leaf_observation=declarations[0] if external else None,
                    leaf_call_observation=call, leaf_contract=contract,
                    domain_policy="full unsigned return-type range only; no narrowed lane assumption")
                print(json.dumps({"phase": "full_type_domain", "leaf": ref["id"], "type": spelling}), flush=True)
                result["full_type_domain_check"] = check_source(root, DECLARATION_ID, contract, ABI)
                break
            current = ref["id"]
        else:
            raise ValueError("diagnostic_depth_budget")
    except (ValueError, KeyError, TypeError) as error:
        result["diagnostic_reason"] = str(error)
    after = implementation_hashes()
    stable = before == after and sha(native) == NATIVE_SHA and all(sha(p) == h for p, h in dependencies.items())
    result.update(status="observed" if stable else "inputs_changed", inputs_unchanged=stable,
                  implementation_before=before, implementation_after=after, driver_dependencies=dependencies)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": result["status"], "reason": result["diagnostic_reason"],
                      "output": str(output), "sha256": sha(output)}), flush=True)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.native, args.output)
    raise SystemExit(0 if result["inputs_unchanged"] else 2)
