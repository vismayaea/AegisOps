from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class BlastRadius:
    """Scope of the incident's blast radius across services and dependencies."""

    affected_services: list[str] = field(default_factory=list)
    affected_dependencies: list[str] = field(default_factory=list)
    affected_endpoints: list[str] = field(default_factory=list)
    estimated_scope: str = ""
    severity_impact: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "affected_services": self.affected_services,
            "affected_dependencies": self.affected_dependencies,
            "affected_endpoints": self.affected_endpoints,
            "estimated_scope": self.estimated_scope,
            "severity_impact": self.severity_impact,
        }


@dataclass
class RootCause:
    """The root cause explanation with supporting evidence and blast radius."""

    root_cause_id: str
    incident_id: str
    statement: str
    affected_service: str
    evidence_ids: list[str] = field(default_factory=list)
    confidence: float = 0.0
    blast_radius: BlastRadius | None = None
    contributing_factors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "root_cause_id": self.root_cause_id,
            "incident_id": self.incident_id,
            "statement": self.statement,
            "affected_service": self.affected_service,
            "evidence_ids": self.evidence_ids,
            "confidence": self.confidence,
            "blast_radius": self.blast_radius.to_dict() if self.blast_radius else None,
            "contributing_factors": self.contributing_factors,
        }


from .service import RCAResult, RCAService


__all__ = ["BlastRadius", "RCAResult", "RCAService", "RootCause"]
