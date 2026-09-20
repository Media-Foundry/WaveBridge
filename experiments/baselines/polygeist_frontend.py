#!/usr/bin/env python3
"""Record one cgeist IR attempt; emission never implies verified or deployable code."""

import argparse
import json
import math
import re
from pathlib import Path
import shutil
import tempfile

from wavebridge.frontend.clang_ast import _sha256, invoke
from wavebridge.frontend import clang_ast


def run(source, cgeist, cuda_path, include_dirs, output_base, *, symbol="*",
        architecture="sm_70", resource_dir=None, timeout=120.0, cuda_lower=False,
        emit_llvm=False, rocm_path=None, amd_architecture=None, optimization_level=0):
    if type(optimization_level) is not int or optimization_level not in range(4):
        raise ValueError("optimization_level must be an integer from 0 to 3")
    if rocm_path is None and amd_architecture is not None:
        raise ValueError("AMD architecture requires an explicit ROCm path")
    if rocm_path is not None:
        if cuda_lower is not False:
            raise ValueError("ROCm attempt forbids cuda_lower and alternatives generation")
        if not isinstance(amd_architecture, str) or not re.fullmatch(r"gfx[0-9a-f]+", amd_architecture):
            raise ValueError("ROCm attempt requires an explicit gfx architecture")
        rocm_path = Path(rocm_path).resolve(strict=True)
        for relative in ("amdgcn/bitcode/opencl.bc", "amdgcn/bitcode/ocml.bc",
                         "amdgcn/bitcode/ockl.bc", "llvm/bin/ld.lld"):
            if not (rocm_path / relative).is_file():
                raise ValueError(f"ROCm prerequisite missing: {relative}")
    if type(emit_llvm) is not bool:
        raise ValueError("emit_llvm must be a boolean")
    if type(cuda_lower) is not bool:
        raise ValueError("cuda_lower must be a boolean")
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
    output = directory / ("output.ll" if emit_llvm else "output.mlir")
    report = {
        "schema_version": "polygeist-frontend-attempt/v1",
        "scope": "llvm_ir_emission_only" if emit_llvm else "frontend_ir_emission_only",
        "requested_output_kind": "llvm_ir" if emit_llvm else "mlir",
        "optimization_level": optimization_level,
        "pipeline": (f"cgeist_O{optimization_level}_cuda_lower_passes" if cuda_lower else
                     f"cgeist_O{optimization_level}_default_passes_not_identity_translation"),
        "cuda_lower_requested": cuda_lower,
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
    if rocm_path is not None:
        report.update(
            scope="rocm_compilation_attempt_only",
            pipeline=(f"cgeist_O{optimization_level}_rocm_llvm" if emit_llvm else
                      f"cgeist_O{optimization_level}_rocm_gpu_mlir"),
            gpu_execution="not_requested_not_independently_observed",
            amd_architecture=amd_architecture, rocm_path=str(rocm_path),
            alternatives_generation_requested=False,
            hsaco_serialization_requested=emit_llvm,
            visibility_mask_is_not_a_sandbox=True,
            runtime_prerequisites=[
                {"path": str(rocm_path / relative), "sha256": _sha256(rocm_path / relative)}
                for relative in ("amdgcn/bitcode/opencl.bc", "amdgcn/bitcode/ocml.bc",
                                 "amdgcn/bitcode/ockl.bc", "llvm/bin/ld.lld")],
        )
    executable = shutil.which(str(cgeist))
    if executable is not None:
        executable = Path(executable).resolve()
        report["tool"] = {"path": str(executable), "sha256": _sha256(executable)}
        command = [str(executable), str(source), "-S", f"-O{optimization_level}", f"--function={symbol}",
                   "--std=c++17", f"--cuda-path={cuda_path}",
                   f"--cuda-gpu-arch={architecture}"]
        command += [f"-I{path}" for path in include_dirs]
        if cuda_lower:
            command.append("--cuda-lower")
        if emit_llvm:
            command.append("--emit-llvm")
        if rocm_path is not None:
            command += ["--emit-rocm", f"--amd-gpu-arch={amd_architecture}",
                        f"--rocm-path={rocm_path}"]
        if resource_dir is not None:
            command.append(f"--resource-dir={resource_dir}")
        command += ["-o", str(output)]
        workdir = Path.cwd().resolve()
        if rocm_path is not None:
            launcher = shutil.which("env")
            if launcher is None:
                raise ValueError("ROCm attempt requires the env launcher")
            report["launcher"] = {"path": launcher, "sha256": _sha256(Path(launcher))}
            command = [launcher, "-u", "POLYGEIST_GPU_KERNEL_BLOCK_SIZE", "-u",
                       "POLYGEIST_GPU_ALTERNATIVES_PRINT_INFO", "HIP_VISIBLE_DEVICES=-1",
                       "ROCR_VISIBLE_DEVICES=-1", "CUDA_VISIBLE_DEVICES=-1", *command]
            workdir = directory
        execution = invoke(command, timeout, workdir)
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
    parser.add_argument("--optimization-level", type=int, choices=range(4), default=0,
                        help="cgeist optimization level (default: 0); not a correctness guarantee")
    parser.add_argument("--cuda-lower", action="store_true",
                        help="request CUDA-to-MLIR lowering, not GPU code generation")
    parser.add_argument("--emit-llvm", action="store_true",
                        help="request textual LLVM IR; does not enable a GPU backend")
    parser.add_argument("--rocm-path", type=Path,
                        help="explicit backend view for a ROCm compilation attempt")
    parser.add_argument("--amd-gpu-arch", dest="amd_architecture")
    parser.add_argument("--output-base", type=Path, default=Path("artifacts"))
    args = parser.parse_args()
    try:
        path, report = run(args.source, args.cgeist, args.cuda_path, args.include_dir,
                           args.output_base, symbol=args.symbol, architecture=args.architecture,
                           resource_dir=args.resource_dir, timeout=args.timeout,
                           cuda_lower=args.cuda_lower, emit_llvm=args.emit_llvm,
                           rocm_path=args.rocm_path, amd_architecture=args.amd_architecture,
                           optimization_level=args.optimization_level)
    except (ValueError, OSError) as error:
        parser.error(str(error))
    print(json.dumps({"status": report["status"], "report": str(path)}))
    return 0 if report["status"] == "emitted_unverified_ir" else 2


if __name__ == "__main__":
    raise SystemExit(main())
