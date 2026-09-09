from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.evidence import Evidence
from core.incident import Incident
from core.investigation import Hypothesis
from core.rca import BlastRadius, RootCause


@dataclass
class RCAResult:
    """Structured output from root-cause analysis."""

    status: str = "completed"
    root_cause: RootCause | None = None
    blast_radius: BlastRadius | None = None
    supported_hypotheses: list[Hypothesis] = field(default_factory=list)
    rejected_hypotheses: list[Hypothesis] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "root_cause": self.root_cause.to_dict() if self.root_cause else None,
            "blast_radius": self.blast_radius.to_dict() if self.blast_radius else None,
            "supported_hypotheses": [item.to_dict() for item in self.supported_hypotheses],
            "rejected_hypotheses": [item.to_dict() for item in self.rejected_hypotheses],
            "error": self.error,
        }


class RCAService:
    """Selects the strongest supported hypothesis and converts it to a root cause."""

    def __init__(self) -> None:
        self._default_scope_map = {
            "SEV1": "CRITICAL",
            "SEV2": "HIGH",
            "SEV3": "MEDIUM",
            "SEV4": "LOW",
        }

    def analyze(
        self,
        incident: Incident,
        evidence_items: list[Evidence],
        hypotheses: list[Hypothesis],
    ) -> RCAResult:
        if not evidence_items:
            return RCAResult(
                status="insufficient_evidence",
                error="Root-cause analysis requires at least one evidence item.",
            )

        ranked = [item for item in hypotheses if item.status is not item.status.REJECTED]
        if not ranked:
            rejected = [item for item in hypotheses if item.status is item.status.REJECTED]
            return RCAResult(
                status="insufficient_evidence",
                supported_hypotheses=[],
                rejected_hypotheses=rejected,
                error="No supported hypothesis satisfied the evidence threshold.",
            )

        best = max(ranked, key=lambda item: (item.confidence, len(item.supporting_evidence_ids)))
        support_ids = list(dict.fromkeys(best.supporting_evidence_ids))
        coverage = [item.evidence_id for item in evidence_items if item.evidence_id in support_ids]
        if not coverage:
            return RCAResult(
                status="insufficient_evidence",
                supported_hypotheses=[best],
                rejected_hypotheses=[item for item in hypotheses if item is not best],
                error="The strongest hypothesis is not supported by incident evidence.",
            )

        blast_radius = self._build_blast_radius(incident, evidence_items, best)
        root_cause = RootCause(
            root_cause_id=f"rc-{incident.incident_id}",
            incident_id=incident.incident_id,
            statement=best.statement,
            affected_service=best.affected_service or incident.service,
            evidence_ids=coverage,
            confidence=best.confidence,
            blast_radius=blast_radius,
            contributing_factors=self._extract_contributing_factors(best, evidence_items),
        )

        return RCAResult(
            status="completed",
            root_cause=root_cause,
            blast_radius=blast_radius,
            supported_hypotheses=[best],
            rejected_hypotheses=[item for item in hypotheses if item is not best],
        )

    def _build_blast_radius(
        self,
        incident: Incident,
        evidence_items: list[Evidence],
        hypothesis: Hypothesis,
    ) -> BlastRadius:
        dependencies: list[str] = []
        endpoints: list[str] = []
        for item in evidence_items:
            metadata = item.metadata or {}
            dep_value = metadata.get("dependencies")
            if isinstance(dep_value, list):
                dependencies.extend(str(value) for value in dep_value)
            elif isinstance(dep_value, str):
                dependencies.append(dep_value)
            endpoint_value = metadata.get("endpoints")
            if isinstance(endpoint_value, list):
                endpoints.extend(str(value) for value in endpoint_value)
            elif isinstance(endpoint_value, str):
                endpoints.append(endpoint_value)

        affected_service = hypothesis.affected_service or incident.service
        scope = self._default_scope_map.get(incident.severity.value, "MEDIUM")
        impact = "LOW"
        if incident.severity.value in {"SEV1", "SEV2"}:
            impact = "HIGH"
        elif incident.severity.value == "SEV3":
            impact = "MEDIUM"

        return BlastRadius(
            affected_services=[affected_service],
            affected_dependencies=sorted(set(dependencies)),
            affected_endpoints=sorted(set(endpoints)),
            estimated_scope=scope,
            severity_impact=impact,
        )

    def _extract_contributing_factors(
        self,
        hypothesis: Hypothesis,
        evidence_items: list[Evidence],
    ) -> list[str]:
        factors: list[str] = []
        for item in evidence_items:
            if item.evidence_id in hypothesis.supporting_evidence_ids:
                if item.metadata.get("contributing_factor"):
                    factors.append(str(item.metadata["contributing_factor"]))
        if not factors:
            factors = [hypothesis.statement]
        return list(dict.fromkeys(factors))


__all__ = ["RCAResult", "RCAService"]
