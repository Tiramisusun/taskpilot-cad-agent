from __future__ import annotations

from dataclasses import dataclass, field
from time import perf_counter
from typing import Any

from .memory import MemoryStore
from .observability import EventLog
from .schemas import AgentStep, AgentTask, EventType
from .tools import ToolRegistry


@dataclass
class RuntimeContext:
    task: AgentTask
    memory_context: dict[str, Any]
    token_usage: dict[str, int] = field(default_factory=lambda: {"estimated_input": 0, "estimated_output": 0})
    audit_flags: list[str] = field(default_factory=list)


class MiddlewareStack:
    def __init__(self, event_log: EventLog, memory: MemoryStore) -> None:
        self.event_log = event_log
        self.memory = memory

    def before_task(self, task: AgentTask) -> RuntimeContext:
        context = RuntimeContext(task=task, memory_context=self.memory.inject_context(task.objective))
        context.token_usage["estimated_input"] = _estimate_tokens(task.objective + " " + task.norm_query)
        self.event_log.emit(
            task.task_id,
            EventType.TASK_STARTED,
            "Task started with injected Memory context.",
            {"memory_context": context.memory_context, "token_usage": context.token_usage},
        )
        return context

    def call_tool(self, registry: ToolRegistry, context: RuntimeContext, step: AgentStep) -> dict[str, Any]:
        started_at = perf_counter()
        self.event_log.emit(
            context.task.task_id,
            EventType.TOOL_STARTED,
            f"Calling tool {step.tool_name}.",
            {"step_id": step.step_id, "args": _safe_args(step.args)},
        )
        try:
            result = registry.call(step.tool_name, step.args)
        except Exception as exc:
            self.event_log.emit(
                context.task.task_id,
                EventType.TASK_FAILED,
                f"Tool {step.tool_name} failed.",
                {"step_id": step.step_id, "error": str(exc)},
            )
            raise

        elapsed_ms = int((perf_counter() - started_at) * 1000)
        context.token_usage["estimated_output"] += _estimate_tokens(str(result))
        self.event_log.emit(
            context.task.task_id,
            EventType.TOOL_FINISHED,
            f"Tool {step.tool_name} finished.",
            {"step_id": step.step_id, "elapsed_ms": elapsed_ms, "result": _safe_result(result)},
        )
        return result

    def after_task(self, context: RuntimeContext, result: dict[str, Any]) -> None:
        self.memory.remember_task_result(context.task.task_id, context.task.objective, result)
        self.event_log.emit(
            context.task.task_id,
            EventType.MEMORY_WRITTEN,
            "Task summary was written to long-term Memory.",
            {"token_usage": context.token_usage},
        )


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _safe_args(args: dict[str, Any]) -> dict[str, Any]:
    return _json_safe({key: value for key, value in args.items() if key not in {"raw_text"}})


def _safe_result(result: dict[str, Any]) -> dict[str, Any]:
    return _json_safe(result)


def _json_safe(value: Any) -> Any:
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if isinstance(value, dict):
        safe = {}
        for key, item in value.items():
            if str(key).endswith("_text") or key == "raw":
                safe[key] = "<omitted>"
            else:
                safe[key] = _json_safe(item)
        return safe
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    return value
