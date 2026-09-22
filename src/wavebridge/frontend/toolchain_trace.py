"""Observe one planned Clang ``-cc1`` job from driver ``-###`` stderr.

This module never executes a command found in the trace.  A successful report
describes one separately requested driver dry-run, not the identity of the
process which produced an AST and not a frozen compilation-input closure.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shlex
from typing import Any


SCHEMA_VERSION = "clang-driver-toolchain-trace/v1"
BITCODE_FLAGS = {"-mlink-builtin-bitcode", "-mlink-bitcode"}


class _Unknown(Exception):
    def __init__(self, reason: str):
        self.reason = reason


def _digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _file(path: Path, reason: str) -> dict[str, Any]:
    try:
        resolved = path.resolve(strict=True)
        if not resolved.is_file():
            raise _Unknown(reason)
        digest = hashlib.sha256()
        size = 0
        with resolved.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                size += len(chunk)
                digest.update(chunk)
    except _Unknown:
        raise
    except (OSError, RuntimeError):
        raise _Unknown(reason)
    return {"observed_path": str(path), "resolved_path": str(resolved),
            "size": size, "sha256": digest.hexdigest()}


def _one_option(tokens: list[str], option: str, *, required: bool) -> str | None:
    values: list[str] = []
    for index, token in enumerate(tokens):
        if token == option:
            if (index + 1 >= len(tokens) or not tokens[index + 1] or
                    tokens[index + 1].startswith("-")):
                raise _Unknown("planned_job_option_value_missing")
            values.append(tokens[index + 1])
        elif token.startswith(option + "="):
            raise _Unknown("planned_job_joined_option_unsupported")
    if not values:
        if required:
            raise _Unknown("planned_job_required_option_missing")
        return None
    if len(values) != 1:
        raise _Unknown("planned_job_option_repeated_or_conflicting")
    return values[0]


def _jobs(stderr: str) -> list[list[str]]:
    jobs: list[list[str]] = []
    for line in stderr.splitlines():
        if "-cc1" not in line:
            continue
        try:
            tokens = shlex.split(line, posix=True)
        except ValueError:
            raise _Unknown("driver_trace_shell_quoting_invalid")
        if "-cc1" in tokens:
            jobs.append(tokens)
    return jobs


def observe(stderr: str, cwd: Path) -> dict[str, Any]:
    """Parse and hash the unique planned cc1 job in Clang driver trace text."""
    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": "unknown",
        "reason": None,
        "raw_stderr": stderr if isinstance(stderr, str) else None,
        "raw_stderr_sha256": (_digest_bytes(stderr.encode("utf-8"))
                              if isinstance(stderr, str) else None),
        "cwd": str(cwd) if isinstance(cwd, Path) else None,
        "planned_job": None,
        "compiler": None,
        "triple": None,
        "target_cpu": None,
        "resource_dir": None,
        "bitcode_files": [],
        "actual_ast_process_identity_established": False,
        "frozen_compilation_input_closure_established": False,
        "source_program_checked": False,
        "deployable": False,
        "scope": "one_unique_cc1_job_printed_by_a_separate_clang_driver_dry_run",
        "limitations": [
            "the planned job was parsed from separate -### stderr and was not executed here",
            "the report does not establish the identity of the subprocess which produced an AST",
            "the report does not freeze or prove a complete compilation-input closure",
        ],
    }
    if not isinstance(stderr, str) or not isinstance(cwd, Path):
        result["reason"] = "invalid_inputs"
        return result
    try:
        try:
            resolved_cwd = cwd.resolve(strict=True)
        except (OSError, RuntimeError):
            raise _Unknown("cwd_not_directory")
        if not resolved_cwd.is_dir():
            raise _Unknown("cwd_not_directory")
        result["cwd"] = str(resolved_cwd)
        jobs = _jobs(stderr)
        if len(jobs) != 1:
            raise _Unknown("planned_cc1_job_not_unique")
        tokens = jobs[0]
        if tokens.count("-cc1") != 1 or tokens.index("-cc1") != 1:
            raise _Unknown("planned_cc1_job_layout_unsupported")
        executable = Path(tokens[0])
        if not executable.is_absolute():
            raise _Unknown("planned_compiler_path_not_absolute")
        compiler = _file(executable, "planned_compiler_missing_or_unreadable")
        triple = _one_option(tokens, "-triple", required=True)
        target_cpu = _one_option(tokens, "-target-cpu", required=False)
        resource_text = _one_option(tokens, "-resource-dir", required=True)
        assert triple is not None and resource_text is not None
        resource_path = Path(resource_text)
        if not resource_path.is_absolute():
            raise _Unknown("resource_dir_path_not_absolute")
        try:
            resource_resolved = resource_path.resolve(strict=True)
            if not resource_resolved.is_dir() or not os.access(resource_resolved, os.R_OK):
                raise _Unknown("resource_dir_missing_or_unreadable")
        except _Unknown:
            raise
        except (OSError, RuntimeError):
            raise _Unknown("resource_dir_missing_or_unreadable")
        bitcode: list[dict[str, Any]] = []
        index = 0
        while index < len(tokens):
            token = tokens[index]
            if token in BITCODE_FLAGS:
                if index + 1 >= len(tokens) or not tokens[index + 1]:
                    raise _Unknown("bitcode_path_missing")
                path = Path(tokens[index + 1])
                if not path.is_absolute():
                    raise _Unknown("bitcode_path_not_absolute")
                bitcode.append({"flag": token,
                                **_file(path, "bitcode_file_missing_or_unreadable")})
                index += 2
                continue
            if any(token.startswith(flag + "=") for flag in BITCODE_FLAGS):
                raise _Unknown("joined_bitcode_option_unsupported")
            index += 1
        result.update(
            status="observed",
            reason=None,
            planned_job=tokens,
            compiler=compiler,
            triple=triple,
            target_cpu=target_cpu,
            resource_dir={"observed_path": resource_text,
                          "resolved_path": str(resource_resolved)},
            bitcode_files=bitcode,
        )
    except _Unknown as error:
        result["reason"] = error.reason
    return result
