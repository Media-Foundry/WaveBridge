#!/usr/bin/env python3
"""Run the minimal WB-01 HIP device probe and preserve raw evidence."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import signal
import shutil
import subprocess
import sys
import time
from typing import Any

SCHEMA_VERSION = "wavebridge-device-probe/v1"
ROOT = Path(__file__).resolve().parents[2]
SOURCE = Path(__file__).with_name("device_probe.hip.cpp")
VISIBLE_ENV = ("HIP_VISIBLE_DEVICES", "ROCR_VISIBLE_DEVICES", "CUDA_VISIBLE_DEVICES")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value


def invoke(command: list[str], timeout: float, cwd: Path | None = None) -> dict[str, Any]:
    started = time.monotonic()
    record: dict[str, Any] = {"command": command, "timeout_seconds": timeout}
    if cwd is not None:
        record["cwd"] = str(cwd)
    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=False, cwd=cwd, start_new_session=True)
        try:
            stdout, stderr = process.communicate(timeout=timeout)
            record.update(status="completed", returncode=process.returncode,
                          stdout=_text(stdout), stderr=_text(stderr))
        except subprocess.TimeoutExpired as error:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            final_stdout, final_stderr = process.communicate()
            record.update(status="timeout", returncode=None,
                          stdout=_text(final_stdout) or _text(error.stdout),
                          stderr=_text(final_stderr) or _text(error.stderr))
    except OSError as error:
        record.update(status="launch_failed", returncode=None, stdout="",
                      stderr=str(error))
    record["duration_seconds"] = round(time.monotonic() - started, 6)
    return record


def parse_probe_output(raw: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in raw.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    return values


def validate_semantics(values: dict[str, str]) -> dict[str, Any]:
    required = ("host_reported_warp_size", "device_warp_sizes", "ballots", "shuffles")
    missing = [key for key in required if key not in values]
    if missing:
        return {"status": "semantic_mismatch", "reason": "missing_output",
                "missing": missing}
    try:
        host_width = int(values["host_reported_warp_size"])
        widths = [int(value) for value in values["device_warp_sizes"].split(",")]
        ballots = [int(value, 16) for value in values["ballots"].split(",")]
        shuffles = [int(value) for value in values["shuffles"].split(",")]
    except ValueError as error:
        return {"status": "semantic_mismatch", "reason": "malformed_output",
                "detail": str(error)}
    if len(widths) != 64 or len(ballots) != 64 or len(shuffles) != 64:
        return {"status": "semantic_mismatch", "reason": "sample_count",
                "counts": [len(widths), len(ballots), len(shuffles)]}
    if host_width not in (32, 64) or any(width != host_width for width in widths):
        return {"status": "semantic_mismatch", "reason": "warp_size_disagreement",
                "host_width": host_width, "device_widths": sorted(set(widths))}
    expected_mask = (1 << host_width) - 1
    if any(mask != expected_mask for mask in ballots):
        return {"status": "semantic_mismatch", "reason": "ballot_disagreement",
                "host_width": host_width,
                "observed_masks": sorted({f"0x{mask:016x}" for mask in ballots})}
    expected_shuffle = [((lane // host_width) * host_width + host_width - 1)
                        for lane in range(64)]
    if shuffles != expected_shuffle:
        return {"status": "semantic_mismatch", "reason": "shuffle_disagreement",
                "host_width": host_width, "observed": shuffles,
                "expected": expected_shuffle}
    return {"status": "consistent", "physical_wave_width": host_width,
            "evidence": ["host_device_property", "device_warpSize",
                         "device_ballot", "device_shuffle"]}


def reconcile_widths(metadata: dict[str, Any], semantics: dict[str, Any]) -> dict[str, Any]:
    if metadata.get("status") != "established":
        return {"status": "unknown", "reason": "metadata_unestablished"}
    if metadata.get("physical_wave_width") != semantics.get("physical_wave_width"):
        return {"status": "failed", "reason": "semantic_mismatch",
                "metadata": metadata.get("physical_wave_width"),
                "runtime": semantics.get("physical_wave_width")}
    return {"status": "verified", "reason": "independent_evidence_consistent",
            "physical_wave_width": semantics["physical_wave_width"]}


def kernel_metadata_widths(text: str) -> set[int]:
    """Read root fields of the named kernel entry under ``amdhsa.kernels``."""
    lines = text.splitlines()
    section_start = next((index for index, line in enumerate(lines)
                          if re.match(r"^\s*amdhsa\.kernels\s*:\s*$", line)), None)
    if section_start is None:
        return set()
    section_indent = len(lines[section_start]) - len(lines[section_start].lstrip())
    item_starts: list[tuple[int, int]] = []
    section_end = len(lines)
    for index in range(section_start + 1, len(lines)):
        line = lines[index]
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        if indent <= section_indent and not line.lstrip().startswith(("---", "...")):
            section_end = index
            break
        match = re.match(r"^(\s*)-\s+\.[A-Za-z_][\w.]*\s*:", line)
        if match and (not item_starts or indent == item_starts[0][1]):
            item_starts.append((index, indent))
    if not item_starts:
        return set()

    widths: set[int] = set()
    for position, (start, item_indent) in enumerate(item_starts):
        end = item_starts[position + 1][0] if position + 1 < len(item_starts) else section_end
        root_indent = item_indent + 2
        fields: dict[str, str] = {}
        first = re.match(r"^\s*-\s+(\.[A-Za-z_][\w.]*)\s*:\s*(.*?)\s*$", lines[start])
        if first:
            fields[first.group(1)] = first.group(2)
        for line in lines[start + 1:end]:
            match = re.match(rf"^\s{{{root_indent}}}(\.[A-Za-z_][\w.]*)\s*:\s*(.*?)\s*$", line)
            if match:
                fields[match.group(1)] = match.group(2)
        name = fields.get(".name", "").strip("'\"")
        is_probe = name == "wavebridge_probe" or name.startswith("_Z16wavebridge_probe")
        if not is_probe:
            continue
        width = fields.get(".wavefront_size")
        if width in ("32", "64"):
            widths.add(int(width))
    return widths


def extract_metadata(binary: Path, artifact: Path, timeout: float,
                     toolchain_dir: Path | None = None) -> dict[str, Any]:
    attempts: list[dict[str, Any]] = []
    widths: set[int] = set()
    objects = [path for path in artifact.iterdir()
               if path.is_file() and path != binary and
               path.suffix not in (".cpp", ".json", ".py")]
    matched_objects: list[dict[str, str]] = []
    possible_readobj = ([toolchain_dir / "llvm-readobj"] if toolchain_dir else []) + [
        Path("/opt/rocm/llvm/bin/llvm-readobj"),
        Path(shutil.which("llvm-readobj")) if shutil.which("llvm-readobj") else None,
    ]
    readobj = next((str(path) for path in possible_readobj
                    if path is not None and path.is_file()), None)
    if not readobj:
        attempts.append({"tool": "llvm-readobj", "status": "tool_missing"})
    for obj in objects:
        if not readobj:
            break
        record = invoke([readobj, "--file-headers", "--notes", str(obj)], timeout)
        attempts.append(record)
        if record["status"] == "completed" and record["returncode"] == 0:
            text = record["stdout"] + "\n" + record["stderr"]
            if "EM_AMDGPU" in text or "Machine: AMDGPU" in text:
                found = kernel_metadata_widths(text)
                if found:
                    widths.update(found)
                    matched_objects.append({"path": str(obj), "sha256": sha256(obj)})
    strings = shutil.which("strings")
    if strings:
        diagnostic = invoke([strings, str(binary)], timeout)
        diagnostic["diagnostic_only"] = True
        attempts.append(diagnostic)
    if len(widths) == 1:
        return {"status": "established", "physical_wave_width": widths.pop(),
                "matched_code_objects": matched_objects, "attempts": attempts}
    reason = "conflicting_wave_metadata" if widths else "wave_metadata_not_found"
    return {"status": "metadata_unestablished", "reason": reason,
            "observed_widths": sorted(widths),
            "matched_code_objects": matched_objects, "attempts": attempts}


def unique_artifact_dir(base: Path) -> Path:
    base = base.resolve()
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for _ in range(20):
        path = base / f"wb01-{stamp}-{os.getpid()}-{secrets.token_hex(3)}"
        try:
            path.mkdir(parents=True, exist_ok=False)
            return path
        except FileExistsError:
            pass
    raise RuntimeError("could not allocate a unique artifact directory")


def run(output_base: Path, timeout: float, hipcc_arg: str | None = None) -> tuple[int, Path, dict[str, Any]]:
    artifact = unique_artifact_dir(output_base)
    source_copy = artifact / SOURCE.name
    runner_copy = artifact / Path(__file__).name
    shutil.copyfile(SOURCE, source_copy)
    shutil.copyfile(Path(__file__), runner_copy)
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "probe_id": artifact.name,
        "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "repository_head": None,
        "visible_device_environment": {key: os.environ.get(key) for key in VISIBLE_ENV},
        "artifacts": {"source": str(source_copy), "source_sha256": sha256(source_copy),
                      "runner": str(runner_copy), "runner_sha256": sha256(runner_copy)},
        "stages": {
            "toolchain": {"status": "not_run"},
            "device_inventory": {"status": "not_run"},
            "compile": {"status": "not_run"},
            "metadata": {"status": "not_run"},
            "execute": {"status": "not_run"},
            "semantic_validation": {"status": "not_run"},
        },
    }
    git = shutil.which("git")
    if git:
        head = invoke([git, "-C", str(ROOT), "rev-parse", "HEAD"], timeout)
        report["repository_head_command"] = head
        if head["status"] == "completed" and head["returncode"] == 0:
            report["repository_head"] = head["stdout"].strip()

    hipcc = hipcc_arg or shutil.which("hipcc")
    if not hipcc:
        report["stages"]["toolchain"] = {"status": "tool_missing", "tool": "hipcc"}
        report["overall_status"] = "unknown"
        report["reason"] = "tool_missing"
        return finish(report, artifact, 2)
    compiler_path = Path(shutil.which(hipcc) or hipcc)
    if compiler_path.is_file():
        report["artifacts"]["compiler_executable_sha256"] = sha256(compiler_path)
        view_manifest = compiler_path.parent.parent / "manifest.json"
        if view_manifest.is_file():
            # Preserve the caller's explicit SDK view, without treating it as proof.
            manifest_copy = artifact / "sdk-view-manifest.json"
            shutil.copyfile(view_manifest, manifest_copy)
            report["artifacts"]["sdk_view_manifest"] = str(manifest_copy)
            report["artifacts"]["sdk_view_manifest_sha256"] = sha256(manifest_copy)
    version = invoke([hipcc, "--version"], timeout)
    report["stages"]["toolchain"] = version
    if version["status"] != "completed" or version["returncode"] != 0:
        missing = version["status"] == "launch_failed"
        report["stages"]["toolchain"]["status"] = (
            "tool_missing" if missing else "tool_unusable"
        )
        report["overall_status"] = "unknown"
        report["reason"] = "tool_missing" if missing else "tool_unusable"
        return finish(report, artifact, 2)

    rocminfo = shutil.which("rocminfo")
    if rocminfo:
        inventory = invoke([rocminfo], timeout)
        if inventory["status"] == "completed" and inventory["returncode"] == 0:
            inventory["status"] = "collected"
        elif inventory["status"] == "timeout":
            inventory["status"] = "inventory_timeout"
        else:
            inventory["status"] = "inventory_failed"
        report["stages"]["device_inventory"] = inventory
    else:
        report["stages"]["device_inventory"] = {"status": "tool_missing",
                                                   "tool": "rocminfo"}

    binary = artifact / "device_probe"
    compile_record = invoke([hipcc, "-O0", "-g", "--save-temps", str(source_copy),
                             "-o", str(binary)], timeout, cwd=artifact)
    report["stages"]["compile"] = compile_record
    if compile_record["status"] == "timeout":
        report["overall_status"] = "unknown"
        report["reason"] = "compile_timeout"
        return finish(report, artifact, 2)
    if compile_record["status"] != "completed" or compile_record["returncode"] != 0 or not binary.exists():
        report["stages"]["compile"]["status"] = "compile_failed"
        report["overall_status"] = "failed"
        report["reason"] = "compile_failed"
        return finish(report, artifact, 1)
    report["stages"]["compile"]["status"] = "compiled"
    report["artifacts"].update(binary=str(binary), binary_sha256=sha256(binary))
    installed = re.search(r"^InstalledDir:\s*(.+)$", version["stdout"], re.MULTILINE)
    toolchain_dir = Path(installed.group(1)) if installed else None
    report["stages"]["metadata"] = extract_metadata(binary, artifact, timeout,
                                                       toolchain_dir)

    execution = invoke([str(binary)], timeout)
    report["stages"]["execute"] = execution
    if execution["status"] == "timeout":
        report["stages"]["execute"]["status"] = "run_timeout"
        report["overall_status"] = "unknown"
        report["reason"] = "run_timeout"
        return finish(report, artifact, 2)
    if execution["status"] != "completed" or execution["returncode"] != 0:
        values = parse_probe_output(execution.get("stdout", ""))
        no_device = (values.get("failure_kind") == "no_device" or
                     values.get("device_count") == "0")
        report["stages"]["execute"]["status"] = "no_device" if no_device else "run_failed"
        report["overall_status"] = "unknown" if no_device else "failed"
        report["reason"] = "no_device" if no_device else "run_failed"
        return finish(report, artifact, 2 if no_device else 1)
    values = parse_probe_output(execution["stdout"])
    report["device_identity"] = {key: values.get(key) for key in
                                 ("device_name", "gcn_arch_name", "pci_bus_id",
                                  "hip_runtime_version", "hip_driver_version")}
    semantics = validate_semantics(values)
    report["stages"]["semantic_validation"] = semantics
    if semantics["status"] != "consistent":
        report["overall_status"] = "failed"
        report["reason"] = "semantic_mismatch"
        return finish(report, artifact, 1)
    reconciliation = reconcile_widths(report["stages"]["metadata"], semantics)
    report["overall_status"] = reconciliation["status"]
    report["reason"] = reconciliation["reason"]
    if reconciliation["status"] == "verified":
        report["physical_wave_width"] = reconciliation["physical_wave_width"]
        return finish(report, artifact, 0)
    if reconciliation["status"] == "failed":
        report["metadata_runtime_disagreement"] = reconciliation
        return finish(report, artifact, 1)
    return finish(report, artifact, 2)


def finish(report: dict[str, Any], artifact: Path, code: int) -> tuple[int, Path, dict[str, Any]]:
    report_path = artifact / "report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return code, report_path, report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-base", type=Path, default=ROOT / "artifacts")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--hipcc", help="explicit hipcc path (primarily for reproducible testing)")
    args = parser.parse_args(argv)
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    code, report_path, report = run(args.output_base, args.timeout, args.hipcc)
    print(json.dumps({"overall_status": report["overall_status"],
                      "reason": report["reason"], "report": str(report_path)},
                     sort_keys=True))
    return code


if __name__ == "__main__":
    sys.exit(main())
