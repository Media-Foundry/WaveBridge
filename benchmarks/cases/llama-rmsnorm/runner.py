#!/usr/bin/env python3
"""Compile and run the frozen logical32 baseline; never signs static claims."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import secrets
import signal
import shutil
import struct
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "baseline" / "rmsnorm_logical32.hip.cpp"

spec = importlib.util.spec_from_file_location("rmsnorm_reference", HERE / "reference.py")
reference = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(reference)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def command(args: list[str], timeout: float) -> dict:
    started = time.monotonic()
    try:
        process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   start_new_session=True)
        try:
            stdout, stderr = process.communicate(timeout=timeout)
            return {"command": args, "status": "completed", "returncode": process.returncode,
                    "stdout": stdout.decode(errors="replace"),
                    "stderr": stderr.decode(errors="replace"),
                    "duration_seconds": round(time.monotonic() - started, 6)}
        except subprocess.TimeoutExpired as error:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            stdout, stderr = process.communicate()
            return {"command": args, "status": "timeout", "returncode": None,
                    "stdout": (stdout or error.stdout or b"").decode(errors="replace"),
                    "stderr": (stderr or error.stderr or b"").decode(errors="replace"),
                    "duration_seconds": round(time.monotonic() - started, 6)}
    except OSError as error:
        return {"command": args, "status": "launch_failed", "returncode": None,
                "stdout": "", "stderr": str(error),
                "duration_seconds": round(time.monotonic() - started, 6)}


def parse_key_values(raw: str) -> dict[str, str]:
    return dict(line.split("=", 1) for line in raw.splitlines() if "=" in line)


def run(output_base: Path, hipcc: str, probe_report: Path, nrows: int,
        ncols: int, timeout: float) -> tuple[int, Path]:
    run_id = (dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" +
              secrets.token_hex(3))
    artifact = output_base.resolve() / f"wb02-{run_id}"
    artifact.mkdir(parents=True, exist_ok=False)
    rows = reference.deterministic_rows(nrows, ncols)
    expected_rows = reference.rmsnorm(rows, 1.0e-5)
    flat_input = [value for row in rows for value in row]
    expected = [value for row in expected_rows for value in row]
    input_path, output_path = artifact / "input.f32", artifact / "output.f32"
    expected_path = artifact / "expected.f32"
    input_path.write_bytes(struct.pack(f"<{len(flat_input)}f", *flat_input))
    expected_path.write_bytes(struct.pack(f"<{len(expected)}f", *expected))
    source_copy = artifact / SOURCE.name
    runner_copy = artifact / Path(__file__).name
    protocol_copy = artifact / "protocol.json"
    reference_copy = artifact / "reference.py"
    provenance_copy = artifact / "provenance.json"
    shutil.copyfile(SOURCE, source_copy)
    shutil.copyfile(Path(__file__), runner_copy)
    shutil.copyfile(HERE / "protocol.json", protocol_copy)
    shutil.copyfile(HERE / "reference.py", reference_copy)
    shutil.copyfile(HERE / "provenance.json", provenance_copy)
    binary = artifact / "rmsnorm_logical32"
    report = {
        "schema_version": "rmsnorm-baseline-run/v1", "case_id": "llama-rmsnorm-f32",
        "status": "not_run", "protocol_sha256": digest(protocol_copy),
        "reference_sha256": digest(reference_copy),
        "provenance_sha256": digest(provenance_copy),
        "source_sha256": digest(source_copy), "runner_sha256": digest(runner_copy),
        "input_sha256": digest(input_path), "expected_sha256": digest(expected_path),
        "visible_device_environment": {key: os.environ.get(key) for key in
                                       ("HIP_VISIBLE_DEVICES", "ROCR_VISIBLE_DEVICES",
                                        "CUDA_VISIBLE_DEVICES")},
        "probe_report": str(probe_report.resolve()), "probe_report_sha256": None,
        "probe_validation": None,
        "nrows": nrows, "ncols": ncols, "epsilon": 1.0e-5,
        "toolchain": None, "compile": None, "execute": None, "comparison": None,
    }
    try:
        probe = json.loads(probe_report.read_text(encoding="utf-8"))
        report["probe_report_sha256"] = digest(probe_report)
    except (OSError, ValueError) as error:
        report["status"] = "invalid_probe_report"
        report["probe_validation"] = {"status": "rejected", "reason": str(error)}
        return finish(report, artifact, 2)
    current_env = report["visible_device_environment"]
    if probe.get("overall_status") != "verified":
        report["status"] = "invalid_probe_report"
        report["probe_validation"] = {"status": "rejected", "reason": "probe_not_verified"}
        return finish(report, artifact, 2)
    if probe.get("visible_device_environment") != current_env:
        report["status"] = "probe_environment_mismatch"
        report["probe_validation"] = {"status": "rejected", "reason": "visible_environment_changed",
                                      "probe": probe.get("visible_device_environment"),
                                      "current": current_env}
        return finish(report, artifact, 2)
    report["probe_validation"] = {"status": "verified_report_accepted",
                                  "physical_wave_width": probe.get("physical_wave_width")}
    toolchain = command([hipcc, "--version"], timeout)
    report["toolchain"] = toolchain
    if toolchain["status"] != "completed" or toolchain["returncode"] != 0:
        report["status"] = "toolchain_unavailable"
        return finish(report, artifact, 2)
    compile_result = command([hipcc, "-O2", str(source_copy), "-o", str(binary)], timeout)
    report["compile"] = compile_result
    if compile_result["status"] != "completed" or compile_result["returncode"] != 0:
        report["status"] = "compile_timeout" if compile_result["status"] == "timeout" else "compile_failed"
        return finish(report, artifact, 2)
    report["binary_sha256"] = digest(binary)
    execute = command([str(binary), str(input_path), str(output_path), str(nrows), str(ncols)], timeout)
    report["execute"] = execute
    if execute["status"] != "completed" or execute["returncode"] != 0:
        report["status"] = "run_timeout" if execute["status"] == "timeout" else "run_failed"
        return finish(report, artifact, 2)
    runtime = parse_key_values(execute["stdout"])
    expected_identity = probe.get("device_identity", {})
    identity_keys = ("device_name", "gcn_arch_name", "pci_bus_id",
                     "hip_runtime_version", "hip_driver_version")
    mismatches = {key: {"probe": expected_identity.get(key), "runtime": runtime.get(key)}
                  for key in identity_keys if expected_identity.get(key) != runtime.get(key)}
    if mismatches:
        report["status"] = "probe_runtime_identity_mismatch"
        report["probe_validation"] = {"status": "rejected", "reason": "identity_mismatch",
                                      "mismatches": mismatches}
        return finish(report, artifact, 2)
    report["runtime_device_identity"] = {key: runtime[key] for key in identity_keys}
    raw = output_path.read_bytes() if output_path.exists() else b""
    if len(raw) != len(expected) * 4:
        report["status"] = "invalid_output"
        return finish(report, artifact, 1)
    actual = struct.unpack(f"<{len(expected)}f", raw)
    report["output_sha256"] = digest(output_path)
    report["comparison"] = reference.compare(actual, expected)
    report["status"] = "passed" if report["comparison"]["passed"] else "numeric_mismatch"
    return finish(report, artifact, 0 if report["status"] == "passed" else 1)


def finish(report: dict, artifact: Path, code: int) -> tuple[int, Path]:
    path = artifact / "report.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n")
    return code, path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hipcc", default=shutil.which("hipcc") or "hipcc")
    parser.add_argument("--probe-report", type=Path, required=True)
    parser.add_argument("--output-base", type=Path, default=HERE.parents[2] / "artifacts")
    parser.add_argument("--nrows", type=int, default=3)
    parser.add_argument("--ncols", type=int, default=777)
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args(argv)
    try:
        code, report = run(args.output_base, args.hipcc, args.probe_report,
                           args.nrows, args.ncols, args.timeout)
    except ValueError as error:
        parser.error(str(error))
    print(json.dumps({"report": str(report), "exit_code": code}))
    return code


if __name__ == "__main__":
    sys.exit(main())
