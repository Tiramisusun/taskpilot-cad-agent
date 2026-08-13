from __future__ import annotations

from typing import Any


def evaluate_agent_run(result: dict[str, Any]) -> dict[str, Any]:
    issues = result.get("issues", [])
    events = result.get("events", [])
    downloads = result.get("downloads", {})
    failed_steps = result.get("failed_steps", [])

    score = 1.0
    if failed_steps:
        score -= 0.4
    if not downloads:
        score -= 0.2
    if not events:
        score -= 0.1

    return {
        "score": max(0.0, round(score, 2)),
        "issue_count": len(issues),
        "auto_fixable_count": sum(1 for issue in issues if issue.get("auto_fix")),
        "high_risk_count": sum(1 for issue in issues if issue.get("severity") == "high"),
        "failed_step_count": len(failed_steps),
        "checks": {
            "has_report": bool(downloads.get("html") and downloads.get("json")),
            "has_fix_output": bool(downloads.get("fixed_dxf")),
            "has_events": bool(events),
        },
    }
