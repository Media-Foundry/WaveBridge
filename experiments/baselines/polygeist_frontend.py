#!/usr/bin/env python3
"""Record one frontend-only cgeist attempt; emitted IR is not verified IR."""

import argparse
import json
import math
from pathlib import Path
import shutil
import tempfile

from wavebridge.frontend.clang_ast import _sha256, invoke
from wavebridge.frontend import clang_ast


def run(source, cgeist, cuda_path, include_dirs, output_base, *, symbol="*",
        architecture="sm_70", resource_dir=None, timeout=120.0):
    if (type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0):
        raise ValueError("timeout must be positive and finite")
    if not symbol:
        raise ValueError("symbol must not be empty")
    source = Path(source).resolve(strict=True)
    if not source.is_file():
        raise ValueError("source must be a file")
    cuda_path = Path(cuda_path).resolve(strict=True)
    include_dirs = [Path(path).resolve(strict=True) for path in include_dirs]
    if not cuda_path.is_dir() or any(not path.is_dir() for path in include_dirs):
        raise ValueError("CUDA and include paths must be directories")
    if resource_dir is not None:
        resource_dir = Path(resource_dir).resolve(strict=True)
        if not resource_dir.is_dir():
            raise ValueError("resource directory must be a directory")
    output_base = Path(output_base).resolve()
    output_base.mkdir(parents=True, exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix="polygeist-frontend-", dir=output_base))
    output = directory / "output.mlir"
    report = {
        "schema_version": "polygeist-frontend-attempt/v1",
        "scope": "frontend_ir_emission_only",
        "status": "tool_missing",
        "source": {"path": str(source), "sha256": _sha256(source)},
        "runner_sha256": _sha256(Path(__file__)),
        "invoker_sha256": _sha256(Path(clang_ast.__file__)),
        "requested_tool": str(cgeist),
        "tool": None, "execution": None, "ir": None,
        "symbol_selection": symbol, "architecture": architecture,
        "cuda_path": str(cuda_path), "include_dirs": list(map(str, include_dirs)),
        "resource_dir": str(resource_dir) if resource_dir else None,
        "header_closure_hash": "not_established",
        "ir_verified": False, "source_program_checked": False,
        "gpu_execution": "not_run", "deployable": False,
    }
    executable = shutil.which(str(cgeist))
    if executable is not None:
        executable = Path(executable).resolve()
        report["tool"] = {"path": str(executable), "sha256": _sha256(executable)}
        command = [str(executable), str(source), "-S", "-O0", f"--function={symbol}",
                   "--std=c++17", f"--cuda-path={cuda_path}",
                   f"--cuda-gpu-arch={architecture}"]
        command += [f"-I{path}" for path in include_dirs]
        if resource_dir is not None:
            command.append(f"--resource-dir={resource_dir}")
        command += ["-o", str(output)]
        execution = invoke(command, timeout, Path.cwd().resolve())
        report["execution"] = execution
        if output.is_file():
            report["ir"] = {"path": str(output), "sha256": _sha256(output),
                            "size_bytes": output.stat().st_size}
        if execution["status"] != "completed":
            report["status"] = execution["status"]
        elif execution["returncode"] != 0:
            report["status"] = "tool_failed"
        elif report["ir"] is None or report["ir"]["size_bytes"] == 0:
            report["status"] = "no_ir_emitted"
        else:
            report["status"] = "emitted_unverified_ir"
    destination = directory / "report.json"
    with destination.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    return destination, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--cgeist", required=True)
    parser.add_argument("--cuda-path", type=Path, required=True)
    parser.add_argument("--include-dir", action="append", default=[], type=Path)
    parser.add_argument("--resource-dir", type=Path)
    parser.add_argument("--symbol", default="*")
    parser.add_argument("--architecture", default="sm_70")
    parser.add_argument("--timeout", type=float, default=120)
    parser.add_argument("--output-base", type=Path, default=Path("artifacts"))
    args = parser.parse_args()
    try:
        path, report = run(args.source, args.cgeist, args.cuda_path, args.include_dir,
                           args.output_base, symbol=args.symbol, architecture=args.architecture,
                           resource_dir=args.resource_dir, timeout=args.timeout)
    except (ValueError, OSError) as error:
        parser.error(str(error))
    print(json.dumps({"status": report["status"], "report": str(path)}))
    return 0 if report["status"] == "emitted_unverified_ir" else 2


if __name__ == "__main__":
    raise SystemExit(main())
