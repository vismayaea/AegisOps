from __future__ import annotations

from collections import Counter

from aegisops.domain import EvidenceItem, InvestigationResult, ScenarioName


class InvestigationService:
    root_causes = {
        ScenarioName.API_LATENCY_SPIKE: "database connection pool saturation causing checkout-api latency",
        ScenarioName.DATABASE_FAILURE: "orders database primary unavailable in local simulation",
        ScenarioName.REDIS_OUTAGE: "Redis cache dependency unavailable to request and worker paths",
        ScenarioName.ELEVATED_ERROR_RATE: "edge gateway retry storm amplifying deterministic upstream failures",
        ScenarioName.WORKER_DELAY: "settlement worker backlog delaying asynchronous job completion",
    }

    affected_services = {
        ScenarioName.API_LATENCY_SPIKE: "checkout-api",
        ScenarioName.DATABASE_FAILURE: "orders-db",
        ScenarioName.REDIS_OUTAGE: "cache-redis",
        ScenarioName.ELEVATED_ERROR_RATE: "edge-gateway",
        ScenarioName.WORKER_DELAY: "settlement-worker",
    }

    def investigate(self, scenario: ScenarioName, evidence: list[EvidenceItem]) -> InvestigationResult:
        service_counts = Counter(item.service for item in evidence)
        affected = self.affected_services[scenario]
        supporting = [
            item.id
            for item in evidence
            if item.service in {affected, "request-path"} or item.severity in {"high", "critical"}
        ]
        confidence = 0.94 if len(supporting) >= 4 else 0.86
        hypotheses = [
            {
                "name": self.root_causes[scenario],
                "score": len(supporting) * 12 + int(confidence * 25),
                "evidence_ids": supporting,
            },
            {
                "name": "generic application regression",
                "score": service_counts.get("request-path", 0) * 8,
                "evidence_ids": [item.id for item in evidence if item.service == "request-path"],
            },
        ]
        hypotheses.sort(key=lambda item: item["score"], reverse=True)
        return InvestigationResult(
            likely_root_cause=hypotheses[0]["name"],
            confidence=confidence,
            affected_service=affected,
            supporting_evidence=supporting,
            hypotheses=hypotheses,
        )
