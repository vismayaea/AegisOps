from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ScenarioName(str, Enum):
    API_LATENCY_SPIKE = "api_latency_spike"
    DATABASE_FAILURE = "database_failure"
    REDIS_OUTAGE = "redis_outage"
    ELEVATED_ERROR_RATE = "elevated_error_rate"
    WORKER_DELAY = "worker_delay"


class IncidentStatus(str, Enum):
    HEALTHY = "healthy"
    DETECTED = "detected"
    INVESTIGATING = "investigating"
    AWAITING_APPROVAL = "awaiting_approval"
    REMEDIATING = "remediating"
    VERIFYING = "verifying"
    RESOLVED = "resolved"


@dataclass(frozen=True)
class MetricsSnapshot:
    label: str
    latency_ms: int
    error_rate: float
    throughput_rpm: int
    database_health: float
    redis_health: float
    worker_lag_ms: int

    def degraded(self) -> bool:
        return (
            self.latency_ms > 450
            or self.error_rate > 0.02
            or self.database_health < 0.9
            or self.redis_health < 0.9
            or self.worker_lag_ms > 500
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "latency_ms": self.latency_ms,
            "error_rate": self.error_rate,
            "throughput_rpm": self.throughput_rpm,
            "database_health": self.database_health,
            "redis_health": self.redis_health,
            "worker_lag_ms": self.worker_lag_ms,
        }


@dataclass(frozen=True)
class EvidenceItem:
    id: str
    source: str
    summary: str
    service: str
    severity: str
    observed_value: str

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass(frozen=True)
class InvestigationResult:
    likely_root_cause: str
    confidence: float
    affected_service: str
    supporting_evidence: list[str]
    hypotheses: list[dict[str, Any]]

    def as_dict(self) -> dict[str, Any]:
        return {
            "likely_root_cause": self.likely_root_cause,
            "confidence": self.confidence,
            "affected_service": self.affected_service,
            "supporting_evidence": self.supporting_evidence,
            "hypotheses": self.hypotheses,
        }


@dataclass(frozen=True)
class RiskReport:
    score: int
    level: str
    approval_required: bool
    factors: dict[str, int | float | str | bool]

    def as_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "level": self.level,
            "approval_required": self.approval_required,
            "factors": self.factors,
        }


@dataclass(frozen=True)
class RemediationAction:
    id: str
    description: str
    affected_service: str
    reversibility: int
    historical_success: int

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass(frozen=True)
class ActionExecution:
    action_id: str
    status: str
    message: str

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass(frozen=True)
class RecoveryReport:
    recovered: bool
    criteria: dict[str, bool]
    before: MetricsSnapshot
    during: MetricsSnapshot
    after: MetricsSnapshot

    def as_dict(self) -> dict[str, Any]:
        return {
            "recovered": self.recovered,
            "criteria": self.criteria,
            "before": self.before.as_dict(),
            "during": self.during.as_dict(),
            "after": self.after.as_dict(),
        }


@dataclass(frozen=True)
class TraceEvent:
    id: str
    event_type: str
    message: str
    created_at: datetime
    references: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        event_type: str,
        message: str,
        *,
        references: list[str] | None = None,
        details: dict[str, Any] | None = None,
    ) -> "TraceEvent":
        return cls(
            id=f"trace_{uuid4().hex[:10]}",
            event_type=event_type,
            message=message,
            created_at=utc_now(),
            references=references or [],
            details=details or {},
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "event_type": self.event_type,
            "message": self.message,
            "created_at": self.created_at.isoformat(),
            "references": self.references,
            "details": self.details,
        }


@dataclass
class Incident:
    id: str
    scenario: ScenarioName
    status: IncidentStatus
    created_at: datetime
    before: MetricsSnapshot
    during: MetricsSnapshot
    after: MetricsSnapshot | None = None
    evidence: list[EvidenceItem] = field(default_factory=list)
    investigation: InvestigationResult | None = None
    risk: RiskReport | None = None
    selected_action: RemediationAction | None = None
    execution: ActionExecution | None = None
    recovery: RecoveryReport | None = None
    trace: list[TraceEvent] = field(default_factory=list)
    approval_granted: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "scenario": self.scenario.value,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "before": self.before.as_dict(),
            "during": self.during.as_dict(),
            "after": self.after.as_dict() if self.after else None,
            "evidence": [item.as_dict() for item in self.evidence],
            "investigation": self.investigation.as_dict() if self.investigation else None,
            "risk": self.risk.as_dict() if self.risk else None,
            "selected_action": self.selected_action.as_dict() if self.selected_action else None,
            "execution": self.execution.as_dict() if self.execution else None,
            "recovery": self.recovery.as_dict() if self.recovery else None,
            "trace": [event.as_dict() for event in self.trace],
            "approval_granted": self.approval_granted,
        }
