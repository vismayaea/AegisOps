from __future__ import annotations

from core.evidence import Evidence, EvidenceSourceType
from core.incident import Incident, IncidentSeverity, IncidentStatus
from core.incident.service import IncidentService
from core.incident_trace import DecisionTraceEventType
from core.rca import BlastRadius
from core.risk import RiskDecision


def test_alert_creates_an_incident_and_triages_it() -> None:
    service = IncidentService()
    incident = service.create_incident(
        title="Checkout API latency spike",
        service="checkout-api",
        environment="prod",
        severity=IncidentSeverity.SEV1,
        summary="Checkout latency is elevated after traffic spike",
    )

    assert incident.incident_id.startswith("inc-")
    assert incident.status is IncidentStatus.TRIAGED
    assert service.get_incident(incident.incident_id)
    assert service.get_timeline(incident.incident_id)[0].event_type is DecisionTraceEventType.INCIDENT_DETECTED


def test_collect_evidence_attaches_to_incident_and_records_trace() -> None:
    service = IncidentService()
    incident = service.create_incident(title="DB failure", service="orders-db", environment="prod")
    evidence = Evidence(
        evidence_id="e-1",
        incident_id=incident.incident_id,
        source_type=EvidenceSourceType.LOGS,
        source="datadog",
        summary="Connection pool exhausted",
        raw_reference="log://orders-db/critical",
        relevance_score=0.93,
        confidence=0.92,
        metadata={"host": "orders-db-01"},
    )

    collected = service.collect_evidence(incident.incident_id, [evidence])
    assert len(collected) == 1
    assert service.get_evidence(incident.incident_id)[0].evidence_id == "e-1"
    assert service.get_timeline(incident.incident_id)[-1].event_type is DecisionTraceEventType.EVIDENCE_COLLECTED


def test_start_investigation_tracks_hypotheses() -> None:
    service = IncidentService()
    incident = service.create_incident(title="Redis latency", service="redis", environment="prod")
    evidence = Evidence(
        evidence_id="e-1",
        incident_id=incident.incident_id,
        source_type=EvidenceSourceType.TRACES,
        source="tempo",
        summary="Queue latency spike",
        raw_reference="trace://redis/slow-spans",
        relevance_score=0.84,
        confidence=0.82,
    )
    service.collect_evidence(incident.incident_id, [evidence])
    service.start_investigation(incident.incident_id)

    hypotheses = service.create_hypotheses(
        incident_id=incident.incident_id,
        hypotheses=[
            {
                "hypothesis_id": "h-1",
                "statement": "Database connection pool exhaustion",
                "affected_service": "orders-db",
                "supporting_evidence_ids": ["e-1"],
                "contradicting_evidence_ids": [],
                "confidence": 0.89,
            }
        ],
    )

    assert hypotheses[0].confidence == 0.89
    assert service.get_timeline(incident.incident_id)[-1].event_type is DecisionTraceEventType.HYPOTHESIS_CREATED
    assert incident.status is IncidentStatus.INVESTIGATING


def test_record_root_cause_and_assess_risk() -> None:
    service = IncidentService()
    incident = service.create_incident(title="Queue backlog", service="worker-queue", environment="prod")
    evidence = Evidence(
        evidence_id="e-1",
        incident_id=incident.incident_id,
        source_type=EvidenceSourceType.METRICS,
        source="grafana",
        summary="Queue depth and downstream latency both rose sharply",
        raw_reference="metric://queue/depth",
        relevance_score=0.9,
        confidence=0.87,
    )
    service.collect_evidence(incident.incident_id, [evidence])
    service.start_investigation(incident.incident_id)

    blast_radius = BlastRadius(
        affected_services=["worker-queue"],
        affected_dependencies=["redis"],
        affected_endpoints=["/jobs"],
        estimated_scope="Medium",
        severity_impact="HIGH",
    )

    root_cause = service.record_root_cause(
        incident_id=incident.incident_id,
        statement="Consumer saturation exceeded queue capacity",
        affected_service="worker-queue",
        evidence_ids=["e-1"],
        confidence=0.91,
        blast_radius=blast_radius,
        contributing_factors=["Queue backlog"],
    )
    assessment = service.assess_risk(
        incident_id=incident.incident_id,
        blast_radius=blast_radius,
        diagnosis_confidence=0.91,
        reversibility=0.75,
        historical_success=0.68,
    )

    assert root_cause.evidence_ids == ["e-1"]
    assert assessment.recommended_decision is RiskDecision.REQUIRES_APPROVAL
    assert service.get_timeline(incident.incident_id)[-1].event_type is DecisionTraceEventType.RISK_ASSESSED


def test_service_context_uses_abstraction_without_vendor_specifics() -> None:
    service = IncidentService()
    incident = service.create_incident(title="Infra drift", service="api", environment="prod")
    context = service.build_service_context(incident.incident_id)

    assert context.affected_service == "api"
    assert context.observability_sources
    assert "deployments" in context.recent_deployments or "configuration" in context.recent_config_changes
