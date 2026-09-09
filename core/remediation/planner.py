from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.incident import Incident
from core.rca import RootCause
from core.risk import RiskAssessment

from . import ActionPlan, ActionType, ApprovalState, ExecutionStatus


@dataclass
class NoSafeRemediation:
    """Structured state for cases where no safe remediation can be proposed."""

    incident_id: str
    reason: str
    requires_approval: bool = False
    risk_score: int = 100
    status: str = "no_safe_remediation_available"

    def to_dict(self) -> dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "reason": self.reason,
            "requires_approval": self.requires_approval,
            "risk_score": self.risk_score,
            "status": self.status,
        }


class RemediationPlanner:
    """Transforms an RCA and a risk assessment into a safe remediation action plan."""

    def plan(
        self,
        incident: Incident,
        root_cause: RootCause | None,
        risk_assessment: RiskAssessment | None,
    ) -> ActionPlan | NoSafeRemediation:
        if root_cause is None:
            return NoSafeRemediation(
                incident_id=incident.incident_id,
                reason="No root cause was available to base a remediation plan on.",
            )

        if risk_assessment is not None and risk_assessment.recommended_decision.value == "blocked":
            return NoSafeRemediation(
                incident_id=incident.incident_id,
                reason="Risk policy blocked remediation due to high blast radius or low reversibility.",
                requires_approval=True,
                risk_score=int(risk_assessment.overall_score),
            )

        normalized = (root_cause.statement or "").lower()
        if "connection" in normalized or "pool" in normalized:
            action_type = ActionType.SCALE
            description = "Increase service capacity and recycle affected connections before resuming normal traffic."
            parameters = {"target_service": root_cause.affected_service, "mode": "scale_and_recycle"}
        elif "deploy" in normalized or "release" in normalized or "version" in normalized:
            action_type = ActionType.ROLLBACK
            description = "Revert the most recent deployment affecting the failing service."
            parameters = {"target_service": root_cause.affected_service, "rollback": True}
        elif "failover" in normalized or "region" in normalized or "dependency" in normalized:
            action_type = ActionType.FAILOVER
            description = "Shift traffic away from the failing dependency or region to the healthy path."
            parameters = {"target_service": root_cause.affected_service, "failover": True}
        elif "restart" in normalized or "crash" in normalized or "deadlock" in normalized:
            action_type = ActionType.RESTART
            description = "Restart the affected service instance to clear the failing runtime state."
            parameters = {"target_service": root_cause.affected_service, "restart": True}
        elif "latency" in normalized and ("fault" in normalized or "spike" in normalized or "delay" in normalized):
            action_type = ActionType.CLEAR_LATENCY_FAULT
            description = "Clear the injected latency fault (clear_latency_fault) in the simulation target to restore nominal API performance."
            parameters = {"target_service": root_cause.affected_service, "action": "clear_latency_fault"}
        elif "error rate" in normalized or "error-rate" in normalized or ("error" in normalized and "rate" in normalized):
            action_type = ActionType.CLEAR_ERROR_RATE_FAULT
            description = "Clear the injected error-rate fault (clear_error_rate_fault) and return the target to a stable, healthy service profile."
            parameters = {"target_service": root_cause.affected_service, "action": "clear_error_rate_fault"}
        elif "database" in normalized or "db" in normalized:
            action_type = ActionType.CLEAR_DATABASE_FAILURE
            description = "Clear the simulated database failure (clear_database_failure) before resuming normal request processing."
            parameters = {"target_service": root_cause.affected_service, "action": "clear_database_failure"}
        elif "redis" in normalized or "cache" in normalized:
            action_type = ActionType.CLEAR_REDIS_FAILURE
            description = "Clear the simulated Redis outage (clear_redis_failure) and restore cache and queue availability."
            parameters = {"target_service": root_cause.affected_service, "action": "clear_redis_failure"}
        elif "worker" in normalized and "delay" in normalized:
            action_type = ActionType.REDUCE_WORKER_DELAY
            description = "Reduce the injected worker delay (reduce_worker_delay) so backlog processing returns to baseline."
            parameters = {"target_service": root_cause.affected_service, "action": "reduce_worker_delay"}
        else:
            action_type = ActionType.PATCH
            description = "Apply the narrowest validated fix for the identified root cause."
            parameters = {"target_service": root_cause.affected_service, "patch": True}

        risk_score = int(risk_assessment.overall_score) if risk_assessment else 55
        requires_approval = risk_score > 30

        return ActionPlan(
            action_id=f"act-{incident.incident_id}",
            incident_id=incident.incident_id,
            action_type=action_type,
            description=description,
            target=root_cause.affected_service,
            parameters=parameters,
            reversibility="REVERSIBLE" if risk_score <= 70 else "UNKNOWN",
            estimated_blast_radius=root_cause.blast_radius.estimated_scope if root_cause.blast_radius else "UNKNOWN",
            risk_score=risk_score,
            requires_approval=requires_approval,
            approval_state=ApprovalState.AWAITING_APPROVAL if requires_approval else ApprovalState.APPROVED,
            execution_status=ExecutionStatus.QUEUED,
        )


__all__ = ["NoSafeRemediation", "RemediationPlanner"]
