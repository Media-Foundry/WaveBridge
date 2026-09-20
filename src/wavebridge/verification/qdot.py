"""Finite symbolic interpreter for the documented qdot-model/v1 only.

Every monomial is q[row, column] * scale[row, scale_index] * x[column].
Counter coefficients preserve duplicate contributions. Exact integer addition
and multiplication permit canonicalization; this is not valid for IEEE floats.
"""

from collections import Counter
from dataclasses import asdict, dataclass

from wavebridge.frontend.fixture import from_dict
from wavebridge.ir.model import EXACT_INTEGER, Program
from wavebridge.verification.report import CheckReport, Verdict

Monomial = tuple[int, int, int]
Polynomial = Counter[Monomial]


@dataclass(frozen=True)
class Limits:
    max_rows: int = 64
    max_columns: int = 4096
    max_threads: int = 256
    max_blocks: int = 64
    max_expansion: int = 2_000_000

    def __post_init__(self) -> None:
        if any(type(value) is not int or value <= 0 for value in asdict(self).values()):
            raise ValueError("all checker limits must be positive integers")


class UnsupportedModel(ValueError):
    pass


class InvalidExecution(ValueError):
    pass


def output_polynomials(program: Program, limits: Limits) -> dict[int, Polynomial]:
    # Validate in-process callers too; JSON is not the only public entry point.
    from_dict(program.to_dict())
    d, launch, k = program.domain, program.launch, program.kernel
    if program.numeric_contract != EXACT_INTEGER:
        raise UnsupportedModel("only explicit unbounded integer semantics are implemented")
    if k.cooperation_width not in (32, 64) or k.reduction_width not in (32, 64):
        raise UnsupportedModel("only logical widths 32 and 64 are supported")
    if (d.rows > limits.max_rows or d.columns > limits.max_columns
            or launch.block_threads > limits.max_threads or launch.grid_blocks > limits.max_blocks):
        raise UnsupportedModel("shape or launch exceeds checker limits")
    if launch.block_threads % k.cooperation_width or launch.block_threads % k.reduction_width:
        raise UnsupportedModel("partial logical groups in a block are not supported")
    if k.writer_lane >= k.cooperation_width:
        raise InvalidExecution("writer lane is outside the cooperation group")
    if any(offset >= k.reduction_width for offset in k.reduction_offsets):
        raise UnsupportedModel("shuffle offset must be inside reduction width")
    # Conservative bound on expanded contributions before allocating expressions.
    per_lane = (d.columns + k.column_stride - 1) // k.column_stride
    expansion = (launch.grid_blocks * launch.block_threads * per_lane
                 * (1 << (len(k.reduction_offsets) + 1)))
    if expansion > limits.max_expansion:
        raise UnsupportedModel("symbolic expansion exceeds checker budget")

    rows_per_block = launch.block_threads // k.cooperation_width
    outputs: dict[int, Polynomial] = {}
    for block in range(launch.grid_blocks):
        values: list[Polynomial | None] = []
        for thread in range(launch.block_threads):
            row = block * rows_per_block + thread // k.cooperation_width
            lane = thread % k.cooperation_width
            if row >= d.rows:
                values.append(None)
                continue
            values.append(Counter(
                (row, column, column // k.quantization_group)
                for column in range(lane, d.columns, k.column_stride)
            ))

        for offset in k.reduction_offsets:
            previous = values
            values = [value.copy() if value is not None else None for value in previous]
            for thread, value in enumerate(values):
                if value is None or thread % k.reduction_width + offset >= k.reduction_width:
                    continue
                incoming = previous[thread + offset]
                if incoming is None:
                    raise UnsupportedModel("collective reads an inactive lane")
                value.update(incoming)

        for thread, value in enumerate(values):
            if value is None or thread % k.cooperation_width != k.writer_lane:
                continue
            row = block * rows_per_block + thread // k.cooperation_width
            if row in outputs:
                raise InvalidExecution(f"multiple writers for row {row}")
            outputs[row] = value
    if set(outputs) != set(range(d.rows)):
        raise InvalidExecution("launch does not write every declared output row")
    return outputs


def check(source: Program, target: Program, limits: Limits | None = None) -> CheckReport:
    limits = limits or Limits()
    common = {
        "source_sha256": source.fingerprint(),
        "target_sha256": target.fingerprint(),
        "domain": asdict(source.domain),
        "limits": asdict(limits),
        "numeric_contract": source.numeric_contract,
    }
    if source.domain != target.domain or source.numeric_contract != target.numeric_contract:
        return CheckReport(Verdict.UNKNOWN, "incompatible_external_contracts", **common)
    try:
        expected = output_polynomials(source, limits)
    except (ValueError, TypeError) as exc:
        return CheckReport(Verdict.UNKNOWN, "source_precondition_not_established",
                           diagnostic={"detail": str(exc)}, **common)
    try:
        actual = output_polynomials(target, limits)
    except UnsupportedModel as exc:
        return CheckReport(Verdict.UNKNOWN, "target_outside_supported_model",
                           diagnostic={"detail": str(exc)}, **common)
    except (ValueError, TypeError) as exc:
        return CheckReport(Verdict.REJECTED, "invalid_target_model",
                           diagnostic={"detail": str(exc)}, **common)
    for row in sorted(expected):
        if expected[row] != actual[row]:
            term = next(term for term in sorted(expected[row].keys() | actual[row].keys())
                        if expected[row][term] != actual[row][term])
            return CheckReport(Verdict.REJECTED, "output_polynomial_mismatch", diagnostic={
                "output_row": row,
                "monomial": {"q_row": term[0], "column": term[1], "scale_index": term[2]},
                "source_coefficient": expected[row][term],
                "target_coefficient": actual[row][term],
            }, **common)
    return CheckReport(Verdict.CHECKED, "all_output_polynomials_identical", **common)
