#!/usr/bin/env python3
"""Independent CPU reference and strict WB-02 input validation."""

from __future__ import annotations

import json
import math
from pathlib import Path
import struct
from typing import Iterable

HERE = Path(__file__).resolve().parent
PROTOCOL = json.loads((HERE / "protocol.json").read_text(encoding="utf-8"))


def f32(value: float) -> float:
    return struct.unpack("<f", struct.pack("<f", value))[0]


def validate(rows: list[list[float]], epsilon: float) -> tuple[int, int]:
    limits = PROTOCOL["input"]
    if not isinstance(epsilon, (int, float)) or isinstance(epsilon, bool) or not math.isfinite(epsilon):
        raise ValueError("epsilon must be finite")
    if not limits["epsilon"]["minimum"] <= epsilon <= limits["epsilon"]["maximum"]:
        raise ValueError("epsilon outside frozen protocol")
    if not isinstance(rows, list) or not limits["nrows"]["minimum"] <= len(rows) <= limits["nrows"]["maximum"]:
        raise ValueError("nrows outside frozen protocol")
    ncols = len(rows[0]) if rows and isinstance(rows[0], list) else 0
    if not limits["ncols"]["minimum"] <= ncols < limits["ncols"]["maximum_exclusive"]:
        raise ValueError("ncols outside frozen protocol")
    for row in rows:
        if not isinstance(row, list) or len(row) != ncols:
            raise ValueError("rows must be rectangular and contiguous")
        for value in row:
            if (not isinstance(value, (int, float)) or isinstance(value, bool) or
                    not math.isfinite(value) or abs(value) > limits["absolute_value_maximum"]):
                raise ValueError("input value outside frozen protocol")
    return len(rows), ncols


def rmsnorm(rows: list[list[float]], epsilon: float) -> list[list[float]]:
    _, ncols = validate(rows, epsilon)
    output = []
    for row in rows:
        values = [f32(value) for value in row]
        mean_square = math.fsum(float(value) * float(value) for value in values) / ncols
        scale = 1.0 / math.sqrt(mean_square + float(epsilon))
        output.append([f32(value * scale) for value in values])
    return output


def deterministic_rows(nrows: int, ncols: int) -> list[list[float]]:
    rows = [[f32((((row * 131 + col * 17) % 257) - 128) / 64.0)
             for col in range(ncols)] for row in range(nrows)]
    validate(rows, 1.0e-5)
    return rows


def compare(actual: Iterable[float], expected: Iterable[float]) -> dict[str, float | int | bool]:
    atol = PROTOCOL["comparison"]["absolute_tolerance"]
    rtol = PROTOCOL["comparison"]["relative_tolerance"]
    actual_values, expected_values = list(actual), list(expected)
    if len(actual_values) != len(expected_values):
        return {"passed": False, "count": len(actual_values), "expected_count": len(expected_values),
                "max_absolute_error": None, "max_relative_error": None,
                "reason": "length_mismatch"}
    max_abs = max_rel = 0.0
    passed = True
    nonfinite = False
    for got, want in zip(actual_values, expected_values):
        if not math.isfinite(got):
            passed = False
            nonfinite = True
            continue
        absolute = abs(got - want)
        relative = absolute / abs(want) if want else 0.0
        max_abs, max_rel = max(max_abs, absolute), max(max_rel, relative)
        passed = passed and absolute <= atol + rtol * abs(want)
    return {"passed": passed, "count": len(actual_values),
            "max_absolute_error": None if nonfinite else max_abs,
            "max_relative_error": None if nonfinite else max_rel,
            "reason": None if passed else "nonfinite_or_outside_tolerance"}
