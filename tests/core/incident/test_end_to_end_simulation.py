from __future__ import annotations

from core.evidence import Evidence, EvidenceSourceType
from core.incident import IncidentSeverity, IncidentStatus
from core.incident.service import IncidentService
from core.incident_trace import DecisionTraceEventType
from core.investigation import HypothesisStatus
from core.rca import BlastRadius
from core.risk import RiskDecision
from core.remediation import ActionType
from core.remediation.target_adapter import SimulationTargetAdapter


class _LatencyFaultAgent:
    def run(self, messages: list[dict[str, str]]) -> dict[str, object]:
        return {
            "tools_used": ["metrics", "traces"],
            "hypotheses": [
                {
                    "hypothesis_id": "h-latency-1",
                    "statement": "API latency fault injected into target-api",
                    "affected_service": "target-api",
                    "supporting_evidence_ids": ["e-1", "e-2"],
                    "contradicting_evidence_ids": [],
                    "confidence": 0.96,
                    "status": HypothesisStatus.VALIDATED.value,
                }
            ],
        }


def test_aegisops_incident_lifecycle_completes_with_simulation_fault_and_recovery() -> None:
    target = SimulationTargetAdapter()
    before = target.snapshot()

    assert before.latency == 0.0
    assert before.error_rate == 0.0

    target.inject_fault(scenario="API_LATENCY_SPIKE")
    during = target.snapshot()

    assert before.latency != during.latency
    assert during.latency > before.latency
    assert during.error_rate >= before.error_rate
    assert during.error_rate > 0.0

    service = IncidentService(agent=_LatencyFaultAgent())
    incident = service.create_incident(
        title="Target API latency spike",
        service="target-api",
        environment="simulation",
        severity=IncidentSeverity.SEV2,
        summary="The simulation target shows an API latency spike and elevated error rate.",
    )

    evidence = [
        Evidence(
            evidence_id="e-1",
            incident_id=incident.incident_id,
            source_type=EvidenceSourceType.METRICS,
            source="simulator",
            summary="Latency is elevated and API responses are slowed under the injected simulation fault.",
            raw_reference="metric://target-api/latency",
            relevance_score=0.95,
            confidence=0.97,
            metadata={
                "dependencies": ["target-api"],
                "endpoints": ["/orders"],
                "contributing_factor": "API latency fault",
            },
        ),
        Evidence(
            evidence_id="e-2",
            incident_id=incident.incident_id,
            source_type=EvidenceSourceType.TRACES,
            source="simulator",
            summary="The API path shows elevated latency and intermittent request failures after the fault is injected.",
            raw_reference="trace://target-api/slow-request",
            relevance_score=0.92,
            confidence=0.94,
            metadata={
                "dependencies": ["target-api"],
                "endpoints": ["/orders"],
                "contributing_factor": "high latency fault",
            },
        ),
    ]
    service.collect_evidence(incident.incident_id, evidence)

    investigation = service.investigate(incident.incident_id)
    assert investigation.hypotheses
    assert investigation.hypotheses[0].statement == "API latency fault injected into target-api"

    rca = service.identify_root_cause(incident.incident_id, hypotheses=investigation.hypotheses)
    assert rca.root_cause is not None
    assert "latency fault" in rca.root_cause.statement.lower()

    blast_radius = BlastRadius(
        affected_services=["target-api"],
        affected_dependencies=["target-api"],
        affected_endpoints=["/orders"],
        estimated_scope="HIGH",
        severity_impact="HIGH",
    )
    risk = service.assess_risk(
        incident_id=incident.incident_id,
        blast_radius=blast_radius,
        diagnosis_confidence=0.96,
        reversibility=0.9,
        historical_success=0.8,
    )
    assert risk.recommended_decision in {RiskDecision.REQUIRES_APPROVAL, RiskDecision.AUTO_EXECUTE}

    plan = service.propose_remediation(incident.incident_id, risk_assessment=risk)
    assert plan.action_type is ActionType.CLEAR_LATENCY_FAULT
    assert plan.action_id == f"act-{incident.incident_id}"
    assert plan.requires_approval is False or plan.requires_approval is True

    if plan.requires_approval:
        approved = service.approve_incident_action(
            incident.incident_id,
            plan.action_id,
            approved=True,
            actor="human-approval",
        )
        assert approved is True

    execution = service.execute_remediation(
        incident_id=incident.incident_id,
        action_plan=plan,
        risk_assessment=risk,
        approved=True,
        before=before,
        during=during,
        evidence=service.get_evidence(incident.incident_id),
        target_adapter=target,
    )
    assert execution.status == "completed"
    assert execution.execution_record is not None
    assert execution.execution_record.action_id == plan.action_id

    after = target.snapshot()
    assert after.latency <= before.latency + 1
    assert after.error_rate <= before.error_rate + 0.01
    assert after.latency == 0.0
    assert after.error_rate == 0.0

    verification = service.verify_recovery(
        incident.incident_id,
        before=before,
        during=during,
        after=after,
    )
    assert verification.recovered is True
    assert verification.metric_comparisons["latency"]["before"] == before.latency
    assert verification.metric_comparisons["latency"]["during"] == during.latency
    assert verification.metric_comparisons["latency"]["after"] == after.latency
    assert service.get_incident(incident.incident_id).status is IncidentStatus.RESOLVED

    event_types = [event.event_type.value for event in service.get_timeline(incident.incident_id)]
    required = {
        "incident_detected",
        "evidence_collected",
        "investigation_started",
        "hypothesis_created",
        "root_cause_identified",
        "risk_assessed",
        "remediation_proposed",
        "approved",
        "remediation_started",
        "remediation_completed",
        "recovery_verified",
        "resolved",
    }
    missing = sorted(required - set(event_types))
    assert not missing, f"Missing trace events: {missing}"

    replay = service.replay_incident(incident.incident_id)
    assert replay["status"] == "resolved"
    assert replay["evidence_references"] == ["e-1", "e-2"]
    assert replay["execution_records"]
    assert replay["verification_results"]

    postmortem = service.generate_postmortem(incident.incident_id)
    assert postmortem["incident_summary"]
    assert "Target API latency spike" in postmortem["incident_summary"]
    assert "e-1" in str(postmortem["supporting_evidence"])
    assert "latency fault" in str(postmortem["root_cause"]).lower()
    assert "clear_latency_fault" in str(postmortem["remediation"]).lower()
    assert "Recovery verified" in str(postmortem["recovery_verification"])
    assert postmortem["timeline"]
