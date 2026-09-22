"""Collect native capture metadata and JSON AST from one Clang ASTContext.

The explicitly supplied plugin is trusted frontend code, not a verifier. No
record in this module proves runtime object identity or authorizes deployment.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil
import tempfile

from wavebridge.frontend.clang_ast import _sha256, invoke
from wavebridge.frontend.dependencies import observe


def collect(source: Path, compiler: str, plugin: Path, compiler_args: list[str],
            *, timeout: float = 60, cwd: Path | None = None) -> dict:
    result = {
        "schema_version": "native-capture-source/v1", "status": "unknown", "reason": None,
        "source_program_checked": False, "deployable": False,
        "runtime_source_identity": "not_established", "payload": None,
        "limitations": [
            "compiler and plugin are trusted frontend components",
            "pointer IDs are scoped to the single embedded AST, not other invocations",
            "capture observations do not prove lifetime, mutation history or launch semantics",
            "dependency hashes are post-compilation observations, not frozen inputs",
            "hashing the driver does not attest its actual cc1 process or SDK closure",
        ],
    }
    if (type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0 or
            not isinstance(compiler_args, list) or any(not isinstance(a, str) for a in compiler_args)):
        result["reason"] = "invalid_arguments"
        return result
    if any(arg.startswith(("-M", "-Wp,", "@", "-fplugin")) or
           arg in {"-Xclang", "-Xpreprocessor"} for arg in compiler_args):
        result["reason"] = "frontend_and_dependency_options_owned_by_collector"
        return result
    executable = shutil.which(compiler)
    if executable is None:
        result.update(status="tool_missing", reason="compiler_missing")
        return result
    try:
        source = Path(source).resolve(strict=True)
        plugin = Path(plugin).resolve(strict=True)
        workdir = (Path.cwd() if cwd is None else Path(cwd)).resolve(strict=True)
        paths = {"source": source, "plugin": plugin, "compiler": Path(executable).resolve(strict=True)}
        if not workdir.is_dir() or any(not path.is_file() for path in paths.values()):
            raise OSError("source, compiler and plugin must be regular files; cwd must be a directory")
        before = {name: _sha256(path) for name, path in paths.items()}
    except OSError as error:
        result.update(reason="input_unreadable", detail=str(error))
        return result
    result["inputs"] = {name: {"path": str(path), "sha256_before": before[name]}
                        for name, path in paths.items()}
    with tempfile.TemporaryDirectory(prefix="wb-native-capture-deps-") as directory:
        depfile = Path(directory) / "inputs.d"
        command = [executable, *compiler_args, "-fsyntax-only", "-Xclang", "-load", "-Xclang",
                   str(plugin), "-Xclang", "-plugin", "-Xclang", "wavebridge-native-captures",
                   "-Xclang", "-dependency-file", "-Xclang", str(depfile),
                   "-Xclang", "-MT", "-Xclang", "wavebridge-inputs",
                   "-Xclang", "-sys-header-deps", str(source)]
        execution = invoke(command, timeout, workdir)
        result["execution"] = execution
        result["dependency_binding"] = observe(depfile, workdir, source, before["source"])
    try:
        after = {name: _sha256(path) for name, path in paths.items()}
    except OSError as error:
        result.update(reason="input_recheck_failed", detail=str(error))
        return result
    for name in paths:
        result["inputs"][name]["sha256_after"] = after[name]
    result["inputs_stable"] = before == after
    if execution["status"] == "timeout":
        result.update(status="timeout", reason="compiler_timeout")
        return result
    if execution["status"] != "completed" or execution["returncode"] != 0:
        result.update(status="compile_failed", reason="compiler_execution_failed")
        return result
    if before != after:
        result["reason"] = "inputs_changed_during_collection"
        return result
    if result["dependency_binding"]["status"] != "observed":
        result["reason"] = "same_invocation_dependencies_not_observed"
        return result
    try:
        payload = json.loads(execution["stdout"])
        if (not isinstance(payload, dict) or payload.get("schema_version") != "clang-native-captures/v1" or
                not isinstance(payload.get("ast"), dict) or
                payload["ast"].get("kind") != "TranslationUnitDecl" or
                not isinstance(payload.get("captures"), list)):
            raise ValueError("expected one native-capture envelope with complete TU")
    except (ValueError, TypeError) as error:
        result.update(status="parse_failed", reason=str(error))
        return result
    raw = execution.pop("stdout")
    execution["stdout_sha256"] = hashlib.sha256(raw.encode()).hexdigest()
    execution["stdout_retention"] = "parsed_envelope_only_not_verbatim"
    result.update(status="collected", payload=payload)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--compiler", required=True)
    parser.add_argument("--plugin", type=Path, required=True)
    parser.add_argument("--compiler-arg", action="append", default=[])
    parser.add_argument("--timeout", type=float, default=60)
    parser.add_argument("--cwd", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    try:
        output = args.output.open("x", encoding="utf-8")
    except FileExistsError:
        parser.error("output must be a new file")
    with output:
        report = collect(args.source, args.compiler, args.plugin, args.compiler_arg,
                         timeout=args.timeout, cwd=args.cwd)
        json.dump(report, output, indent=2, sort_keys=True, allow_nan=False)
        output.write("\n")
    print(json.dumps({"status": report["status"], "output": str(args.output)}))
    return 0 if report["status"] == "collected" else 2


if __name__ == "__main__":
    raise SystemExit(main())
