from __future__ import annotations

import json
import os
from typing import Any

from .evaluation import evaluate_agent_run
from .runtime import AgentRuntime
from .schemas import AgentStep, EventType, TaskStatus


SYSTEM_PROMPT = """You are a CAD compliance review agent.

Use cad_full_review for complete CAD review tasks. Do not invent drawing facts,
issue counts, file paths, or standards clauses. Base the final answer on tool
results only.
"""


class DeepAgentRuntime:
    def __init__(self, classic_runtime: AgentRuntime) -> None:
        self.classic_runtime = classic_runtime
        self._agent: Any | None = None

    @property
    def agent(self) -> Any:
        if self._agent is None:
            from deepagents import create_deep_agent

            from .deepagent_tools import build_deepagent_tools

            self._agent = create_deep_agent(
                model=_build_model(),
                tools=build_deepagent_tools(self.classic_runtime),
                system_prompt=SYSTEM_PROMPT,
            )
        return self._agent

    async def run_task(self, task_id: str) -> Any:
        task = self.classic_runtime._require_task(task_id)
        if not task.drawing_id:
            raise ValueError("CAD review tasks require a drawing_id.")

        task.status = TaskStatus.RUNNING
        task.plan = [
            AgentStep(
                step_id="deepagent-1",
                name="Run Deep Agents CAD workflow",
                tool_name="cad_full_review",
                args={"drawing_id": task.drawing_id, "norm_query": task.norm_query},
            )
        ]
        task.touch()
        context = self.classic_runtime.middleware.before_task(task)
        self.classic_runtime.event_log.emit(
            task.task_id,
            EventType.PLAN_CREATED,
            "Deep Agents workflow plan created.",
            {"plan": [step.to_dict() for step in task.plan]},
        )

        try:
            result = await self.agent.ainvoke(
                {
                    "messages": [
                        {
                            "role": "user",
                            "content": (
                                "Run a complete CAD review by calling cad_full_review exactly once. "
                                f"drawing_id={task.drawing_id}. "
                                f"norm_query={task.norm_query or 'architectural drawing review'}. "
                                "After the tool returns, summarize the result without changing the data."
                            ),
                        }
                    ]
                }
            )
            structured_result = _extract_full_review_result(result)
            structured_result["events"] = self.classic_runtime.event_log.replay(task.task_id)
            structured_result["deepagent"] = {"raw_messages": _safe_messages(result)}
            structured_result["evaluation"] = evaluate_agent_run(structured_result)

            task.result = structured_result
            task.status = TaskStatus.SUCCEEDED
            task.plan[0].status = "succeeded"
            task.plan[0].result = {
                "review_id": structured_result.get("review_id"),
                "issue_count": structured_result.get("issue_count", 0),
            }
            task.touch()
            self.classic_runtime.middleware.after_task(context, structured_result)
            self.classic_runtime.event_log.emit(
                task.task_id,
                EventType.EVALUATION_FINISHED,
                "Deep Agents evaluation finished.",
                structured_result["evaluation"],
            )
            self.classic_runtime.event_log.emit(task.task_id, EventType.TASK_FINISHED, "Task finished.", task.to_dict())
        except Exception as exc:
            task.status = TaskStatus.FAILED
            task.error = str(exc)
            task.plan[0].status = "failed"
            task.plan[0].error = str(exc)
            task.touch()
            self.classic_runtime.event_log.emit(task.task_id, EventType.TASK_FAILED, "Task failed.", {"error": str(exc)})
        return task


def _build_model() -> Any:
    deepseek_api_key = os.getenv("DEEPSEEK_API_KEY")
    if deepseek_api_key:
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=os.getenv("DEEPAGENT_MODEL", "deepseek-v4-pro"),
            api_key=deepseek_api_key,
            base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        )
    return os.getenv("DEEPAGENT_MODEL", "openai:gpt-4.1")


def _extract_full_review_result(agent_result: Any) -> dict[str, Any]:
    for message in reversed(_messages(agent_result)):
        name = _message_attr(message, "name")
        if name != "cad_full_review":
            continue
        parsed = _parse_tool_content(_message_attr(message, "content"))
        if isinstance(parsed, dict):
            return parsed
    raise ValueError("Deep Agent finished without a structured cad_full_review tool result.")


def _messages(agent_result: Any) -> list[Any]:
    if isinstance(agent_result, dict):
        messages = agent_result.get("messages", [])
        return messages if isinstance(messages, list) else []
    messages = getattr(agent_result, "messages", [])
    return messages if isinstance(messages, list) else []


def _message_attr(message: Any, key: str) -> Any:
    if isinstance(message, dict):
        return message.get(key)
    return getattr(message, key, None)


def _parse_tool_content(content: Any) -> Any:
    if isinstance(content, dict):
        return content
    if isinstance(content, list):
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parsed = _parse_tool_content(item.get("text"))
                if parsed is not None:
                    return parsed
        return None
    if isinstance(content, str):
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return None
    return None


def _safe_messages(agent_result: Any) -> list[dict[str, Any]]:
    safe = []
    for message in _messages(agent_result):
        safe.append(
            {
                "type": message.__class__.__name__,
                "name": _message_attr(message, "name"),
                "content": _message_attr(message, "content"),
            }
        )
    return safe
