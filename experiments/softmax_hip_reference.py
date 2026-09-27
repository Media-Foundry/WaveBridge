"""Frozen finite-input reference for the manual HIP softmax compatibility harness."""

from __future__ import annotations

import math
import struct


ABS_TOLERANCE = 2e-6
REL_TOLERANCE = 2e-5
ROW_SUM_TOLERANCE = 2e-5
PATTERNS = {"zero", "sawtooth", "alternating"}


def _dimensions(rows, columns):
    if type(rows) is not int or type(columns) is not int or rows <= 0 or columns <= 0:
        raise ValueError("rows_and_columns_must_be_positive_integers")
    return rows * columns


def _float32(value):
    if type(value) is not float or not math.isfinite(value):
        raise ValueError("input_element_not_finite_float")
    try:
        converted = struct.unpack("<f", struct.pack("<f", value))[0]
    except (OverflowError, struct.error) as error:
        raise ValueError("input_element_not_finite_binary32") from error
    if not math.isfinite(converted) or converted != value:
        raise ValueError("input_element_not_exact_binary32")
    return converted


def _values(values, rows, columns, label):
    size = _dimensions(rows, columns)
    if not isinstance(values, (list, tuple)) or len(values) != size:
        raise ValueError(f"{label}_length_mismatch")
    checked = []
    for value in values:
        if type(value) is not float or not math.isfinite(value):
            raise ValueError(f"{label}_element_not_finite_float")
        checked.append(value)
    return checked


def make_input(rows, columns, pattern):
    """Return one row-major input whose elements are exact finite binary32 values."""
    size = _dimensions(rows, columns)
    if pattern not in PATTERNS:
        raise ValueError("unknown_input_pattern")
    values = []
    for index in range(size):
        if pattern == "zero":
            value = 0.0
        elif pattern == "sawtooth":
            value = ((index * 17) % 101 - 50) / 8.0
        else:
            value = 8.0 if index % 2 == 0 else -8.0
        values.append(_float32(value))
    return values


def reference(values, rows, columns):
    """Compute stable row-wise softmax in Python binary64 arithmetic."""
    checked = _values(values, rows, columns, "input")
    # Bind this reference to binary32 inputs rather than silently rounding them.
    for value in checked:
        _float32(value)
    output = []
    for row in range(rows):
        row_values = checked[row * columns:(row + 1) * columns]
        maximum = max(row_values)
        exponentials = [math.exp(value - maximum) for value in row_values]
        denominator = math.fsum(exponentials)
        output.extend(value / denominator for value in exponentials)
    return output


def evaluate(actual, expected, rows, columns):
    """Apply the frozen element and row-sum tolerances without truncating inputs."""
    actual_values = _values(actual, rows, columns, "actual")
    expected_values = _values(expected, rows, columns, "expected")
    max_abs_error = 0.0
    elements_passed = True
    for observed, wanted in zip(actual_values, expected_values, strict=True):
        error = abs(observed - wanted)
        max_abs_error = max(max_abs_error, error)
        if error > ABS_TOLERANCE + REL_TOLERANCE * abs(wanted):
            elements_passed = False
    max_row_sum_error = 0.0
    for row in range(rows):
        row_sum = math.fsum(actual_values[row * columns:(row + 1) * columns])
        max_row_sum_error = max(max_row_sum_error, abs(row_sum - 1.0))
    passed = elements_passed and max_row_sum_error <= ROW_SUM_TOLERANCE
    return {
        "status": "passed" if passed else "failed",
        "max_abs_error": max_abs_error,
        "max_row_sum_error": max_row_sum_error,
    }


__all__ = ["make_input", "reference", "evaluate"]
