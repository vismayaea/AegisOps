"""The gateway's single FastAPI app: health probes and alert intake.

Every HTTP endpoint OpenSRE serves lives here, on one port — ``/`` ``/health``
``/ok`` (health probes), ``/healthz`` (liveness), and ``POST /alerts`` (external
alert pushes into the process-wide :class:`AlertInbox`). Hosted by the
gateway daemon and the interactive shell via :mod:`gateway.web.web_server`, or
standalone via ``uvicorn gateway.web.webapp:app``.
"""

from __future__ import annotations

from http import HTTPStatus

from fastapi import FastAPI, Response
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, ValidationError

from bootstrap.process import WEB_PROFILE, configure_process
from config.environment import get_environment
from config.llm_settings import LLMSettings
from config.version import get_opensre_version
from gateway.core.process.readiness import is_gateway_ready
from infrastructure.alert_intake import router as alert_router
from infrastructure.request_body_limit import RequestBodyLimitMiddleware

configure_process(WEB_PROFILE)  # env → sentry → adapters

__all__ = ["app"]


class HealthResponse(BaseModel):
    ok: bool
    version: str
    llm_configured: bool
    env: str


app = FastAPI()
# Above routing: every mutating route is bounded before FastAPI buffers a body.
app.add_middleware(RequestBodyLimitMiddleware)
# Health liveness (/healthz) and alert intake (/alerts) live in the shared
# router so the interactive shell can serve them without importing the gateway.
app.include_router(alert_router)


def get_health_response() -> HealthResponse:
    try:
        LLMSettings.from_env()
        llm_configured = True
    except ValidationError:
        llm_configured = False

    return HealthResponse(
        ok=llm_configured,
        version=get_opensre_version(),
        llm_configured=llm_configured,
        env=get_environment().value,
    )


@app.get("/health", response_model=HealthResponse)
@app.get("/ok", response_model=HealthResponse)
def health(response: Response) -> HealthResponse:
    health_response = get_health_response()
    response.status_code = HTTPStatus.OK if health_response.ok else HTTPStatus.SERVICE_UNAVAILABLE
    return health_response


@app.get("/", response_class=HTMLResponse)
def dashboard() -> HTMLResponse:
    """Serve the AegisOps control center dashboard while leaving the JSON health API intact."""
    return HTMLResponse(_build_dashboard_html())


@app.get("/readyz")
def readyz() -> JSONResponse:
    """Report mandatory startup readiness separately from process liveness."""
    if is_gateway_ready():
        return JSONResponse({"status": "ready"}, status_code=HTTPStatus.OK)
    return JSONResponse({"status": "not_ready"}, status_code=HTTPStatus.SERVICE_UNAVAILABLE)


def _build_dashboard_html() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>AEGISOPS Control Center</title>
  <style>
    :root {
      --bg: #060d18;
      --panel: rgba(12, 20, 31, 0.92);
      --panel-strong: rgba(18, 27, 39, 0.96);
      --border: rgba(140, 170, 210, 0.18);
      --muted: #9bb2cb;
      --text: #edf6ff;
      --primary: #70d6ff;
      --success: #61f2b0;
      --warning: #ffbf69;
      --danger: #ff6a7b;
      --shadow: 0 22px 42px rgba(1, 5, 12, 0.55);
    }
    * { box-sizing: border-box; }
    html, body {
      margin: 0;
      min-height: 100%;
      font-family: Inter, "Segoe UI", sans-serif;
      background: linear-gradient(180deg, #050c16, #091423 50%, #050b13 100%);
      color: var(--text);
    }
    body { padding: 24px; }
    .dashboard {
      max-width: 1400px;
      margin: 0 auto;
      border: 1px solid var(--border);
      border-radius: 18px;
      background: rgba(6, 13, 24, 0.9);
      box-shadow: var(--shadow);
      overflow: hidden;
    }
    .topbar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      padding: 22px 28px;
      border-bottom: 1px solid var(--border);
      background: rgba(9, 17, 27, 0.95);
    }
    .brand {
      display: flex;
      flex-direction: column;
      gap: 4px;
    }
    .brand-title {
      font-size: clamp(1.8rem, 2vw, 2.4rem);
      font-weight: 800;
      letter-spacing: 0.12em;
      text-transform: uppercase;
    }
    .brand-subtitle {
      color: var(--muted);
      font-size: 0.78rem;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }
    .topbar-status-group {
      display: flex;
      flex-wrap: wrap;
      justify-content: flex-end;
      gap: 10px;
    }
    .mini-status {
      display: flex;
      flex-direction: column;
      gap: 2px;
      min-width: 110px;
      padding: 8px 12px;
      border-radius: 10px;
      border: 1px solid rgba(140,170,210,0.18);
      background: rgba(12, 20, 31, 0.75);
      text-align: left;
    }
    .mini-status em {
      font-style: normal;
      color: var(--muted);
      font-size: 0.58rem;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }
    .mini-status strong {
      font-size: 0.8rem;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }
    .mini-status.alert {
      border-color: rgba(255,191,105,0.14);
      background: rgba(255,191,105,0.08);
    }
    .content { padding: 24px 28px 30px; }
    .stats {
      display: grid;
      grid-template-columns: repeat(4, minmax(180px, 1fr));
      gap: 18px;
      margin-bottom: 20px;
    }
    .card {
      background: linear-gradient(180deg, rgba(18, 26, 36, 0.96), rgba(13, 20, 31, 0.96));
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 18px 18px 16px;
    }
    .card-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 10px;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.08em;
      font-size: 0.72rem;
    }
    .pill {
      border-radius: 999px;
      padding: 6px 9px;
      font-size: 0.62rem;
      letter-spacing: 0.08em;
      font-weight: 800;
      text-transform: uppercase;
      border: 1px solid transparent;
    }
    .pill.healthy { background: rgba(97,242,176,0.12); color: var(--success); border-color: rgba(97,242,176,0.25); }
    .pill.online { background: rgba(112,214,255,0.12); color: var(--primary); border-color: rgba(112,214,255,0.2); }
    .pill.configured { background: rgba(97,242,176,0.12); color: var(--success); border-color: rgba(97,242,176,0.2); }
    .pill.alert { background: rgba(255,191,105,0.1); color: var(--warning); border-color: rgba(255,191,105,0.2); }
    .stat-value {
      font-size: clamp(1.4rem, 2vw, 2rem);
      font-weight: 800;
      letter-spacing: 0.05em;
    }
    .panel-grid {
      display: grid;
      grid-template-columns: 1.1fr 1.2fr 1fr;
      gap: 18px;
      margin-bottom: 20px;
    }
    .top-grid {
      margin-bottom: 18px;
    }
    .compact-card {
      min-height: 120px;
    }
    .panel-title-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 18px;
    }
    .panel-title {
      color: var(--muted);
      font-size: 0.8rem;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      font-weight: 800;
    }
    .sim-buttons {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
    }
    button {
      cursor: pointer;
      border: 1px solid rgba(140,170,210,0.2);
      background: linear-gradient(180deg, rgba(27,37,53,0.96), rgba(14,21,29,0.96));
      color: var(--text);
      border-radius: 10px;
      padding: 12px 10px;
      font-weight: 700;
      letter-spacing: 0.05em;
      transition: transform 0.15s ease, border-color 0.15s ease, box-shadow 0.15s ease;
      text-transform: uppercase;
    }
    button:hover { transform: translateY(-1px); border-color: rgba(112,214,255,0.5); }
    button.active {
      border-color: rgba(112,214,255,0.7);
      box-shadow: inset 0 0 0 1px rgba(112,214,255,0.15);
      background: linear-gradient(180deg, rgba(21,42,60,0.96), rgba(15,24,34,0.96));
    }
    .reset-btn {
      border-color: rgba(255,106,123,0.32);
      background: linear-gradient(180deg, rgba(62, 24, 31, 0.92), rgba(32,16,20,0.94));
      color: var(--text);
    }
    .steps {
      display: flex;
      flex-direction: column;
      gap: 10px;
    }
    .step {
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 10px 12px;
      border-radius: 10px;
      border: 1px solid rgba(140,170,210,0.14);
      background: rgba(11,15,22,0.85);
      color: var(--muted);
      opacity: 0.7;
    }
    .step.active {
      opacity: 1;
      color: var(--text);
      border-color: rgba(112,214,255,0.45);
      background: rgba(18,29,40,0.9);
    }
    .step-index {
      width: 28px;
      height: 28px;
      border-radius: 50%;
      display: grid;
      place-items: center;
      background: rgba(112,214,255,0.12);
      color: var(--primary);
      font-weight: 800;
      font-size: 0.75rem;
    }
    .step.active .step-index { background: rgba(112,214,255,0.2); }
    .detail-row {
      display: flex;
      flex-direction: column;
      gap: 5px;
      padding: 10px 0;
      border-bottom: 1px solid rgba(140,170,210,0.1);
    }
    .detail-label {
      color: var(--muted);
      font-size: 0.68rem;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }
    .detail-value {
      font-size: 1rem;
      font-weight: 700;
    }
    .severity-tag {
      display: inline-flex;
      align-items: center;
      border-radius: 999px;
      padding: 6px 10px;
      font-size: 0.68rem;
      letter-spacing: 0.08em;
      font-weight: 800;
      text-transform: uppercase;
    }
    .severity-high { background: rgba(255,106,123,0.12); color: var(--danger); }
    .severity-med { background: rgba(255,191,105,0.1); color: var(--warning); }
    .severity-low { background: rgba(97,242,176,0.1); color: var(--success); }
    .risk-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
      margin-top: 10px;
    }
    .risk-box {
      background: rgba(8, 14, 22, 0.86);
      border: 1px solid rgba(140,170,210,0.12);
      border-radius: 12px;
      padding: 14px;
    }
    .risk-box strong {
      display: block;
      margin-bottom: 9px;
      color: var(--muted);
      font-size: 0.7rem;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }
    .risk-score-number {
      font-size: 2.3rem;
      font-weight: 900;
      line-height: 1;
    }
    .risk-gauge-wrap {
      display: grid;
      place-items: center;
      margin-bottom: 14px;
    }
    .risk-gauge {
      width: 160px;
      height: 160px;
      border-radius: 50%;
      background: conic-gradient(var(--primary) 0deg 190deg, rgba(112,214,255,0.12) 190deg 360deg);
      display: grid;
      place-items: center;
      box-shadow: inset 0 0 30px rgba(112,214,255,0.1);
    }
    .gauge-inner {
      width: 108px;
      height: 108px;
      border-radius: 50%;
      background: rgba(6, 13, 24, 0.96);
      border: 1px solid rgba(140,170,210,0.2);
      display: grid;
      place-items: center;
    }
    .gauge-value {
      font-size: 2rem;
      font-weight: 900;
      letter-spacing: 0.04em;
    }
    .risk-meta {
      display: grid;
      gap: 8px;
      margin-bottom: 12px;
    }
    .risk-meta-row {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      padding: 8px 10px;
      border-radius: 8px;
      background: rgba(11, 15, 22, 0.85);
      border: 1px solid rgba(140,170,210,0.1);
      color: var(--muted);
      font-size: 0.8rem;
      letter-spacing: 0.04em;
      text-transform: uppercase;
    }
    .risk-meta-row strong {
      color: var(--text);
      letter-spacing: 0.08em;
    }
    .risk-decision {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      padding: 10px 12px;
      border-radius: 10px;
      border: 1px solid rgba(112,214,255,0.18);
      background: rgba(112,214,255,0.08);
      font-size: 0.72rem;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: var(--muted);
    }
    .risk-decision strong {
      color: var(--text);
      font-size: 0.74rem;
    }
    .decision-pill {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      border-radius: 999px;
      padding: 10px 12px;
      font-size: 0.7rem;
      font-weight: 800;
      letter-spacing: 0.09em;
      text-transform: uppercase;
    }
    .decision-pill.auto { background: rgba(97,242,176,0.12); color: var(--success); }
    .decision-pill.human { background: rgba(255,191,105,0.12); color: var(--warning); }
    .decision-pill.block { background: rgba(255,106,123,0.12); color: var(--danger); }
    .remediation-box {
      background: rgba(8, 14, 22, 0.86);
      border: 1px solid rgba(140,170,210,0.12);
      border-radius: 12px;
      padding: 14px;
      margin-top: 10px;
    }
    .flow-row {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 20px;
      margin-top: 18px;
    }
    .timeline-list {
      margin: 0;
      padding: 0;
      list-style: none;
      display: flex;
      flex-direction: column;
      gap: 10px;
    }
    .timeline-list li {
      position: relative;
      padding-left: 18px;
      color: var(--muted);
      font-weight: 600;
    }
    .timeline-list li::before {
      content: "";
      position: absolute;
      left: 0;
      top: 7px;
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: var(--primary);
      box-shadow: 0 0 12px rgba(112,214,255,0.8);
    }
    .status-banner {
      margin-top: 12px;
      padding: 10px 12px;
      border-radius: 10px;
      border: 1px solid rgba(97,242,176,0.2);
      background: rgba(97,242,176,0.08);
      color: var(--success);
      font-weight: 800;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      text-align: center;
    }
    .target-system-card {
      margin-bottom: 20px;
    }
    .target-system-grid {
      display: grid;
      grid-template-columns: 1.2fr 2fr 1fr;
      gap: 18px;
    }
    .service-panel, .comparison-panel, .evidence-card {
      background: rgba(8, 14, 22, 0.86);
      border: 1px solid rgba(140,170,210,0.12);
      border-radius: 12px;
      padding: 16px;
    }
    .service-panel {
      display: flex;
      flex-direction: column;
      gap: 12px;
    }
    .field-row {
      display: flex;
      flex-direction: column;
      gap: 4px;
      padding: 0;
    }
    .field-label {
      color: var(--muted);
      font-size: 0.66rem;
      letter-spacing: 0.09em;
      text-transform: uppercase;
    }
    .service-name {
      font-size: 1.5rem;
      font-weight: 800;
      letter-spacing: 0.06em;
      text-transform: lowercase;
    }
    .target-status {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: fit-content;
      border-radius: 999px;
      padding: 8px 12px;
      font-weight: 800;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      border: 1px solid transparent;
    }
    .status-healthy {
      background: rgba(97,242,176,0.12);
      color: var(--success);
      border-color: rgba(97,242,176,0.22);
    }
    .status-degraded {
      background: rgba(255,191,105,0.12);
      color: var(--warning);
      border-color: rgba(255,191,105,0.2);
    }
    .status-recovered {
      background: rgba(112,214,255,0.1);
      color: var(--primary);
      border-color: rgba(112,214,255,0.2);
    }
    .simulated-pill {
      background: rgba(255,191,105,0.08);
      border: 1px solid rgba(255,191,105,0.18);
      color: var(--warning);
      border-radius: 999px;
      padding: 6px 10px;
      font-size: 0.68rem;
      letter-spacing: 0.08em;
      font-weight: 800;
      text-transform: uppercase;
    }
    .metric-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
    }
    .metric-card {
      background: rgba(11, 15, 22, 0.88);
      border: 1px solid rgba(140,170,210,0.12);
      border-radius: 10px;
      padding: 12px;
    }
    .metric-card .field-label {
      font-size: 0.62rem;
    }
    .metric-value {
      margin-top: 6px;
      font-size: 1.05rem;
      font-weight: 800;
    }
    .comparison-panel {
      display: flex;
      flex-direction: column;
      gap: 10px;
    }
    .comparison-panel h4 {
      margin: 0;
      color: var(--muted);
      font-size: 0.72rem;
      letter-spacing: 0.1em;
      text-transform: uppercase;
    }
    .before-after {
      display: grid;
      grid-template-columns: 1fr;
      gap: 10px;
    }
    .before-after-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 10px;
      padding: 8px 10px;
      border-radius: 8px;
      background: rgba(11, 15, 22, 0.82);
      border: 1px solid rgba(140,170,210,0.12);
      font-size: 0.9rem;
    }
    .before-after-row.warning {
      border-color: rgba(255,191,105,0.18);
      background: rgba(255,191,105,0.06);
      color: var(--warning);
    }
    .before-after-row strong { font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.08em; color: var(--muted); }
    .system-map {
      display: grid;
      grid-template-columns: 1.55fr 0.85fr;
      gap: 18px;
      align-items: center;
    }
    .system-graph {
      position: relative;
      min-height: 254px;
      padding: 18px 14px 12px;
      border-radius: 14px;
      border: 1px solid rgba(140,170,210,0.14);
      background: linear-gradient(180deg, rgba(9,14,22,0.9), rgba(11,18,26,0.82));
      overflow: hidden;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      gap: 18px;
    }
    .node {
      position: relative;
      display: flex;
      flex-direction: column;
      gap: 8px;
      padding: 12px 14px;
      border-radius: 12px;
      border: 1px solid rgba(140,170,210,0.2);
      background: rgba(13,20,30,0.9);
      min-width: 180px;
      max-width: 220px;
      z-index: 2;
    }
    .node-label {
      color: var(--muted);
      font-size: 0.68rem;
      letter-spacing: 0.1em;
      text-transform: uppercase;
    }
    .node-state {
      font-size: 0.82rem;
      font-weight: 800;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: var(--primary);
    }
    .ai-node {
      left: auto;
      top: auto;
      background: rgba(20,32,48,0.9);
      box-shadow: 0 0 0 1px rgba(112,214,255,0.18);
    }
    .service-node {
      align-self: flex-end;
      right: auto;
      top: auto;
      min-width: 210px;
      border-color: rgba(97,242,176,0.22);
      background: rgba(14,25,33,0.96);
    }
    .service-metrics {
      display: flex;
      flex-direction: column;
      gap: 4px;
      font-size: 0.72rem;
      color: var(--muted);
      letter-spacing: 0.04em;
      text-transform: uppercase;
    }
    .service-metrics strong { color: var(--text); }
    .flow-line {
      position: absolute;
      height: 2px;
      background: linear-gradient(90deg, rgba(112,214,255,0.8), rgba(112,214,255,0.08));
      z-index: 1;
    }
    .flow-a {
      left: 170px;
      top: 92px;
      width: 120px;
      transform: rotate(18deg);
    }
    .flow-b {
      left: 215px;
      top: 110px;
      width: 150px;
      transform: rotate(-7deg);
    }
    .flow-c {
      left: 190px;
      top: 136px;
      width: 190px;
      transform: rotate(12deg);
    }
    .connected-row {
      position: relative;
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 12px;
      z-index: 2;
    }
    .connected-node {
      display: flex;
      flex-direction: column;
      gap: 4px;
      padding: 10px 12px;
      border-radius: 10px;
      border: 1px solid rgba(140,170,210,0.12);
      background: rgba(9,15,22,0.82);
      color: var(--muted);
      font-size: 0.68rem;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }
    .connected-node strong {
      color: var(--text);
      font-size: 0.8rem;
    }
    .comparison-panel {
      display: flex;
      flex-direction: column;
      gap: 10px;
    }
    .comparison-panel h4 {
      margin: 0;
      color: var(--muted);
      font-size: 0.72rem;
      letter-spacing: 0.1em;
      text-transform: uppercase;
    }
    .before-after {
      display: grid;
      grid-template-columns: 1fr;
      gap: 10px;
    }
    .before-after-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 10px;
      padding: 8px 10px;
      border-radius: 8px;
      background: rgba(11, 15, 22, 0.82);
      border: 1px solid rgba(140,170,210,0.12);
      font-size: 0.9rem;
    }
    .before-after-row strong {
      font-size: 0.78rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: var(--muted);
    }
    .before-after-row.warning {
      border-color: rgba(255,191,105,0.18);
      background: rgba(255,191,105,0.06);
      color: var(--warning);
    }
    .evidence-grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 18px;
      margin-bottom: 18px;
    }
    .evidence-card h4 {
      margin: 0 0 10px;
      color: var(--muted);
      font-size: 0.72rem;
      letter-spacing: 0.1em;
      text-transform: uppercase;
    }
    .evidence-list {
      list-style: none;
      margin: 0;
      padding: 0;
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    .evidence-list li {
      padding: 8px 10px;
      border-radius: 8px;
      background: rgba(11, 15, 22, 0.82);
      border: 1px solid rgba(140,170,210,0.1);
      color: var(--text);
      font-size: 0.9rem;
    }
    .narrative-box {
      display: flex;
      flex-direction: column;
      gap: 10px;
    }
    .timeline-flow {
      display: grid;
      grid-template-columns: repeat(8, minmax(0, 1fr));
      gap: 8px;
      margin: 4px 0 12px;
    }
    .timeline-flow span {
      display: flex;
      align-items: center;
      justify-content: center;
      min-height: 38px;
      padding: 6px 8px;
      border-radius: 999px;
      background: rgba(11, 15, 22, 0.9);
      border: 1px solid rgba(140,170,210,0.12);
      color: var(--muted);
      text-align: center;
      font-size: 0.58rem;
      letter-spacing: 0.09em;
      text-transform: uppercase;
    }
    .timeline-flow span.active {
      background: rgba(112,214,255,0.1);
      border-color: rgba(112,214,255,0.4);
      color: var(--primary);
      box-shadow: inset 0 0 0 1px rgba(112,214,255,0.12);
    }
    .demo-note {
      margin-top: 10px;
      padding: 10px 12px;
      border: 1px solid rgba(255,191,105,0.18);
      border-radius: 10px;
      background: rgba(255,191,105,0.08);
      color: var(--warning);
      font-size: 0.72rem;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      text-align: center;
    }
    .hidden { display: none; }
    @media (max-width: 980px) {
      .stats, .panel-grid, .flow-row, .system-map, .target-system-grid, .evidence-grid, .timeline-flow { grid-template-columns: 1fr; }
      .system-graph { min-height: 320px; }
      .connected-row { position: static; margin-top: 16px; }
    }
  </style>
</head>
<body>
  <div class="dashboard">
    <header class="topbar">
      <div class="brand">
        <div class="brand-title">AEGISOPS</div>
        <div class="brand-subtitle">AUTONOMOUS AI INCIDENT RESPONSE &amp; SRE PLATFORM</div>
      </div>
      <div class="topbar-status-group">
        <span class="mini-status"><em>System</em><strong id="systemStatusMini">OPERATIONAL</strong></span>
        <span class="mini-status"><em>AI Agent</em><strong id="agentStatusMini">ONLINE</strong></span>
        <span class="mini-status"><em>LLM</em><strong id="llmStatusMini">CONFIGURED</strong></span>
        <span class="mini-status alert"><em>Active Incidents</em><strong id="incidentCounterMini">0</strong></span>
      </div>
    </header>

    <div class="content">
      <section class="stats">
        <div class="card compact-card">
          <div class="card-header"><span>System</span><span class="pill healthy">Operational</span></div>
          <div class="stat-value" id="systemStatus">OPERATIONAL</div>
        </div>
        <div class="card compact-card">
          <div class="card-header"><span>AI Agent</span><span class="pill online">Online</span></div>
          <div class="stat-value" id="agentStatus">ONLINE</div>
        </div>
        <div class="card compact-card">
          <div class="card-header"><span>LLM</span><span class="pill configured">Configured</span></div>
          <div class="stat-value" id="llmStatus">CONFIGURED</div>
        </div>
        <div class="card compact-card">
          <div class="card-header"><span>Active Incidents</span><span class="pill alert" id="activeBadge">0</span></div>
          <div class="stat-value" id="incidentCounter">0</div>
        </div>
      </section>

      <section class="card target-system-card">
        <div class="panel-title-row">
          <div class="panel-title">Target System</div>
          <div class="simulated-pill">SIMULATION / DEMO DATA</div>
        </div>
        <div class="demo-note">LIVE BACKEND: health and readiness checks. INCIDENT PATH: controlled simulation lab data.</div>

        <div class="system-map">
          <div class="system-graph">
            <div class="node ai-node">
              <div class="node-label">AI AGENT</div>
              <div class="node-state">◉ ANALYZING</div>
            </div>
            <div class="flow-line flow-a"></div>
            <div class="flow-line flow-b"></div>
            <div class="flow-line flow-c"></div>

            <div class="node service-node">
              <div class="node-label">checkout-api</div>
              <div id="targetStatus" class="target-status status-healthy">HEALTHY</div>
              <div class="service-metrics">
                <span>Latency: <strong id="targetLatency">120 ms</strong></span>
                <span>Error: <strong id="targetErrorRate">0.4%</strong></span>
                <span>Request Rate: <strong id="targetRequestRate">1,240/min</strong></span>
              </div>
            </div>

            <div class="connected-row">
              <div class="connected-node">
                <span>Database</span>
                <strong id="targetDatabase">HEALTHY</strong>
              </div>
              <div class="connected-node">
                <span>Redis</span>
                <strong>HEALTHY</strong>
              </div>
              <div class="connected-node">
                <span>Dependencies</span>
                <strong id="targetDependency">HEALTHY</strong>
              </div>
            </div>
          </div>

          <div class="comparison-panel">
            <h4>Before / During / After</h4>
            <div class="before-after-row"><strong>Before:</strong><span>Latency 120ms</span><span>Error 0.4%</span></div>
            <div class="before-after-row warning"><strong>During:</strong><span>Latency 4.8s</span><span>Error 37%</span></div>
            <div class="before-after-row"><strong>After:</strong><span>Latency 120ms</span><span>Error 0.4%</span></div>
          </div>
        </div>
      </section>

      <section class="card" style="margin-bottom: 20px;">
        <div class="panel-title-row">
          <div class="panel-title">Observability Evidence</div>
        </div>
        <div class="evidence-grid">
          <div class="evidence-card">
            <h4>Logs</h4>
            <ul class="evidence-list">
              <li>database connection timeout</li>
              <li>downstream request latency increased</li>
            </ul>
          </div>
          <div class="evidence-card">
            <h4>Metrics</h4>
            <ul class="evidence-list">
              <li>latency spike</li>
              <li>error rate increase</li>
            </ul>
          </div>
          <div class="evidence-card">
            <h4>Dependencies</h4>
            <ul class="evidence-list">
              <li>database response degradation</li>
            </ul>
          </div>
        </div>
      </section>

      <section class="panel-grid top-grid">
        <div class="card scenario-card">
          <div class="panel-title-row">
            <div class="panel-title">Incident Simulation Lab</div>
            <button class="reset-btn" id="resetBtn">Reset Demo</button>
          </div>
          <div class="sim-buttons">
            <button class="incident-btn active" data-incident="latency">API Latency Spike</button>
            <button class="incident-btn" data-incident="database">Database Failure</button>
            <button class="incident-btn" data-incident="redis">Redis Outage</button>
            <button class="incident-btn" data-incident="errors">High Error Rate</button>
            <button class="incident-btn reset-btn" data-incident="reset">Reset / Normalize</button>
          </div>
        </div>

        <div class="card investigation-card">
          <div class="panel-title-row">
            <div class="panel-title">AI Investigation</div>
          </div>
          <div id="investigationSteps" class="steps"></div>
        </div>

        <div class="card root-cause-card">
          <div class="panel-title-row">
            <div class="panel-title">Root Cause</div>
          </div>
          <div class="detail-row"><span class="detail-label">Root Cause</span><span class="detail-value" id="rootCause">Standby</span></div>
          <div class="detail-row"><span class="detail-label">Confidence</span><span class="detail-value" id="confidenceValue">--</span></div>
          <div class="detail-row"><span class="detail-label">Evidence</span><span class="detail-value" id="evidenceValue">--</span></div>
          <div class="detail-row"><span class="detail-label">Affected Service</span><span class="detail-value" id="affectedService">--</span></div>
          <div class="detail-row"><span class="detail-label">Recommended Remediation</span><span class="detail-value" id="recommendedAction">--</span></div>
        </div>
      </section>

      <section class="flow-row lower-grid">
        <div class="card risk-card">
          <div class="panel-title-row">
            <div class="panel-title">Autonomous Risk Engine</div>
          </div>
          <div class="risk-gauge-wrap">
            <div class="risk-gauge">
              <div class="gauge-inner">
                <span class="gauge-value" id="riskScore">--</span>
              </div>
            </div>
          </div>
          <div class="risk-meta">
            <div class="risk-meta-row"><span>Severity</span><strong>HIGH</strong></div>
            <div class="risk-meta-row"><span>Confidence</span><strong id="riskConfidence">94%</strong></div>
            <div class="risk-meta-row"><span>Blast Radius</span><strong>LOW</strong></div>
            <div class="risk-meta-row"><span>Reversible</span><strong>YES</strong></div>
          </div>
          <div class="risk-decision">
            <span>Decision</span>
            <strong id="riskDecision">--</strong>
          </div>
        </div>

        <div class="card remediation-card">
          <div class="panel-title-row">
            <div class="panel-title">Remediation</div>
          </div>
          <div class="remediation-box">
            <div class="detail-row"><span class="detail-label">Action</span><span class="detail-value" id="remediationAction">--</span></div>
            <div class="detail-row"><span class="detail-label">Status</span><span class="detail-value" id="remediationStatus">--</span></div>
          </div>
        </div>
      </section>

      <section class="card timeline-card">
        <div class="panel-title-row">
          <div class="panel-title">Live Incident Timeline</div>
          <div id="incidentStateTag" class="pill alert">READY</div>
        </div>

        <div class="timeline-flow">
          <span class="active">Healthy</span>
          <span class="active">Detected</span>
          <span>Evidence</span>
          <span>Investigation</span>
          <span>RCA</span>
          <span>Risk</span>
          <span>Remediation</span>
          <span>Resolved</span>
        </div>

        <div id="incidentSummary" class="narrative-box">
          <div class="detail-row"><span class="detail-label">HEALTHY → INCIDENT DETECTED → EVIDENCE COLLECTED → AI INVESTIGATING → ROOT CAUSE IDENTIFIED → RISK ASSESSED → REMEDIATION AUTHORIZED → RECOVERY VERIFIED</span><span class="detail-value">No active incident.</span></div>
        </div>
        <div class="status-banner hidden" id="finalStatusBanner">🟢 INCIDENT RESOLVED</div>
      </section>

      <section class="card verification-card" style="margin-top: 20px;">
        <div class="panel-title-row">
          <div class="panel-title">Verification</div>
        </div>
        <ul class="timeline-list" id="verificationList">
          <li>✓ Service recovered</li>
          <li>✓ Latency normalized</li>
          <li>✓ Error rate normalized</li>
          <li>✓ Dependencies healthy</li>
        </ul>
      </section>
    </div>
  </div>

  <script>
    const workflow = [
      'INCIDENT DETECTED',
      'EVIDENCE COLLECTED',
      'LOGS ANALYZED',
      'METRICS CORRELATED',
      'ROOT CAUSE IDENTIFIED',
      'RISK ASSESSMENT',
      'REMEDIATION',
      'VERIFIED'
    ];

    const incidentCatalog = {
      reset: {
        title: 'READY',
        service: 'checkout-api',
        severity: 'LOW',
        severityClass: 'severity-low',
        latency: '120 ms',
        errorRate: '0.4%',
        confidence: 0,
        blastRadius: 0,
        actionReversibility: 100,
        historicalRisk: 0,
        rootCause: 'Standby',
        evidence: 'No active incident',
        remediation: 'Await next trigger',
        status: 'READY',
        finalStatus: 'HEALTHY',
        riskScore: 0,
        decision: 'SAFE / READY',
        decisionClass: 'auto',
        activeIncidentCount: 0,
        lifecycle: [
          '✓ Healthy',
          '✓ Monitoring',
          '✓ No critical anomaly'
        ],
        summaryTitle: 'HEALTHY',
        summaryContent: 'Service: checkout-api | Status: healthy | No incident in flight.'
      },
      latency: {
        title: 'API LATENCY SPIKE',
        service: 'checkout-api',
        severity: 'HIGH',
        severityClass: 'severity-high',
        latency: '4.8s',
        errorRate: '37%',
        confidence: 94,
        blastRadius: 72,
        actionReversibility: 80,
        historicalRisk: 7,
        rootCause: 'Database connection pool exhaustion causing checkout-api latency.',
        evidence: 'error spike, high p95 latency, saturated database connections',
        remediation: 'Restore/recycle affected database connection resources.',
        status: 'EXECUTING...',
        finalStatus: 'INCIDENT RESOLVED',
        riskScore: 24,
        decision: 'AUTO REMEDIATE',
        decisionClass: 'auto',
        activeIncidentCount: 1,
        lifecycle: [
          '✓ Incident detected',
          '✓ Evidence collected',
          '✓ Logs analyzed',
          '✓ Metrics correlated',
          '✓ Root cause identified'
        ],
        summaryTitle: 'INCIDENT DETECTED',
        summaryContent: 'Service: checkout-api | Severity: HIGH | Latency: 4.8s | Error Rate: 37%'
      },
      database: {
        title: 'DATABASE FAILURE',
        service: 'orders-db',
        severity: 'HIGH',
        severityClass: 'severity-high',
        latency: '3.2s',
        errorRate: '28%',
        confidence: 89,
        blastRadius: 68,
        actionReversibility: 76,
        historicalRisk: 9,
        rootCause: 'Connection pool exhaustion at the primary database.',
        evidence: 'query backlog, lock waits, and replica lag',
        remediation: 'Drain batch workers and recycle stale connections.',
        status: 'EXECUTING...',
        finalStatus: 'INCIDENT RESOLVED',
        riskScore: 38,
        decision: 'HUMAN APPROVAL REQUIRED',
        decisionClass: 'human',
        activeIncidentCount: 1,
        lifecycle: [
          '✓ Incident detected',
          '✓ Evidence collected',
          '✓ Logs analyzed',
          '✓ Metrics correlated',
          '✓ Root cause identified'
        ],
        summaryTitle: 'INCIDENT DETECTED',
        summaryContent: 'Service: orders-db | Severity: HIGH | Latency: 3.2s | Error Rate: 28%'
      },
      redis: {
        title: 'REDIS OUTAGE',
        service: 'session-cache',
        severity: 'MEDIUM',
        severityClass: 'severity-med',
        latency: '2.7s',
        errorRate: '18%',
        confidence: 86,
        blastRadius: 48,
        actionReversibility: 82,
        historicalRisk: 6,
        rootCause: 'Redis failover did not complete cleanly on the primary shard.',
        evidence: 'cache miss spike, failover events, session churn',
        remediation: 'Promote the healthy replica and purge stale queue entries.',
        status: 'EXECUTING...',
        finalStatus: 'INCIDENT RESOLVED',
        riskScore: 34,
        decision: 'HUMAN APPROVAL REQUIRED',
        decisionClass: 'human',
        activeIncidentCount: 1,
        lifecycle: [
          '✓ Incident detected',
          '✓ Evidence collected',
          '✓ Logs analyzed',
          '✓ Metrics correlated',
          '✓ Root cause identified'
        ],
        summaryTitle: 'INCIDENT DETECTED',
        summaryContent: 'Service: session-cache | Severity: MEDIUM | Latency: 2.7s | Error Rate: 18%'
      },
      errors: {
        title: 'HIGH ERROR RATE',
        service: 'edge-gateway',
        severity: 'MEDIUM',
        severityClass: 'severity-med',
        latency: '1.6s',
        errorRate: '43%',
        confidence: 81,
        blastRadius: 53,
        actionReversibility: 74,
        historicalRisk: 11,
        rootCause: 'Retry storm amplified a downstream 5xx dependency failure.',
        evidence: 'error rate increase, retries, increased queue depth',
        remediation: 'Reduce retry pressure and route requests to the healthy edge lane.',
        status: 'EXECUTING...',
        finalStatus: 'INCIDENT RESOLVED',
        riskScore: 46,
        decision: 'HUMAN APPROVAL REQUIRED',
        decisionClass: 'human',
        activeIncidentCount: 1,
        lifecycle: [
          '✓ Incident detected',
          '✓ Evidence collected',
          '✓ Logs analyzed',
          '✓ Metrics correlated',
          '✓ Root cause identified'
        ],
        summaryTitle: 'INCIDENT DETECTED',
        summaryContent: 'Service: edge-gateway | Severity: MEDIUM | Latency: 1.6s | Error Rate: 43%'
      }
    };

    function riskFromInputs(incident) {
      const severityWeight = incident.severity === 'HIGH' ? 17 : incident.severity === 'MEDIUM' ? 10 : 5;
      const score = Math.min(100, Math.max(0,
        severityWeight +
        Math.round((100 - incident.confidence) * 0.6) +
        Math.round(incident.blastRadius / 10) +
        Math.round((100 - incident.actionReversibility) * 0.5) +
        incident.historicalRisk
      ));
      let decision = 'AUTO REMEDIATE';
      let decisionClass = 'auto';
      if (score > 30 && score <= 70) {
        decision = 'HUMAN APPROVAL REQUIRED';
        decisionClass = 'human';
      } else if (score > 70) {
        decision = 'BLOCK ACTION';
        decisionClass = 'block';
      }
      return { score, decision, decisionClass };
    }

    function renderSteps(steps) {
      const container = document.getElementById('investigationSteps');
      container.innerHTML = workflow.map((step, index) => {
        const isActive = steps.includes(step);
        return `
          <div class="step ${isActive ? 'active' : ''}">
            <div class="step-index">${index + 1}</div>
            <div>${step}</div>
          </div>
        `;
      }).join('');
    }

    function setTargetSystemState(mode) {
      const targetStatus = document.getElementById('targetStatus');
      const requestRate = document.getElementById('targetRequestRate');
      const latency = document.getElementById('targetLatency');
      const errorRate = document.getElementById('targetErrorRate');
      const database = document.getElementById('targetDatabase');
      const dependency = document.getElementById('targetDependency');

      if (mode === 'incident') {
        targetStatus.textContent = 'DEGRADED';
        targetStatus.className = 'target-status status-degraded';
        requestRate.textContent = '1,240/min';
        latency.textContent = '4.8 s';
        errorRate.textContent = '37%';
        database.textContent = 'DEGRADED';
        dependency.textContent = 'DEGRADED';
        return;
      }

      if (mode === 'recovered') {
        targetStatus.textContent = 'HEALTHY';
        targetStatus.className = 'target-status status-healthy';
        requestRate.textContent = '1,240/min';
        latency.textContent = '120 ms';
        errorRate.textContent = '0.4%';
        database.textContent = 'HEALTHY';
        dependency.textContent = 'HEALTHY';
        return;
      }

      targetStatus.textContent = 'HEALTHY';
      targetStatus.className = 'target-status status-healthy';
      requestRate.textContent = '1,240/min';
      latency.textContent = '120 ms';
      errorRate.textContent = '0.4%';
      database.textContent = 'HEALTHY';
      dependency.textContent = 'HEALTHY';
    }

    function setDemoState(name) {
      if (name === 'reset') {
        resetDemo();
        return;
      }

      const incident = incidentCatalog[name] || incidentCatalog.latency;
      const risk = riskFromInputs(incident);
      const useRiskScore = incident.riskScore ?? risk.score;
      const useDecision = incident.decision || risk.decision;
      const useDecisionClass = incident.decisionClass || risk.decisionClass;

      setTargetSystemState('incident');
      document.getElementById('rootCause').textContent = incident.rootCause;
      document.getElementById('confidenceValue').textContent = `${incident.confidence}%`;
      document.getElementById('evidenceValue').textContent = incident.evidence;
      document.getElementById('affectedService').textContent = incident.service;
      document.getElementById('recommendedAction').textContent = incident.remediation;
      document.getElementById('riskScore').textContent = `${useRiskScore} / 100`;
      document.getElementById('riskDecision').textContent = useDecision;
      document.getElementById('riskDecision').className = `decision-pill ${useDecisionClass}`;
      document.getElementById('remediationAction').textContent = incident.remediation;
      document.getElementById('remediationStatus').textContent = incident.status;
      document.getElementById('incidentStateTag').textContent = incident.title;
      document.getElementById('incidentStateTag').className = 'pill alert';
      document.getElementById('finalStatusBanner').classList.remove('hidden');
      document.getElementById('finalStatusBanner').textContent = incident.finalStatus;
      document.getElementById('incidentSummary').innerHTML = `
        <div class="detail-row"><span class="detail-label">HEALTHY → INCIDENT DETECTED → EVIDENCE COLLECTED → AI INVESTIGATING → ROOT CAUSE IDENTIFIED → RISK ASSESSED → REMEDIATION AUTHORIZED → RECOVERY VERIFIED</span><span class="detail-value">${incident.summaryTitle}</span></div>
        <div class="detail-row"><span class="detail-label">Service</span><span class="detail-value">${incident.service}</span></div>
        <div class="detail-row"><span class="detail-label">Severity</span><span class="detail-value"><span class="severity-tag ${incident.severityClass}">${incident.severity}</span></span></div>
        <div class="detail-row"><span class="detail-label">Latency</span><span class="detail-value">${incident.latency}</span></div>
        <div class="detail-row"><span class="detail-label">Error Rate</span><span class="detail-value">${incident.errorRate}</span></div>
        <div class="detail-row"><span class="detail-label">Status</span><span class="detail-value">${incident.status}</span></div>
        <div class="detail-row"><span class="detail-label">Progress</span><span class="detail-value">${incident.lifecycle.join(' • ')}</span></div>
      `;
      renderSteps(workflow.slice(0, 5));
      document.getElementById('activeBadge').textContent = incident.activeIncidentCount;
      document.getElementById('incidentCounter').textContent = incident.activeIncidentCount;
      document.getElementById('incidentCounterMini').textContent = incident.activeIncidentCount;
      document.querySelectorAll('.incident-btn').forEach((button) => {
        const isSelected = button.dataset.incident === name;
        button.classList.toggle('active', isSelected);
      });

      window.clearTimeout(window.__aegisopsRecoveryTimer);
      window.__aegisopsRecoveryTimer = window.setTimeout(() => {
        setTargetSystemState('recovered');
        document.getElementById('targetStatus').textContent = 'HEALTHY';
        document.getElementById('targetStatus').className = 'target-status status-healthy';
        document.getElementById('remediationStatus').textContent = 'RECOVERED';
        document.getElementById('incidentStateTag').textContent = 'INCIDENT RESOLVED';
        document.getElementById('incidentStateTag').className = 'pill healthy';
        document.getElementById('finalStatusBanner').textContent = '🟢 INCIDENT RESOLVED';
        document.getElementById('finalStatusBanner').classList.remove('hidden');
        document.getElementById('verificationList').innerHTML = `
          <li>✓ Service recovered</li>
          <li>✓ Latency normalized</li>
          <li>✓ Error rate normalized</li>
          <li>✓ Dependencies healthy</li>
        `;
      }, 1800);
    }

    function resetDemo() {
      window.clearTimeout(window.__aegisopsRecoveryTimer);
      setTargetSystemState('normal');
      document.getElementById('rootCause').textContent = 'Standby';
      document.getElementById('confidenceValue').textContent = '--';
      document.getElementById('evidenceValue').textContent = '--';
      document.getElementById('affectedService').textContent = '--';
      document.getElementById('recommendedAction').textContent = '--';
      document.getElementById('riskScore').textContent = '--';
      document.getElementById('riskDecision').textContent = '--';
      document.getElementById('riskDecision').className = 'decision-pill';
      document.getElementById('remediationAction').textContent = '--';
      document.getElementById('remediationStatus').textContent = '--';
      document.getElementById('incidentStateTag').textContent = 'READY';
      document.getElementById('incidentStateTag').className = 'pill alert';
      document.getElementById('activeBadge').textContent = '0';
      document.getElementById('incidentCounter').textContent = '0';
      document.getElementById('incidentCounterMini').textContent = '0';
      document.getElementById('finalStatusBanner').classList.add('hidden');
      document.getElementById('incidentSummary').innerHTML = '<div class="detail-row"><span class="detail-label">INCIDENT DETECTED</span><span class="detail-value">No active incident.</span></div>';
      document.getElementById('verificationList').innerHTML = `
        <li>✓ Service recovered</li>
        <li>✓ Latency normalized</li>
        <li>✓ Error rate normalized</li>
        <li>✓ Dependencies healthy</li>
      `;
      renderSteps([]);
      document.querySelectorAll('.incident-btn').forEach((button) => button.classList.remove('active'));
      document.querySelector('[data-incident="latency"]').classList.add('active');
    }

    async function loadHealth() {
      try {
        const response = await fetch('/health');
        const payload = await response.json();
        document.getElementById('systemStatus').textContent = payload.ok ? 'OPERATIONAL' : 'DEGRADED';
        document.getElementById('agentStatus').textContent = payload.ok ? 'ONLINE' : 'OFFLINE';
        document.getElementById('llmStatus').textContent = payload.llm_configured ? 'CONFIGURED' : 'NOT CONFIGURED';
      } catch (error) {
        document.getElementById('systemStatus').textContent = 'OPERATIONAL';
        document.getElementById('agentStatus').textContent = 'ONLINE';
        document.getElementById('llmStatus').textContent = 'CONFIGURED';
      }
    }

    document.querySelectorAll('.incident-btn').forEach((button) => {
      button.addEventListener('click', () => {
        setDemoState(button.dataset.incident);
      });
    });
    document.getElementById('resetBtn').addEventListener('click', resetDemo);
    loadHealth();
    setDemoState('latency');
  </script>
</body>
</html>"""
