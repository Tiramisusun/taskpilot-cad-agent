from __future__ import annotations

import re
from pathlib import Path
from uuid import uuid4

from .models import NormDocument


KEYWORDS = {
    "door_width": ["door width", "clear width", "exit door", "door"],
    "egress": ["egress", "exit", "stair", "travel distance"],
    "area": ["area", "room", "usable area"],
    "fire": ["fire", "fire rating", "fire door", "fire compartment"],
    "accessibility": ["accessibility", "wheelchair", "ramp", "accessible restroom"],
    "annotation": ["annotation", "title", "number", "text", "label"],
}


def load_norm(path: Path) -> NormDocument:
    text = path.read_text(errors="ignore")
    chunks = chunk_norm_text(text)
    return NormDocument(doc_id=uuid4().hex, filename=path.name, text=text, chunks=chunks)


def chunk_norm_text(text: str, chunk_size: int = 900) -> list[dict]:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if not cleaned:
        return []
    chunks = []
    for index in range(0, len(cleaned), chunk_size):
        body = cleaned[index : index + chunk_size]
        chunks.append({"chunk_id": len(chunks) + 1, "text": body})
    return chunks


def search_norms(norms: list[NormDocument], query: str, limit: int = 5) -> list[dict]:
    terms = [term for term in re.split(r"\W+", query.lower()) if term]
    expanded = set(terms)
    for words in KEYWORDS.values():
        if any(word in query for word in words):
            expanded.update(words)

    scored = []
    for norm in norms:
        for chunk in norm.chunks:
            chunk_text = chunk["text"]
            score = sum(chunk_text.lower().count(term.lower()) for term in expanded)
            if score:
                scored.append(
                    {
                        "score": score,
                        "document": norm.filename,
                        "chunk_id": chunk["chunk_id"],
                        "text": chunk_text,
                    }
                )
    return sorted(scored, key=lambda item: item["score"], reverse=True)[:limit]


def infer_rule_categories(norms: list[NormDocument], query: str) -> list[str]:
    source = " ".join([query] + [norm.text[:5000] for norm in norms])
    categories = []
    for category, words in KEYWORDS.items():
        if any(word in source for word in words):
            categories.append(category)
    return categories or ["annotation", "area"]
