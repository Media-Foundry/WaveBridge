"""Pinned softmax history replay under explicit, unverified development premises."""
import argparse
import json
from pathlib import Path

from experiments.pytorch_softmax_intake import implementation_hashes, select_entry, sha, walk
from wavebridge.analysis.column_loops import _hinted_loop, _static_bool_value, _Unknown
from wavebridge.verification.getter_returns import _hash
from wavebridge.verification.initializer_domain import check_to_statement

NATIVE_SHA = "a59c12247f796fe2034ba03ecc43782f77ac3942496b18a140ceacbb24c7ff45"
LEAF_PROTOCOL_SHA = "c9a085aa07bf43e2e3a9221dc92bce58b5237e9ddc4a1b9568ca454b1f065996"
PREMISE = "UNVERIFIED development sensitivity assumption, not a certificate or SDK purity proof"


def calls_on_supported_paths(node):
    """Mirror only the history checker's static branch selection, not its verdict."""
    children = node.get("inner", [])
    if (node.get("kind") == "IfStmt" and
            not any(node.get(flag) for flag in ("hasInit", "hasVar", "isConstexpr", "isConsteval")) and
            len(children) == (3 if node.get("hasElse") else 2)):
        try:
            value = _static_bool_value(children[0])
        except _Unknown:
            pass
        else:
            children = [children[0]] + ([children[1]] if value else children[2:])
    if node.get("kind") == "CallExpr":
        yield node
    for child in children:
        yield from calls_on_supported_paths(child)


def direct_target(call):
    node = call["inner"][0]
    while node.get("kind") in {"ImplicitCastExpr", "ParenExpr"}:
        if len(node.get("inner", [])) != 1:
            raise ValueError("callee_shape_unsupported")
        node = node["inner"][0]
    if node.get("kind") != "DeclRefExpr":
        raise ValueError("callee_not_direct")
    return node["referencedDecl"]["id"]


def run(native, leaf_protocol, output):
    if sha(native) != NATIVE_SHA or sha(leaf_protocol) != LEAF_PROTOCOL_SHA or output.exists():
        raise ValueError("fixed_input_mismatch_or_output_exists")
    dependencies = {str(p): sha(p) for p in (Path(__file__), leaf_protocol,
                    Path(__file__).with_name("pytorch_softmax_intake.py"))}
    before = implementation_hashes()
    capture = json.loads(native.read_text())
    if capture.get("status") != "collected":
        raise ValueError("capture_not_collected")
    payload = capture["payload"]
    root = payload["ast"]
    native_hash, root_hash = _hash(payload), _hash(root)
    entry = select_entry(root)
    body, = [n for n in entry["inner"] if n.get("kind") == "CompoundStmt"]
    statements = body["inner"]
    protected, = [n for n in walk(entry) if n.get("kind") == "VarDecl" and n.get("name") == "local_idx"]
    # Frozen source position, selected before looking at any checking results.
    target = _hinted_loop(statements[20])
    if (entry["id"] != "0x30d762e0" or protected["id"] != "0x30ddbeb0" or
            statements[20]["id"] != "0x30de6830"):
        raise ValueError("fixed_source_selection_mismatch")
    declarations = {}
    for node in walk(root):
        if node.get("kind") in {"FunctionDecl", "CXXMethodDecl"}:
            declarations.setdefault(node["id"], []).append(node)

    def declaration(identifier):
        candidates = declarations.get(identifier, [])
        if len(candidates) != 1:
            raise ValueError("declaration_not_unique")
        return candidates[0]

    def leaf(call):
        for _ in range(5):
            selected = declaration(direct_target(call))
            bodies = [n for n in selected.get("inner", []) if n.get("kind") == "CompoundStmt"]
            if not bodies:
                return call, selected
            returns = bodies[0].get("inner", [])
            if len(returns) != 1 or returns[0].get("kind") != "ReturnStmt":
                raise ValueError("wrapper_not_single_return")
            expression, = returns[0]["inner"]
            while expression.get("kind") in {"ImplicitCastExpr", "ParenExpr"}:
                expression, = expression["inner"]
            if expression.get("kind") != "CallExpr":
                raise ValueError("wrapper_return_not_call")
            call = expression
        raise ValueError("wrapper_depth_exceeded")

    base = json.loads(leaf_protocol.read_text())
    if base["native_envelope_sha256"] != native_hash:
        raise ValueError("leaf_native_mismatch")
    protocols = {}
    for statement in statements[8:20]:
        for call in calls_on_supported_paths(statement):
            callee = declaration(direct_target(call))
            signature = callee.get("type", {}).get("qualType")
            if signature == "void (float *)":
                inner, = [n for n in walk(callee) if n.get("kind") == "CallExpr" and
                          direct_target(n) == "0x30d89288"]
                accessible = dict(base, call_expression_id=inner["id"])
                protocol = {"schema_version": "array-call-preservation-request/v1",
                            "native_envelope_sha256": native_hash, "call_expression_id": call["id"],
                            "protected_declaration_id": protected["id"],
                            "accessible_call_protocols": {inner["id"]: accessible}}
            elif signature in {"float ()", "float () noexcept"}:
                leaf_call, leaf_decl = leaf(call)
                protocol = {"schema_version": "builtin-leaf-effect-assumption/v1",
                            "native_envelope_sha256": native_hash,
                            "call_expression_id": leaf_call["id"], "callee_declaration_id": leaf_decl["id"],
                            "builtin_no_memory_write_assumed": True,
                            "valid_call_and_normal_return_assumed": True, "evidence_reference": PREMISE}
            elif signature in {"float (float)", "float (float) noexcept"}:
                _, leaf_decl = leaf(call)
                protocol = {"schema_version": "scalar-leaf-effect-assumption/v1", "root_sha256": root_hash,
                            "call_expression_id": call["id"], "leaf_declaration_id": leaf_decl["id"],
                            "leaf_no_memory_write_assumed": True,
                            "valid_call_and_normal_return_assumed": True, "evidence_reference": PREMISE}
            else:
                raise ValueError(f"unsupported_development_protocol_route: {signature}")
            protocols[call["id"]] = protocol
    getter = declaration("0x2dc8c548")
    if getter.get("name") != "__nvvm_read_ptx_sreg_tid_x":
        raise ValueError("getter_selection_mismatch")
    contract = {"schema_version": "getter-leaf-domain/v1", "declaration_id": getter["id"],
                "arguments": [], "return_type": {"qualType": "int"}, "lower": 0, "upper": 31}
    abi = {"int": {"bits": 32, "signed": True}, "unsigned int": {"bits": 32, "signed": False}}
    print(json.dumps({"phase": "protocols_bound", "calls": list(protocols), "target": target["id"]}), flush=True)
    checked = check_to_statement(payload, protected["id"], target["id"], contract, abi,
                                 protocols, use_static_branches=True)
    after = implementation_hashes()
    report = {"schema_version": "softmax-native-history-development/v1", "check": checked,
              "native_sha256": NATIVE_SHA, "call_protocols": protocols, "leaf_contract": contract,
              "integer_types": abi, "implementation_before": before, "implementation_after": after,
              "driver_dependencies": dependencies, "GPU_executed": False,
              "source_program_checked": False, "deployable": False,
              "premise_scope": "External leaf range/effects remain unverified; not launch or coordinate proof",
              "inputs_unchanged": before == after and sha(native) == NATIVE_SHA and
              all(sha(p) == digest for p, digest in dependencies.items())}
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": checked["status"], "reason": checked["reason"],
                      "unknown_call_id": checked.get("unknown_call_id"), "sha256": sha(output),
                      "inputs_unchanged": report["inputs_unchanged"]}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native", type=Path, required=True)
    parser.add_argument("--leaf-protocol", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.native, args.leaf_protocol, args.output)
