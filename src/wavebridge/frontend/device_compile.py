"""Compile-only HIP FP observations. No artifact is executed or certified.

Only a fixed -O2 device-only recipe is supported. The numeric protocol is an
opaque hashed input, not a protocol validated by this collector. Driver traces
describe separate dry-runs, never the identity of actual compiler subprocesses.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import tempfile

from wavebridge.frontend import clang_ast, toolchain_trace


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _command_hash(command: list[str]) -> str:
    return hashlib.sha256(json.dumps(command, ensure_ascii=True,
                                    separators=(",", ":")).encode()).hexdigest()


def collect(source: Path, protocol: Path, compiler: Path, output_parent: Path, *,
            target: str, contraction: str = "default", timeout: float = 120) -> dict:
    """Save IR, assembly, commands, and observations in a fresh run directory.

    No free-form compiler flags: this entry never changes a baseline recipe or
    claims to reproduce a historical executable. Invalid input raises ValueError
    or OSError before compilation. Missing outputs and failures retain logs.
    """
    if not isinstance(target, str) or not re.fullmatch(r"gfx[0-9a-f]+", target):
        raise ValueError("target must be a plain gfx architecture")
    if contraction not in {"default", "off"}:
        raise ValueError("contraction must be default or off")
    if isinstance(timeout, bool) or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout must be finite and positive")
    paths = {name: path.resolve(strict=True) for name, path in
             (("source", source), ("numeric_protocol", protocol), ("compiler", compiler))}
    if any(not path.is_file() for path in paths.values()):
        raise ValueError("source, protocol and compiler must be files")
    before = {name: {"path": str(path), "sha256": _sha(path)}
              for name, path in paths.items()}
    output_parent = output_parent.resolve(strict=True)
    run_dir = Path(tempfile.mkdtemp(prefix="fp-compile-", dir=output_parent))
    source, compiler = paths["source"], paths["compiler"]
    # Preserve quoted-include lookup: compile the original path, not a relocated copy.
    cwd = source.parent
    report = {
        "schema_version": "hip-device-fp-compilation/v1",
        "status": "unknown", "run_directory": str(run_dir), "inputs": before,
        "configuration": {"optimization": "O2", "debug": "line_tables_only",
                          "target": target, "contraction": contraction,
                          "wave_mode": "compiler_default"},
        "implementation_sha256": {str(Path(module.__file__).resolve()):
                                  _sha(Path(module.__file__))
                                  for module in (clang_ast, toolchain_trace)},
        "collector_sha256": _sha(Path(__file__)), "jobs": [],
        "numeric_protocol_validated": False, "source_program_checked": False,
        "floating_point_equivalence_checked": False, "runtime_verified": False,
        "deployable": False, "compilation_input_closure_established": False,
        "scope": "separate_IR_and_assembly_compilations_with_explicit_configuration",
        "limitations": [
            "no GPU execution, numeric comparison, or semantic acceptance",
            "IR and assembly compiled separately; not a verified lowering chain",
            "dependency headers, shared libraries and environment not frozen",
            "dry-run toolchain is planned, not actual subprocess identity",
            "before/after hashes do not exclude transient input changes",
            "default contraction and wave mode are not asserted runtime semantics",
        ],
    }

    def save() -> None:
        (run_dir / "report.json").write_text(json.dumps(report, indent=2) + "\n")

    def invoke(command: list[str]) -> dict:
        result = clang_ast.invoke(command, timeout, cwd)
        result["command_sha256"] = _command_hash(command)
        return result

    report["version"] = invoke([str(compiler), "--version"])
    save()
    for kind, extra, suffix in (("ir", ["-emit-llvm"], ".ll"),
                                ("assembly", [], ".s")):
        artifact = run_dir / (kind + suffix)
        command = [str(compiler), "-O2", "-gline-tables-only", "--offload-device-only",
                   "--offload-arch=" + target]
        if contraction == "off":
            command.append("-ffp-contract=off")
        command += ["-S", *extra, str(source), "-o", str(artifact)]
        execution = invoke(command)
        trace = invoke([*command, "-###"])
        job = {"kind": kind, "execution": execution, "driver_dry_run": trace,
               "planned_toolchain": toolchain_trace.observe(trace["stderr"], cwd),
               "artifact": {"path": str(artifact), "sha256": None, "size": None},
               "status": "unknown"}
        if artifact.is_file():
            job["artifact"].update(sha256=_sha(artifact), size=artifact.stat().st_size)
        if execution["status"] != "completed":
            job["status"] = execution["status"]
        elif execution["returncode"] != 0:
            job["status"] = "compile_failed"
        elif not job["artifact"]["size"]:
            job["status"] = "output_missing_or_empty"
        else:
            job["status"] = "compiled"
        report["jobs"].append(job)
        save()
    after = {}
    for name, path in paths.items():
        try:
            after[name] = _sha(path)
        except OSError:
            after[name] = None
    report["input_hashes_after"] = after
    report["direct_inputs_unchanged"] = all(after[name] == item["sha256"]
                                             for name, item in before.items())
    if not report["direct_inputs_unchanged"]:
        report["status"] = "input_changed"
    elif all(job["status"] == "compiled" for job in report["jobs"]):
        report["status"] = "compiled"
    else:
        report["status"] = "incomplete"
    save()
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ("source", "protocol", "compiler", "output-parent"):
        parser.add_argument("--" + flag, required=True, type=Path)
    parser.add_argument("--target", required=True)
    parser.add_argument("--contraction", choices=("default", "off"), default="default")
    parser.add_argument("--timeout", type=float, default=120)
    args = parser.parse_args()
    try:
        report = collect(args.source, args.protocol, args.compiler, args.output_parent,
                         target=args.target, contraction=args.contraction, timeout=args.timeout)
    except (OSError, ValueError) as error:
        parser.exit(3, str(error) + "\n")
    print(json.dumps({"status": report["status"],
                      "report": str(Path(report["run_directory"]) / "report.json"),
                      "deployable": False}))
    return 0 if report["status"] == "compiled" else 2


if __name__ == "__main__":
    raise SystemExit(main())
