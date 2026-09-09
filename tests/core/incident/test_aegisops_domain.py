from __future__ import annotations

import pytest

from core.evidence import Evidence, EvidenceSourceType, EvidenceStore
from core.incident import Incident, IncidentSeverity, IncidentStatus
from core.incident.lifecycle import require_valid_transition
from core.incident_trace import DecisionTrace, DecisionTraceEventType
from core.investigation import Hypothesis, HypothesisRanker, HypothesisStatus
from core.rca import BlastRadius, RootCause
from core.recovery import RecoverySnapshot, RecoverySnapshotType, VerificationResult
from core.remediation import ActionPlan, ActionType, ApprovalState, ExecutionRecord, ExecutionStatus
from core.risk import RiskAssessment, RiskDecision, RiskEngine
from core.incident_trace import Postmortem


def test_incident_lifecycle_transitions_are_valid() -> None:
    incident = Incident(title="API latency spike", service="checkout-api", environment="prod")
    assert incident.status is IncidentStatus.DETECTED

    incident.transition_to(IncidentStatus.TRIAGED)
    assert incident.status is IncidentStatus.TRIAGED

    incident.transition_to(IncidentStatus.EVIDENCE_COLLECTED)
    assert incident.status is IncidentStatus.EVIDENCE_COLLECTED


def test_invalid_lifecycle_transitions_are_rejected() -> None:
    incident = Incident(title="Redis outage", service="session-cache", environment="prod")

    with pytest.raises(ValueError):
        incident.transition_to(IncidentStatus.RESOLVED)


def test_severity_values_are_valid() -> None:
    assert IncidentSeverity.SEV1.value == "SEV1"
    assert IncidentSeverity.SEV4.value == "SEV4"


def test_evidence_can_be_attached_to_an_incident() -> None:
    incident = Incident(title="DB failure", service="orders-db", environment="prod")
    evidence_store = EvidenceStore()
    evidence = Evidence(
        evidence_id="e-1",
        incident_id=incident.incident_id,
        source_type=EvidenceSourceType.LOGS,
        source="datadog",
        summary="Database connection pool exhausted",
        raw_reference="log://db/critical",
        relevance_score=0.96,
        confidence=0.93,
        metadata={"host": "db-01"},
    )

    evidence_store.add(evidence)
    incident_evidence = evidence_store.get_for_incident(incident.incident_id)
    assert incident_evidence
    assert incident_evidence[0].evidence_id == "e-1"


def test_hypotheses_can_reference_supporting_evidence() -> None:
    incident = Incident(title="high error rate", service="checkout-api", environment="prod")
    hypothesis = Hypothesis(
        hypothesis_id="h-1",
        incident_id=incident.incident_id,
        statement="Database connection pool saturation caused the failures",
        affected_service="checkout-api",
        supporting_evidence_ids=["e-1", "e-2"],
        contradicting_evidence_ids=["e-3"],
        confidence=0.9,
        status=HypothesisStatus.PROPOSED,
    )

    assert hypothesis.supporting_evidence_ids == ["e-1", "e-2"]
    assert hypothesis.status is HypothesisStatus.PROPOSED


def test_hypothesis_ranking_is_deterministic() -> None:
    low = Hypothesis(
        hypothesis_id="h-low",
        incident_id="inc-1",
        statement="Low-confidence hypothesis",
        affected_service="service-a",
        supporting_evidence_ids=["e-1"],
        contradicting_evidence_ids=[],
        confidence=0.4,
        status=HypothesisStatus.PROPOSED,
    )
    high = Hypothesis(
        hypothesis_id="h-high",
        incident_id="inc-1",
        statement="High-confidence hypothesis",
        affected_service="service-b",
        supporting_evidence_ids=["e-1", "e-2", "e-3"],
        contradicting_evidence_ids=[],
        confidence=0.92,
        status=HypothesisStatus.TESTING,
    )

    ranked = HypothesisRanker.rank([low, high])
    assert [item.hypothesis_id for item in ranked] == ["h-high", "h-low"]


def test_rca_contains_evidence_and_confidence() -> None:
    blast_radius = BlastRadius(
        affected_services=["checkout-api", "orders-api"],
        affected_dependencies=["orders-db"],
        affected_endpoints=["/checkout"],
        estimated_scope="20% of traffic",
        severity_impact="HIGH",
    )
    root_cause = RootCause(
        root_cause_id="rc-1",
        incident_id="inc-1",
        statement="Orders DB saturation caused checkout retries and queue buildup",
        affected_service="checkout-api",
        evidence_ids=["e-1", "e-2"],
        confidence=0.94,
        blast_radius=blast_radius,
        contributing_factors=["DB pool exhaustion", "retry amplification"],
    )

    assert root_cause.confidence == 0.94
    assert root_cause.evidence_ids == ["e-1", "e-2"]
    assert root_cause.blast_radius.estimated_scope == "20% of traffic"


def test_risk_scores_stay_within_0_100() -> None:
    engine = RiskEngine()
    assessment = engine.assess(
        incident=Incident(
            title="Checkout overload",
            service="checkout-api",
            environment="prod",
            severity=IncidentSeverity.SEV1,
            status=IncidentStatus.ROOT_CAUSE_IDENTIFIED,
        ),
        blast_radius=BlastRadius(
            affected_services=["checkout-api"],
            affected_dependencies=["orders-db"],
            affected_endpoints=["/checkout"],
            estimated_scope="Large",
            severity_impact="HIGH",
        ),
        diagnosis_confidence=0.91,
        reversibility=0.25,
        historical_success=0.72,
    )
    assert 0 <= assessment.overall_score <= 100


def test_risk_policy_0_30_produces_auto_execute() -> None:
    engine = RiskEngine()
    assessment = engine.assess(
        incident=Incident(title="minor drift", service="api", environment="prod", severity=IncidentSeverity.SEV4),
        blast_radius=BlastRadius(
            affected_services=["api"],
            affected_dependencies=[],
            affected_endpoints=["/health"],
            estimated_scope="Small",
            severity_impact="LOW",
        ),
        diagnosis_confidence=0.7,
        reversibility=0.9,
        historical_success=0.9,
    )
    assert assessment.recommended_decision is RiskDecision.AUTO_EXECUTE


def test_risk_policy_31_70_produces_requires_approval() -> None:
    engine = RiskEngine()
    assessment = engine.assess(
        incident=Incident(title="API retry burst", service="api", environment="prod", severity=IncidentSeverity.SEV3),
        blast_radius=BlastRadius(
            affected_services=["api", "worker"],
            affected_dependencies=["redis"],
            affected_endpoints=["/api/*"],
            estimated_scope="Medium",
            severity_impact="MEDIUM",
        ),
        diagnosis_confidence=0.85,
        reversibility=0.6,
        historical_success=0.55,
    )
    assert assessment.recommended_decision is RiskDecision.REQUIRES_APPROVAL


def test_risk_policy_71_100_produces_blocked() -> None:
    engine = RiskEngine()
    assessment = engine.assess(
        incident=Incident(title="Database corruption", service="orders-db", environment="prod", severity=IncidentSeverity.SEV1),
        blast_radius=BlastRadius(
            affected_services=["orders-db", "checkout-api", "payments"],
            affected_dependencies=["primary-db", "replica"],
            affected_endpoints=["/checkout", "/payments"],
            estimated_scope="Large",
            severity_impact="HIGH",
        ),
        diagnosis_confidence=0.95,
        reversibility=0.1,
        historical_success=0.2,
    )
    assert assessment.recommended_decision is RiskDecision.BLOCKED


def test_remediation_approval_states_work_correctly() -> None:
    action = ActionPlan(
        action_id="a-1",
        incident_id="inc-1",
        action_type=ActionType.ROLLBACK,
        description="Revert deployment",
        target="checkout-api",
        parameters={"version": "v123"},
        reversibility="REVERSIBLE",
        estimated_blast_radius="LOW",
        risk_score=40,
        requires_approval=True,
        approval_state=ApprovalState.AWAITING_APPROVAL,
    )

    assert action.requires_approval is True
    assert action.approval_state is ApprovalState.AWAITING_APPROVAL

    action.approval_state = ApprovalState.APPROVED
    assert action.approval_state is ApprovalState.APPROVED


def test_recovery_verification_requires_explicit_metric_checks() -> None:
    before = RecoverySnapshot(
        kind=RecoverySnapshotType.BEFORE,
        latency=250.0,
        error_rate=0.12,
        throughput=900.0,
        dependency_health=0.62,
    )
    after = RecoverySnapshot(
        kind=RecoverySnapshotType.AFTER,
        latency=120.0,
        error_rate=0.02,
        throughput=1200.0,
        dependency_health=0.93,
    )

    result = VerificationResult.from_snapshots(before, after)
    assert result.recovered is True
    assert result.failed_checks == []
    assert "latency" in result.metric_comparisons


def test_decision_trace_preserves_chronological_order() -> None:
    trace = DecisionTrace(incident_id="inc-1")
    trace.append_event(DecisionTraceEventType.INCIDENT_DETECTED, summary="Detected incident", actor="monitor")
    trace.append_event(DecisionTraceEventType.ROOT_CAUSE_IDENTIFIED, summary="Root cause isolated", actor="agent")
    trace.append_event(DecisionTraceEventType.REMEDIATION_STARTED, summary="Rollback started", actor="operator")

    assert [event.event_type for event in trace.events] == [
        DecisionTraceEventType.INCIDENT_DETECTED,
        DecisionTraceEventType.ROOT_CAUSE_IDENTIFIED,
        DecisionTraceEventType.REMEDIATION_STARTED,
    ]


def test_incident_replay_reconstructs_the_lifecycle() -> None:
    incident = Incident(title="Queue backlog", service="worker-queue", environment="prod")
    trace = DecisionTrace(incident_id=incident.incident_id)
    trace.append_event(DecisionTraceEventType.INCIDENT_DETECTED, summary="Queue spike detected", actor="monitor")
    trace.append_event(DecisionTraceEventType.ROOT_CAUSE_IDENTIFIED, summary="Consumer lag", actor="agent")
    trace.append_event(DecisionTraceEventType.RECOVERY_VERIFIED, summary="Queue recovered", actor="system")

    replay = trace.replay(incident)
    assert replay.current_state == IncidentStatus.ROOT_CAUSE_IDENTIFIED
    assert replay.decision_history[-1].event_type == DecisionTraceEventType.RECOVERY_VERIFIED


def test_postmortem_contains_required_sections() -> None:
    postmortem = Postmortem(
        incident_summary="Checkout API degraded after DB saturation",
        customer_or_system_impact="Checkout latency and failed payments",
        timeline=["Detection", "Investigation", "Recovery"],
        root_cause="Database saturation from connection pool exhaustion",
        supporting_evidence=["Datadog logs", "DB metrics"],
        remediation="Rolled back the hotfix and scaled the pool",
        recovery_verification="Latency returned to baseline; error rate below threshold",
        human_intervention="On-call engineer approved rollback",
        lessons_learned=["Add capacity guardrails before deploy"],
    )

    assert postmortem.incident_summary
    assert postmortem.root_cause
    assert postmortem.recovery_verification
    assert "lessons_learned" in postmortem.to_dict()
