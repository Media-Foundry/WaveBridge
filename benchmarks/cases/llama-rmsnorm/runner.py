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
import re

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


def strict_json(path: Path):
    def pairs(values):
        result = {}
        for key, value in values:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    def nonfinite(value):
        raise ValueError(f"non-finite JSON constant: {value}")

    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=pairs,
                      parse_constant=nonfinite)


def canonical_json(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def check_artifact_integrity(bindings: dict[str, dict]) -> dict:
    """Observe hashes at a boundary, not a race-free filesystem or build closure."""
    observed = {}
    changed = []
    for name, binding in bindings.items():
        try:
            value = digest(Path(binding["path"]))
        except OSError:
            value = None
        observed[name] = value
        if value != binding["sha256"]:
            changed.append(name)
    return {"status": "unchanged" if not changed else "changed_or_missing",
            "observed_sha256": observed, "changed": changed,
            "race_free_execution_established": False}


def validate_baseline_inputs(source: Path, protocol: Path, provenance: Path) -> dict:
    """Bind this runner to the frozen logical32 baseline before invoking a command."""
    result = {"status": "rejected", "reason": None, "source_sha256": None,
              "provenance_baseline_sha256": None, "protocol_matches_reference": False,
              "frozen_launch": None}
    try:
        protocol_value = strict_json(protocol)
        provenance_value = strict_json(provenance)
        source_sha = digest(source)
        protocol_matches_reference = canonical_json(protocol_value) == canonical_json(reference.PROTOCOL)
    except (OSError, UnicodeError, ValueError) as error:
        result.update(reason="baseline_input_missing_or_malformed", detail=str(error))
        return result
    if not isinstance(protocol_value, dict) or not isinstance(provenance_value, dict):
        result["reason"] = "baseline_input_json_not_object"
        return result
    expected_sha = provenance_value.get("baseline_sha256")
    result.update(source_sha256=source_sha, provenance_baseline_sha256=expected_sha,
                  protocol_matches_reference=protocol_matches_reference)
    if not isinstance(expected_sha, str) or re.fullmatch(r"[0-9a-f]{64}", expected_sha) is None:
        result["reason"] = "invalid_provenance_baseline_sha256"
        return result
    if source_sha != expected_sha:
        result["reason"] = "baseline_source_provenance_mismatch"
        return result
    if not protocol_matches_reference:
        result["reason"] = "copied_protocol_reference_mismatch"
        return result
    launch = protocol_value.get("launch")
    if not isinstance(launch, dict):
        result["reason"] = "frozen_launch_missing"
        return result
    frozen = {"logical_width": launch.get("logical_width"), "block": launch.get("block"),
              "dynamic_shared_bytes": launch.get("dynamic_shared_bytes")}
    result["frozen_launch"] = frozen
    if (type(frozen["logical_width"]) is not int or frozen["logical_width"] != 32 or
            frozen["block"] != [256, 1, 1] or
            any(type(value) is not int for value in frozen["block"]) or
            type(frozen["dynamic_shared_bytes"]) is not int or
            frozen["dynamic_shared_bytes"] != 128):
        result["reason"] = "not_frozen_logical32_launch"
        return result
    result.update(status="verified_frozen_logical32_baseline", reason=None)
    return result


def validate_runtime_logical_width(stdout: str, expected: int) -> dict:
    values = [line.split("=", 1)[1] for line in stdout.splitlines()
              if line.startswith("logical_width=")]
    result = {"status": "rejected", "expected_logical_width": expected,
              "observed_values": values,
              "physical_wave_width_inferred": False}
    if len(values) != 1:
        result["reason"] = "logical_width_missing_or_repeated"
        return result
    raw = values[0]
    if len(raw) > 10 or re.fullmatch(r"(?:0|[1-9][0-9]*)", raw) is None:
        result["reason"] = "logical_width_not_canonical_nonnegative_integer"
        return result
    observed = int(raw)
    result["observed_logical_width"] = observed
    if observed != expected:
        result["reason"] = "logical_width_protocol_mismatch"
        return result
    result.update(status="verified_runtime_logical_width", reason=None)
    return result


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
    binary = artifact / "rmsnorm_logical32"
    report = {
        "schema_version": "rmsnorm-baseline-run/v1", "case_id": "llama-rmsnorm-f32",
        "status": "not_run", "protocol_sha256": None,
        "reference_sha256": None, "provenance_sha256": None,
        "source_sha256": None, "runner_sha256": None,
        "input_sha256": digest(input_path), "expected_sha256": digest(expected_path),
        "visible_device_environment": {key: os.environ.get(key) for key in
                                       ("HIP_VISIBLE_DEVICES", "ROCR_VISIBLE_DEVICES",
                                        "CUDA_VISIBLE_DEVICES")},
        "probe_report": str(probe_report.resolve()), "probe_report_sha256": None,
        "probe_validation": None,
        "input_protocol_validation": None, "runtime_protocol_validation": None,
        "nrows": nrows, "ncols": ncols, "epsilon": 1.0e-5,
        "toolchain": None, "compile": None, "execute": None, "comparison": None,
        "build_binding": None, "artifact_integrity": {},
    }
    copies = [(SOURCE, source_copy), (Path(__file__), runner_copy),
              (HERE / "protocol.json", protocol_copy), (HERE / "reference.py", reference_copy),
              (HERE / "provenance.json", provenance_copy)]
    try:
        for source, destination in copies:
            shutil.copyfile(source, destination)
        report.update(protocol_sha256=digest(protocol_copy), reference_sha256=digest(reference_copy),
                      provenance_sha256=digest(provenance_copy), source_sha256=digest(source_copy),
                      runner_sha256=digest(runner_copy))
    except OSError as error:
        report["status"] = "invalid_baseline_inputs"
        report["input_protocol_validation"] = {
            "status": "rejected", "reason": "baseline_input_copy_failed", "detail": str(error)}
        return finish(report, artifact, 2)
    input_validation = validate_baseline_inputs(source_copy, protocol_copy, provenance_copy)
    report["input_protocol_validation"] = input_validation
    if input_validation["status"] != "verified_frozen_logical32_baseline":
        report["status"] = "invalid_baseline_inputs"
        return finish(report, artifact, 2)
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
    compile_command = [hipcc, "-O2", str(source_copy), "-o", str(binary)]
    bound_files = {name: {"path": str(path), "sha256": report[name + "_sha256"]}
                   for name, path in (("source", source_copy), ("protocol", protocol_copy),
                                      ("reference", reference_copy), ("runner", runner_copy),
                                      ("provenance", provenance_copy), ("input", input_path),
                                      ("expected", expected_path), ("probe_report", probe_report.resolve()))}
    report["build_binding"] = {
        "schema_version": "rmsnorm-baseline-build-binding/v1",
        "command": compile_command,
        "command_sha256": hashlib.sha256(canonical_json(compile_command).encode()).hexdigest(),
        "cwd": str(Path.cwd()), "files": bound_files,
        "optimization": "O2", "contraction": "compiler_default_not_overridden",
        "target": "compiler_default_not_overridden",
        "compiler_process_identity_established": False,
        "compilation_input_closure_established": False,
        "compile_only_observation_used_as_binary_proof": False,
        "floating_point_equivalence_checked": False,
    }
    toolchain = command([hipcc, "--version"], timeout)
    report["toolchain"] = toolchain
    if toolchain["status"] != "completed" or toolchain["returncode"] != 0:
        report["status"] = "toolchain_unavailable"
        return finish(report, artifact, 2)
    integrity = check_artifact_integrity(bound_files)
    report["artifact_integrity"]["before_compile"] = integrity
    if integrity["status"] != "unchanged":
        report["status"] = "artifact_integrity_mismatch"
        return finish(report, artifact, 2)
    compile_result = command(compile_command, timeout)
    report["compile"] = compile_result
    if compile_result["status"] != "completed" or compile_result["returncode"] != 0:
        report["status"] = "compile_timeout" if compile_result["status"] == "timeout" else "compile_failed"
        return finish(report, artifact, 2)
    try:
        if not binary.is_file() or binary.stat().st_size == 0:
            raise OSError("compiler did not produce a nonempty binary")
        report["binary_sha256"] = digest(binary)
    except OSError as error:
        report["status"] = "invalid_binary"
        report["binary_error"] = str(error)
        return finish(report, artifact, 2)
    bound_files["binary"] = {"path": str(binary), "sha256": report["binary_sha256"]}
    integrity = check_artifact_integrity(bound_files)
    report["artifact_integrity"]["before_execute"] = integrity
    if integrity["status"] != "unchanged":
        report["status"] = "artifact_integrity_mismatch"
        return finish(report, artifact, 2)
    execute = command([str(binary), str(input_path), str(output_path), str(nrows), str(ncols)], timeout)
    report["execute"] = execute
    integrity = check_artifact_integrity(bound_files)
    report["artifact_integrity"]["after_execute"] = integrity
    if integrity["status"] != "unchanged":
        report["status"] = "artifact_integrity_mismatch"
        return finish(report, artifact, 2)
    if execute["status"] != "completed" or execute["returncode"] != 0:
        report["status"] = "run_timeout" if execute["status"] == "timeout" else "run_failed"
        return finish(report, artifact, 2)
    runtime = parse_key_values(execute["stdout"])
    runtime_protocol = validate_runtime_logical_width(
        execute["stdout"], report["input_protocol_validation"]["frozen_launch"]["logical_width"])
    report["runtime_protocol_validation"] = runtime_protocol
    if runtime_protocol["status"] != "verified_runtime_logical_width":
        report["status"] = "runtime_protocol_mismatch"
        return finish(report, artifact, 2)
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
