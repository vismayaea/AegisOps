from __future__ import annotations

from aegisops.domain import Incident, TraceEvent


class TraceRecorder:
    def add(
        self,
        incident: Incident,
        event_type: str,
        message: str,
        *,
        references: list[str] | None = None,
        details: dict[str, object] | None = None,
    ) -> TraceEvent:
        event = TraceEvent.create(event_type, message, references=references, details=details)
        incident.trace.append(event)
        return event
