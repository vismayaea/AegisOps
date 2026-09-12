from __future__ import annotations

from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from aegisops.domain import ScenarioName
from aegisops.incident import IncidentOrchestrator


class ScenarioRequest(BaseModel):
    scenario: ScenarioName


def create_app() -> FastAPI:
    app = FastAPI(title="AegisOps Control Center", version="0.1.0")
    orchestrator = IncidentOrchestrator()
    static_dir = Path(__file__).resolve().parents[1] / "web" / "static"
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/", response_class=HTMLResponse)
    def home() -> str:
        return (static_dir / "index.html").read_text(encoding="utf-8")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "healthy", "service": "aegisops"}

    @app.get("/api/state")
    def state() -> dict[str, object]:
        return orchestrator.state()

    @app.post("/api/reset")
    def reset() -> dict[str, object]:
        return orchestrator.reset()

    @app.get("/api/scenarios")
    def scenarios() -> list[dict[str, str]]:
        return orchestrator.scenarios()

    @app.post("/api/incidents")
    def create_incident(request: ScenarioRequest) -> dict[str, object]:
        return orchestrator.create_incident(request.scenario).as_dict()

    @app.post("/api/incidents/{incident_id}/approve")
    def approve(incident_id: str) -> dict[str, object]:
        try:
            return orchestrator.approve(incident_id).as_dict()
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/incidents/{incident_id}/execute")
    def execute(incident_id: str) -> dict[str, object]:
        try:
            return orchestrator.execute(incident_id).as_dict()
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/lifecycle")
    def lifecycle(request: ScenarioRequest) -> dict[str, object]:
        return orchestrator.run_full_lifecycle(request.scenario).as_dict()

    @app.get("/api/incidents/{incident_id}/evidence")
    def evidence(incident_id: str) -> list[dict[str, object]]:
        try:
            return [item.as_dict() for item in orchestrator._get(incident_id).evidence]
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/incidents/{incident_id}/investigation")
    def investigation(incident_id: str) -> dict[str, object] | None:
        try:
            result = orchestrator._get(incident_id).investigation
            return result.as_dict() if result else None
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/incidents/{incident_id}/risk")
    def risk(incident_id: str) -> dict[str, object] | None:
        try:
            result = orchestrator._get(incident_id).risk
            return result.as_dict() if result else None
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/incidents/{incident_id}/recovery")
    def recovery(incident_id: str) -> dict[str, object] | None:
        try:
            result = orchestrator._get(incident_id).recovery
            return result.as_dict() if result else None
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/incidents/{incident_id}/trace")
    def trace(incident_id: str) -> list[dict[str, object]]:
        try:
            return [event.as_dict() for event in orchestrator._get(incident_id).trace]
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/incidents/{incident_id}/postmortem")
    def postmortem(incident_id: str) -> dict[str, object]:
        try:
            return orchestrator.postmortem(incident_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    return app


def main() -> None:
    uvicorn.run("aegisops.api.app:create_app", factory=True, host="127.0.0.1", port=8000, reload=False)
