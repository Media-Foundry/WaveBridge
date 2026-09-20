from dataclasses import asdict, dataclass, field
from enum import Enum


class Verdict(str, Enum):
    CHECKED = "checked"
    REJECTED = "rejected"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class CheckReport:
    verdict: Verdict
    reason: str
    source_sha256: str
    target_sha256: str
    domain: dict
    limits: dict
    diagnostic: dict = field(default_factory=dict)
    checker: str = "qdot-polynomial/v1"
    scope: str = "fixed_shape_structured_model_unbounded_integer_polynomial_identity"
    numeric_contract: str = "integer_exact_unbounded"
    not_established: tuple[str, ...] = (
        "HIP/CUDA source correspondence",
        "machine integer overflow semantics",
        "floating-point equivalence or error tolerance",
        "physical wave, mask, convergence, aliasing or memory-model correctness",
        "other shapes, GPU execution, performance or novelty",
    )

    def to_dict(self) -> dict:
        return asdict(self)
