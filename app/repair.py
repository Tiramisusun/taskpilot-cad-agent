from __future__ import annotations

from pathlib import Path

from .cad_parser import ENTITY_TYPES
from .models import Issue


def apply_low_risk_fixes(source: Path, destination: Path, issues: list[Issue]) -> dict:
    text = source.read_text(errors="ignore")
    applied = []
    delete_handles = []
    text_heights = {}

    for issue in issues:
        if not issue.auto_fix or issue.requires_confirmation or not issue.fix:
            continue
        action = issue.fix.get("action")
        if action == "rename_layer":
            old = str(issue.fix["from"])
            new = str(issue.fix["to"])
            text = _replace_layer_value(text, old, new)
            applied.append({"issue_id": issue.issue_id, "action": action, "from": old, "to": new})
        elif action == "set_text_height":
            height = str(issue.fix["height"])
            for handle in issue.fix.get("handles", []):
                text_heights[str(handle)] = height
            applied.append({"issue_id": issue.issue_id, "action": action, "height": height})
        elif action == "delete_entities":
            handles = [str(handle) for handle in issue.fix.get("handles", [])]
            delete_handles.extend(handles)
            applied.append({"issue_id": issue.issue_id, "action": action, "handles": handles})

    if delete_handles or text_heights:
        text = _rewrite_entities(text, set(delete_handles), text_heights)

    destination.write_text(text)
    return {"applied": applied, "output": str(destination)}


def _replace_layer_value(raw_text: str, old: str, new: str) -> str:
    lines = raw_text.splitlines()
    for index in range(len(lines) - 1):
        if lines[index].strip() == "8" and lines[index + 1].strip() == old:
            lines[index + 1] = new
    return "\n".join(lines) + "\n"


def _rewrite_entities(raw_text: str, delete_handles: set[str], text_heights: dict[str, str]) -> str:
    pairs = _pairs(raw_text)
    output: list[tuple[str, str]] = []
    index = 0

    while index < len(pairs):
        code, value = pairs[index]
        if code == "0" and value in ENTITY_TYPES:
            entity_pairs = [(code, value)]
            index += 1
            while index < len(pairs) and not (pairs[index][0] == "0" and pairs[index][1] in ENTITY_TYPES | {"ENDSEC", "EOF", "SEQEND"}):
                entity_pairs.append(pairs[index])
                index += 1

            handle = _pair_value(entity_pairs, "5")
            if handle in delete_handles:
                continue
            if handle in text_heights:
                entity_pairs = _set_group_value(entity_pairs, "40", text_heights[handle])
            output.extend(entity_pairs)
            continue

        output.append((code, value))
        index += 1

    return "\n".join(item for pair in output for item in pair) + "\n"


def _pairs(raw_text: str) -> list[tuple[str, str]]:
    lines = raw_text.splitlines()
    return [(lines[index].strip(), lines[index + 1]) for index in range(0, len(lines) - 1, 2)]


def _pair_value(pairs: list[tuple[str, str]], code: str) -> str | None:
    for pair_code, value in pairs:
        if pair_code == code:
            return value.strip()
    return None


def _set_group_value(pairs: list[tuple[str, str]], code: str, value: str) -> list[tuple[str, str]]:
    updated = []
    replaced = False
    for pair_code, pair_value in pairs:
        if pair_code == code:
            updated.append((pair_code, value))
            replaced = True
        else:
            updated.append((pair_code, pair_value))
    if not replaced:
        updated.extend([(code, value)])
    return updated
