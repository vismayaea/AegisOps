# AegisOps

Autonomous AI Incident Response & SRE Platform.

AegisOps is a local incident-response control plane for demonstrating how an SRE platform can detect a simulated incident, collect evidence, identify a root cause, evaluate remediation risk, require approval when policy says so, execute only registered actions, verify recovery, resolve the incident, and preserve a decision trace.

## Problem

Incident response often spreads across logs, metrics, dependency health, chat, and runbooks. AegisOps shows one deterministic control-plane workflow that keeps evidence, decisions, approvals, remediation, and recovery checks together.

## Architecture

The project is an independently implemented Python/FastAPI application:

- `aegisops/simulation`: deterministic local target state and fault injection.
- `aegisops/evidence`: structured synthetic logs, metrics, and dependency evidence.
- `aegisops/investigation`: transparent hypothesis scoring and RCA selection.
- `aegisops/risk`: deterministic risk scoring and approval policy.
- `aegisops/remediation`: registry of allowed local simulation actions.
- `aegisops/recovery`: baseline/degraded/recovered verification.
- `aegisops/trace`: structured incident decision audit events.
- `aegisops/postmortem`: deterministic postmortem generation.
- `aegisops/api`: HTTP API and static Control Center UI.

## Incident Lifecycle

The local demo follows:

`healthy -> fault injected -> degraded -> evidence collected -> investigation -> RCA -> risk -> approval -> remediation -> recovery verification -> resolved -> postmortem`

## Simulation Lab

The simulation is safe and local. It does not connect to production systems. Supported deterministic scenarios:

- API latency spike
- database failure
- Redis outage
- elevated error rate
- worker delay

Healthy baseline metrics are approximately 120 ms latency and 0.4% error rate. The API latency scenario degrades to 4800 ms latency and 37% error rate.

## Investigation

The investigation engine does not claim magical autonomous reasoning. It consumes structured evidence, scores hypotheses, chooses the strongest explanation, and records supporting evidence IDs. Optional LLM integrations can be added later, but the core demo does not require one.

## Risk Engine

Risk is deterministic and based on severity, RCA confidence, blast radius, action reversibility, and historical success. Actions with score >= 35 or error rate above 25% require human approval.

## Controlled Remediation

AegisOps never executes arbitrary AI-generated commands. The remediation layer exposes only registered local actions such as recycling simulated stale connections, restarting a simulated dependency, reducing retry pressure, draining workers, or clearing a fault.

## Recovery Verification

Recovery compares before, during, and after metrics. An incident is marked resolved only when latency, error rate, dependency health, worker lag, and meaningful-improvement criteria all pass.

## Incident Trace

Every major transition records a structured trace event: detection, evidence collection, investigation, RCA, risk, approval, selected action, executed action, recovery check, and resolution.

## Postmortem Generation

The postmortem endpoint builds a deterministic report from the recorded incident object and trace. It includes impact, timeline, evidence, root cause, remediation, recovery, decision trace, and follow-up lessons.

## Local Setup

```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install -e ".[dev]"
```

If you use `uv`:

```bash
uv sync --extra dev
```

## Run The Demo

```bash
python -m aegisops.api.app
```

Then open `http://127.0.0.1:8000`.

## Run Tests

```bash
python -m pytest
```

## Limitations

AegisOps is a deterministic local simulation. It does not control real production infrastructure, does not run shell commands as remediation, and does not require an external LLM for reasoning.
