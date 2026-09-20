"""Evidence-preserving Clang JSON AST ingestion; no relation recovery occurs here.

Relative source, compiler, and output paths use the launcher's current directory. ``--cwd``
only sets the compiler subprocess directory, including the base for its relative include flags.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import signal
import subprocess
import time
from typing import Any

SCHEMA_VERSION = "clang-ast-source/v1"
FUNCTION_KINDS = {"FunctionDecl", "CXXMethodDecl", "CXXConstructorDecl",
                  "CXXConversionDecl", "FunctionTemplateDecl"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _text(value: bytes | str | None) -> str:
    if value is None:
        return ""
    return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value


def invoke(command: list[str], timeout: float, cwd: Path) -> dict[str, Any]:
    """Run one compiler process group and retain raw text for every terminal state."""
    started = time.monotonic()
    record: dict[str, Any] = {"command": command, "cwd": str(cwd),
                              "timeout_seconds": timeout}
    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   start_new_session=True, cwd=cwd)
        try:
            stdout, stderr = process.communicate(timeout=timeout)
            record.update(status="completed", returncode=process.returncode,
                          stdout=_text(stdout), stderr=_text(stderr))
        except subprocess.TimeoutExpired as error:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            stdout, stderr = process.communicate()
            record.update(status="timeout", returncode=None,
                          stdout=_text(stdout) or _text(error.stdout),
                          stderr=_text(stderr) or _text(error.stderr))
    except OSError as error:
        record.update(status="launch_failed", returncode=None, stdout="", stderr=str(error))
    record["duration_seconds"] = round(time.monotonic() - started, 6)
    return record


def parse_json_roots(raw: str) -> list[dict[str, Any]]:
    """Parse Clang's whitespace-separated JSON documents without assuming one root."""
    decoder = json.JSONDecoder()
    roots: list[dict[str, Any]] = []
    offset = 0
    while True:
        while offset < len(raw) and raw[offset].isspace():
            offset += 1
        if offset == len(raw):
            return roots
        value, offset = decoder.raw_decode(raw, offset)
        if not isinstance(value, dict):
            raise ValueError("each Clang AST JSON root must be an object")
        roots.append(value)


def _walk(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.get("inner", []):
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def function_locations(roots: list[dict[str, Any]], symbol: str) -> list[dict[str, Any]]:
    locations = []
    for root_index, root in enumerate(roots):
        for node in _walk(root):
            if node.get("kind") not in FUNCTION_KINDS:
                continue
            if node.get("name") != symbol and node.get("qualifiedName") != symbol:
                continue
            locations.append({key: value for key, value in {
                "root_index": root_index,
                "id": node.get("id"),
                "kind": node.get("kind"),
                "name": node.get("name"),
                "qualified_name": node.get("qualifiedName"),
                "mangled_name": node.get("mangledName"),
                "location": node.get("loc"),
                "range": node.get("range"),
            }.items() if value is not None})
    return locations


def collect(source: str | Path, compiler: str, compiler_args: list[str], symbol: str,
            timeout: float = 30.0, cwd: str | Path | None = None,
            full_translation_unit: bool = False) -> dict[str, Any]:
    """Collect genuine AST roots and source locations, with no semantic interpretation."""
    source_path = Path(source).resolve()
    workdir = Path(cwd).resolve() if cwd is not None else Path.cwd().resolve()
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": "input_error",
        "source": str(source_path),
        "source_sha256": None,
        "compiler": compiler,
        "compiler_sha256": None,
        "cwd": str(workdir),
        "symbol": symbol,
        "collection_scope": "translation_unit" if full_translation_unit else "symbol_filter",
        "command": None,
        "execution": None,
        "ast_roots": [],
        "function_locations": [],
        "relation_recovery": "not_implemented",
        "manual_oracle_read": False,
    }
    if (not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or
            not math.isfinite(timeout) or timeout <= 0):
        report["reason"] = "invalid_timeout"
        return report
    if not symbol:
        report["reason"] = "empty_symbol"
        return report
    if not source_path.is_file():
        report["reason"] = "source_missing"
        return report
    try:
        report["source_sha256"] = _sha256(source_path)
    except OSError as error:
        report["reason"] = "source_unreadable"
        report["detail"] = str(error)
        return report
    compiler_path_text = shutil.which(compiler) if not Path(compiler).is_absolute() else compiler
    compiler_path = Path(compiler_path_text).resolve() if compiler_path_text else None
    if compiler_path is None or not compiler_path.is_file():
        report["status"] = "tool_missing"
        report["reason"] = "compiler_missing"
        return report
    report["compiler"] = str(compiler_path)
    try:
        report["compiler_sha256"] = _sha256(compiler_path)
    except OSError as error:
        report["status"] = "tool_missing"
        report["reason"] = "compiler_unreadable"
        report["detail"] = str(error)
        return report
    command = [str(compiler_path), *compiler_args, "-fsyntax-only", "-Xclang",
               "-ast-dump=json"]
    if not full_translation_unit:
        command.extend(["-Xclang", f"-ast-dump-filter={symbol}"])
    command.append(str(source_path))
    report["command"] = command
    execution = invoke(command, timeout, workdir)
    report["execution"] = execution
    if execution["status"] == "timeout":
        report["status"] = "timeout"
        report["reason"] = "compiler_timeout"
        return report
    if execution["status"] != "completed" or execution["returncode"] != 0:
        report["status"] = "compile_failed"
        report["reason"] = "compiler_launch_failed" if execution["status"] == "launch_failed" else "compiler_nonzero_exit"
        return report
    try:
        roots = parse_json_roots(execution["stdout"])
    except (json.JSONDecodeError, ValueError) as error:
        report["status"] = "ast_parse_failed"
        report["reason"] = str(error)
        return report
    report["ast_roots"] = roots
    if full_translation_unit:
        # The parsed tree already retains the AST. Avoid storing a second giant
        # escaped string in the report; keep its digest and make the loss explicit.
        raw_stdout = execution.pop("stdout")
        execution["stdout_sha256"] = hashlib.sha256(raw_stdout.encode()).hexdigest()
        execution["stdout_retention"] = "parsed_ast_only_not_verbatim"
        execution["stdout"] = None
        del raw_stdout
    locations = function_locations(roots, symbol)
    report["function_locations"] = locations
    if not locations:
        report["status"] = "no_symbol"
        report["reason"] = "matching_function_declaration_not_found"
        return report
    report["status"] = "collected"
    report["reason"] = None
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--compiler", required=True)
    parser.add_argument("--compiler-arg", action="append", default=[],
                        help="repeatable explicit argument; use --compiler-arg=VALUE for dash-prefixed values")
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--full-translation-unit", action="store_true",
                        help="retain all declarations in each compiler AST root; may produce large output")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--cwd", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    source_path = args.source.resolve()
    output_path = args.output.resolve()
    if output_path == source_path:
        parser.error("--output must not be the source path")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        output_stream = output_path.open("x", encoding="utf-8")
    except FileExistsError:
        parser.error("--output already exists; AST evidence is never overwritten")
    with output_stream:
        report = collect(source_path, args.compiler, args.compiler_arg, args.symbol,
                         args.timeout, args.cwd, args.full_translation_unit)
        # Full HIP translation units are large: do not materialize a second JSON string.
        json.dump(report, output_stream, indent=2, sort_keys=True, allow_nan=False)
        output_stream.write("\n")
    print(json.dumps({"status": report["status"], "output": str(output_path)}, sort_keys=True))
    return 0 if report["status"] == "collected" else 2


if __name__ == "__main__":
    raise SystemExit(main())
