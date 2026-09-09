from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.recovery import RecoverySnapshot
from integrations.simulations.aegisops_target import SimulationTarget


@dataclass
class SimulationTargetAdapter:
    """Controlled adapter between AegisOps remediation and the simulation target."""

    target: SimulationTarget | None = None

    def __post_init__(self) -> None:
        if self.target is None:
            from integrations.simulations.aegisops_target import SimulationTarget as _SimulationTarget

            self.target = _SimulationTarget()

    def health(self) -> dict[str, Any]:
        return self.target.health()

    def readiness(self) -> dict[str, Any]:
        return self.target.readiness()

    def metrics(self) -> dict[str, Any]:
        return self.target.metrics()

    def inject_fault(self, *, scenario: str, **kwargs: Any) -> dict[str, Any]:
        return self.target.inject_fault(scenario=scenario, **kwargs)

    def clear_fault(self, *, fault_name: str) -> dict[str, Any]:
        return self.target.clear_fault(fault_name=fault_name)

    def snapshot(self, *, kind: str = "during") -> RecoverySnapshot:
        data = self.target.snapshot()
        return RecoverySnapshot(
            kind=kind,
            latency=float(data.get("latency", 0.0)),
            error_rate=float(data.get("error_rate", 0.0)),
            throughput=float(data.get("throughput", 0.0)),
            dependency_health=float(data.get("dependency_health", 0.0)),
        )


__all__ = ["SimulationTargetAdapter"]
