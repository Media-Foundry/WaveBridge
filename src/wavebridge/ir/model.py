"""A deliberately restricted model of integer grouped quantized dot products.

Physical wave execution is not modeled. The model's collective is a guarded,
synchronous shuffle-down within reduction_width, independent of cooperation_width.
"""

from dataclasses import asdict, dataclass
from hashlib import sha256
import json

MODEL_VERSION = "qdot-model/v1"
EXACT_INTEGER = "integer_exact_unbounded"


@dataclass(frozen=True)
class Domain:
    rows: int
    columns: int


@dataclass(frozen=True)
class Launch:
    block_threads: int
    grid_blocks: int


@dataclass(frozen=True)
class Kernel:
    cooperation_width: int
    column_stride: int
    quantization_group: int
    reduction_width: int
    reduction_offsets: tuple[int, ...]
    writer_lane: int


@dataclass(frozen=True)
class Program:
    domain: Domain
    launch: Launch
    kernel: Kernel
    numeric_contract: str = EXACT_INTEGER
    schema_version: str = MODEL_VERSION

    def to_dict(self) -> dict:
        value = asdict(self)
        value["kernel"]["reduction_offsets"] = list(self.kernel.reduction_offsets)
        return value

    def fingerprint(self) -> str:
        encoded = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
        return sha256(encoded.encode()).hexdigest()


def reduction_offsets(width: int) -> tuple[int, ...]:
    if type(width) is not int or width not in (32, 64):
        raise ValueError("reference model supports only logical widths 32 and 64")
    return tuple(1 << shift for shift in reversed(range(width.bit_length() - 1)))


def example_source() -> Program:
    return Program(
        domain=Domain(rows=5, columns=65),
        launch=Launch(block_threads=128, grid_blocks=2),
        kernel=Kernel(32, 32, 32, 32, reduction_offsets(32), 0),
    )
