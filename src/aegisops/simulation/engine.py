from __future__ import annotations

from dataclasses import dataclass

from aegisops.domain import MetricsSnapshot, ScenarioName


@dataclass(frozen=True)
class ScenarioDefinition:
    name: ScenarioName
    title: str
    target_service: str
    degraded: MetricsSnapshot


class SimulationEngine:
    """Deterministic local target; no external infrastructure is contacted."""

    baseline = MetricsSnapshot(
        label="before",
        latency_ms=120,
        error_rate=0.004,
        throughput_rpm=1180,
        database_health=1.0,
        redis_health=1.0,
        worker_lag_ms=45,
    )

    scenarios: dict[ScenarioName, ScenarioDefinition] = {
        ScenarioName.API_LATENCY_SPIKE: ScenarioDefinition(
            ScenarioName.API_LATENCY_SPIKE,
            "API latency spike",
            "checkout-api",
            MetricsSnapshot("during", 4800, 0.37, 410, 0.64, 0.96, 180),
        ),
        ScenarioName.DATABASE_FAILURE: ScenarioDefinition(
            ScenarioName.DATABASE_FAILURE,
            "Database failure",
            "orders-db",
            MetricsSnapshot("during", 2200, 0.29, 520, 0.18, 0.98, 340),
        ),
        ScenarioName.REDIS_OUTAGE: ScenarioDefinition(
            ScenarioName.REDIS_OUTAGE,
            "Redis outage",
            "cache-redis",
            MetricsSnapshot("during", 980, 0.18, 690, 0.97, 0.10, 760),
        ),
        ScenarioName.ELEVATED_ERROR_RATE: ScenarioDefinition(
            ScenarioName.ELEVATED_ERROR_RATE,
            "Elevated error rate",
            "edge-gateway",
            MetricsSnapshot("during", 390, 0.42, 740, 0.98, 0.94, 95),
        ),
        ScenarioName.WORKER_DELAY: ScenarioDefinition(
            ScenarioName.WORKER_DELAY,
            "Worker delay",
            "settlement-worker",
            MetricsSnapshot("during", 260, 0.021, 970, 0.98, 0.91, 4200),
        ),
    }

    def __init__(self) -> None:
        self.current = self.baseline
        self.active_scenario: ScenarioName | None = None

    def available_scenarios(self) -> list[dict[str, str]]:
        return [
            {
                "id": scenario.value,
                "title": definition.title,
                "target_service": definition.target_service,
            }
            for scenario, definition in self.scenarios.items()
        ]

    def reset(self) -> MetricsSnapshot:
        self.current = self.baseline
        self.active_scenario = None
        return self.current

    def inject(self, scenario: ScenarioName) -> MetricsSnapshot:
        definition = self.scenarios[scenario]
        self.current = definition.degraded
        self.active_scenario = scenario
        return self.current

    def remediate(self, scenario: ScenarioName) -> MetricsSnapshot:
        self.active_scenario = None
        self.current = MetricsSnapshot(
            label="after",
            latency_ms=138 if scenario is not ScenarioName.WORKER_DELAY else 126,
            error_rate=0.006,
            throughput_rpm=1145,
            database_health=0.99,
            redis_health=0.99,
            worker_lag_ms=70,
        )
        return self.current

    def state(self) -> dict[str, object]:
        return {
            "target_system": "local deterministic simulation",
            "system_status": "degraded" if self.current.degraded() else "healthy",
            "active_scenario": self.active_scenario.value if self.active_scenario else None,
            "metrics": self.current.as_dict(),
        }
