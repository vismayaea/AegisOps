# AegisOps Incident Simulation Lab

This is a deterministic local incident simulation environment used by AegisOps for development, testing, demonstrations, and evaluation. It is not a production service.

## Purpose

The simulation lab intentionally models a small e-commerce/order-processing system with a public API, a worker, and dependency faults. It is designed to exercise the incident lifecycle:

NORMAL
↓
FAULT INJECTION
↓
INCIDENT DETECTION
↓
EVIDENCE COLLECTION
↓
AI INVESTIGATION
↓
ROOT CAUSE ANALYSIS
↓
RISK ASSESSMENT
↓
REMEDIATION
↓
RECOVERY VERIFICATION
↓
INCIDENT REPLAY / POSTMORTEM

## Services

- aegisops-target-api: public HTTP surface for products, orders, jobs, health, readiness, and controlled faults.
- aegisops-target-worker: deterministic job processing with queue delay simulation.
- PostgreSQL: simulated database dependency state.
- Redis: simulated cache/queue dependency state.

## Local usage

1. Start the simulation stack:
   ```bash
   docker compose -f simulation/docker-compose.yml up -d
   ```
2. Verify health: `curl http://localhost:8088/health`
3. Verify readiness: `curl http://localhost:8088/ready`
4. Inject a scenario:
   ```bash
   curl -X POST http://localhost:8088/faults -H 'Content-Type: application/json' -d '{"scenario":"API_LATENCY_SPIKE"}'
   ```
5. Clear a fault through the registered remediation action:
   ```bash
   curl -X POST http://localhost:8088/faults/clear -H 'Content-Type: application/json' -d '{"fault":"clear_latency_fault"}'
   ```

## Deterministic scenarios

- API_LATENCY_SPIKE
- HIGH_ERROR_RATE
- DATABASE_FAILURE
- REDIS_OUTAGE
- WORKER_DELAY

The fault state is intentionally local and deterministic. No arbitrary command execution is exposed.
