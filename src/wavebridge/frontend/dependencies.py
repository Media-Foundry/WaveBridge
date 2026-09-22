"""Observe files named by one Clang depfile without claiming a frozen snapshot."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "compilation-input-manifest/v1"
EXPECTED_TARGET = "wavebridge-inputs"
MAX_DEPFILE_BYTES = 16 * 1024 * 1024
MAX_DEPENDENCIES = 10000


class _Unknown(Exception):
    def __init__(self, reason: str):
        self.reason = reason


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_hash(value: dict[str, Any]) -> str:
    payload = {key: item for key, item in value.items() if key != "manifest_sha256"}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False).encode()
    return _sha256_bytes(encoded)


def _logical_line(raw: str) -> str:
    output: list[str] = []
    index = 0
    while index < len(raw):
        if raw[index] == "\\" and index + 1 < len(raw) and raw[index + 1] == "\n":
            output.append(" ")
            index += 2
            continue
        if (raw[index] == "\\" and index + 2 < len(raw) and raw[index + 1] == "\r" and
                raw[index + 2] == "\n"):
            output.append(" ")
            index += 3
            continue
        output.append(raw[index])
        index += 1
    lines = [line for line in "".join(output).splitlines() if line.strip()]
    if len(lines) != 1:
        raise _Unknown("depfile_not_exactly_one_rule")
    return lines[0]


def _tokens(line: str) -> tuple[str, list[str]]:
    tokens: list[str] = []
    token: list[str] = []
    delimiter: int | None = None
    index = 0
    while index < len(line):
        character = line[index]
        if character == "\\":
            if index + 1 >= len(line) or line[index + 1] not in {" ", "\t", "#", "\\"}:
                raise _Unknown("depfile_unsupported_backslash_escape")
            token.append(line[index + 1])
            index += 2
            continue
        if character == "$":
            if index + 1 >= len(line) or line[index + 1] != "$":
                raise _Unknown("depfile_ambiguous_dollar_escape")
            token.append("$")
            index += 2
            continue
        if character == "#":
            raise _Unknown("depfile_unescaped_comment_marker")
        if character == ":":
            if delimiter is not None or tokens or not token:
                raise _Unknown("depfile_rule_delimiter_ambiguous")
            delimiter = index
            target = "".join(token)
            token = []
            index += 1
            continue
        if character.isspace():
            if token:
                tokens.append("".join(token))
                token = []
            index += 1
            continue
        if character == "\x00":
            raise _Unknown("depfile_nul_byte")
        token.append(character)
        index += 1
    if token:
        tokens.append("".join(token))
    if delimiter is None:
        raise _Unknown("depfile_rule_delimiter_missing")
    if target != EXPECTED_TARGET:
        raise _Unknown("depfile_target_mismatch")
    if not tokens:
        raise _Unknown("depfile_dependencies_missing")
    if len(tokens) > MAX_DEPENDENCIES:
        raise _Unknown("depfile_dependency_budget_exceeded")
    return target, tokens


def observe(depfile: Path, cwd: Path, source: Path,
            source_before_sha256: str) -> dict[str, Any]:
    """Hash dependencies observed after compilation from one strict Clang depfile."""
    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": "unknown",
        "reason": None,
        "observation": "dependency_contents_observed_after_compilation",
        "frozen_snapshot": False,
        "complete_dependency_closure_guaranteed": False,
        "source_stable": None,
        "files": [],
        "raw_depfile": None,
        "raw_depfile_sha256": None,
        "manifest_sha256": None,
        "limitations": [
            "file contents are observed after compilation and are not a frozen compiler input snapshot",
            "the depfile is trusted only as compiler-emitted dependency evidence, not as a closure proof",
            "concurrent dependency modification during compilation cannot be excluded",
        ],
    }
    if (not isinstance(depfile, Path) or not isinstance(cwd, Path) or
            not isinstance(source, Path) or not isinstance(source_before_sha256, str) or
            len(source_before_sha256) != 64 or
            any(character not in "0123456789abcdef" for character in source_before_sha256)):
        result["reason"] = "invalid_inputs"
        return result
    try:
        raw_bytes = depfile.read_bytes()
    except OSError:
        result["reason"] = "depfile_unreadable"
        return result
    result["raw_depfile_sha256"] = _sha256_bytes(raw_bytes)
    if len(raw_bytes) > MAX_DEPFILE_BYTES:
        result["reason"] = "depfile_size_budget_exceeded"
        return result
    try:
        raw = raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        result["reason"] = "depfile_not_utf8"
        return result
    result["raw_depfile"] = raw
    try:
        _, dependencies = _tokens(_logical_line(raw))
        workdir = cwd.resolve(strict=True)
        source_path = source.resolve(strict=True)
        if not workdir.is_dir() or not source_path.is_file():
            raise _Unknown("cwd_or_source_invalid")
        files: list[dict[str, Any]] = []
        seen: set[str] = set()
        source_seen = False
        for observed in dependencies:
            if not observed or observed in seen:
                if not observed:
                    raise _Unknown("depfile_empty_dependency")
                continue
            seen.add(observed)
            candidate = Path(observed)
            if not candidate.is_absolute():
                candidate = workdir / candidate
            try:
                resolved = candidate.resolve(strict=True)
                stat = resolved.stat()
                if not resolved.is_file():
                    raise _Unknown("dependency_not_regular_file")
                digest = _sha256_file(resolved)
            except _Unknown:
                raise
            except (OSError, RuntimeError):
                raise _Unknown("dependency_missing_or_unreadable")
            is_source = resolved == source_path
            source_seen = source_seen or is_source
            files.append({"observed_path": observed, "resolved_path": str(resolved),
                          "size": stat.st_size, "sha256": digest,
                          "roles": ["source"] if is_source else ["dependency"]})
        if not source_seen:
            raise _Unknown("source_missing_from_depfile")
        files.sort(key=lambda item: (item["resolved_path"], item["observed_path"]))
        result["files"] = files
        source_after = next(item["sha256"] for item in files if "source" in item["roles"])
        result["source_stable"] = source_after == source_before_sha256
        if not result["source_stable"]:
            raise _Unknown("source_changed_during_collection")
        result.update(status="observed", reason=None)
        result["manifest_sha256"] = _canonical_hash(result)
    except _Unknown as error:
        result["reason"] = error.reason
    except (OSError, RuntimeError):
        result["reason"] = "cwd_or_source_missing_or_unreadable"
    return result
