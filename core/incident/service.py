from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from core.evidence import Evidence
from core.incident import Incident, IncidentSeverity, IncidentStatus
from core.incident_trace import DecisionTrace, DecisionTraceEventType
from core.incident_trace.postmortem import generate_postmortem
from core.incident_trace.replay import replay_incident
from core.investigation import Hypothesis
from core.investigation.service import InvestigationResult, InvestigationService
from core.rca import BlastRadius, RootCause
from core.rca.service import RCAResult, RCAService
from core.recovery import RecoverySnapshot, VerificationResult
from core.recovery.verification import RecoveryVerificationResult, verify_recovery
from core.remediation import ActionPlan, ApprovalState, ExecutionRecord, ExecutionStatus
from core.remediation.executor import RemediationExecutionResult, RemediationExecutor
from core.remediation.planner import NoSafeRemediation, RemediationPlanner
from core.risk import RiskAssessment, RiskEngine


@dataclass(frozen=True)
class ServiceContext:
    """Abstracted investigation context built from incident evidence and runtime metadata."""

    affected_service: str
    related_dependencies: list[str] = field(default_factory=list)
    observability_sources: list[str] = field(default_factory=list)
    recent_deployments: list[str] = field(default_factory=list)
    recent_config_changes: list[str] = field(default_factory=list)
    historical_context: list[str] = field(default_factory=list)


@dataclass
class InvestigationRequest:
    """Bounded investigation request passed into the underlying agent runtime."""

    incident_id: str
    question: str
    evidence_ids: list[str] = field(default_factory=list)
    max_hypotheses: int = 5


@dataclass
class InvestigationResult:
    """Structured result returned after a runtime-backed investigation pass."""

    incident_id: str
    evidence_ids: list[str]
    hypotheses: list[Hypothesis] = field(default_factory=list)
    agent_runtime_used: bool = False
    summary: str = ""


class IncidentService:
    """Coordinates the AegisOps incident lifecycle using the existing runtime underneath.

    The default implementation is in-memory so the current codebase continues to
    work without introducing a new persistence technology. This is the smallest
    architecture that supports the investigation lifecycle reliably while leaving
    the underlying OpenSRE-derived runtime intact.
    """

    def __init__(self, *, agent: Any | None = None) -> None:
        self._agent = agent
        self._investigation_service = InvestigationService(agent=agent)
        self._rca_service = RCAService()
        self._remediation_planner = RemediationPlanner()
        self._incidents: dict[str, Incident] = {}
        self._evidence_store: dict[str, list[Evidence]] = {}
        self._decision_traces: dict[str, DecisionTrace] = {}
        self._hypotheses: dict[str, list[Hypothesis]] = {}
        self._root_causes: dict[str, RootCause] = {}
        self._risk_assessments: dict[str, RiskAssessment] = {}
        self._remediation_plans: dict[str, ActionPlan | NoSafeRemediation] = {}
        self._execution_records: dict[str, list[ExecutionRecord]] = {}
        self._recovery_verifications: dict[str, RecoveryVerificationResult] = {}

    def _ensure_incident(self, incident_id: str) -> Incident:
        incident = self._incidents.get(incident_id)
        if incident is None:
            raise KeyError(f"incident not found: {incident_id}")
        return incident

    def _ensure_trace(self, incident_id: str) -> DecisionTrace:
        trace = self._decision_traces.get(incident_id)
        if trace is None:
            trace = DecisionTrace(incident_id=incident_id)
            self._decision_traces[incident_id] = trace
        return trace

    def create_incident(
        self,
        *,
        title: str,
        service: str,
        environment: str,
        severity: IncidentSeverity | str | None = None,
        summary: str = "",
        owner: str = "",
    ) -> Incident:
        incident = Incident(
            title=title,
            service=service,
            environment=environment,
            severity=severity or IncidentSeverity.SEV2,
            summary=summary,
            owner=owner,
        )
        self._incidents[incident.incident_id] = incident
        self._evidence_store[incident.incident_id] = []
        trace = DecisionTrace(incident_id=incident.incident_id)
        trace.append_event(
            DecisionTraceEventType.INCIDENT_DETECTED,
            summary=f"Incident detected: {title}",
            actor="alert-intake",
        )
        incident.transition_to(IncidentStatus.TRIAGED)
        trace.append_event(
            DecisionTraceEventType.TRIAGED,
            summary=f"Incident triaged for {service}",
            actor="incident-service",
        )
        self._decision_traces[incident.incident_id] = trace
        return incident

    def get_incident(self, incident_id: str) -> Incident | None:
        return self._incidents.get(incident_id)

    def triage_incident(self, incident_id: str) -> Incident:
        incident = self._ensure_incident(incident_id)
        if incident.status in {IncidentStatus.DETECTED}:  # pragma: no branch - clarity
            incident.transition_to(IncidentStatus.TRIAGED)
        trace = self._ensure_trace(incident_id)
        trace.append_event(
            DecisionTraceEventType.TRIAGED,
            summary=f"Incident triaged for {incident.service}",
            actor="incident-service",
        )
        return incident

    def collect_evidence(
        self,
        incident_id: str,
        evidence_items: Sequence[Evidence],
    ) -> list[Evidence]:
        incident = self._ensure_incident(incident_id)
        evidence_list = list(evidence_items)
        attached = self._evidence_store.setdefault(incident_id, [])
        for item in evidence_list:
            attached.append(item)
        if incident.status is IncidentStatus.TRIAGED:
            incident.transition_to(IncidentStatus.EVIDENCE_COLLECTED)
        trace = self._ensure_trace(incident_id)
        trace.append_event(
            DecisionTraceEventType.EVIDENCE_COLLECTED,
            summary=f"Collected {len(evidence_list)} evidence item(s)",
            actor="incident-service",
        )
        return attached

    def get_evidence(self, incident_id: str) -> list[Evidence]:
        return list(self._evidence_store.get(incident_id, []))

    def start_investigation(
        self,
        incident_id: str,
        *,
        request: InvestigationRequest | Any | None = None,
    ) -> InvestigationResult:
        incident = self._ensure_incident(incident_id)
        if incident.status in {IncidentStatus.TRIAGED, IncidentStatus.EVIDENCE_COLLECTED}:
            incident.transition_to(IncidentStatus.INVESTIGATING)
        trace = self._ensure_trace(incident_id)
        trace.append_event(
            DecisionTraceEventType.INVESTIGATION_STARTED,
            summary=f"Investigation started for {incident.title}",
            actor="agent-runtime",
        )

        evidence_ids = [item.evidence_id for item in self.get_evidence(incident_id)]
        result = InvestigationResult(
            incident_id=incident_id,
            evidence_ids=evidence_ids,
            summary=f"Investigation started for {incident.service}",
        )

        request_payload = request
        if request_payload is None:
            request_payload = InvestigationRequest(
                incident_id=incident_id,
                question=f"Investigate incident {incident.incident_id}: {incident.title}",
                evidence_ids=evidence_ids,
            )

        if self._agent is not None and hasattr(self._agent, "run"):
            try:
                self._agent.run([
                    {"role": "user", "content": request_payload.question}
                ])
                result.agent_runtime_used = True
            except Exception:
                result.agent_runtime_used = False
        return result

    def investigate(
        self,
        incident_id: str,
        *,
        request: dict[str, Any] | None = None,
        agent: Any | None = None,
    ) -> InvestigationResult:
        incident = self._ensure_incident(incident_id)
        evidence = self.get_evidence(incident_id)
        if incident.status in {IncidentStatus.TRIAGED, IncidentStatus.EVIDENCE_COLLECTED}:
            incident.transition_to(IncidentStatus.INVESTIGATING)

        trace = self._ensure_trace(incident_id)
        if not any(event.event_type is DecisionTraceEventType.INVESTIGATION_STARTED for event in trace.events):
            trace.append_event(
                DecisionTraceEventType.INVESTIGATION_STARTED,
                summary=f"Investigation started for {incident.title}",
                actor="agent-runtime",
                incident_id=incident_id,
            )

        result = self._investigation_service.investigate(
            incident,
            evidence,
            request=request,
            agent=agent or self._agent,
        )

        if result.hypotheses:
            self._hypotheses.setdefault(incident_id, []).extend(result.hypotheses)
            for hypothesis in result.hypotheses:
                self._ensure_trace(incident_id).append_event(
                    DecisionTraceEventType.HYPOTHESIS_CREATED,
                    summary=f"Hypothesis created: {hypothesis.statement}",
                    actor="agent-runtime",
                )
        return result

    def create_hypotheses(
        self,
        *,
        incident_id: str,
        hypotheses: Sequence[Hypothesis | dict[str, Any]],
    ) -> list[Hypothesis]:
        incident = self._ensure_incident(incident_id)
        if incident.status is IncidentStatus.EVIDENCE_COLLECTED:
            incident.transition_to(IncidentStatus.INVESTIGATING)
        created: list[Hypothesis] = []
        for item in hypotheses:
            if isinstance(item, Hypothesis):
                hypothesis = item
            else:
                hypothesis = Hypothesis(
                    hypothesis_id=str(item["hypothesis_id"]),
                    incident_id=incident_id,
                    statement=str(item["statement"]),
                    affected_service=str(item.get("affected_service", incident.service)),
                    supporting_evidence_ids=list(item.get("supporting_evidence_ids", [])),
                    contradicting_evidence_ids=list(item.get("contradicting_evidence_ids", [])),
                    confidence=float(item.get("confidence", 0.0)),
                    status=str(item.get("status", "proposed")),
                )
            created.append(hypothesis)
        self._hypotheses.setdefault(incident_id, []).extend(created)
        trace = self._ensure_trace(incident_id)
        for hypothesis in created:
            trace.append_event(
                DecisionTraceEventType.HYPOTHESIS_TESTED,
                summary=f"Hypothesis tested: {hypothesis.statement}",
                actor="agent-runtime",
            )
            trace.append_event(
                DecisionTraceEventType.HYPOTHESIS_CREATED,
                summary=f"Hypothesis created: {hypothesis.statement}",
                actor="agent-runtime",
            )
        return created

    def record_root_cause(
        self,
        *,
        incident_id: str,
        statement: str,
        affected_service: str,
        evidence_ids: Sequence[str],
        confidence: float,
        blast_radius: BlastRadius | None = None,
        contributing_factors: Sequence[str] | None = None,
    ) -> RootCause:
        if not evidence_ids:
            raise ValueError("root cause requires at least one supporting evidence item")
        incident = self._ensure_incident(incident_id)
        root_cause = RootCause(
            root_cause_id=f"rc-{incident_id}",
            incident_id=incident_id,
            statement=statement,
            affected_service=affected_service,
            evidence_ids=list(evidence_ids),
            confidence=float(confidence),
            blast_radius=blast_radius,
            contributing_factors=list(contributing_factors or []),
        )
        self._root_causes[incident_id] = root_cause
        if incident.status is not IncidentStatus.ROOT_CAUSE_IDENTIFIED:
            incident.transition_to(IncidentStatus.ROOT_CAUSE_IDENTIFIED)
        trace = self._ensure_trace(incident_id)
        trace.append_event(
            DecisionTraceEventType.ROOT_CAUSE_IDENTIFIED,
            summary=f"Root cause identified: {statement}",
            actor="agent-runtime",
        )
        return root_cause

    def identify_root_cause(
        self,
        incident_id: str,
        *,
        hypotheses: Sequence[Hypothesis | dict[str, Any]] | None = None,
    ) -> RCAResult:
        incident = self._ensure_incident(incident_id)
        evidence = self.get_evidence(incident_id)
        candidates = list(hypotheses) if hypotheses is not None else list(self._hypotheses.get(incident_id, []))
        result = self._rca_service.analyze(incident, evidence, [
            item if isinstance(item, Hypothesis) else Hypothesis(
                hypothesis_id=str(item["hypothesis_id"]),
                incident_id=incident_id,
                statement=str(item["statement"]),
                affected_service=str(item.get("affected_service", incident.service)),
                supporting_evidence_ids=list(item.get("supporting_evidence_ids", [])),
                contradicting_evidence_ids=list(item.get("contradicting_evidence_ids", [])),
                confidence=float(item.get("confidence", 0.0)),
                status=str(item.get("status", "proposed")),
            )
            for item in candidates
        ])

        if result.root_cause is not None:
            self._root_causes[incident_id] = result.root_cause
            if incident.status is not IncidentStatus.ROOT_CAUSE_IDENTIFIED:
                incident.transition_to(IncidentStatus.ROOT_CAUSE_IDENTIFIED)
            self._ensure_trace(incident_id).append_event(
                DecisionTraceEventType.ROOT_CAUSE_IDENTIFIED,
                summary=f"Root cause identified: {result.root_cause.statement}",
                actor="rca-service",
            )
        return result

    def assess_risk(
        self,
        *,
        incident_id: str,
        blast_radius: BlastRadius,
        diagnosis_confidence: float,
        reversibility: float,
        historical_success: float,
    ) -> RiskAssessment:
        incident = self._ensure_incident(incident_id)
        assessment = RiskEngine().assess(
            incident=incident,
            blast_radius=blast_radius,
            diagnosis_confidence=float(diagnosis_confidence),
            reversibility=float(reversibility),
            historical_success=float(historical_success),
        )
        self._risk_assessments[incident_id] = assessment
        if incident.status is not IncidentStatus.RISK_ASSESSED:
            incident.transition_to(IncidentStatus.RISK_ASSESSED)
        trace = self._ensure_trace(incident_id)
        trace.append_event(
            DecisionTraceEventType.RISK_ASSESSED,
            summary=f"Risk assessed: {assessment.recommended_decision.value}",
            actor="risk-engine",
        )
        return assessment

    def propose_remediation(
        self,
        incident_id: str,
        *,
        risk_assessment: RiskAssessment | None = None,
    ) -> ActionPlan | NoSafeRemediation:
        incident = self._ensure_incident(incident_id)
        root_cause = self.get_root_cause(incident_id)
        assessment = risk_assessment or self.get_risk(incident_id)
        if assessment is None:
            blast_radius = root_cause.blast_radius if root_cause else BlastRadius()
            assessment = RiskEngine().assess(
                incident=incident,
                blast_radius=blast_radius,
                diagnosis_confidence=root_cause.confidence if root_cause else 0.5,
                reversibility=0.7,
                historical_success=0.7,
            )
            self._risk_assessments[incident_id] = assessment

        plan = self._remediation_planner.plan(incident, root_cause, assessment)
        self._remediation_plans[incident_id] = plan
        trace = self._ensure_trace(incident_id)
        if isinstance(plan, ActionPlan):
            trace.append_event(
                DecisionTraceEventType.REMEDIATION_PROPOSED,
                summary=(
                    plan.description if isinstance(plan, ActionPlan) else plan.reason
                ),
                actor="remediation-planner",
                incident_id=incident_id,
                action_id=plan.action_id,
            )
            if plan.requires_approval:
                trace.append_event(
                    DecisionTraceEventType.APPROVAL_REQUESTED,
                    summary=f"Approval requested for {plan.action_id}",
                    actor="remediation-planner",
                    incident_id=incident_id,
                    action_id=plan.action_id,
                )
        else:
            trace.append_event(
                DecisionTraceEventType.REMEDIATION_PROPOSED,
                summary=plan.reason,
                actor="remediation-planner",
                incident_id=incident_id,
            )
        return plan

    def approve_incident_action(
        self,
        incident_id: str,
        action_id: str,
        *,
        approved: bool,
        actor: str = "human-approval",
    ) -> bool:
        plan = self._remediation_plans.get(incident_id)
        if not isinstance(plan, ActionPlan) or plan.action_id != action_id:
            raise KeyError(f"action not found for incident {incident_id}: {action_id}")
        if approved:
            plan.approval_state = ApprovalState.APPROVED
            self._ensure_trace(incident_id).append_event(
                DecisionTraceEventType.APPROVED,
                summary=f"Approved action {action_id}",
                actor=actor,
                incident_id=incident_id,
                action_id=action_id,
            )
            return True
        plan.approval_state = ApprovalState.REJECTED
        self._ensure_trace(incident_id).append_event(
            DecisionTraceEventType.REJECTED,
            summary=f"Rejected action {action_id}",
            actor=actor,
            incident_id=incident_id,
            action_id=action_id,
        )
        return False

    def execute_remediation(
        self,
        incident_id: str,
        *,
        action_plan: ActionPlan | None = None,
        risk_assessment: RiskAssessment | None = None,
        approved: bool | None = None,
        before: RecoverySnapshot | None = None,
        during: RecoverySnapshot | None = None,
        evidence: list | None = None,
        target_adapter: Any | None = None,
    ) -> RemediationExecutionResult:
        incident = self._ensure_incident(incident_id)
        plan = action_plan or self._remediation_plans.get(incident_id)
        if plan is None or not isinstance(plan, ActionPlan):
            return RemediationExecutionResult(
                status="NO_SAFE_REMEDIATION_AVAILABLE",
                error="No safe remediation plan is available for execution.",
            )
        assessment = risk_assessment or self.get_risk(incident_id)
        if assessment is None:
            return RemediationExecutionResult(
                status="NO_RISK_ASSESSMENT",
                error="Risk assessment is required before execution.",
            )
        result = RemediationExecutor(target_adapter=target_adapter).execute(
            incident=incident,
            action_plan=plan,
            risk_assessment=assessment,
            trace=self._ensure_trace(incident_id),
            before=before,
            during=during,
            evidence=evidence or self.get_evidence(incident_id),
            approved=approved,
        )
        if result.execution_record is not None:
            self._execution_records.setdefault(incident_id, []).append(result.execution_record)
            if incident.status is not IncidentStatus.REMEDIATION_IN_PROGRESS:
                incident.transition_to(IncidentStatus.REMEDIATION_IN_PROGRESS)
        return result

    def verify_recovery(
        self,
        incident_id: str,
        *,
        before: RecoverySnapshot | None,
        during: RecoverySnapshot | None,
        after: RecoverySnapshot | None,
    ) -> RecoveryVerificationResult:
        result = verify_recovery(before=before, during=during, after=after)
        self._recovery_verifications[incident_id] = result
        trace = self._ensure_trace(incident_id)
        if result.recovered:
            trace.append_event(
                DecisionTraceEventType.RECOVERY_VERIFIED,
                summary="Recovery verification passed.",
                actor="recovery-verifier",
                incident_id=incident_id,
            )
            if self._ensure_incident(incident_id).status is not IncidentStatus.RESOLVED:
                self._ensure_incident(incident_id).transition_to(IncidentStatus.RESOLVED)
            trace.append_event(
                DecisionTraceEventType.RESOLVED,
                summary="Incident resolved after recovery verification.",
                actor="incident-service",
                incident_id=incident_id,
            )
        else:
            trace.append_event(
                DecisionTraceEventType.RECOVERY_FAILED,
                summary="Recovery verification failed.",
                actor="recovery-verifier",
                incident_id=incident_id,
            )
        return result

    def replay_incident(self, incident_id: str) -> dict[str, object]:
        incident = self._ensure_incident(incident_id)
        trace = self._ensure_trace(incident_id)
        return replay_incident(
            incident=incident,
            trace=trace,
            evidence_refs=[item.evidence_id for item in self.get_evidence(incident_id)],
            execution_records=[item.__dict__ for item in self._execution_records.get(incident_id, [])],
            verification_results=[self._recovery_verifications.get(incident_id).to_dict()] if incident_id in self._recovery_verifications else [],
        ).to_dict()

    def generate_postmortem(self, incident_id: str) -> dict[str, object]:
        incident = self._ensure_incident(incident_id)
        trace = self._ensure_trace(incident_id)
        root_cause = self.get_root_cause(incident_id)
        risk = self.get_risk(incident_id)
        evidence = [item.evidence_id for item in self.get_evidence(incident_id)]
        plan = self._remediation_plans.get(incident_id)
        verification = self._recovery_verifications.get(incident_id)
        human_intervention = "approval required" if isinstance(plan, ActionPlan) and plan.requires_approval else "automatic execution"
        if plan is not None and isinstance(plan, ActionPlan) and plan.approval_state is ApprovalState.REJECTED:
            human_intervention = "approval rejected"
        elif plan is not None and isinstance(plan, ActionPlan) and plan.approval_state is ApprovalState.APPROVED:
            human_intervention = "approval granted"
        return generate_postmortem(
            incident=incident,
            trace=trace,
            summary=f"Incident {incident.incident_id}: {incident.title}",
            impact=incident.summary or "Not available from incident record.",
            root_cause=root_cause.statement if root_cause else "Not available from incident record.",
            evidence=evidence or ["Not available from incident record."],
            remediation=(plan.description if isinstance(plan, ActionPlan) else "Not available from incident record."),
            verification=(verification.verification_summary if verification else "Not available from incident record."),
            human_intervention=human_intervention,
            lessons=["Not available from incident record."],
        ).to_dict()

    def get_timeline(self, incident_id: str) -> list[Any]:
        return list(self._ensure_trace(incident_id).events)

    def get_root_cause(self, incident_id: str) -> RootCause | None:
        return self._root_causes.get(incident_id)

    def get_risk(self, incident_id: str) -> RiskAssessment | None:
        return self._risk_assessments.get(incident_id)

    def build_service_context(self, incident_id: str) -> ServiceContext:
        incident = self._ensure_incident(incident_id)
        evidence_items = self.get_evidence(incident_id)
        dependencies: list[str] = []
        for item in evidence_items:
            deps = item.metadata.get("dependencies")
            if isinstance(deps, Sequence) and not isinstance(deps, (str, bytes)):
                dependencies.extend(str(v) for v in deps)
            if isinstance(item.metadata.get("dependency"), str):
                dependencies.append(item.metadata["dependency"])

        observability_sources = list({item.source for item in evidence_items if item.source})
        if not observability_sources:
            observability_sources = ["logs", "metrics", "traces"]

        deployments = [
            str(item.metadata.get("deployment"))
            for item in evidence_items
            if item.metadata.get("deployment") is not None
        ]
        if not deployments:
            deployments = ["deployments"]

        config_changes = [
            str(item.metadata.get("config_change"))
            for item in evidence_items
            if item.metadata.get("config_change") is not None
        ]
        if not config_changes:
            config_changes = ["configuration"]

        historical_context = [
            item.summary
            for item in evidence_items
            if item.summary and item.summary.strip()
        ]

        return ServiceContext(
            affected_service=incident.service,
            related_dependencies=sorted(set(dependencies)),
            observability_sources=sorted(set(observability_sources)),
            recent_deployments=sorted(set(deployments)),
            recent_config_changes=sorted(set(config_changes)),
            historical_context=historical_context,
        )


__all__ = [
    "IncidentService",
    "InvestigationRequest",
    "InvestigationResult",
    "ServiceContext",
]
