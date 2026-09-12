from fastapi.testclient import TestClient

from aegisops.api import create_app
from aegisops.domain import IncidentStatus, ScenarioName
from aegisops.incident import IncidentOrchestrator
from aegisops.remediation import RemediationRegistry
from aegisops.simulation import SimulationEngine


def test_healthy_simulation_baseline():
    simulation = SimulationEngine()
    assert simulation.state()["system_status"] == "healthy"
    assert simulation.baseline.latency_ms == 120
    assert simulation.baseline.error_rate == 0.004


def test_api_latency_fault_injection():
    simulation = SimulationEngine()
    degraded = simulation.inject(ScenarioName.API_LATENCY_SPIKE)
    assert degraded.latency_ms == 4800
    assert degraded.error_rate == 0.37
    assert simulation.state()["system_status"] == "degraded"


def test_evidence_generation_correlation_rca_and_risk():
    orchestrator = IncidentOrchestrator()
    incident = orchestrator.create_incident(ScenarioName.API_LATENCY_SPIKE)
    assert {item.source for item in incident.evidence} == {"logs", "metrics", "dependencies"}
    assert incident.investigation is not None
    assert "database connection pool" in incident.investigation.likely_root_cause
    assert incident.risk is not None
    assert incident.risk.score == 38
    assert incident.risk.approval_required is True


def test_approval_gating_registered_remediation_recovery_resolution_and_trace():
    orchestrator = IncidentOrchestrator()
    incident = orchestrator.create_incident(ScenarioName.API_LATENCY_SPIKE)
    try:
        orchestrator.execute(incident.id)
    except PermissionError:
        pass
    else:
        raise AssertionError("high-risk remediation should require approval")
    orchestrator.approve(incident.id)
    resolved = orchestrator.execute(incident.id)
    assert resolved.execution is not None
    assert resolved.execution.action_id == "recycle_stale_connections"
    assert resolved.recovery is not None
    assert resolved.recovery.recovered is True
    assert resolved.status is IncidentStatus.RESOLVED
    event_types = [event.event_type for event in resolved.trace]
    assert event_types == [
        "incident_detected",
        "evidence_collected",
        "investigation_performed",
        "rca_produced",
        "risk_evaluated",
        "remediation_selected",
        "approval_decision",
        "remediation_executed",
        "recovery_checked",
        "incident_resolved",
    ]


def test_registry_rejects_unregistered_action():
    registry = RemediationRegistry(SimulationEngine())
    try:
        registry.execute(ScenarioName.API_LATENCY_SPIKE, "run_arbitrary_shell")
    except ValueError:
        pass
    else:
        raise AssertionError("unregistered action should not execute")


def test_postmortem_generation():
    orchestrator = IncidentOrchestrator()
    incident = orchestrator.run_full_lifecycle(ScenarioName.REDIS_OUTAGE)
    postmortem = orchestrator.postmortem(incident.id)
    assert postmortem["incident_id"] == incident.id
    assert postmortem["root_cause"]["affected_service"] == "cache-redis"
    assert postmortem["recovery"]["recovered"] is True
    assert postmortem["lessons"]


def test_api_endpoints_and_ui_smoke_behavior():
    client = TestClient(create_app())
    assert client.get("/health").json()["service"] == "aegisops"
    html = client.get("/").text
    assert "AEGISOPS CONTROL CENTER" in html
    assert "INCIDENT SIMULATION LAB" in html
    created = client.post("/api/incidents", json={"scenario": "api_latency_spike"}).json()
    assert created["status"] == "awaiting_approval"
    assert client.post(f"/api/incidents/{created['id']}/execute").status_code == 409
    approved = client.post(f"/api/incidents/{created['id']}/approve").json()
    assert approved["approval_granted"] is True
    executed = client.post(f"/api/incidents/{created['id']}/execute").json()
    assert executed["status"] == "resolved"
    assert client.get(f"/api/incidents/{created['id']}/trace").json()[-1]["event_type"] == "incident_resolved"


def test_end_to_end_lifecycle_proves_complete_flow():
    orchestrator = IncidentOrchestrator()
    incident = orchestrator.run_full_lifecycle(ScenarioName.API_LATENCY_SPIKE)
    assert incident.before.label == "before"
    assert incident.during.label == "during"
    assert incident.after.label == "after"
    assert incident.evidence
    assert incident.investigation
    assert incident.risk
    assert incident.approval_granted
    assert incident.execution.status == "executed"
    assert incident.recovery.recovered
    assert incident.status is IncidentStatus.RESOLVED
    assert incident.trace[-1].event_type == "incident_resolved"
