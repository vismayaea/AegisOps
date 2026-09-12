from __future__ import annotations

from aegisops.domain import InvestigationResult, MetricsSnapshot, RiskReport


class RiskEngine:
    def evaluate(
        self,
        *,
        during: MetricsSnapshot,
        investigation: InvestigationResult,
        reversibility: int,
        historical_success: int,
    ) -> RiskReport:
        severity = 25 if during.error_rate >= 0.30 or during.latency_ms >= 4000 else 12
        confidence_risk = max(0, round((1.0 - investigation.confidence) * 40))
        blast_radius = 7 if investigation.affected_service in {"checkout-api", "edge-gateway"} else 4
        reversibility_risk = max(0, round((100 - reversibility) / 5))
        history_risk = max(0, round((100 - historical_success) / 4))
        score = severity + confidence_risk + blast_radius + reversibility_risk + history_risk
        level = "low" if score < 30 else "moderate" if score < 50 else "high"
        approval_required = score >= 35 or during.error_rate > 0.25
        return RiskReport(
            score=score,
            level=level,
            approval_required=approval_required,
            factors={
                "severity": severity,
                "confidence": investigation.confidence,
                "blast_radius": blast_radius,
                "reversibility": reversibility,
                "historical_success": historical_success,
                "human_approval_policy": "required at score >= 35 or error rate > 25%",
            },
        )
