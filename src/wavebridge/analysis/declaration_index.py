"""Root-local exact-ID declaration indexing for collected Clang AST reports."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

INPUT_SCHEMA = "clang-ast-source/v1"
SCHEMA_VERSION = "declaration-index/v1"
BODY_KINDS = {"CompoundStmt", "CXXTryStmt", "CoroutineBodyStmt"}


def _canonical_hash(value: object) -> str:
    digest = hashlib.sha256()
    encoder = json.JSONEncoder(sort_keys=True, separators=(",", ":"),
                               ensure_ascii=False, allow_nan=False)
    for chunk in encoder.iterencode(value):
        digest.update(chunk.encode())
    return digest.hexdigest()


def _children(node: dict[str, Any]) -> list[dict[str, Any]]:
    inner = node.get("inner", [])
    return [child for child in inner if isinstance(child, dict)] if isinstance(inner, list) else []


def _walk(node: dict[str, Any]):
    yield node
    for child in _children(node):
        yield from _walk(child)


def _is_declaration(node: dict[str, Any]) -> bool:
    kind = node.get("kind")
    return isinstance(kind, str) and kind.endswith("Decl") and isinstance(node.get("id"), str)


def _namespaced(report_hash: str, root_index: int, clang_id: object) -> str | None:
    return (f"{report_hash}:root{root_index}:{clang_id}"
            if isinstance(clang_id, str) else None)


def _declaration_fact(node: dict[str, Any], report_hash: str,
                      root_index: int) -> dict[str, Any]:
    children = _children(node)
    return {
        "declaration_id": _namespaced(report_hash, root_index, node.get("id")),
        "clang_id": node["id"],
        "root_index": root_index,
        "kind": node.get("kind"),
        "name": node.get("name"),
        "range": node.get("range"),
        "initializer_present": "init" in node,
        "body_present": any(child.get("kind") in BODY_KINDS for child in children),
        "previous_decl_present": isinstance(node.get("previousDecl"), str),
        "previous_decl_followed": False,
    }


def build(report: object) -> dict[str, Any]:
    if not isinstance(report, dict):
        raise ValueError("input report must be an object")
    if report.get("schema_version") != INPUT_SCHEMA:
        raise ValueError("unsupported input schema")
    if report.get("status") != "collected":
        raise ValueError("input report status must be collected")
    roots = report.get("ast_roots")
    if not isinstance(roots, list) or any(not isinstance(root, dict) for root in roots):
        raise ValueError("ast_roots must be a list of objects")
    report_hash = _canonical_hash(report)
    declarations: list[dict[str, Any]] = []
    references: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    for root_index, root in enumerate(roots):
        nodes = list(_walk(root))
        root_index_by_id = {node["id"]: node for node in nodes if _is_declaration(node)}
        declarations.extend(_declaration_fact(node, report_hash, root_index)
                            for node in root_index_by_id.values())
        for node in nodes:
            target_id = None
            reference_kind = None
            if node.get("kind") == "DeclRefExpr":
                stub = node.get("referencedDecl")
                target_id = stub.get("id") if isinstance(stub, dict) else None
                reference_kind = "referencedDecl"
            elif "referencedMemberDecl" in node:
                member = node.get("referencedMemberDecl")
                target_id = member.get("id") if isinstance(member, dict) else member
                reference_kind = "referencedMemberDecl"
            else:
                continue
            target = root_index_by_id.get(target_id)
            fact = {
                "reference_id": _namespaced(report_hash, root_index, node.get("id")),
                "root_index": root_index,
                "reference_kind": reference_kind,
                "range": node.get("range"),
                "target_clang_id": target_id,
                "target_declaration_id": _namespaced(report_hash, root_index, target_id),
                "complete_declaration_node_found": target is not None,
                "previous_decl_followed": False,
            }
            if target is not None:
                declaration = _declaration_fact(target, report_hash, root_index)
                fact.update(target_kind=declaration["kind"], target_name=declaration["name"],
                            target_range=declaration["range"],
                            target_initializer_present=declaration["initializer_present"],
                            target_body_present=declaration["body_present"],
                            target_previous_decl_present=declaration["previous_decl_present"])
            else:
                unresolved.append({**fact, "reason": "no_exact_declaration_node_in_root"})
            references.append(fact)
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "index_built",
        "input_report_sha256": report_hash,
        "id_namespace": "<input_report_sha256>:root<root_index>:<clang_id>",
        "declarations": declarations,
        "references": references,
        "unresolved": unresolved,
        "join_policy": "exact_clang_id_within_same_root_only",
        "previous_decl_policy": "recorded_but_not_followed",
        "relation_recovery": "incomplete",
        "checked": False,
        "deployable": False,
        "manual_oracle_read": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    input_path, output_path = args.report.resolve(), args.output.resolve()
    if input_path == output_path:
        parser.error("--output must not overwrite the input report")
    if output_path.exists():
        parser.error("--output already exists; declaration indices are never overwritten")
    try:
        result = build(json.loads(input_path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, ValueError) as error:
        parser.error(str(error))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with output_path.open("x", encoding="utf-8") as stream:
            stream.write(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
    except FileExistsError:
        parser.error("--output already exists; declaration indices are never overwritten")
    print(json.dumps({"status": result["status"], "output": str(output_path)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
