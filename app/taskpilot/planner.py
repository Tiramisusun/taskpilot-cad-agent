from __future__ import annotations

from .schemas import AgentStep


def build_plan(drawing_id: str, norm_query: str) -> list[AgentStep]:
    return [
        AgentStep(
            step_id="step-1",
            name="Parse CAD drawing",
            tool_name="cad.parse",
            args={"drawing_id": drawing_id},
        ),
        AgentStep(
            step_id="step-2",
            name="Retrieve relevant standards",
            tool_name="norm.search",
            args={"query": norm_query or "architectural drawing review"},
        ),
        AgentStep(
            step_id="step-3",
            name="Run CAD review rules",
            tool_name="cad.review",
            args={"drawing_id": drawing_id, "norm_query": norm_query},
        ),
        AgentStep(
            step_id="step-4",
            name="Generate repaired drawing",
            tool_name="cad.repair",
            args={},
        ),
        AgentStep(
            step_id="step-5",
            name="Generate review report",
            tool_name="report.generate",
            args={},
        ),
    ]
