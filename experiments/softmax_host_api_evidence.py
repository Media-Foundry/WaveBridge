"""Pinned upstream API provenance and exact AST call observation, not API proof."""

import argparse
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen

from experiments.pytorch_softmax_intake import sha
from experiments.softmax_launch_native import NATIVE_SHA
from wavebridge.verification.getter_returns import _hash


COMMIT = "a8d6afb511a69687bbb2b7e88a3cf67917e1697e"
BASE_URL = f"https://raw.githubusercontent.com/pytorch/pytorch/{COMMIT}/"
SOURCES = {
    "aten/src/ATen/cuda/CUDAContext.cpp": "41e17aca9ce11e2ff961f2877244899462efb7ecc0ca657891cdd7363b1a8d81",
    "LICENSE": "47a26beb94e3f6b333a3677fc85d546f1fdfd2f0b3686c26d2fb5b10e0134165",
}


def verify_download(data, expected_sha):
    if not isinstance(data, bytes) or hashlib.sha256(data).hexdigest() != expected_sha:
        raise ValueError("pinned_source_hash_mismatch")
    return data.decode("utf-8")


def observe_call(root, call_id, declaration_id, initializer_id, *, max_ast_nodes=10_000_000):
    """Record exact syntax and symbol evidence without inferring a return domain."""
    if (not isinstance(root, dict) or root.get("kind") != "TranslationUnitDecl" or
            type(max_ast_nodes) is not int or not 1 <= max_ast_nodes <= 10_000_000 or
            any(not isinstance(i, str) or not i for i in (call_id, declaration_id, initializer_id))):
        raise ValueError("invalid_inputs_or_budget")
    nodes, pending, index, locations = [], [(root, None, None, None)], {}, {}
    while pending:
        node, parent, grandparent, function = pending.pop()
        if not isinstance(node, dict):
            raise ValueError("malformed_ast_node")
        nodes.append(node)
        if len(nodes) > max_ast_nodes:
            raise ValueError("ast_budget_exceeded")
        children = node.get("inner", [])
        if not isinstance(children, list) or any(not isinstance(c, dict) for c in children):
            raise ValueError("malformed_ast_children")
        if node.get("id") in (call_id, declaration_id, initializer_id):
            index.setdefault(node["id"], []).append(node)
            locations[node["id"]] = (parent, grandparent, function)
        if node.get("kind") == "FunctionDecl":
            function = node
        pending.extend((c, node, parent, function) for c in children)
    if any(len(index.get(i, [])) != 1 for i in (call_id, declaration_id, initializer_id)):
        raise ValueError("selected_identity_not_unique")
    call, declaration, initializer = (index[i][0] for i in (call_id, declaration_id, initializer_id))
    parent, grandparent, function = locations[initializer_id]
    if (function is None or parent is None or parent.get("kind") != "DeclStmt" or
            grandparent is None or grandparent.get("kind") != "CompoundStmt"):
        raise ValueError("initializer_not_direct_automatic_block_variable")
    if (call.get("kind") != "CallExpr" or call.get("type", {}).get("qualType") != "int" or
            declaration.get("kind") != "FunctionDecl" or declaration.get("type", {}).get("qualType") != "int ()" or
            any(c.get("kind") == "ParmVarDecl" for c in declaration.get("inner", [])) or
            initializer.get("kind") != "VarDecl" or initializer.get("type", {}).get("qualType") != "int" or
            initializer.get("storageClass") not in (None, "auto", "register") or
            initializer.get("tls") not in (None, "none") or initializer.get("tlsKind") not in (None, "none") or
            initializer.get("inner") != [call]):
        raise ValueError("call_or_initializer_shape_unsupported")
    children = call.get("inner", [])
    if len(children) != 1:
        raise ValueError("call_not_zero_argument")
    callee = children[0]
    if (callee.get("kind") != "ImplicitCastExpr" or callee.get("castKind") != "FunctionToPointerDecay" or
            len(callee.get("inner", [])) != 1):
        raise ValueError("callee_not_direct_decay")
    reference = callee["inner"][0]
    referenced = reference.get("referencedDecl", {})
    if (reference.get("kind") != "DeclRefExpr" or reference.get("inner", []) or
            referenced.get("kind") != "FunctionDecl" or referenced.get("id") != declaration_id or
            referenced.get("type") != declaration.get("type")):
        raise ValueError("callee_declaration_binding_mismatch")
    mangled = declaration.get("mangledName")
    if not isinstance(mangled, str) or not mangled:
        raise ValueError("symbol_identity_missing")
    definitions = [n.get("id") for n in nodes if n.get("kind") == "FunctionDecl" and
                   n.get("mangledName") == mangled and
                   any(c.get("kind") == "CompoundStmt" for c in n.get("inner", []))]
    return {"status": "observed", "call_id": call_id, "declaration_id": declaration_id,
            "initializer_id": initializer_id, "mangled_name": mangled,
            "call_ast": call, "declaration_ast": declaration,
            "matching_symbol_definition_ids_observed": definitions,
            "runtime_return_interval": None, "runtime_implementation_linkage_verified": False,
            "api_no_memory_write_established": False, "source_program_checked": False, "deployable": False}


def run(native, output):
    if output.exists() or sha(native) != NATIVE_SHA:
        raise ValueError("native_mismatch_or_output_exists")
    paths = [Path(__file__), Path(__file__).with_name("pytorch_softmax_intake.py"),
             Path(__file__).with_name("softmax_launch_native.py"),
             Path("src/wavebridge/verification/getter_returns.py")]
    dependencies = {str(p): sha(p) for p in paths}
    source_evidence = {}
    for path, digest in SOURCES.items():
        with urlopen(BASE_URL + path, timeout=20) as response:
            data = response.read(1_000_001)
        if len(data) > 1_000_000:
            raise ValueError("source_size_limit")
        source_evidence[path] = {"url": BASE_URL + path, "sha256": digest,
                                 "text": verify_download(data, digest)}
    capture = json.loads(native.read_text())
    if capture.get("status") != "collected":
        raise ValueError("native_not_collected")
    root = capture["payload"]["ast"]
    observed = observe_call(root, "0x30d69260", "0x3020c788", "0x30d691d8")
    report = {"schema_version": "softmax-host-api-provenance/v1", "status": "observed",
              "upstream_commit": COMMIT, "source_evidence": source_evidence,
              "native_sha256": NATIVE_SHA, "ast_root_sha256": _hash(root),
              "call_observation": observed, "driver_dependencies": dependencies,
              "source_semantics_automatically_checked": False,
              "runtime_implementation_linkage_verified": False,
              "runtime_device_binding_established": False, "runtime_return_interval": None,
              "GPU_executed": False, "source_program_checked": False, "deployable": False,
              "limitations": ["upstream source content is pinned, not linked to a running binary",
                              "matching symbol text is not cross-translation-unit semantic validation",
                              "separate HIP W7900 probes do not establish this CUDA call result"],
              "inputs_unchanged": sha(native) == NATIVE_SHA and
                  all(sha(p) == h for p, h in dependencies.items())}
    with output.open("x") as stream:
        stream.write(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": "observed", "inputs_unchanged": report["inputs_unchanged"],
                      "sha256": sha(output), "runtime_return_interval": None}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.native, args.output)
