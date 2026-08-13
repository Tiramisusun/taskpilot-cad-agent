from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class MemoryStore:
    path: Path
    user_preferences: dict[str, Any] = field(default_factory=dict)
    task_facts: list[dict[str, Any]] = field(default_factory=list)
    historical_results: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path) -> "MemoryStore":
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            return cls(path=path)
        data = json.loads(path.read_text() or "{}")
        return cls(
            path=path,
            user_preferences=data.get("user_preferences", {}),
            task_facts=data.get("task_facts", []),
            historical_results=data.get("historical_results", []),
        )

    def inject_context(self, objective: str) -> dict[str, Any]:
        recent_results = self.historical_results[-5:]
        relevant_facts = [
            fact for fact in self.task_facts[-20:] if _overlap(objective, fact.get("text", ""))
        ]
        return {
            "user_preferences": self.user_preferences,
            "relevant_facts": relevant_facts,
            "recent_results": recent_results,
        }

    def remember_task_result(self, task_id: str, objective: str, result: dict[str, Any]) -> None:
        self.historical_results.append(
            {
                "task_id": task_id,
                "objective": objective,
                "summary": result.get("summary", ""),
                "issue_count": result.get("issue_count", 0),
            }
        )
        self._save()

    def remember_fact(self, text: str, source: str) -> None:
        self.task_facts.append({"text": text, "source": source})
        self._save()

    def _save(self) -> None:
        payload = {
            "user_preferences": self.user_preferences,
            "task_facts": self.task_facts[-200:],
            "historical_results": self.historical_results[-100:],
        }
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))


def _overlap(left: str, right: str) -> bool:
    return any(token and token in right for token in left.split())
