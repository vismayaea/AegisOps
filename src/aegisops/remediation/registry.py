from __future__ import annotations

from aegisops.domain import ActionExecution, RemediationAction, ScenarioName
from aegisops.simulation import SimulationEngine


class RemediationRegistry:
    def __init__(self, simulation: SimulationEngine) -> None:
        self.simulation = simulation
        self._actions = {
            ScenarioName.API_LATENCY_SPIKE: RemediationAction(
                "recycle_stale_connections",
                "Recycle simulated stale database connections for checkout-api",
                "checkout-api",
                88,
                90,
            ),
            ScenarioName.DATABASE_FAILURE: RemediationAction(
                "restart_simulated_database",
                "Restart the simulated orders database dependency",
                "orders-db",
                82,
                86,
            ),
            ScenarioName.REDIS_OUTAGE: RemediationAction(
                "restart_simulated_cache",
                "Restart the simulated Redis dependency",
                "cache-redis",
                86,
                88,
            ),
            ScenarioName.ELEVATED_ERROR_RATE: RemediationAction(
                "reduce_retry_pressure",
                "Reduce simulated retry pressure and route to healthy edge lane",
                "edge-gateway",
                76,
                82,
            ),
            ScenarioName.WORKER_DELAY: RemediationAction(
                "drain_batch_workers",
                "Drain delayed worker queue and clear simulated backlog",
                "settlement-worker",
                91,
                92,
            ),
        }

    def actions(self) -> list[RemediationAction]:
        return list(self._actions.values())

    def select_for(self, scenario: ScenarioName) -> RemediationAction:
        return self._actions[scenario]

    def execute(self, scenario: ScenarioName, action_id: str) -> ActionExecution:
        action = self.select_for(scenario)
        if action.id != action_id:
            raise ValueError("Only registered scenario remediation actions may execute")
        self.simulation.remediate(scenario)
        return ActionExecution(action.id, "executed", "Registered local remediation action completed")
