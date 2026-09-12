from __future__ import annotations

from datetime import timezone
from uuid import uuid4

from aegisops.domain import Incident, IncidentStatus, ScenarioName, utc_now
from aegisops.evidence import EvidenceEngine
from aegisops.investigation import InvestigationService
from aegisops.postmortem import PostmortemGenerator
from aegisops.recovery import RecoveryVerifier
from aegisops.remediation import RemediationRegistry
from aegisops.risk import RiskEngine
from aegisops.simulation import SimulationEngine
from aegisops.trace import TraceRecorder


class IncidentOrchestrator:
    def __init__(self) -> None:
        self.simulation = SimulationEngine()
        self.evidence = EvidenceEngine()
        self.investigator = InvestigationService()
        self.remediation = RemediationRegistry(self.simulation)
        self.risk = RiskEngine()
        self.recovery = RecoveryVerifier()
        self.trace = TraceRecorder()
        self.postmortems = PostmortemGenerator()
        self.incidents: dict[str, Incident] = {}

    def reset(self) -> dict[str, object]:
        self.simulation.reset()
        self.incidents.clear()
        return self.state()

    def state(self) -> dict[str, object]:
        active = [item.as_dict() for item in self.incidents.values() if item.status is not IncidentStatus.RESOLVED]
        return {
            **self.simulation.state(),
            "ai_status": "deterministic investigation ready",
            "llm_status": "optional; not required for local demo",
            "active_incidents": active,
        }

    def scenarios(self) -> list[dict[str, str]]:
        return self.simulation.available_scenarios()

    def create_incident(self, scenario: ScenarioName) -> Incident:
        before = self.simulation.baseline
        during = self.simulation.inject(scenario)
        incident = Incident(
            id=f"inc_{uuid4().hex[:8]}",
            scenario=scenario,
            status=IncidentStatus.DETECTED,
            created_at=utc_now().astimezone(timezone.utc),
            before=before,
            during=during,
        )
        self.trace.add(incident, "incident_detected", "Incident detected from deterministic simulation signals")
        incident.evidence = self.evidence.generate(scenario, during)
        self.trace.add(
            incident,
            "evidence_collected",
            "Synthetic observability evidence generated",
            references=[item.id for item in incident.evidence],
        )
        incident.status = IncidentStatus.INVESTIGATING
        incident.investigation = self.investigator.investigate(scenario, incident.evidence)
        self.trace.add(
            incident,
            "investigation_performed",
            "Evidence correlated and hypotheses scored",
            references=incident.investigation.supporting_evidence,
            details={"confidence": incident.investigation.confidence},
        )
        self.trace.add(
            incident,
            "rca_produced",
            "Root cause analysis produced",
            references=incident.investigation.supporting_evidence,
            details={"root_cause": incident.investigation.likely_root_cause},
        )
        action = self.remediation.select_for(scenario)
        incident.selected_action = action
        incident.risk = self.risk.evaluate(
            during=during,
            investigation=incident.investigation,
            reversibility=action.reversibility,
            historical_success=action.historical_success,
        )
        incident.status = IncidentStatus.AWAITING_APPROVAL if incident.risk.approval_required else IncidentStatus.REMEDIATING
        self.trace.add(
            incident,
            "risk_evaluated",
            "Risk evaluated with transparent deterministic factors",
            details=incident.risk.as_dict(),
        )
        self.trace.add(
            incident,
            "remediation_selected",
            "Registered remediation action selected",
            details=action.as_dict(),
        )
        self.incidents[incident.id] = incident
        return incident

    def approve(self, incident_id: str) -> Incident:
        incident = self._get(incident_id)
        incident.approval_granted = True
        self.trace.add(incident, "approval_decision", "Human approval granted for registered action")
        return incident

    def execute(self, incident_id: str) -> Incident:
        incident = self._get(incident_id)
        if incident.risk and incident.risk.approval_required and not incident.approval_granted:
            raise PermissionError("Human approval is required before remediation")
        if incident.selected_action is None:
            raise RuntimeError("No remediation action selected")
        incident.status = IncidentStatus.REMEDIATING
        incident.execution = self.remediation.execute(incident.scenario, incident.selected_action.id)
        self.trace.add(
            incident,
            "remediation_executed",
            "Registered remediation action executed against local simulation",
            details=incident.execution.as_dict(),
        )
        incident.status = IncidentStatus.VERIFYING
        incident.after = self.simulation.current
        incident.recovery = self.recovery.verify(incident.before, incident.during, incident.after)
        self.trace.add(
            incident,
            "recovery_checked",
            "Recovery criteria evaluated against baseline and degraded metrics",
            details=incident.recovery.as_dict(),
        )
        if incident.recovery.recovered:
            incident.status = IncidentStatus.RESOLVED
            self.trace.add(incident, "incident_resolved", "Incident resolved after recovery verification")
        return incident

    def run_full_lifecycle(self, scenario: ScenarioName) -> Incident:
        incident = self.create_incident(scenario)
        if incident.risk and incident.risk.approval_required:
            self.approve(incident.id)
        return self.execute(incident.id)

    def postmortem(self, incident_id: str) -> dict[str, object]:
        return self.postmortems.generate(self._get(incident_id))

    def _get(self, incident_id: str) -> Incident:
        try:
            return self.incidents[incident_id]
        except KeyError as exc:
            raise KeyError(f"Unknown incident: {incident_id}") from exc
