from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from uuid import uuid4


class IncidentStatus(StrEnum):
    """Lifecycle state for the incident record."""

    DETECTED = "detected"
    TRIAGED = "triaged"
    EVIDENCE_COLLECTED = "evidence_collected"
    INVESTIGATING = "investigating"
    ROOT_CAUSE_IDENTIFIED = "root_cause_identified"
    RISK_ASSESSED = "risk_assessed"
    REMEDIATION_IN_PROGRESS = "remediation_in_progress"
    RECOVERY_VERIFIED = "recovery_verified"
    RECOVERY_FAILED = "recovery_failed"
    RESOLVED = "resolved"


class IncidentSeverity(StrEnum):
    """Severity tier for customer or service impact."""

    SEV1 = "SEV1"
    SEV2 = "SEV2"
    SEV3 = "SEV3"
    SEV4 = "SEV4"


IncidentLifecycleState = IncidentStatus


@dataclass
class Incident:
    """A single operational incident that follows an investigation lifecycle."""

    title: str
    service: str
    environment: str
    incident_id: str = field(default_factory=lambda: f"inc-{uuid4().hex[:8]}")
    severity: IncidentSeverity = IncidentSeverity.SEV2
    status: IncidentStatus = IncidentStatus.DETECTED
    owner: str = ""
    summary: str = ""
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise ValueError("incident title cannot be empty")
        if not self.service.strip():
            raise ValueError("incident service cannot be empty")
        if not self.environment.strip():
            raise ValueError("incident environment cannot be empty")
        if isinstance(self.severity, str):
            self.severity = IncidentSeverity(self.severity)
        if isinstance(self.status, str):
            self.status = IncidentStatus(self.status)

    def transition_to(self, next_status: IncidentStatus | str) -> None:
        target = IncidentStatus(next_status)
        require_valid_transition(self.status, target)
        self.status = target
        self.updated_at = self.updated_at or target.value

    def to_dict(self) -> dict[str, str | object]:
        return {
            "incident_id": self.incident_id,
            "title": self.title,
            "service": self.service,
            "environment": self.environment,
            "severity": self.severity.value,
            "status": self.status.value,
            "owner": self.owner,
            "summary": self.summary,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


def require_valid_transition(current: IncidentStatus | str, target: IncidentStatus | str) -> None:
    """Validate the incident lifecycle progression and reject invalid jumps."""

    current_status = IncidentStatus(current)
    next_status = IncidentStatus(target)
    valid_transitions: dict[IncidentStatus, tuple[IncidentStatus, ...]] = {
        IncidentStatus.DETECTED: (IncidentStatus.TRIAGED,),
        IncidentStatus.TRIAGED: (IncidentStatus.EVIDENCE_COLLECTED,),
        IncidentStatus.EVIDENCE_COLLECTED: (IncidentStatus.INVESTIGATING,),
        IncidentStatus.INVESTIGATING: (IncidentStatus.ROOT_CAUSE_IDENTIFIED,),
        IncidentStatus.ROOT_CAUSE_IDENTIFIED: (IncidentStatus.RISK_ASSESSED,),
        IncidentStatus.RISK_ASSESSED: (IncidentStatus.REMEDIATION_IN_PROGRESS, IncidentStatus.RESOLVED),
        IncidentStatus.REMEDIATION_IN_PROGRESS: (IncidentStatus.RECOVERY_VERIFIED, IncidentStatus.RECOVERY_FAILED, IncidentStatus.RESOLVED),
        IncidentStatus.RECOVERY_VERIFIED: (IncidentStatus.RESOLVED,),
        IncidentStatus.RECOVERY_FAILED: (IncidentStatus.REMEDIATION_IN_PROGRESS,),
        IncidentStatus.RESOLVED: (),
    }

    if next_status not in valid_transitions.get(current_status, ()):  # pragma: no branch - clarity
        raise ValueError(
            f"invalid incident transition: {current_status.value} -> {next_status.value}"
        )


__all__ = [
    "Incident",
    "IncidentSeverity",
    "IncidentStatus",
    "IncidentLifecycleState",
    "require_valid_transition",
]
