from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CadEntity:
    handle: str
    type: str
    layer: str = "0"
    text: str = ""
    points: list[tuple[float, float]] = field(default_factory=list)
    insert: tuple[float, float] | None = None
    height: float | None = None
    raw: list[tuple[str, str]] = field(default_factory=list)

    def bbox(self) -> list[float] | None:
        pts = list(self.points)
        if self.insert:
            pts.append(self.insert)
        if not pts:
            return None
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        return [min(xs), min(ys), max(xs), max(ys)]


@dataclass
class DrawingModel:
    filename: str
    raw_text: str
    entities: list[CadEntity]

    @property
    def layers(self) -> list[str]:
        return sorted({e.layer for e in self.entities if e.layer})

    def to_summary(self) -> dict[str, Any]:
        counts: dict[str, int] = {}
        for entity in self.entities:
            counts[entity.type] = counts.get(entity.type, 0) + 1
        return {
            "filename": self.filename,
            "entity_count": len(self.entities),
            "layers": self.layers,
            "entity_counts": counts,
        }


@dataclass
class NormDocument:
    doc_id: str
    filename: str
    text: str
    chunks: list[dict[str, Any]]


@dataclass
class Issue:
    issue_id: str
    severity: str
    category: str
    title: str
    evidence: list[str]
    suggestion: str
    location: dict[str, Any] = field(default_factory=dict)
    rule_reference: dict[str, Any] = field(default_factory=dict)
    auto_fix: bool = False
    requires_confirmation: bool = False
    fix: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "issue_id": self.issue_id,
            "severity": self.severity,
            "category": self.category,
            "title": self.title,
            "evidence": self.evidence,
            "suggestion": self.suggestion,
            "location": self.location,
            "rule_reference": self.rule_reference,
            "auto_fix": self.auto_fix,
            "requires_confirmation": self.requires_confirmation,
            "fix": self.fix,
        }
