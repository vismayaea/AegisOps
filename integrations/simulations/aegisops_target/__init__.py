"""Deterministic AegisOps Incident Simulation Lab target.

This package is intentionally separated from the core platform and is designed
for local demos, testing, and evaluation. It is not production infrastructure.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from threading import Lock
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field


class ScenarioName(str, Enum):
    API_LATENCY_SPIKE = "API_LATENCY_SPIKE"
    HIGH_ERROR_RATE = "HIGH_ERROR_RATE"
    DATABASE_FAILURE = "DATABASE_FAILURE"
    REDIS_OUTAGE = "REDIS_OUTAGE"
    WORKER_DELAY = "WORKER_DELAY"


class FaultAction(str, Enum):
    CLEAR_LATENCY_FAULT = "clear_latency_fault"
    CLEAR_ERROR_RATE_FAULT = "clear_error_rate_fault"
    CLEAR_DATABASE_FAILURE = "clear_database_failure"
    CLEAR_REDIS_FAILURE = "clear_redis_failure"
    REDUCE_WORKER_DELAY = "reduce_worker_delay"


_SCENARIOS: dict[str, dict[str, Any]] = {
    ScenarioName.API_LATENCY_SPIKE.value: {
        "description": "Increase synthetic API latency to simulate a gateway or dependency delay.",
        "component": "target-api",
        "fault_params": {"latency_ms": 500, "error_rate": 0.02, "worker_delay_ms": 0, "db_failed": False, "redis_failed": False},
        "symptoms": ["p99 latency elevated", "dependency timeouts rising"],
        "recovery": "clear_latency_fault",
        "remediation": "clear_latency_fault",
    },
    ScenarioName.HIGH_ERROR_RATE.value: {
        "description": "Return a controlled percentage of failed requests.",
        "component": "target-api",
        "fault_params": {"latency_ms": 80, "error_rate": 0.25, "worker_delay_ms": 0, "db_failed": False, "redis_failed": False},
        "symptoms": ["error rate elevated", "user requests fail"],
        "recovery": "clear_error_rate_fault",
        "remediation": "clear_error_rate_fault",
    },
    ScenarioName.DATABASE_FAILURE.value: {
        "description": "Simulate database failures in a deterministic local mode.",
        "component": "postgresql",
        "fault_params": {"latency_ms": 120, "error_rate": 0.15, "worker_delay_ms": 0, "db_failed": True, "redis_failed": False},
        "symptoms": ["database dependency unavailable", "read/write operations fail"],
        "recovery": "clear_database_failure",
        "remediation": "clear_database_failure",
    },
    ScenarioName.REDIS_OUTAGE.value: {
        "description": "Simulate cache outage and queue access failures.",
        "component": "redis",
        "fault_params": {"latency_ms": 140, "error_rate": 0.2, "worker_delay_ms": 0, "db_failed": False, "redis_failed": True},
        "symptoms": ["redis dependency error", "jobs queue degraded"],
        "recovery": "clear_redis_failure",
        "remediation": "clear_redis_failure",
    },
    ScenarioName.WORKER_DELAY.value: {
        "description": "Simulate increased worker processing delay and backlog growth.",
        "component": "target-worker",
        "fault_params": {"latency_ms": 60, "error_rate": 0.05, "worker_delay_ms": 500, "db_failed": False, "redis_failed": False},
        "symptoms": ["queue lag", "job completion slower"],
        "recovery": "reduce_worker_delay",
        "remediation": "reduce_worker_delay",
    },
}


@dataclass
class SimulationTargetState:
    latency_ms: int = 0
    error_rate: float = 0.0
    worker_delay_ms: int = 0
    db_failed: bool = False
    redis_failed: bool = False
    request_count: int = 0
    error_count: int = 0
    jobs_processed: int = 0
    active_faults: list[str] = field(default_factory=list)

    def reset(self) -> None:
        self.latency_ms = 0
        self.error_rate = 0.0
        self.worker_delay_ms = 0
        self.db_failed = False
        self.redis_failed = False
        self.active_faults = []

    def is_healthy(self) -> bool:
        return not self.db_failed and not self.redis_failed and self.latency_ms == 0 and self.error_rate == 0.0 and self.worker_delay_ms == 0

    def to_metrics(self) -> dict[str, Any]:
        return {
            "request_count": self.request_count,
            "error_count": self.error_count,
            "latency_ms": self.latency_ms,
            "error_rate": self.error_rate,
            "worker_delay_ms": self.worker_delay_ms,
            "db_failed": self.db_failed,
            "redis_failed": self.redis_failed,
            "active_faults": self.active_faults,
            "jobs_processed": self.jobs_processed,
        }


class SimulationTarget:
    """Local, deterministic target for AegisOps incident simulation."""

    def __init__(self) -> None:
        self._state = SimulationTargetState()
        self._lock = Lock()

    @property
    def state(self) -> SimulationTargetState:
        return self._state

    def inject_fault(self, *, scenario: str | ScenarioName, **kwargs: Any) -> dict[str, Any]:
        scenario_name = scenario.value if isinstance(scenario, ScenarioName) else str(scenario)
        config = _SCENARIOS.get(scenario_name)
        if config is None:
            raise ValueError(f"Unsupported simulation scenario: {scenario_name}")
        fault_params = config["fault_params"]
        with self._lock:
            latency_ms = kwargs.get("latency_ms")
            error_rate = kwargs.get("error_rate")
            worker_delay_ms = kwargs.get("worker_delay_ms")
            db_failed = kwargs.get("db_failed")
            redis_failed = kwargs.get("redis_failed")

            self._state.latency_ms = int(latency_ms if latency_ms is not None else fault_params["latency_ms"])
            self._state.error_rate = float(error_rate if error_rate is not None else fault_params["error_rate"])
            self._state.worker_delay_ms = int(worker_delay_ms if worker_delay_ms is not None else fault_params["worker_delay_ms"])
            self._state.db_failed = bool(db_failed if db_failed is not None else fault_params["db_failed"])
            self._state.redis_failed = bool(redis_failed if redis_failed is not None else fault_params["redis_failed"])
            self._state.active_faults = [scenario_name]
        return {
            "scenario": scenario_name,
            "component": config["component"],
            "description": config["description"],
            "fault_params": self._state.to_metrics(),
            "active_faults": self._state.active_faults,
            "latency_ms": self._state.latency_ms,
            "error_rate": self._state.error_rate,
            "worker_delay_ms": self._state.worker_delay_ms,
            "db_failed": self._state.db_failed,
            "redis_failed": self._state.redis_failed,
            "ready": self._state.is_healthy() is False,
        }

    def clear_fault(self, *, fault_name: str) -> dict[str, Any]:
        mapping = {
            "clear_latency_fault": (lambda state: (setattr(state, "latency_ms", 0), setattr(state, "error_rate", 0.0)), "API_LATENCY_SPIKE"),
            "clear_error_rate_fault": (lambda state: (setattr(state, "error_rate", 0.0), setattr(state, "latency_ms", 0)), "HIGH_ERROR_RATE"),
            "clear_database_failure": (lambda state: (setattr(state, "db_failed", False), setattr(state, "latency_ms", 0), setattr(state, "error_rate", 0.0), setattr(state, "worker_delay_ms", 0)), "DATABASE_FAILURE"),
            "clear_redis_failure": (lambda state: (setattr(state, "redis_failed", False), setattr(state, "latency_ms", 0), setattr(state, "error_rate", 0.0), setattr(state, "worker_delay_ms", 0)), "REDIS_OUTAGE"),
            "reduce_worker_delay": (lambda state: (setattr(state, "worker_delay_ms", 0), setattr(state, "latency_ms", 0), setattr(state, "error_rate", 0.0)), "WORKER_DELAY"),
        }
        if fault_name not in mapping:
            raise ValueError(f"Unsupported fault clear request: {fault_name}")
        with self._lock:
            clear_fn, scenario_name = mapping[fault_name]
            clear_fn(self._state)
            self._state.active_faults = [
                name for name in self._state.active_faults if name != scenario_name
            ]
        return {
            "fault": fault_name,
            "latency_ms": self._state.latency_ms,
            "error_rate": self._state.error_rate,
            "worker_delay_ms": self._state.worker_delay_ms,
            "db_failed": self._state.db_failed,
            "redis_failed": self._state.redis_failed,
            "active_faults": self._state.active_faults,
            "state": self._state.to_metrics(),
            "ready": self._state.is_healthy(),
        }

    def health(self) -> dict[str, Any]:
        with self._lock:
            healthy = self._state.is_healthy()
            return {"status": "healthy" if healthy else "degraded", "healthy": healthy, "state": self._state.to_metrics()}

    def readiness(self) -> dict[str, Any]:
        with self._lock:
            ready = self._state.is_healthy()
            return {"status": "ready" if ready else "not_ready", "ready": ready, "state": self._state.to_metrics()}

    def metrics(self) -> dict[str, Any]:
        with self._lock:
            return {
                "request_count": self._state.request_count,
                "error_count": self._state.error_count,
                "latency_ms": self._state.latency_ms,
                "error_rate": self._state.error_rate,
                "worker_delay_ms": self._state.worker_delay_ms,
                "db_failed": self._state.db_failed,
                "redis_failed": self._state.redis_failed,
                "jobs_processed": self._state.jobs_processed,
                "active_faults": self._state.active_faults,
            }

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            metrics = self._state.to_metrics()
            healthy = self._state.is_healthy()
            return {
                "latency": float(self._state.latency_ms),
                "error_rate": float(self._state.error_rate),
                "throughput": float(self._state.jobs_processed),
                "dependency_health": 1.0 if healthy else 0.0,
                "db_failed": self._state.db_failed,
                "redis_failed": self._state.redis_failed,
                "worker_delay_ms": self._state.worker_delay_ms,
                "health": {"status": "healthy" if healthy else "degraded", "healthy": healthy, "state": metrics},
                "ready": {"status": "ready" if healthy else "not_ready", "ready": healthy, "state": metrics},
            }

    def record_request(self, *, ok: bool = True) -> None:
        with self._lock:
            self._state.request_count += 1
            if not ok:
                self._state.error_count += 1

    def process_job(self) -> dict[str, Any]:
        with self._lock:
            self._state.jobs_processed += 1
            return {"job_id": f"job-{self._state.jobs_processed}", "status": "processed", "worker_delay_ms": self._state.worker_delay_ms}


class FaultRequest(BaseModel):
    scenario: str = Field(..., description="Named simulation scenario to inject.")
    latency_ms: int | None = None
    error_rate: float | None = None
    worker_delay_ms: int | None = None
    db_failed: bool | None = None
    redis_failed: bool | None = None


class ClearFaultRequest(BaseModel):
    fault: str = Field(..., description="Registered simulation fault to clear.")


def create_target_app(*, target: SimulationTarget | None = None) -> FastAPI:
    app = FastAPI(title="AegisOps Incident Simulation Lab")
    sim_target = target or SimulationTarget()

    @app.get("/health")
    def health() -> dict[str, Any]:
        return sim_target.health()

    @app.get("/ready")
    def ready() -> dict[str, Any]:
        return sim_target.readiness()

    @app.get("/metrics")
    def metrics() -> dict[str, Any]:
        return sim_target.metrics()

    @app.get("/products")
    def products() -> list[dict[str, str]]:
        return [{"id": "p-100", "name": "widget"}, {"id": "p-101", "name": "gadget"}]

    @app.get("/products/{product_id}")
    def product_detail(product_id: str) -> dict[str, str]:
        return {"id": product_id, "name": "widget"}

    @app.post("/orders")
    def create_order() -> dict[str, Any]:
        sim_target.record_request(ok=True)
        return {"order_id": "o-1", "status": "created"}

    @app.get("/orders/{order_id}")
    def order_detail(order_id: str) -> dict[str, Any]:
        sim_target.record_request(ok=not sim_target.state.db_failed and not sim_target.state.redis_failed)
        return {"order_id": order_id, "status": "ok" if not sim_target.state.db_failed else "degraded"}

    @app.get("/jobs/{job_id}")
    def job_status(job_id: str) -> dict[str, Any]:
        sim_target.record_request(ok=not sim_target.state.redis_failed)
        return {"job_id": job_id, "status": "queued", "delay_ms": sim_target.state.worker_delay_ms}

    @app.post("/faults")
    def inject_fault(payload: FaultRequest) -> dict[str, Any]:
        return sim_target.inject_fault(
            scenario=payload.scenario,
            latency_ms=payload.latency_ms,
            error_rate=payload.error_rate,
            worker_delay_ms=payload.worker_delay_ms,
            db_failed=payload.db_failed,
            redis_failed=payload.redis_failed,
        )

    @app.post("/faults/clear")
    def clear_fault(payload: ClearFaultRequest) -> dict[str, Any]:
        return sim_target.clear_fault(fault_name=payload.fault)

    return app


__all__ = [
    "ClearFaultRequest",
    "FaultAction",
    "FaultRequest",
    "ScenarioName",
    "SimulationTarget",
    "SimulationTargetState",
    "_SCENARIOS",
    "create_target_app",
]
