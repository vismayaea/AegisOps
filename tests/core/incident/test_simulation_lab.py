from __future__ import annotations

from fastapi.testclient import TestClient

from core.incident import Incident, IncidentSeverity
from core.recovery import RecoverySnapshot, RecoverySnapshotType
from core.remediation import ActionPlan, ActionType
from core.remediation.executor import RemediationExecutor
from core.remediation.target_adapter import SimulationTargetAdapter
from core.risk import RiskAssessment, RiskDecision
from core.recovery.verification import verify_recovery
from integrations.simulations.aegisops_target import SimulationTarget, create_target_app


def test_simulation_target_reports_healthy_state() -> None:
    target = SimulationTarget()
    app = create_target_app(target=target)
    client = TestClient(app)

    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "healthy"

    ready = client.get("/ready")
    assert ready.status_code == 200
    assert ready.json()["status"] == "ready"


def test_api_latency_scenario_degrades_observable_state() -> None:
    target = SimulationTarget()
    app = create_target_app(target=target)
    client = TestClient(app)

    response = client.post("/faults", json={"scenario": "API_LATENCY_SPIKE"})
    assert response.status_code == 200
    fault_payload = response.json()
    assert fault_payload["active_faults"]

    metrics = client.get("/metrics").json()
    assert metrics["latency_ms"] > 0
    assert metrics["active_faults"]


def test_high_error_scenario_and_clear_fault() -> None:
    target = SimulationTarget()
    app = create_target_app(target=target)
    client = TestClient(app)

    response = client.post("/faults", json={"scenario": "HIGH_ERROR_RATE"})
    assert response.status_code == 200
    assert response.json()["error_rate"] > 0.0

    clear = client.post("/faults/clear", json={"fault": "clear_error_rate_fault"})
    assert clear.status_code == 200
    assert clear.json()["error_rate"] == 0.0


def test_database_and_redis_failures_are_supported_and_cleared() -> None:
    target = SimulationTarget()
    app = create_target_app(target=target)
    client = TestClient(app)

    client.post("/faults", json={"scenario": "DATABASE_FAILURE"})
    assert client.get("/ready").json()["status"] == "not_ready"

    client.post("/faults/clear", json={"fault": "clear_database_failure"})
    assert client.get("/ready").json()["status"] == "ready"

    client.post("/faults", json={"scenario": "REDIS_OUTAGE"})
    assert client.get("/ready").json()["status"] == "not_ready"

    client.post("/faults/clear", json={"fault": "clear_redis_failure"})
    assert client.get("/ready").json()["status"] == "ready"


def test_worker_delay_scenario_is_exposed_and_whitelisted() -> None:
    target = SimulationTarget()
    adapter = SimulationTargetAdapter(target=target)

    result = adapter.inject_fault(scenario="WORKER_DELAY")
    assert result["worker_delay_ms"] > 0
    assert result["active_faults"]

    cleared = adapter.clear_fault(fault_name="clear_redis_failure")
    assert cleared["state"]["redis_failed"] is False

    executor = RemediationExecutor(target_adapter=adapter)
    plan = ActionPlan(
        action_id="plan-1",
        incident_id="inc-sim-1",
        action_type=ActionType.CLEAR_LATENCY_FAULT,
        description="Clear API latency simulation.",
        target="aegisops-target-api",
        parameters={},
        risk_score=10,
        requires_approval=False,
    )
    risk = RiskAssessment(recommended_decision=RiskDecision.AUTO_EXECUTE, overall_score=10)
    execution = executor.execute(
        incident=Incident(title="sim", service="aegisops-target-api", environment="simulation", severity=IncidentSeverity.SEV2),
        action_plan=plan,
        risk_assessment=risk,
        trace=type("Trace", (), {"append_event": lambda *args, **kwargs: None})(),
    )
    assert execution.status in {"completed", "AWAITING_APPROVAL"}


def test_recovery_verification_uses_target_observations() -> None:
    target = SimulationTarget()
    adapter = SimulationTargetAdapter(target=target)

    before = RecoverySnapshot(
        kind=RecoverySnapshotType.BEFORE,
        latency=220.0,
        error_rate=0.18,
        throughput=800.0,
        dependency_health=0.45,
    )
    adapter.inject_fault(scenario="API_LATENCY_SPIKE")
    during = adapter.snapshot()

    adapter.clear_fault(fault_name="clear_latency_fault")
    after = adapter.snapshot()

    assert during.latency > before.latency
    recovered = verify_recovery(before=before, during=during, after=after)
    assert recovered.recovered is True


def test_unsupported_remediation_action_is_rejected() -> None:
    target = SimulationTarget()
    adapter = SimulationTargetAdapter(target=target)
    executor = RemediationExecutor(target_adapter=adapter)

    plan = ActionPlan(
        action_id="plan-unsupported",
        incident_id="inc-sim-unsupported",
        action_type="unsupported_action",
        description="This should be rejected.",
        target="aegisops-target-api",
        parameters={},
        risk_score=40,
        requires_approval=False,
    )
    risk = RiskAssessment(recommended_decision=RiskDecision.AUTO_EXECUTE, overall_score=10)
    result = executor.execute(
        incident=Incident(title="sim", service="aegisops-target-api", environment="simulation", severity=IncidentSeverity.SEV2),
        action_plan=plan,
        risk_assessment=risk,
        trace=type("Trace", (), {"append_event": lambda *args, **kwargs: None})(),
    )
    assert result.status in {"UNSUPPORTED_REMEDIATION", "BLOCKED"}
