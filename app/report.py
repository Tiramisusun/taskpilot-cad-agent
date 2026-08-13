from __future__ import annotations

import html
import json
from pathlib import Path

from .models import DrawingModel, Issue


def write_json_report(path: Path, drawing: DrawingModel, issues: list[Issue], norm_matches: list[dict]) -> None:
    payload = {
        "drawing": drawing.to_summary(),
        "issue_count": len(issues),
        "issues": [issue.to_dict() for issue in issues],
        "norm_matches": norm_matches,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))


def write_html_report(path: Path, drawing: DrawingModel, issues: list[Issue], norm_matches: list[dict]) -> None:
    issue_rows = "\n".join(_issue_row(issue) for issue in issues)
    norm_rows = "\n".join(
        f"<li><strong>{html.escape(match['document'])}</strong> #{match['chunk_id']}: "
        f"{html.escape(match['text'][:260])}</li>"
        for match in norm_matches
    )
    body = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>CAD Review Report</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 32px; color: #1f2937; }}
    h1 {{ font-size: 26px; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 16px; }}
    th, td {{ border: 1px solid #d1d5db; padding: 10px; vertical-align: top; }}
    th {{ background: #f3f4f6; text-align: left; }}
    .high {{ color: #b91c1c; font-weight: 700; }}
    .medium {{ color: #b45309; font-weight: 700; }}
    .low {{ color: #047857; font-weight: 700; }}
    .info {{ color: #2563eb; font-weight: 700; }}
  </style>
</head>
<body>
  <h1>CAD Review Report</h1>
  <p>Drawing: {html.escape(drawing.filename)}; Entities: {len(drawing.entities)}; Issues: {len(issues)}</p>
  <h2>Issue List</h2>
  <table>
    <thead><tr><th>ID</th><th>Severity</th><th>Category</th><th>Issue</th><th>Evidence</th><th>Suggestion</th><th>Auto Fix</th></tr></thead>
    <tbody>{issue_rows}</tbody>
  </table>
  <h2>Referenced Standards</h2>
  <ul>{norm_rows}</ul>
</body>
</html>"""
    path.write_text(body)


def _issue_row(issue: Issue) -> str:
    evidence = "<br>".join(html.escape(item) for item in issue.evidence)
    return (
        f"<tr><td>{issue.issue_id}</td><td class='{html.escape(issue.severity)}'>{html.escape(issue.severity)}</td>"
        f"<td>{html.escape(issue.category)}</td><td>{html.escape(issue.title)}</td>"
        f"<td>{evidence}</td><td>{html.escape(issue.suggestion)}</td>"
        f"<td>{'Yes' if issue.auto_fix else 'No'}</td></tr>"
    )
