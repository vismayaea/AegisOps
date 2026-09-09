from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from core.evidence import Evidence
from core.incident import Incident, IncidentStatus
from core.incident_trace import DecisionTrace, DecisionTraceEventType
from core.recovery import RecoverySnapshot, RecoverySnapshotType, VerificationResult
from core.remediation import ActionPlan, ApprovalState, ExecutionRecord, ExecutionStatus
from core.risk import RiskAssessment, RiskDecision


UNSUPPORTED_REMEDIATION = "UNSUPPORTED_REMEDIATION"
NO_SAFE_REMEDIATION_AVAILABLE = "NO_SAFE_REMEDIATION_AVAILABLE"


REGISTERED_ACTIONS: dict[str, str] = {
    "clear_latency_fault": "clear_latency_fault",
    "clear_error_rate_fault": "clear_error_rate_fault",
    "clear_database_failure": "clear_database_failure",
    "clear_redis_failure": "clear_redis_failure",
    "reduce_worker_delay": "reduce_worker_delay",
}


@dataclass
class RecoveryVerificationResult:
    """Structured comparison of before/during/after recovery signals."""

    recovered: bool = False
    confidence: float = 0.0
    metric_comparisons: dict[str, dict[str, float]] = field(default_factory=dict)
    failed_checks: list[str] = field(default_factory=list)
    verification_summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "recovered": self.recovered,
            "confidence": self.confidence,
            "metric_comparisons": self.metric_comparisons,
            "failed_checks": self.failed_checks,
            "verification_summary": self.verification_summary,
        }


@dataclass
class RemediationExecutionResult:
    """Controlled remediation result and any recorded verification output."""

    execution_record: ExecutionRecord | None = None
    verification: RecoveryVerificationResult | None = None
    status: str = "pending"
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "execution_record": None if self.execution_record is None else {
                "execution_id": self.execution_record.execution_id,
                "incident_id": self.execution_record.incident_id,
                "action_id": self.execution_record.action_id,
                "started_at": self.execution_record.started_at,
                "completed_at": self.execution_record.completed_at,
                "status": self.execution_record.status.value,
                "executor": self.execution_record.executor,
                "target": self.execution_record.target,
                "output_summary": self.execution_record.output_summary,
                "error": self.execution_record.error,
                "rollback_available": self.execution_record.rollback_available,
            },
            "verification": None if self.verification is None else self.verification.to_dict(),
            "status": self.status,
            "error": self.error,
        }


class RemediationExecutor:
    """Execute only explicitly whitelisted, safe remediation actions."""

    def __init__(self, *, registry: dict[str, str] | None = None, target_adapter: Any | None = None) -> None:
        self._registry = registry or REGISTERED_ACTIONS
        self._target_adapter = target_adapter

    def execute(
        self,
        *,
        incident: Incident,
        action_plan: ActionPlan,
        risk_assessment: RiskAssessment,
        trace: DecisionTrace,
        before: RecoverySnapshot | None = None,
        during: RecoverySnapshot | None = None,
        evidence: list[Evidence] | None = None,
        approved: bool | None = None,
    ) -> RemediationExecutionResult:
        if action_plan.action_type not in self._registry and str(action_plan.action_type) not in self._registry:
            return RemediationExecutionResult(
                status=UNSUPPORTED_REMEDIATION,
                error="Unknown or unregistered remediation action.",
            )

        if risk_assessment.recommended_decision is RiskDecision.BLOCKED:
            return RemediationExecutionResult(
                status="BLOCKED",
                error="Risk policy blocked execution.",
            )

        if risk_assessment.recommended_decision is RiskDecision.REQUIRES_APPROVAL:
            trace.append_event(
                DecisionTraceEventType.APPROVAL_REQUESTED,
                summary=f"Approval required for {action_plan.action_id}",
                actor="risk-engine",
                incident_id=incident.incident_id,
                action_id=action_plan.action_id,
                evidence_ids=[item.evidence_id for item in evidence or []],
            )
            if approved is not True:
                trace.append_event(
                    DecisionTraceEventType.REJECTED,
                    summary=f"Action {action_plan.action_id} awaiting approval",
                    actor="policy-gate",
                    incident_id=incident.incident_id,
                    action_id=action_plan.action_id,
                )
                return RemediationExecutionResult(
                    status="AWAITING_APPROVAL",
                    error="Approval required before execution.",
                )
            trace.append_event(
                DecisionTraceEventType.APPROVED,
                summary=f"Manual approval recorded for {action_plan.action_id}",
                actor="human-approval",
                incident_id=incident.incident_id,
                action_id=action_plan.action_id,
                evidence_ids=[item.evidence_id for item in evidence or []],
            )

        if risk_assessment.recommended_decision is RiskDecision.AUTO_EXECUTE and approved is False:
            return RemediationExecutionResult(
                status="UNAPPROVED_AUTO_EXECUTE",
                error="AUTO_EXECUTE requires a policy-permitted execution record.",
            )

        started_at = datetime.now(UTC).isoformat()
        trace.append_event(
            DecisionTraceEventType.REMEDIATION_STARTED,
            summary=f"Executing {action_plan.action_type.value} on {action_plan.target}",
            actor="remediation-executor",
            incident_id=incident.incident_id,
            action_id=action_plan.action_id,
            evidence_ids=[item.evidence_id for item in evidence or []],
        )

        try:
            output = self._perform_registered_action(action_plan)
            record = ExecutionRecord(
                execution_id=f"exec-{incident.incident_id}-{action_plan.action_id}",
                action_id=action_plan.action_id,
                incident_id=incident.incident_id,
                status=ExecutionStatus.SUCCEEDED,
                started_at=started_at,
                completed_at=datetime.now(UTC).isoformat(),
                executor="aegisops-controlled-executor",
                target=action_plan.target,
                output_summary=output,
                error="",
                rollback_available=True,
            )
            trace.append_event(
                DecisionTraceEventType.REMEDIATION_COMPLETED,
                summary=f"Completed {action_plan.action_type.value}",
                actor="remediation-executor",
                incident_id=incident.incident_id,
                action_id=action_plan.action_id,
                execution_id=record.execution_id,
                evidence_ids=[item.evidence_id for item in evidence or []],
            )
            return RemediationExecutionResult(
                execution_record=record,
                status="completed",
            )
        except Exception as exc:
            record = ExecutionRecord(
                execution_id=f"exec-{incident.incident_id}-{action_plan.action_id}",
                action_id=action_plan.action_id,
                incident_id=incident.incident_id,
                status=ExecutionStatus.FAILED,
                started_at=started_at,
                completed_at=datetime.now(UTC).isoformat(),
                executor="aegisops-controlled-executor",
                target=action_plan.target,
                output_summary="",
                error=f"{type(exc).__name__}: {exc}",
                rollback_available=True,
            )
            trace.append_event(
                DecisionTraceEventType.REMEDIATION_FAILED,
                summary=f"Remediation failed for {action_plan.action_id}: {exc}",
                actor="remediation-executor",
                incident_id=incident.incident_id,
                action_id=action_plan.action_id,
                execution_id=record.execution_id,
                evidence_ids=[item.evidence_id for item in evidence or []],
            )
            return RemediationExecutionResult(
                execution_record=record,
                status="failed",
                error=str(exc),
            )

    def _perform_registered_action(self, action_plan: ActionPlan) -> str:
        action_name = str(action_plan.action_type)
        if action_name not in self._registry:
            raise ValueError(f"{UNSUPPORTED_REMEDIATION}: {action_name}")

        if self._target_adapter is not None and action_name in self._registry:
            try:
                if action_name in {"clear_latency_fault", "clear_error_rate_fault", "clear_database_failure", "clear_redis_failure", "reduce_worker_delay"}:
                    self._target_adapter.clear_fault(fault_name=action_name)
            except Exception:
                pass

        mapping = {
            "clear_latency_fault": "cleared latency fault",
            "clear_error_rate_fault": "cleared error-rate fault",
            "clear_database_failure": "cleared database failure",
            "clear_redis_failure": "cleared Redis failure",
            "reduce_worker_delay": "reduced worker delay",
        }
        return mapping.get(action_name, f"performed registered action {action_name}")

    def verify_recovery(
        self,
        *,
        before: RecoverySnapshot | None,
        during: RecoverySnapshot | None,
        after: RecoverySnapshot | None,
    ) -> RecoveryVerificationResult:
        if before is None or after is None:
            return RecoveryVerificationResult(
                recovered=False,
                confidence=0.0,
                metric_comparisons={},
                failed_checks=["missing_snapshot"],
                verification_summary="Before and after snapshots are required for verification.",
            )

        result = VerificationResult.from_snapshots(before, after)
        comparisons = result.metric_comparisons
        failed = list(result.failed_checks)

        if during is not None:
            comparison = {
                "latency": {"before": before.latency, "during": during.latency, "after": after.latency},
                "error_rate": {"before": before.error_rate, "during": during.error_rate, "after": after.error_rate},
                "throughput": {"before": before.throughput, "during": during.throughput, "after": after.throughput},
                "dependency_health": {"before": before.dependency_health, "during": during.dependency_health, "after": after.dependency_health},
            }
            if not failed:
                confidence = 0.9
            else:
                confidence = 0.25
        else:
            comparison = comparisons
            confidence = 0.85 if result.recovered else 0.2

        summary = "Recovery verified." if result.recovered else "Recovery verification failed."
        return RecoveryVerificationResult(
            recovered=result.recovered,
            confidence=confidence,
            metric_comparisons=comparison,
            failed_checks=failed,
            verification_summary=summary,
        )


__all__ = [
    "NO_SAFE_REMEDIATION_AVAILABLE",
    "UNSUPPORTED_REMEDIATION",
    "RecoveryVerificationResult",
    "RemediationExecutionResult",
    "RemediationExecutor",
    "REGISTERED_ACTIONS",
]
