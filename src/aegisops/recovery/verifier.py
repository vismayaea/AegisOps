from __future__ import annotations

from aegisops.domain import MetricsSnapshot, RecoveryReport


class RecoveryVerifier:
    def verify(self, before: MetricsSnapshot, during: MetricsSnapshot, after: MetricsSnapshot) -> RecoveryReport:
        criteria = {
            "latency_near_baseline": after.latency_ms <= before.latency_ms * 1.5,
            "error_rate_near_baseline": after.error_rate <= 0.01,
            "dependency_health_restored": after.database_health >= 0.95 and after.redis_health >= 0.95,
            "worker_lag_acceptable": after.worker_lag_ms <= 250,
            "meaningful_improvement": after.latency_ms < during.latency_ms and after.error_rate < during.error_rate,
        }
        return RecoveryReport(all(criteria.values()), criteria, before, during, after)
