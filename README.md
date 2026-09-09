# AegisOps

## Autonomous AI Incident Response & SRE Platform

AegisOps is the product identity for this repository: an incident-response control plane that turns operational evidence into investigation, risk assessment, remediation planning, and safe recovery verification.

This codebase preserves the historical OpenSRE upstream lineage under the Apache-2.0 license. The original OpenSRE runtime remains intact as the technical foundation, while AegisOps is the public-facing product layer and operational workflow designed around autonomous incident handling.

> The repository is not a fake production environment and does not claim autonomous control of live infrastructure. The current implementation includes a deterministic local simulation lab for validating incident lifecycle behavior without connecting to real production systems.

---

## Why AegisOps?

Production incidents are noisy, fragmented, and expensive to triage. Teams usually piece together evidence from logs, metrics, traces, alerts, runbooks, and chat threads after the damage is already underway.

AegisOps addresses that gap by combining:

- structured evidence collection and correlation
- investigation and root-cause analysis
- risk-based approval gates
- remediation planning and controlled execution
- recovery verification and incident replay
- postmortem generation grounded in recorded lifecycle events

The project is intentionally built as a grounded operational workflow, not as a free-form agent that blindly executes actions in real environments.

---

## What this repository contains

This repository integrates a local runtime, an incident lifecycle model, and a simulation boundary for validation:

- incident creation, evidence intake, and decision tracing
- investigation and root-cause analysis services
- risk scoring and approval gating
- remediation planning and execution adapters
- recovery verification and replay/postmortem outputs
- a deterministic local incident simulation target for exercising the full lifecycle safely

The runtime still supports the historical `opensre` CLI and related local tooling, but the product story and user-facing identity are now AegisOps.

---

## Quick start

From the repository root:

```bash
uv sync
uv run pytest tests/core/incident -q
```

You can also run the project entrypoint directly:

```bash
uv run python main.py
```

For the existing local CLI workflow, the repository still exposes the historical command surface:

```bash
uv run opensre --help
uv run opensre setup
uv run opensre ask "why is checkout-api slow?"
```

These commands are part of the underlying execution stack; the public product narrative is AegisOps, while the underlying implementation retains provenance and compatibility.

---

## Simulation and validation

AegisOps includes a focused incident simulation lab for validating the lifecycle without relying on a real target environment.

The simulation exercises:

1. fault injection and observability degradation
2. incident investigation and RCA flow
3. risk decisioning and approval gating
4. remediation planning and controlled execution
5. recovery verification
6. incident trace replay and postmortem output

This is a safe validation boundary for engineering and regression testing, not a production deployment target.

---

## Repository provenance

This project originated as an Apache-2.0 licensed OpenSRE codebase and remains faithful to that upstream lineage. AegisOps is the clear product identity for the operational layer built on top of that foundation.

We do not erase, conceal, or misrepresent the original project history. The legal provenance and attribution remain intact.

---

## Project status

Current focus:

- operational incident lifecycle integrity
- evidence-backed investigation and RCA
- controlled remediation and safe verification
- deterministic simulation for validation
- user-facing product presentation without breaking upstream attribution

---

## License

This project is licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE) for details.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md), [SETUP.md](SETUP.md), and [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) for development setup and repository workflows.

## Security

AegisOps is designed with production environments in mind: structured and auditable LLM prompts, local transcript handling by default, and no silent bulk export of raw logs. See **[SECURITY.md](SECURITY.md)** for responsible disclosure.

---

## Telemetry

PostHog (product analytics) and Sentry (errors) are **opt-out**. Quick disable:

```bash
export OPENSRE_NO_TELEMETRY=1
```

**[Full matrix, DSN override, and local event logging → docs/DEVELOPMENT.md](docs/DEVELOPMENT.md#telemetry-and-privacy)**

---

## License

Apache 2.0 — see [LICENSE](LICENSE).

## Citations

<sup>1</sup> https://arxiv.org/abs/2310.06770
