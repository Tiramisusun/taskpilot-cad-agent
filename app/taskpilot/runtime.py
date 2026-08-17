from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from .evaluation import evaluate_agent_run
from .middleware import MiddlewareStack
from .observability import EventLog
from .planner import build_plan
from .schemas import AgentStep, AgentTask, EventType, TaskStatus
from .tools import ToolRegistry, ToolSpec
from ..models import DrawingModel, NormDocument
from ..norms import search_norms
from ..repair import apply_low_risk_fixes
from ..report import write_html_report, write_json_report
from ..reviewer import review_drawing


class TaskStore:
    def __init__(self) -> None:
        self.tasks: dict[str, AgentTask] = {}

    def create(self, objective: str, drawing_id: str | None, norm_query: str) -> AgentTask:
        task = AgentTask(task_id=uuid4().hex, objective=objective, drawing_id=drawing_id, norm_query=norm_query)
        self.tasks[task.task_id] = task
        return task

    def get(self, task_id: str) -> AgentTask | None:
        return self.tasks.get(task_id)

    def list(self) -> list[AgentTask]:
        return sorted(self.tasks.values(), key=lambda task: task.created_at, reverse=True)


class AgentRuntime:
    def __init__(
        self,
        drawings: dict[str, tuple[Path, DrawingModel]],
        norms: dict[str, NormDocument],
        report_dir: Path,
        event_log: EventLog,
        middleware: MiddlewareStack,
    ) -> None:
        self.drawings = drawings
        self.norms = norms
        self.report_dir = report_dir
        self.event_log = event_log
        self.middleware = middleware
        self.tasks = TaskStore()
        self.registry = ToolRegistry()
        self._register_tools()

    def create_task(self, objective: str, drawing_id: str | None, norm_query: str) -> AgentTask:
        task = self.tasks.create(objective=objective, drawing_id=drawing_id, norm_query=norm_query)
        self.event_log.emit(task.task_id, EventType.TASK_CREATED, "Task created.", task.to_dict())
        return task

    def new_review_id(self) -> str:
        return uuid4().hex

    def compose_deepagent_result(
        self,
        review_result: dict[str, Any],
        norm_result: dict[str, Any],
        repair_result: dict[str, Any],
        report_result: dict[str, Any],
    ) -> dict[str, Any]:
        issues = review_result.get("issues", [])
        return {
            "summary": f"CAD review completed with {len(issues)} issues found.",
            "review_id": report_result.get("review_id"),
            "drawing": review_result.get("drawing", {}),
            "issues": issues,
            "issue_count": len(issues),
            "norm_matches": norm_result.get("norm_matches", []),
            "downloads": report_result.get("downloads", {}),
            "repair_result": repair_result,
            "events": [],
            "failed_steps": [],
        }

    async def run_task(self, task_id: str) -> AgentTask:
        task = self._require_task(task_id)
        if not task.drawing_id:
            raise ValueError("CAD review tasks require a drawing_id.")

        task.status = TaskStatus.RUNNING
        task.plan = build_plan(task.drawing_id, task.norm_query)
        task.touch()
        context = self.middleware.before_task(task)
        self.event_log.emit(
            task.task_id,
            EventType.PLAN_CREATED,
            "Plan-Execute workflow plan created.",
            {"plan": [step.to_dict() for step in task.plan]},
        )

        runtime_state: dict[str, Any] = {"task": task, "failed_steps": []}
        try:
            for step in task.plan:
                step.status = "running"
                task.touch()
                self.event_log.emit(task.task_id, EventType.STEP_STARTED, step.name, step.to_dict())
                call_step = AgentStep(
                    step_id=step.step_id,
                    name=step.name,
                    tool_name=step.tool_name,
                    args={**step.args, **_state_args(runtime_state, step.tool_name)},
                )
                tool_result = self.middleware.call_tool(self.registry, context, call_step)
                if step.tool_name == "cad.review":
                    runtime_state["_issue_objects"] = tool_result.pop("issue_objects", [])
                step.result = tool_result
                runtime_state[step.tool_name] = tool_result
                step.status = "succeeded"
                self.event_log.emit(task.task_id, EventType.STEP_FINISHED, f"{step.name} finished.", step.to_dict())
                await asyncio.sleep(0)

            result = _compose_result(runtime_state, self.event_log.replay(task.task_id))
            evaluation = evaluate_agent_run(result)
            result["evaluation"] = evaluation
            task.result = result
            task.status = TaskStatus.SUCCEEDED
            task.touch()
            self.middleware.after_task(context, result)
            self.event_log.emit(task.task_id, EventType.EVALUATION_FINISHED, "Agent Evaluation finished.", evaluation)
            self.event_log.emit(task.task_id, EventType.TASK_FINISHED, "Task finished.", task.to_dict())
        except Exception as exc:
            task.status = TaskStatus.FAILED
            task.error = str(exc)
            task.touch()
            self.event_log.emit(task.task_id, EventType.TASK_FAILED, "Task failed.", {"error": str(exc)})
        return task

    async def event_stream(self, task_id: str):
        last_event_id = 0
        while True:
            task = self._require_task(task_id)
            events = self.event_log.list_events(task_id, after=last_event_id)
            for event in events:
                last_event_id = event.event_id
                yield f"event: {event.type}\ndata: {json.dumps(event.to_dict(), ensure_ascii=False)}\n\n"
            if task.status in {TaskStatus.SUCCEEDED, TaskStatus.FAILED, TaskStatus.CANCELLED} and not events:
                break
            await asyncio.sleep(0.35)

    def _require_task(self, task_id: str) -> AgentTask:
        task = self.tasks.get(task_id)
        if task is None:
            raise ValueError("Task not found.")
        return task

    def _register_tools(self) -> None:
        self.registry.register(
            ToolSpec(
                name="cad.parse",
                description="Read the structured summary of an uploaded drawing.",
                required_args=["drawing_id"],
                handler=self._tool_parse_drawing,
            )
        )
        self.registry.register(
            ToolSpec(
                name="norm.search",
                description="Retrieve task-relevant clauses from uploaded standards.",
                required_args=["query"],
                handler=self._tool_search_norms,
            )
        )
        self.registry.register(
            ToolSpec(
                name="cad.review",
                description="Run architectural CAD review rules.",
                required_args=["drawing_id"],
                handler=self._tool_review_drawing,
            )
        )
        self.registry.register(
            ToolSpec(
                name="cad.repair",
                description="Apply low-risk deterministic DXF auto-repairs.",
                required_args=["source_path", "issues"],
                handler=self._tool_repair_drawing,
            )
        )
        self.registry.register(
            ToolSpec(
                name="report.generate",
                description="Generate JSON and HTML review reports.",
                required_args=["drawing", "issues", "norm_matches", "review_id"],
                handler=self._tool_generate_report,
            )
        )

    def _tool_parse_drawing(self, args: dict[str, Any]) -> dict[str, Any]:
        drawing_id = args["drawing_id"]
        if drawing_id not in self.drawings:
            raise ValueError("Drawing not found. Please upload it again.")
        source_path, drawing = self.drawings[drawing_id]
        return {"source_path": str(source_path), "drawing": drawing.to_summary()}

    def _tool_search_norms(self, args: dict[str, Any]) -> dict[str, Any]:
        matches = search_norms(list(self.norms.values()), args["query"], limit=5)
        return {"norm_matches": matches, "match_count": len(matches)}

    def _tool_review_drawing(self, args: dict[str, Any]) -> dict[str, Any]:
        drawing_id = args["drawing_id"]
        _, drawing = self.drawings[drawing_id]
        issues = review_drawing(drawing, list(self.norms.values()), args.get("norm_query", ""))
        return {
            "drawing": drawing.to_summary(),
            "issues": [issue.to_dict() for issue in issues],
            "issue_objects": issues,
            "issue_count": len(issues),
        }

    def _tool_repair_drawing(self, args: dict[str, Any]) -> dict[str, Any]:
        review_id = args["review_id"]
        result = apply_low_risk_fixes(Path(args["source_path"]), self.report_dir / f"{review_id}_fixed.dxf", args["issues"])
        return result

    def _tool_generate_report(self, args: dict[str, Any]) -> dict[str, Any]:
        review_id = args["review_id"]
        drawing_id = args["drawing_id"]
        _, drawing = self.drawings[drawing_id]
        json_path = self.report_dir / f"{review_id}.json"
        html_path = self.report_dir / f"{review_id}.html"
        issue_objects = args["issue_objects"]
        norm_matches = args["norm_matches"]
        write_json_report(json_path, drawing, issue_objects, norm_matches)
        write_html_report(html_path, drawing, issue_objects, norm_matches)
        return {
            "review_id": review_id,
            "json_path": str(json_path),
            "html_path": str(html_path),
            "fixed_path": args.get("fixed_path", ""),
            "downloads": {
                "json": f"/api/reviews/{review_id}/report.json",
                "html": f"/api/reviews/{review_id}/report.html",
                "fixed_dxf": f"/api/reviews/{review_id}/fixed.dxf",
            },
        }


def _state_args(runtime_state: dict[str, Any], tool_name: str) -> dict[str, Any]:
    task = runtime_state["task"]
    review_id = runtime_state.setdefault("review_id", uuid4().hex)
    parse_result = runtime_state.get("cad.parse", {})
    norm_result = runtime_state.get("norm.search", {})
    review_result = runtime_state.get("cad.review", {})
    repair_result = runtime_state.get("cad.repair", {})

    if tool_name == "cad.repair":
        return {
            "review_id": review_id,
            "source_path": parse_result.get("source_path"),
            "issues": runtime_state.get("_issue_objects", []),
        }
    if tool_name == "report.generate":
        return {
            "review_id": review_id,
            "drawing_id": task.drawing_id,
            "drawing": review_result.get("drawing", {}),
            "issues": review_result.get("issues", []),
            "issue_objects": runtime_state.get("_issue_objects", []),
            "norm_matches": norm_result.get("norm_matches", []),
            "fixed_path": repair_result.get("output", ""),
        }
    return {}


def _compose_result(runtime_state: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    review_result = runtime_state.get("cad.review", {})
    report_result = runtime_state.get("report.generate", {})
    repair_result = runtime_state.get("cad.repair", {})
    issues = review_result.get("issues", [])
    return {
        "summary": f"CAD review completed with {len(issues)} issues found.",
        "review_id": report_result.get("review_id"),
        "drawing": review_result.get("drawing", {}),
        "issues": issues,
        "issue_count": len(issues),
        "norm_matches": runtime_state.get("norm.search", {}).get("norm_matches", []),
        "downloads": report_result.get("downloads", {}),
        "repair_result": repair_result,
        "events": events,
        "failed_steps": runtime_state.get("failed_steps", []),
    }
