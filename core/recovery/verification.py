from __future__ import annotations

from dataclasses import dataclass, field

from core.recovery import RecoverySnapshot, VerificationResult


@dataclass
class RecoveryVerificationResult:
    """Structured comparison of before, during, and after health snapshots."""

    recovered: bool = False
    confidence: float = 0.0
    metric_comparisons: dict[str, dict[str, float]] = field(default_factory=dict)
    failed_checks: list[str] = field(default_factory=list)
    verification_summary: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "recovered": self.recovered,
            "confidence": self.confidence,
            "metric_comparisons": self.metric_comparisons,
            "failed_checks": self.failed_checks,
            "verification_summary": self.verification_summary,
        }


def verify_recovery(
    *,
    before: RecoverySnapshot | None,
    during: RecoverySnapshot | None,
    after: RecoverySnapshot | None,
) -> RecoveryVerificationResult:
    """Compare the baseline and post-remediation signals to determine whether recovery holds."""
    if before is None or after is None:
        return RecoveryVerificationResult(
            recovered=False,
            confidence=0.0,
            metric_comparisons={},
            failed_checks=["missing_snapshot"],
            verification_summary="Before and after snapshots are required for recovery verification.",
        )

    result = VerificationResult.from_snapshots(before, after)
    metric_comparisons = result.metric_comparisons
    failed_checks = list(result.failed_checks)

    if during is not None:
        metric_comparisons = {
            "latency": {"before": before.latency, "during": during.latency, "after": after.latency},
            "error_rate": {"before": before.error_rate, "during": during.error_rate, "after": after.error_rate},
            "throughput": {"before": before.throughput, "during": during.throughput, "after": after.throughput},
            "dependency_health": {"before": before.dependency_health, "during": during.dependency_health, "after": after.dependency_health},
        }

    if result.recovered:
        summary = "Recovery verified: service metrics returned to baseline or better after the remediation."
        confidence = 0.9
    else:
        summary = "Recovery verification failed: at least one required metric remained degraded after remediation."
        confidence = 0.2

    return RecoveryVerificationResult(
        recovered=result.recovered,
        confidence=confidence,
        metric_comparisons=metric_comparisons,
        failed_checks=failed_checks,
        verification_summary=summary,
    )


__all__ = ["RecoveryVerificationResult", "verify_recovery"]
