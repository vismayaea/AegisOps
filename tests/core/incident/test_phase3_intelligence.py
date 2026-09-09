from __future__ import annotations

from core.evidence import Evidence, EvidenceSourceType
from core.incident import Incident, IncidentSeverity, IncidentStatus
from core.incident.service import IncidentService
from core.incident_trace import DecisionTraceEventType
from core.investigation import Hypothesis, HypothesisStatus
from core.investigation.service import InvestigationService
from core.rca import BlastRadius
from core.remediation import ActionType
from core.remediation.planner import NoSafeRemediation
from core.risk import RiskAssessment, RiskDecision


class _FakeAgent:
    def __init__(self) -> None:
        self.messages: list[dict[str, str]] | None = None

    def run(self, messages: list[dict[str, str]]) -> dict[str, object]:
        self.messages = messages
        return {
            "tools_used": ["datadog", "grafana"],
            "hypotheses": [
                {
                    "hypothesis_id": "h-1",
                    "statement": "database connection pool exhaustion",
                    "affected_service": "orders-db",
                    "supporting_evidence_ids": ["e-1", "e-2"],
                    "contradicting_evidence_ids": [],
                    "confidence": 0.93,
                    "status": HypothesisStatus.VALIDATED.value,
                }
            ],
        }


def test_investigation_request_reaches_existing_runtime_boundary() -> None:
    fake = _FakeAgent()
    service = InvestigationService(agent=fake)
    incident = Incident(title="Checkout backlog", service="checkout-api", environment="prod", severity=IncidentSeverity.SEV2)
    evidence = [
        Evidence(
            evidence_id="e-1",
            incident_id=incident.incident_id,
            source_type=EvidenceSourceType.LOGS,
            source="datadog",
            summary="Connection pool saturation",
            raw_reference="log://db/pool",
            relevance_score=0.9,
            confidence=0.92,
        ),
        Evidence(
            evidence_id="e-2",
            incident_id=incident.incident_id,
            source_type=EvidenceSourceType.METRICS,
            source="grafana",
            summary="DB latency climbed sharply",
            raw_reference="metric://db/latency",
            relevance_score=0.88,
            confidence=0.9,
        ),
    ]

    result = service.investigate(incident, evidence)

    assert fake.messages is not None
    assert result.hypotheses[0].statement == "database connection pool exhaustion"
    assert result.evidence_used == ["e-1", "e-2"]
    assert result.tools_used == ["datadog", "grafana"]


def test_incident_service_builds_intelligence_pipeline_with_trace() -> None:
    fake = _FakeAgent()
    service = IncidentService(agent=fake)
    incident = service.create_incident(
        title="Orders API latency",
        service="orders-api",
        environment="prod",
        severity=IncidentSeverity.SEV1,
    )
    evidence_one = Evidence(
        evidence_id="e-1",
        incident_id=incident.incident_id,
        source_type=EvidenceSourceType.LOGS,
        source="datadog",
        summary="connection pool exhaustion",
        raw_reference="log://orders-db/pool",
        relevance_score=0.95,
        confidence=0.94,
        metadata={"dependencies": ["orders-db"], "endpoints": ["/checkout"], "contributing_factor": "pool saturation"},
    )
    evidence_two = Evidence(
        evidence_id="e-2",
        incident_id=incident.incident_id,
        source_type=EvidenceSourceType.TRACES,
        source="tempo",
        summary="checkout spans show DB waits",
        raw_reference="trace://checkout/db",
        relevance_score=0.9,
        confidence=0.88,
        metadata={"dependencies": ["orders-db"], "endpoints": ["/checkout"], "contributing_factor": "database latency"},
    )
    service.collect_evidence(incident.incident_id, [evidence_one, evidence_two])

    investigation = service.investigate(incident.incident_id)
    assert investigation.hypotheses
    assert investigation.hypotheses[0].supporting_evidence_ids == ["e-1", "e-2"]

    rca = service.identify_root_cause(incident.incident_id, hypotheses=investigation.hypotheses)
    assert rca.root_cause is not None
    assert rca.root_cause.confidence == 0.93

    blast = BlastRadius(
        affected_services=["orders-api"],
        affected_dependencies=["orders-db"],
        affected_endpoints=["/checkout"],
        estimated_scope="HIGH",
        severity_impact="HIGH",
    )
    risk = service.assess_risk(
        incident_id=incident.incident_id,
        blast_radius=blast,
        diagnosis_confidence=0.93,
        reversibility=0.8,
        historical_success=0.7,
    )
    plan = service.propose_remediation(incident.incident_id, risk_assessment=risk)

    assert risk.recommended_decision is RiskDecision.REQUIRES_APPROVAL
    assert plan.action_type is ActionType.SCALE
    assert any(event.event_type is DecisionTraceEventType.REMEDIATION_PROPOSED for event in service.get_timeline(incident.incident_id))
    assert incident.status is IncidentStatus.RISK_ASSESSED


def test_no_evidence_and_agent_failure_are_structured() -> None:
    incident = Incident(title="Unknown issue", service="api", environment="prod")
    empty = InvestigationService(agent=None)
    result = empty.investigate(incident, [])
    assert result.status == "no_evidence"
    assert result.error is not None

    class _BrokenAgent:
        def run(self, messages: list[dict[str, str]]) -> None:
            raise RuntimeError("agent boom")

    broken = InvestigationService(agent=_BrokenAgent())
    result_broken = broken.investigate(incident, [
        Evidence(
            evidence_id="e-1",
            incident_id=incident.incident_id,
            source_type=EvidenceSourceType.ALERTS,
            source="pagerduty",
            summary="SLO drop",
            raw_reference="alert://slo/checkout",
            relevance_score=0.7,
            confidence=0.7,
        )
    ])
    assert result_broken.status == "agent_failed"
    assert "agent boom" in result_broken.error


def test_risk_policy_blocks_unsafe_remediation_plan() -> None:
    incident = Incident(title="Critical outage", service="payments-api", environment="prod", severity=IncidentSeverity.SEV1)
    plan = NoSafeRemediation(
        incident_id=incident.incident_id,
        reason="Risk policy blocked remediation due to high blast radius.",
        requires_approval=True,
        risk_score=92,
    )
    assert plan.status == "no_safe_remediation_available"

    service = IncidentService()
    service._incidents[incident.incident_id] = incident
    service._root_causes[incident.incident_id] = None  # type: ignore[index]
    result = service.propose_remediation(incident.incident_id, risk_assessment=RiskAssessment(
        overall_score=92,
        risk_level="high",
        recommended_decision=RiskDecision.BLOCKED,
        rationale="Blocked",
    ))
    assert isinstance(result, NoSafeRemediation)
    assert result.status == "no_safe_remediation_available"


def test_hypothesis_without_support_is_rejected() -> None:
    class _UnsupportedAgent:
        def run(self, messages: list[dict[str, str]]) -> dict[str, object]:
            return {
                "hypotheses": [{
                    "hypothesis_id": "h-unsupported",
                    "statement": "A code bug caused it",
                    "affected_service": "db",
                    "supporting_evidence_ids": [],
                    "contradicting_evidence_ids": [],
                    "confidence": 0.2,
                    "status": HypothesisStatus.PROPOSED.value,
                }]
            }

    evidence = [
        Evidence(
            evidence_id="e-1",
            incident_id="inc-1",
            source_type=EvidenceSourceType.LOGS,
            source="datadog",
            summary="Database latency appeared elevated",
            raw_reference="log://db/latency",
            relevance_score=0.8,
            confidence=0.7,
        )
    ]
    result = InvestigationService().investigate(
        Incident(title="DB issue", service="db", environment="prod"),
        evidence,
        request={"hypotheses": [{
            "statement": "A code bug caused it",
            "affected_service": "db",
            "supporting_evidence_ids": [],
            "confidence": 0.2,
            "status": HypothesisStatus.PROPOSED.value,
        }]},
        agent=_UnsupportedAgent(),
    )
    assert result.hypotheses
    assert result.hypotheses[0].status is HypothesisStatus.REJECTED
