from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class HypothesisStatus(StrEnum):
    """Lifecycle states for in-flight hypotheses."""

    PROPOSED = "proposed"
    TESTING = "testing"
    VALIDATED = "validated"
    REJECTED = "rejected"


@dataclass
class Hypothesis:
    """A single explanation under investigation for an incident."""

    hypothesis_id: str
    incident_id: str
    statement: str
    affected_service: str
    supporting_evidence_ids: list[str] = field(default_factory=list)
    contradicting_evidence_ids: list[str] = field(default_factory=list)
    confidence: float = 0.0
    status: HypothesisStatus = HypothesisStatus.PROPOSED

    def __post_init__(self) -> None:
        if isinstance(self.status, str):
            self.status = HypothesisStatus(self.status)

    def to_dict(self) -> dict[str, object]:
        return {
            "hypothesis_id": self.hypothesis_id,
            "incident_id": self.incident_id,
            "statement": self.statement,
            "affected_service": self.affected_service,
            "supporting_evidence_ids": self.supporting_evidence_ids,
            "contradicting_evidence_ids": self.contradicting_evidence_ids,
            "confidence": self.confidence,
            "status": self.status.value,
        }


class HypothesisRanker:
    """Sorts hypotheses by confidence and support."""

    @staticmethod
    def rank(hypotheses: list[Hypothesis]) -> list[Hypothesis]:
        return sorted(
            hypotheses,
            key=lambda hypothesis: (
                hypothesis.confidence,
                len(hypothesis.supporting_evidence_ids),
                -len(hypothesis.contradicting_evidence_ids),
            ),
            reverse=True,
        )


from .service import InvestigationResult, InvestigationService


__all__ = [
    "Hypothesis",
    "HypothesisRanker",
    "HypothesisStatus",
    "InvestigationResult",
    "InvestigationService",
]
