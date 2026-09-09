from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class EvidenceSourceType(StrEnum):
    """Source that produced a unit of evidence."""

    ALERTS = "alerts"
    LOGS = "logs"
    METRICS = "metrics"
    TRACES = "traces"
    DEPLOYMENT = "deployment"
    USER_REPORT = "user_report"


@dataclass
class Evidence:
    """One atomic item of information collected during an investigation."""

    evidence_id: str
    incident_id: str
    source_type: EvidenceSourceType | str
    source: str
    summary: str
    raw_reference: str
    relevance_score: float = 0.0
    confidence: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""

    def __post_init__(self) -> None:
        if isinstance(self.source_type, str):
            self.source_type = EvidenceSourceType(self.source_type)

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "incident_id": self.incident_id,
            "source_type": self.source_type.value,
            "source": self.source,
            "summary": self.summary,
            "raw_reference": self.raw_reference,
            "relevance_score": self.relevance_score,
            "confidence": self.confidence,
            "metadata": self.metadata,
            "created_at": self.created_at,
        }


class EvidenceStore:
    """Simple in-memory evidence store for a single incident session."""

    def __init__(self) -> None:
        self._items: list[Evidence] = []

    def add(self, evidence: Evidence) -> Evidence:
        self._items.append(evidence)
        return evidence

    def get_for_incident(self, incident_id: str) -> list[Evidence]:
        return [item for item in self._items if item.incident_id == incident_id]


__all__ = ["Evidence", "EvidenceSourceType", "EvidenceStore"]
