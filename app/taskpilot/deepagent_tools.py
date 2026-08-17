from __future__ import annotations

from typing import Any


def build_deepagent_tools(runtime: Any) -> list[Any]:
    from langchain_core.tools import tool

    @tool("cad_parse")
    def cad_parse(drawing_id: str) -> dict[str, Any]:
        """Read the structured summary and source path for an uploaded CAD drawing."""
        return runtime._tool_parse_drawing({"drawing_id": drawing_id})

    @tool("norm_search")
    def norm_search(query: str) -> dict[str, Any]:
        """Retrieve task-relevant clauses from uploaded standards."""
        return runtime._tool_search_norms({"query": query})

    @tool("cad_review")
    def cad_review(drawing_id: str, norm_query: str = "") -> dict[str, Any]:
        """Run deterministic architectural CAD review rules for an uploaded drawing."""
        result = runtime._tool_review_drawing({"drawing_id": drawing_id, "norm_query": norm_query})
        result.pop("issue_objects", None)
        return result

    @tool("cad_full_review")
    def cad_full_review(drawing_id: str, norm_query: str = "") -> dict[str, Any]:
        """Run the complete CAD review workflow and generate JSON, HTML, and repaired DXF outputs."""
        parse_result = runtime._tool_parse_drawing({"drawing_id": drawing_id})
        norm_result = runtime._tool_search_norms({"query": norm_query or "architectural drawing review"})
        review_result = runtime._tool_review_drawing({"drawing_id": drawing_id, "norm_query": norm_query})
        review_id = runtime.new_review_id()
        repair_result = runtime._tool_repair_drawing(
            {
                "review_id": review_id,
                "source_path": parse_result["source_path"],
                "issues": review_result["issue_objects"],
            }
        )
        report_result = runtime._tool_generate_report(
            {
                "review_id": review_id,
                "drawing_id": drawing_id,
                "drawing": review_result["drawing"],
                "issues": review_result["issues"],
                "issue_objects": review_result["issue_objects"],
                "norm_matches": norm_result["norm_matches"],
                "fixed_path": repair_result.get("output", ""),
            }
        )
        return runtime.compose_deepagent_result(review_result, norm_result, repair_result, report_result)

    return [cad_parse, norm_search, cad_review, cad_full_review]
