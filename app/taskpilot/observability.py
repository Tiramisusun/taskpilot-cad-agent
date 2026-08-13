from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .schemas import AgentEvent, EventType


class EventLog:
    def __init__(self, log_dir: Path):
        self.log_dir = log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._events: dict[str, list[AgentEvent]] = {}

    def emit(self, task_id: str, event_type: EventType, message: str, payload: dict[str, Any] | None = None) -> AgentEvent:
        events = self._events.setdefault(task_id, [])
        event = AgentEvent(
            event_id=len(events) + 1,
            task_id=task_id,
            type=event_type,
            message=message,
            payload=payload or {},
        )
        events.append(event)
        self._append_to_disk(event)
        return event

    def list_events(self, task_id: str, after: int = 0) -> list[AgentEvent]:
        return [event for event in self._events.get(task_id, []) if event.event_id > after]

    def replay(self, task_id: str) -> list[dict[str, Any]]:
        return [event.to_dict() for event in self._events.get(task_id, [])]

    def _append_to_disk(self, event: AgentEvent) -> None:
        path = self.log_dir / f"{event.task_id}.jsonl"
        with path.open("a") as output:
            output.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")
