from __future__ import annotations

from aegisops.domain import EvidenceItem, MetricsSnapshot, ScenarioName


class EvidenceEngine:
    def generate(self, scenario: ScenarioName, metrics: MetricsSnapshot) -> list[EvidenceItem]:
        common = [
            EvidenceItem(
                "met_latency",
                "metrics",
                f"p99 latency rose to {metrics.latency_ms} ms",
                "request-path",
                "high" if metrics.latency_ms > 1000 else "medium",
                f"{metrics.latency_ms}ms",
            ),
            EvidenceItem(
                "met_errors",
                "metrics",
                f"error rate measured at {metrics.error_rate:.1%}",
                "request-path",
                "high" if metrics.error_rate > 0.10 else "low",
                f"{metrics.error_rate:.1%}",
            ),
        ]
        by_scenario = {
            ScenarioName.API_LATENCY_SPIKE: [
                EvidenceItem("log_db_timeout", "logs", "database connection timeout observed in checkout-api", "checkout-api", "high", "17 timeout entries"),
                EvidenceItem("dep_db_slow", "dependencies", "orders database response health degraded", "orders-db", "high", f"{metrics.database_health:.0%} health"),
            ],
            ScenarioName.DATABASE_FAILURE: [
                EvidenceItem("log_db_refused", "logs", "orders-db refused write connection", "orders-db", "critical", "connection refused"),
                EvidenceItem("dep_db_down", "dependencies", "database primary unavailable in simulation", "orders-db", "critical", f"{metrics.database_health:.0%} health"),
            ],
            ScenarioName.REDIS_OUTAGE: [
                EvidenceItem("log_redis_miss", "logs", "cache calls failing with simulated connection reset", "cache-redis", "high", "connection reset"),
                EvidenceItem("dep_redis_down", "dependencies", "Redis dependency health below recovery threshold", "cache-redis", "high", f"{metrics.redis_health:.0%} health"),
            ],
            ScenarioName.ELEVATED_ERROR_RATE: [
                EvidenceItem("log_edge_5xx", "logs", "edge gateway emitted deterministic 5xx burst", "edge-gateway", "high", "42% failures"),
                EvidenceItem("dep_retry_pressure", "dependencies", "retry pressure increased on request path", "edge-gateway", "medium", "retry budget exhausted"),
            ],
            ScenarioName.WORKER_DELAY: [
                EvidenceItem("log_worker_backlog", "logs", "settlement worker queue lag increased", "settlement-worker", "medium", f"{metrics.worker_lag_ms}ms lag"),
                EvidenceItem("dep_queue_depth", "dependencies", "queue depth exceeded normal operating range", "settlement-worker", "medium", "depth 2400"),
            ],
        }
        return common + by_scenario[scenario]
