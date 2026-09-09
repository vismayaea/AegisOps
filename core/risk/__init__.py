from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from core.incident import Incident, IncidentSeverity
from core.rca import BlastRadius


class RiskDecision(StrEnum):
    """Policy decision for whether a remediation may proceed."""

    AUTO_EXECUTE = "auto_execute"
    REQUIRES_APPROVAL = "requires_approval"
    BLOCKED = "blocked"


@dataclass
class RiskAssessment:
    """The result of running the incident risk policy."""

    overall_score: float
    risk_level: str = "unknown"
    recommended_decision: RiskDecision = RiskDecision.AUTO_EXECUTE
    rationale: str = ""
    details: dict[str, float | str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "overall_score": self.overall_score,
            "risk_level": self.risk_level,
            "recommended_decision": self.recommended_decision.value,
            "rationale": self.rationale,
            "details": self.details,
        }


class RiskEngine:
    """Scores operations risk based on incident severity, scope, and recovery confidence."""

    def assess(
        self,
        incident: Incident,
        blast_radius: BlastRadius,
        diagnosis_confidence: float,
        reversibility: float,
        historical_success: float,
    ) -> RiskAssessment:
        severity_weights = {
            IncidentSeverity.SEV1: 35,
            IncidentSeverity.SEV2: 25,
            IncidentSeverity.SEV3: 18,
            IncidentSeverity.SEV4: 8,
        }
        impact_factor = {
            "LOW": 4,
            "MEDIUM": 9,
            "HIGH": 15,
            "CRITICAL": 22,
        }
        blast_factor = (
            len(blast_radius.affected_services) * 6
            + len(blast_radius.affected_dependencies) * 4
            + len(blast_radius.affected_endpoints) * 2
        )
        score = (
            severity_weights.get(incident.severity, 10) * 0.35
            + (1.0 - diagnosis_confidence) * 30
            + (1.0 - reversibility) * 25
            + (1.0 - historical_success) * 25
            + impact_factor.get(blast_radius.severity_impact.upper(), 6) * 0.5
            + min(blast_factor, 20) * 0.75
        )
        score = max(0.0, min(100.0, score))

        if score <= 30:
            decision = RiskDecision.AUTO_EXECUTE
            risk_level = "low"
            rationale = "Low-risk change with strong reversibility and low blast radius."
        elif score <= 70:
            decision = RiskDecision.REQUIRES_APPROVAL
            risk_level = "moderate"
            rationale = "The change should proceed only with explicit approval and safeguards."
        else:
            decision = RiskDecision.BLOCKED
            risk_level = "high"
            rationale = "The remediation is too risky without additional confidence or controls."

        return RiskAssessment(
            overall_score=round(score, 2),
            risk_level=risk_level,
            recommended_decision=decision,
            rationale=rationale,
            details={
                "diagnosis_confidence": diagnosis_confidence,
                "reversibility": reversibility,
                "historical_success": historical_success,
                "severity": incident.severity.value,
                "blast_scope": blast_radius.estimated_scope,
            },
        )


__all__ = ["RiskAssessment", "RiskDecision", "RiskEngine"]
