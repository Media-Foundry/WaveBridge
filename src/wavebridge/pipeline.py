"""The reference pipeline gates model candidates; it never deploys GPU code."""

from wavebridge.ir.model import Program
from wavebridge.transforms.qdot import retile
from wavebridge.verification.qdot import check
from wavebridge.verification.report import Verdict


def adapt_model(source: Program, target_width: int) -> dict:
    candidate = retile(source, target_width)
    report = check(source, candidate)
    return {
        "decision": "accept_model_candidate" if report.verdict == Verdict.CHECKED else "refuse_adaptation",
        "deployable_gpu_artifact": False,
        "fallback": "not_provisioned_requires_target_validation",
        "candidate": candidate.to_dict(),
        "report": report.to_dict(),
    }
