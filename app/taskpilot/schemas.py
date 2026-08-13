from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class TaskStatus(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    WAITING_CONFIRMATION = "waiting_confirmation"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class EventType(StrEnum):
    TASK_CREATED = "task.created"
    TASK_STARTED = "task.started"
    PLAN_CREATED = "plan.created"
    STEP_STARTED = "step.started"
    TOOL_STARTED = "tool.started"
    TOOL_FINISHED = "tool.finished"
    STEP_FINISHED = "step.finished"
    MEMORY_WRITTEN = "memory.written"
    EVALUATION_FINISHED = "evaluation.finished"
    TASK_FINISHED = "task.finished"
    TASK_FAILED = "task.failed"


@dataclass
class AgentEvent:
    event_id: int
    task_id: str
    type: EventType
    message: str
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "task_id": self.task_id,
            "type": self.type,
            "message": self.message,
            "payload": self.payload,
            "created_at": self.created_at,
        }


@dataclass
class AgentStep:
    step_id: str
    name: str
    tool_name: str
    args: dict[str, Any]
    status: str = "pending"
    result: dict[str, Any] | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "name": self.name,
            "tool_name": self.tool_name,
            "args": self.args,
            "status": self.status,
            "result": self.result,
            "error": self.error,
        }


@dataclass
class AgentTask:
    task_id: str
    objective: str
    drawing_id: str | None = None
    norm_query: str = ""
    status: TaskStatus = TaskStatus.CREATED
    plan: list[AgentStep] = field(default_factory=list)
    result: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def touch(self) -> None:
        self.updated_at = datetime.now(UTC).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "objective": self.objective,
            "drawing_id": self.drawing_id,
            "norm_query": self.norm_query,
            "status": self.status,
            "plan": [step.to_dict() for step in self.plan],
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
