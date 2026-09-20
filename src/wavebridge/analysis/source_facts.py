"""Structural facts from a collected Clang AST; this is not relation recovery."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

INPUT_SCHEMA = "clang-ast-source/v1"
SCHEMA_VERSION = "source-facts/v1"
CALL_WRAPPERS = {
    "ParenExpr", "ImplicitCastExpr", "CStyleCastExpr", "CXXStaticCastExpr",
    "CXXFunctionalCastExpr", "CXXReinterpretCastExpr", "CXXConstCastExpr",
    "CXXDynamicCastExpr",
}
OPERATOR_KINDS = {"BinaryOperator", "CompoundAssignOperator", "UnaryOperator"}
LOOP_KINDS = {"ForStmt", "WhileStmt", "DoStmt", "CXXForRangeStmt"}
UNSUPPORTED_CALL_KINDS = {"CXXMemberCallExpr", "CXXOperatorCallExpr", "CUDAKernelCallExpr"}


def _canonical_hash(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def _node_id(report_hash: str, root_index: int, raw_id: object) -> str | None:
    if not isinstance(raw_id, str):
        return None
    return f"{report_hash}:root{root_index}:{raw_id}"


def _children(node: dict[str, Any]) -> list[dict[str, Any]]:
    inner = node.get("inner", [])
    return [child for child in inner if isinstance(child, dict)] if isinstance(inner, list) else []


def _walk(node: dict[str, Any]):
    yield node
    for child in _children(node):
        yield from _walk(child)


def _unwrap_callee(node: dict[str, Any]) -> dict[str, Any]:
    current = node
    while current.get("kind") in CALL_WRAPPERS:
        children = _children(current)
        if len(children) != 1:
            break
        current = children[0]
    return current


def _direct_callee(node: dict[str, Any], report_hash: str,
                   root_index: int) -> dict[str, Any] | None:
    expression = _unwrap_callee(node)
    if expression.get("kind") != "DeclRefExpr":
        return None
    declaration = expression.get("referencedDecl")
    if not isinstance(declaration, dict) or declaration.get("kind") != "FunctionDecl":
        return None
    return {
        "name": declaration.get("name"),
        "declaration_id": _node_id(report_hash, root_index, declaration.get("id")),
        "expression_id": _node_id(report_hash, root_index, expression.get("id")),
    }


def extract(report: object) -> dict[str, Any]:
    """Extract syntax facts from one collected report, without consulting an oracle."""
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
    calls: list[dict[str, Any]] = []
    references: list[dict[str, Any]] = []
    operators: list[dict[str, Any]] = []
    loops: list[dict[str, Any]] = []
    for root_index, root in enumerate(roots):
        for node in _walk(root):
            kind = node.get("kind")
            namespaced_id = _node_id(report_hash, root_index, node.get("id"))
            if kind == "CallExpr":
                children = _children(node)
                callee = _direct_callee(children[0], report_hash, root_index) if children else None
                fact = {"node_id": namespaced_id, "root_index": root_index,
                        "range": node.get("range")}
                if callee is None:
                    fact.update(resolution="unknown", reason="indirect_or_unresolved_callee",
                                callee_expression_kind=children[0].get("kind") if children else None)
                else:
                    fact.update(resolution="direct", callee=callee)
                calls.append(fact)
            elif kind in UNSUPPORTED_CALL_KINDS:
                calls.append({"node_id": namespaced_id, "root_index": root_index,
                              "range": node.get("range"), "resolution": "unknown",
                              "reason": "unsupported_call_kind", "call_kind": kind})
            if kind == "DeclRefExpr":
                declaration = node.get("referencedDecl")
                references.append({
                    "node_id": namespaced_id,
                    "root_index": root_index,
                    "range": node.get("range"),
                    "referenced_kind": declaration.get("kind") if isinstance(declaration, dict) else None,
                    "referenced_name": declaration.get("name") if isinstance(declaration, dict) else None,
                    "declaration_id": _node_id(report_hash, root_index, declaration.get("id"))
                    if isinstance(declaration, dict) else None,
                })
            if kind in OPERATOR_KINDS:
                operators.append({"node_id": namespaced_id, "root_index": root_index,
                                  "kind": kind, "opcode": node.get("opcode"),
                                  "range": node.get("range")})
            if kind in LOOP_KINDS:
                loops.append({"node_id": namespaced_id, "root_index": root_index,
                              "kind": kind, "range": node.get("range")})
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "facts_extracted",
        "input_report_sha256": report_hash,
        "id_namespace": "<input_report_sha256>:root<root_index>:<clang_id>",
        "facts": {"calls": calls, "declaration_references": references,
                  "operators": operators, "loops": loops},
        "fact_extraction_only": True,
        "relation_recovery": "incomplete",
        "deployable": False,
        "manual_oracle_read": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    report_path, output_path = args.report.resolve(), args.output.resolve()
    if report_path == output_path:
        parser.error("--output must not overwrite the input report")
    try:
        input_report = json.loads(report_path.read_text(encoding="utf-8"))
        result = extract(input_report)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        parser.error(str(error))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with output_path.open("x", encoding="utf-8") as stream:
            stream.write(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
    except FileExistsError:
        parser.error("--output already exists; source facts are never overwritten")
    print(json.dumps({"status": result["status"], "output": str(output_path)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
