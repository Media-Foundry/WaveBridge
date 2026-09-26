"""Pinned CUDA compile-only probe. Observed IR is never a semantic acceptance."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from experiments.pytorch_softmax_intake import sha
from wavebridge.frontend import clang_ast, dependencies

CONFIG_SHA = "fb6fb7374ba536f61c6a83553cd7b27f3f8281093eae1cdd158ac0d42f9bb1b5"
COMPILER_SHA = "0aafa5b0712f974db5bbdd93a849b0b1e094bbb6314b8163278a22a90ce766b8"


def run(config_path, output_dir):
    config_path = Path(config_path).resolve(strict=True)
    if sha(config_path) != CONFIG_SHA:
        raise ValueError("frozen_config_mismatch")
    config = json.loads(config_path.read_text())
    compiler = Path(config["compiler"]).resolve(strict=True)
    if sha(compiler) != COMPILER_SHA:
        raise ValueError("historical_compiler_mismatch")
    source = Path(__file__).parent / "probes" / "builtin_values.cu"
    source = source.resolve(strict=True)
    directory = Path(output_dir).resolve()
    directory.mkdir(parents=True, exist_ok=False)
    files = [config_path, compiler, source, Path(__file__).resolve(),
             Path(clang_ast.__file__).resolve(), Path(dependencies.__file__).resolve(),
             Path(__file__).with_name("pytorch_softmax_intake.py").resolve()]
    before = {str(path): sha(path) for path in files}
    report = {"schema_version": "builtin-value-probe/v1", "status": "started",
              "inputs_before": before, "jobs": [], "GPU_executed": False,
              "source_program_checked": False, "deployable": False,
              "full_compilation_closure_established": False,
              "scope": "synthetic_compile_only_not_translation_validation",
              "version": clang_ast.invoke([str(compiler), "--version"], 30, Path.cwd())}
    def save():
        (directory / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    save()
    for optimization in ("O0", "O2"):
        output, depfile = directory / (optimization + ".ll"), directory / (optimization + ".d")
        command = [str(compiler), *config["compiler_args"], "-" + optimization, "-S", "-emit-llvm",
                   "-Xclang", "-dependency-file", "-Xclang", str(depfile),
                   "-Xclang", "-MT", "-Xclang", "wavebridge-inputs", "-Xclang", "-sys-header-deps",
                   str(source), "-o", str(output)]
        execution = clang_ast.invoke(command, 30, Path.cwd())
        job = {"optimization": optimization, "command": command, "execution": execution,
               "dependency_binding": dependencies.observe(depfile, Path.cwd(), source, before[str(source)]),
               "output_sha256": sha(output) if output.is_file() else None}
        job["status"] = ("compiled" if execution["status"] == "completed" and
                         execution["returncode"] == 0 and output.is_file() and output.stat().st_size
                         else "not_compiled")
        report["jobs"].append(job)
        save()
    report["inputs_after"] = {str(path): sha(path) for path in files}
    report["inputs_unchanged"] = before == report["inputs_after"]
    report["status"] = ("observed" if report["inputs_unchanged"] and
                        report["version"]["status"] == "completed" and
                        report["version"]["returncode"] == 0 and
                        all(job["status"] == "compiled" and job["dependency_binding"]["status"] == "observed"
                            for job in report["jobs"]) else "incomplete")
    save()
    print(json.dumps({"status": report["status"], "sha256": sha(directory / "report.json")}))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    return 0 if run(args.config, args.output_dir)["status"] == "observed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
