from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from core.evidence import Evidence
from core.incident import Incident
from core.investigation import Hypothesis, HypothesisRanker, HypothesisStatus


@dataclass
class InvestigationResult:
    """Structured result from a bounded investigation pass."""

    incident_id: str
    hypotheses: list[Hypothesis] = field(default_factory=list)
    evidence_used: list[str] = field(default_factory=list)
    investigation_summary: str = ""
    confidence: float = 0.0
    investigation_duration: float | None = None
    tools_used: list[str] = field(default_factory=list)
    status: str = "completed"
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "hypotheses": [item.to_dict() for item in self.hypotheses],
            "evidence_used": self.evidence_used,
            "investigation_summary": self.investigation_summary,
            "confidence": self.confidence,
            "investigation_duration": self.investigation_duration,
            "tools_used": self.tools_used,
            "status": self.status,
            "error": self.error,
        }


class InvestigationService:
    """Coordinates an agent-backed investigation against the incident evidence."""

    def __init__(self, *, agent: Any | None = None) -> None:
        self._agent = agent

    def investigate(
        self,
        incident: Incident,
        evidence_items: list[Evidence],
        *,
        request: dict[str, Any] | None = None,
        agent: Any | None = None,
    ) -> InvestigationResult:
        if not evidence_items:
            return InvestigationResult(
                incident_id=incident.incident_id,
                investigation_summary="No evidence available for investigation.",
                status="no_evidence",
                error="No evidence was attached to this incident.",
            )

        actual_agent = agent or self._agent
        if actual_agent is None or not hasattr(actual_agent, "run"):
            return InvestigationResult(
                incident_id=incident.incident_id,
                evidence_used=[item.evidence_id for item in evidence_items],
                investigation_summary="Investigation did not run because no agent runtime was configured.",
                status="agent_unavailable",
                error="No agent runtime was available to investigate the incident.",
            )

        evidence_ids = [item.evidence_id for item in evidence_items]
        request_payload = request or {
            "incident_id": incident.incident_id,
            "service": incident.service,
            "title": incident.title,
            "environment": incident.environment,
            "evidence_ids": evidence_ids,
            "question": f"Investigate incident {incident.incident_id} and identify the most likely root cause using the evidence provided.",
        }

        started = time.perf_counter()
        try:
            raw_response = actual_agent.run([
                {
                    "role": "user",
                    "content": self._build_prompt(incident, evidence_items, request_payload),
                }
            ])
        except Exception as exc:  # pragma: no cover - exercised by tests with explicit failure
            return InvestigationResult(
                incident_id=incident.incident_id,
                evidence_used=evidence_ids,
                investigation_summary="The investigation agent failed.",
                status="agent_failed",
                error=f"{type(exc).__name__}: {str(exc) or 'agent failure'}",
            )

        tool_names = self._extract_tools(raw_response)
        hypotheses = self._build_hypotheses(incident, evidence_items, raw_response)
        ranked = HypothesisRanker.rank(hypotheses)
        duration = time.perf_counter() - started

        if not ranked:
            return InvestigationResult(
                incident_id=incident.incident_id,
                evidence_used=evidence_ids,
                investigation_summary="No supported hypotheses were produced from the available evidence.",
                status="insufficient_evidence",
                error="The investigation produced no usable hypotheses.",
                investigation_duration=duration,
                tools_used=tool_names,
            )

        confidence = max((item.confidence for item in ranked), default=0.0)
        summary = " | ".join(
            f"{item.hypothesis_id}:{item.statement} ({item.confidence:.2f})" for item in ranked[:3]
        )

        return InvestigationResult(
            incident_id=incident.incident_id,
            hypotheses=ranked,
            evidence_used=evidence_ids,
            investigation_summary=summary,
            confidence=confidence,
            investigation_duration=duration,
            tools_used=tool_names,
            status="completed",
        )

    def _build_prompt(
        self,
        incident: Incident,
        evidence_items: list[Evidence],
        request_payload: dict[str, Any],
    ) -> str:
        evidence_lines = "\n".join(
            f"- {item.evidence_id}: {item.summary} (source={item.source}, confidence={item.confidence})"
            for item in evidence_items
        )
        return (
            f"Incident: {incident.title}\n"
            f"Service: {incident.service}\n"
            f"Environment: {incident.environment}\n"
            f"Severity: {incident.severity.value}\n"
            f"Question: {request_payload.get('question', '')}\n\n"
            "Evidence:\n"
            f"{evidence_lines}\n\n"
            "Return structured hypotheses as a JSON object with a 'hypotheses' list. "
            "Each item must include: statement, affected_service, supporting_evidence_ids, "
            "contradicting_evidence_ids, confidence, status."
        )

    def _extract_tools(self, raw_response: Any) -> list[str]:
        if isinstance(raw_response, dict):
            tools = raw_response.get("tools_used")
            if isinstance(tools, list):
                return [str(item) for item in tools]
        if isinstance(raw_response, list):
            for item in raw_response:
                if isinstance(item, dict) and isinstance(item.get("tool"), str):
                    return [str(item["tool"])]
        return []

    def _build_hypotheses(
        self,
        incident: Incident,
        evidence_items: list[Evidence],
        raw_response: Any,
    ) -> list[Hypothesis]:
        candidates: list[Any] = []
        if isinstance(raw_response, dict):
            data = raw_response.get("hypotheses")
            if isinstance(data, list):
                candidates = data
            elif isinstance(raw_response.get("result"), list):
                candidates = raw_response["result"]
            elif isinstance(raw_response.get("output"), list):
                candidates = raw_response["output"]
        elif isinstance(raw_response, list):
            candidates = raw_response

        if not candidates:
            return []

        built: list[Hypothesis] = []
        evidence_by_id = {item.evidence_id: item for item in evidence_items}
        for index, entry in enumerate(candidates, start=1):
            if isinstance(entry, Hypothesis):
                built.append(entry)
                continue
            if not isinstance(entry, dict):
                continue

            statement = str(entry.get("statement") or entry.get("title") or "").strip()
            if not statement:
                continue

            supporting = entry.get("supporting_evidence_ids") or entry.get("supporting_evidence") or []
            contrad = entry.get("contradicting_evidence_ids") or entry.get("contradicting_evidence") or []

            support_ids = [str(item) for item in self._normalize_evidence_ids(supporting, evidence_by_id)]
            contradiction_ids = [str(item) for item in self._normalize_evidence_ids(contrad, evidence_by_id)]
            confidence = float(entry.get("confidence", 0.0) or 0.0)
            status = str(entry.get("status") or HypothesisStatus.PROPOSED.value)

            supported = bool(support_ids)
            final_status = HypothesisStatus(status) if status in HypothesisStatus._value2member_map_ else HypothesisStatus.PROPOSED
            if not supported:
                final_status = HypothesisStatus.REJECTED
                confidence = 0.0

            built.append(
                Hypothesis(
                    hypothesis_id=str(entry.get("hypothesis_id") or f"h-{incident.incident_id}-{index}"),
                    incident_id=incident.incident_id,
                    statement=statement,
                    affected_service=str(entry.get("affected_service") or incident.service),
                    supporting_evidence_ids=support_ids,
                    contradicting_evidence_ids=contradiction_ids,
                    confidence=confidence,
                    status=final_status,
                )
            )

        return built

    def _normalize_evidence_ids(
        self,
        values: Any,
        evidence_by_id: dict[str, Evidence],
    ) -> list[str]:
        if isinstance(values, str):
            return [values] if values in evidence_by_id else []
        if not isinstance(values, list):
            return []

        normalized: list[str] = []
        for item in values:
            if isinstance(item, Evidence):
                normalized.append(item.evidence_id)
            elif isinstance(item, str):
                if item in evidence_by_id:
                    normalized.append(item)
            elif isinstance(item, dict):
                candidate = item.get("evidence_id") or item.get("id")
                if isinstance(candidate, str) and candidate in evidence_by_id:
                    normalized.append(candidate)
        return list(dict.fromkeys(normalized))


__all__ = ["InvestigationResult", "InvestigationService"]
