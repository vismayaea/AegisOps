from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.incident import Incident
from core.incident_trace import DecisionTrace


@dataclass
class Postmortem:
    """Structured postmortem generated from actual incident records."""

    incident_summary: str = "Not available from incident record."
    customer_or_system_impact: str = "Not available from incident record."
    timeline: list[str] = None  # type: ignore[assignment]
    root_cause: str = "Not available from incident record."
    supporting_evidence: list[str] = None  # type: ignore[assignment]
    remediation: str = "Not available from incident record."
    recovery_verification: str = "Not available from incident record."
    human_intervention: str = "Not available from incident record."
    lessons_learned: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.timeline is None:
            self.timeline = []
        if self.supporting_evidence is None:
            self.supporting_evidence = []
        if self.lessons_learned is None:
            self.lessons_learned = []

    def to_dict(self) -> dict[str, Any]:
        return {
            "incident_summary": self.incident_summary,
            "customer_or_system_impact": self.customer_or_system_impact,
            "timeline": self.timeline,
            "root_cause": self.root_cause,
            "supporting_evidence": self.supporting_evidence,
            "remediation": self.remediation,
            "recovery_verification": self.recovery_verification,
            "human_intervention": self.human_intervention,
            "lessons_learned": self.lessons_learned,
        }


def generate_postmortem(
    *,
    incident: Incident,
    trace: DecisionTrace,
    summary: str | None = None,
    impact: str | None = None,
    root_cause: str | None = None,
    evidence: list[str] | None = None,
    remediation: str | None = None,
    verification: str | None = None,
    human_intervention: str | None = None,
    lessons: list[str] | None = None,
) -> Postmortem:
    """Generate a structured postmortem from the stored incident data and trace."""
    return Postmortem(
        incident_summary=summary or f"Incident {incident.incident_id}: {incident.title}",
        customer_or_system_impact=impact or "Not available from incident record.",
        timeline=[event.summary for event in trace.events],
        root_cause=root_cause or "Not available from incident record.",
        supporting_evidence=evidence or ["Not available from incident record."],
        remediation=remediation or "Not available from incident record.",
        recovery_verification=verification or "Not available from incident record.",
        human_intervention=human_intervention or "Not available from incident record.",
        lessons_learned=lessons or ["Not available from incident record."],
    )


__all__ = ["Postmortem", "generate_postmortem"]
