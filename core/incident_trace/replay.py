from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.incident import Incident, IncidentStatus
from core.incident_trace import DecisionTrace, DecisionTraceEventType


@dataclass
class IncidentReplay:
    """Deterministic reconstruction of an incident timeline from stored state and trace."""

    incident_id: str
    status: IncidentStatus
    chronological_events: list[dict[str, Any]] = field(default_factory=list)
    decisions: list[str] = field(default_factory=list)
    evidence_references: list[str] = field(default_factory=list)
    execution_records: list[dict[str, Any]] = field(default_factory=list)
    verification_results: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "status": self.status.value,
            "chronological_events": self.chronological_events,
            "decisions": self.decisions,
            "evidence_references": self.evidence_references,
            "execution_records": self.execution_records,
            "verification_results": self.verification_results,
        }


def replay_incident(
    *,
    incident: Incident,
    trace: DecisionTrace,
    evidence_refs: list[str] | None = None,
    execution_records: list[dict[str, Any]] | None = None,
    verification_results: list[dict[str, Any]] | None = None,
) -> IncidentReplay:
    """Reconstruct the incident lifecycle from stored state and trace as a deterministic timeline."""
    ordered = [
        {
            "event_type": event.event_type.value,
            "summary": event.summary,
            "actor": event.actor,
            "timestamp": event.timestamp,
            "incident_id": event.incident_id,
            "action_id": event.action_id,
            "execution_id": event.execution_id,
            "evidence_ids": event.evidence_ids,
        }
        for event in trace.events
    ]
    decisions = [event.summary for event in trace.events]
    evidence_refs = list(evidence_refs or [])
    execution_records = list(execution_records or [])
    verification_results = list(verification_results or [])

    status = incident.status
    if any(item["event_type"] == DecisionTraceEventType.RESOLVED.value for item in ordered):
        status = IncidentStatus.RESOLVED

    return IncidentReplay(
        incident_id=incident.incident_id,
        status=status,
        chronological_events=ordered,
        decisions=decisions,
        evidence_references=evidence_refs,
        execution_records=execution_records,
        verification_results=verification_results,
    )


__all__ = ["IncidentReplay", "replay_incident"]
