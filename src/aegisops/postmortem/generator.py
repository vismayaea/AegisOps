from __future__ import annotations

from aegisops.domain import Incident


class PostmortemGenerator:
    def generate(self, incident: Incident) -> dict[str, object]:
        evidence = [item.as_dict() for item in incident.evidence]
        timeline = [event.as_dict() for event in incident.trace]
        return {
            "incident_id": incident.id,
            "summary": f"{incident.scenario.value} affected {incident.investigation.affected_service if incident.investigation else 'unknown service'}",
            "impact": {
                "latency_ms": incident.during.latency_ms,
                "error_rate": incident.during.error_rate,
                "status": incident.status.value,
            },
            "timeline": timeline,
            "evidence": evidence,
            "root_cause": incident.investigation.as_dict() if incident.investigation else None,
            "remediation": incident.selected_action.as_dict() if incident.selected_action else None,
            "recovery": incident.recovery.as_dict() if incident.recovery else None,
            "decision_trace": timeline,
            "lessons": [
                "Keep remediation actions registered and reviewable.",
                "Require recovery verification before resolving incidents.",
                "Preserve evidence identifiers in every RCA and audit event.",
            ],
        }
