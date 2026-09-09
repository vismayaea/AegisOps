from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from uuid import uuid4


class ActionType(StrEnum):
    """Type of operational action."""

    ROLLBACK = "rollback"
    SCALE = "scale"
    FAILOVER = "failover"
    PATCH = "patch"
    RESTART = "restart"
    CLEAR_LATENCY_FAULT = "clear_latency_fault"
    CLEAR_ERROR_RATE_FAULT = "clear_error_rate_fault"
    CLEAR_DATABASE_FAILURE = "clear_database_failure"
    CLEAR_REDIS_FAILURE = "clear_redis_failure"
    REDUCE_WORKER_DELAY = "reduce_worker_delay"


class ApprovalState(StrEnum):
    """Approval lifecycle for unsafe actions."""

    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTED = "executed"


class ExecutionStatus(StrEnum):
    """State of an action execution record."""

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class ActionPlan:
    """A candidate remediation action with risk and approval metadata."""

    action_id: str
    incident_id: str
    action_type: ActionType | str
    description: str
    target: str
    parameters: dict[str, object] = field(default_factory=dict)
    reversibility: str = "UNKNOWN"
    estimated_blast_radius: str = "UNKNOWN"
    risk_score: int = 0
    requires_approval: bool = False
    approval_state: ApprovalState = ApprovalState.AWAITING_APPROVAL
    execution_status: ExecutionStatus = ExecutionStatus.QUEUED

    def __post_init__(self) -> None:
        if isinstance(self.action_type, str):
            try:
                self.action_type = ActionType(self.action_type)
            except ValueError:
                pass
        if isinstance(self.approval_state, str):
            self.approval_state = ApprovalState(self.approval_state)
        if isinstance(self.execution_status, str):
            self.execution_status = ExecutionStatus(self.execution_status)

    def to_dict(self) -> dict[str, object]:
        return {
            "action_id": self.action_id,
            "incident_id": self.incident_id,
            "action_type": self.action_type.value,
            "description": self.description,
            "target": self.target,
            "parameters": self.parameters,
            "reversibility": self.reversibility,
            "estimated_blast_radius": self.estimated_blast_radius,
            "risk_score": self.risk_score,
            "requires_approval": self.requires_approval,
            "approval_state": self.approval_state.value,
            "execution_status": self.execution_status.value,
        }


@dataclass
class ExecutionRecord:
    """A single execution of a remediation within an incident."""

    execution_id: str = ""
    record_id: str = ""
    action_id: str = ""
    incident_id: str = ""
    status: ExecutionStatus = ExecutionStatus.QUEUED
    started_at: str = ""
    completed_at: str = ""
    executor: str = "aegisops"
    target: str = ""
    output_summary: str = ""
    error: str = ""
    rollback_available: bool = False
    output: str = ""

    def __post_init__(self) -> None:
        if isinstance(self.status, str):
            self.status = ExecutionStatus(self.status)
        if not self.execution_id:
            self.execution_id = self.record_id or f"exec-{uuid4().hex[:8]}"
        if not self.record_id:
            self.record_id = self.execution_id
        if not self.output_summary and self.output:
            self.output_summary = self.output


from .planner import NoSafeRemediation, RemediationPlanner


__all__ = [
    "ActionPlan",
    "ActionType",
    "ApprovalState",
    "ExecutionRecord",
    "ExecutionStatus",
    "NoSafeRemediation",
    "RemediationPlanner",
]
