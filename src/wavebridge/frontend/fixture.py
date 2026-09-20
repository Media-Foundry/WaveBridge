"""Strict loading prevents misspelled model fields from silently taking defaults."""

import json
from pathlib import Path

from wavebridge.ir.model import Domain, Kernel, Launch, MODEL_VERSION, Program

MAX_FIXTURE_BYTES = 65536


def _fields(value: object, names: set[str], location: str) -> dict:
    if not isinstance(value, dict) or set(value) != names:
        raise ValueError(f"{location}: expected exactly {sorted(names)}")
    return value


def _integer(value: object, location: str, minimum: int = 1) -> int:
    if type(value) is not int or value < minimum:
        raise ValueError(f"{location}: expected integer >= {minimum}, not bool")
    return value


def from_dict(value: object) -> Program:
    root = _fields(value, {"schema_version", "domain", "launch", "kernel", "numeric_contract"}, "root")
    if root["schema_version"] != MODEL_VERSION:
        raise ValueError(f"unsupported schema_version: {root['schema_version']!r}")
    if not isinstance(root["numeric_contract"], str):
        raise ValueError("numeric_contract: expected explicit string")
    domain = _fields(root["domain"], {"rows", "columns"}, "domain")
    launch = _fields(root["launch"], {"block_threads", "grid_blocks"}, "launch")
    kernel = _fields(root["kernel"], {
        "cooperation_width", "column_stride", "quantization_group", "reduction_width",
        "reduction_offsets", "writer_lane",
    }, "kernel")
    offsets = kernel["reduction_offsets"]
    if not isinstance(offsets, list) or len(offsets) > 16:
        raise ValueError("reduction_offsets: expected a list of at most 16 offsets")
    return Program(
        domain=Domain(**{k: _integer(v, f"domain.{k}") for k, v in domain.items()}),
        launch=Launch(**{k: _integer(v, f"launch.{k}") for k, v in launch.items()}),
        kernel=Kernel(
            cooperation_width=_integer(kernel["cooperation_width"], "cooperation_width"),
            column_stride=_integer(kernel["column_stride"], "column_stride"),
            quantization_group=_integer(kernel["quantization_group"], "quantization_group"),
            reduction_width=_integer(kernel["reduction_width"], "reduction_width"),
            reduction_offsets=tuple(_integer(v, "reduction_offset") for v in offsets),
            writer_lane=_integer(kernel["writer_lane"], "writer_lane", minimum=0),
        ),
        numeric_contract=root["numeric_contract"],
    )


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON field: {key}")
        result[key] = value
    return result


def load(path: str | Path) -> Program:
    with Path(path).open("rb") as stream:
        raw = stream.read(MAX_FIXTURE_BYTES + 1)
    if len(raw) > MAX_FIXTURE_BYTES:
        raise ValueError(f"fixture exceeds {MAX_FIXTURE_BYTES} bytes")
    return from_dict(json.loads(raw, object_pairs_hook=_unique_object))
