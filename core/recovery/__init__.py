from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class RecoverySnapshotType(StrEnum):
    """Recovery observation point."""

    BEFORE = "before"
    DURING = "during"
    AFTER = "after"


@dataclass
class RecoverySnapshot:
    """Point-in-time service health snapshot during recovery."""

    kind: RecoverySnapshotType | str
    latency: float = 0.0
    error_rate: float = 0.0
    throughput: float = 0.0
    dependency_health: float = 0.0

    def __post_init__(self) -> None:
        if isinstance(self.kind, str):
            self.kind = RecoverySnapshotType(self.kind)

    def to_dict(self) -> dict[str, float | str]:
        return {
            "kind": self.kind.value,
            "latency": self.latency,
            "error_rate": self.error_rate,
            "throughput": self.throughput,
            "dependency_health": self.dependency_health,
        }


@dataclass
class VerificationResult:
    """Outcome of comparing recovery-before and recovery-after snapshots."""

    recovered: bool
    metric_comparisons: dict[str, dict[str, float]]
    failed_checks: list[str]

    @classmethod
    def from_snapshots(
        cls,
        before: RecoverySnapshot,
        after: RecoverySnapshot,
    ) -> "VerificationResult":
        comparisons: dict[str, dict[str, float]] = {
            "latency": {"before": before.latency, "after": after.latency},
            "error_rate": {"before": before.error_rate, "after": after.error_rate},
            "throughput": {"before": before.throughput, "after": after.throughput},
            "dependency_health": {
                "before": before.dependency_health,
                "after": after.dependency_health,
            },
        }
        failed_checks: list[str] = []
        if after.latency > before.latency:
            failed_checks.append("latency")
        if after.error_rate > before.error_rate:
            failed_checks.append("error_rate")
        service_healthy = (
            after.latency <= before.latency
            and after.error_rate <= before.error_rate
            and after.dependency_health >= before.dependency_health
        )
        if after.throughput < before.throughput and not service_healthy:
            failed_checks.append("throughput")
        if after.dependency_health < before.dependency_health:
            failed_checks.append("dependency_health")

        recovered = service_healthy and not failed_checks
        return cls(
            recovered=recovered,
            metric_comparisons=comparisons,
            failed_checks=failed_checks,
        )


__all__ = ["RecoverySnapshot", "RecoverySnapshotType", "VerificationResult"]
