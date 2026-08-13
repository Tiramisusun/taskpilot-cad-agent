from __future__ import annotations

import math
import re
from collections import defaultdict

from .models import DrawingModel, Issue, NormDocument
from .norms import infer_rule_categories, search_norms


STANDARD_LAYER_HINTS = {
    "wall": "A-WALL",
    "door": "A-DOOR",
    "window": "A-WINDOW",
    "text": "A-ANNO-TEXT",
    "anno": "A-ANNO-TEXT",
    "dim": "A-ANNO-DIMS",
    "axis": "A-GRID",
    "grid": "A-GRID",
}


def review_drawing(drawing: DrawingModel, norms: list[NormDocument], query: str = "") -> list[Issue]:
    issues: list[Issue] = []
    categories = set(infer_rule_categories(norms, query))
    issue_index = 1

    for issue in _check_layers(drawing):
        issue.issue_id = f"CAD-{issue_index:03d}"
        issue_index += 1
        issues.append(issue)

    for issue in _check_duplicate_lines(drawing):
        issue.issue_id = f"CAD-{issue_index:03d}"
        issue_index += 1
        issues.append(issue)

    if "annotation" in categories or "area" in categories:
        for issue in _check_text_and_room_labels(drawing):
            issue.issue_id = f"CAD-{issue_index:03d}"
            issue_index += 1
            issues.append(issue)

    if "door_width" in categories:
        for issue in _check_door_width_text(drawing):
            issue.issue_id = f"CAD-{issue_index:03d}"
            issue.rule_reference = _reference_for(norms, "door width clear width exit door")
            issue_index += 1
            issues.append(issue)

    if "egress" in categories:
        for issue in _check_egress_markers(drawing):
            issue.issue_id = f"CAD-{issue_index:03d}"
            issue.rule_reference = _reference_for(norms, "egress exit stair travel distance")
            issue_index += 1
            issues.append(issue)

    if "fire" in categories:
        for issue in _check_fire_markers(drawing):
            issue.issue_id = f"CAD-{issue_index:03d}"
            issue.rule_reference = _reference_for(norms, "fire fire door fire compartment")
            issue_index += 1
            issues.append(issue)

    return issues


def _check_layers(drawing: DrawingModel) -> list[Issue]:
    issues = []
    for layer in drawing.layers:
        normalized = layer.strip().upper()
        if layer == "0":
            affected = [e.handle for e in drawing.entities if e.layer == layer][:30]
            issues.append(
                Issue(
                    issue_id="",
                    severity="medium",
                    category="layer",
                    title="Objects placed on layer 0",
                    evidence=[f"Detected {len(affected)} objects on layer 0 or the default layer."],
                    suggestion="Move objects to standard layers by type, such as wall, door/window, or annotation layers.",
                    auto_fix=True,
                    requires_confirmation=True,
                    fix={"action": "infer_layers", "handles": affected},
                )
            )
        elif normalized != layer or " " in layer:
            issues.append(
                Issue(
                    issue_id="",
                    severity="low",
                    category="layer",
                    title="Layer naming format is inconsistent",
                    evidence=[f"Layer `{layer}` contains casing or whitespace issues."],
                    suggestion=f"Rename it to `{normalized.replace(' ', '-')}`.",
                    auto_fix=True,
                    fix={"action": "rename_layer", "from": layer, "to": normalized.replace(" ", "-")},
                )
            )
    return issues


def _check_duplicate_lines(drawing: DrawingModel) -> list[Issue]:
    buckets: dict[tuple, list[str]] = defaultdict(list)
    for entity in drawing.entities:
        if entity.type != "LINE" or len(entity.points) < 2:
            continue
        p1, p2 = entity.points[:2]
        key = tuple(sorted([_round_point(p1), _round_point(p2)]))
        buckets[key].append(entity.handle)

    issues = []
    for handles in buckets.values():
        if len(handles) > 1:
            issues.append(
                Issue(
                    issue_id="",
                    severity="low",
                    category="geometry",
                    title="Duplicate line entities detected",
                    evidence=[f"Lines {', '.join(handles[:5])} share the same geometry."],
                    suggestion="Keep one line and remove the duplicate entities.",
                    auto_fix=True,
                    fix={"action": "delete_entities", "handles": handles[1:]},
                )
            )
    return issues


def _check_text_and_room_labels(drawing: DrawingModel) -> list[Issue]:
    text_entities = [e for e in drawing.entities if e.type in {"TEXT", "MTEXT"}]
    issues = []
    tiny_text = [e for e in text_entities if e.height is not None and e.height < 100]
    if tiny_text:
        issues.append(
            Issue(
                issue_id="",
                severity="low",
                category="annotation",
                title="Text height may be too small",
                evidence=[f"Detected {len(tiny_text)} text entities with height below 100 drawing units."],
                suggestion="Normalize text height to improve plot readability.",
                auto_fix=True,
                fix={"action": "set_text_height", "handles": [e.handle for e in tiny_text], "height": 250},
            )
        )

    room_texts = [e for e in text_entities if re.search(r"(office|room|hall|lobby|bedroom|kitchen|toilet|restroom)", e.text, re.I)]
    area_texts = [e for e in text_entities if re.search(r"(\d+(\.\d+)?\s*(m2|sqm|sq\.?\s*m|square\s*meters?))", e.text, re.I)]
    if room_texts and len(area_texts) < max(1, math.ceil(len(room_texts) * 0.4)):
        issues.append(
            Issue(
                issue_id="",
                severity="medium",
                category="area",
                title="Room area annotations may be missing",
                evidence=[f"Detected {len(room_texts)} room-name labels but only {len(area_texts)} area annotations."],
                suggestion="Add room area annotations or check whether the area annotation layer is missing.",
                auto_fix=False,
                requires_confirmation=True,
            )
        )
    if not room_texts:
        issues.append(
            Issue(
                issue_id="",
                severity="medium",
                category="annotation",
                title="No clear room labels detected",
                evidence=["No common room-name text was detected in the DXF."],
                suggestion="Check whether labels are block attributes, external references, or PDF underlays, and add room labels if needed.",
                auto_fix=False,
                requires_confirmation=True,
            )
        )
    return issues


def _check_door_width_text(drawing: DrawingModel) -> list[Issue]:
    issues = []
    for entity in drawing.entities:
        if entity.type not in {"TEXT", "MTEXT"}:
            continue
        match = re.search(r"(door\s*width|clear\s*width|width|W)\D*(\d{2,4})", entity.text, re.I)
        if match and int(match.group(2)) < 900:
            issues.append(
                Issue(
                    issue_id="",
                    severity="high",
                    category="door_width",
                    title="Door clear width may be insufficient",
                    evidence=[f"Text `{entity.text}` indicates a width below 900 mm."],
                    suggestion="Review the door opening clear width and adjust the door size or type if needed.",
                    location={"bbox": entity.bbox(), "handle": entity.handle},
                    auto_fix=False,
                    requires_confirmation=True,
                )
            )
    if not issues:
        door_like = [e for e in drawing.entities if "door" in e.layer.lower() or "door" in e.text.lower()]
        if door_like:
            issues.append(
                Issue(
                    issue_id="",
                    severity="info",
                    category="door_width",
                    title="Door width requires manual review",
                    evidence=[f"Detected {len(door_like)} door-related objects but could not reliably read clear width dimensions."],
                    suggestion="Add door width annotations or integrate more precise door block recognition rules.",
                    auto_fix=False,
                    requires_confirmation=True,
                )
            )
    return issues


def _check_egress_markers(drawing: DrawingModel) -> list[Issue]:
    text = " ".join(e.text for e in drawing.entities if e.text)
    lower_text = text.lower()
    has_exit = any(word in lower_text for word in ["exit", "egress exit", "emergency exit"])
    has_stair = any(word in lower_text for word in ["stair", "egress stair", "staircase"])
    issues = []
    if not has_exit:
        issues.append(
            Issue(
                issue_id="",
                severity="high",
                category="egress",
                title="No exit annotation detected",
                evidence=["No exit or egress exit text was found in the drawing."],
                suggestion="Review egress exit annotations and add exit symbols or text where needed.",
                auto_fix=False,
                requires_confirmation=True,
            )
        )
    if not has_stair:
        issues.append(
            Issue(
                issue_id="",
                severity="medium",
                category="egress",
                title="No stair annotation detected",
                evidence=["No stair-related annotation was found in the drawing text."],
                suggestion="Check whether stair labels are missing, stored in external references, or need to be added.",
                auto_fix=False,
                requires_confirmation=True,
            )
        )
    return issues


def _check_fire_markers(drawing: DrawingModel) -> list[Issue]:
    text = " ".join(e.text for e in drawing.entities if e.text)
    lower_text = text.lower()
    if any(word in lower_text for word in ["fire door", "fire rating", "fire compartment", "rated door"]):
        return []
    return [
        Issue(
            issue_id="",
            severity="medium",
            category="fire",
            title="Fire-safety annotations may be missing",
            evidence=["No fire door rating or fire compartment annotation was detected."],
            suggestion="Review fire doors, fire compartments, and fire-safety annotations against the selected standards.",
            auto_fix=False,
            requires_confirmation=True,
        )
    ]


def _reference_for(norms: list[NormDocument], query: str) -> dict:
    matches = search_norms(norms, query, limit=1)
    if not matches:
        return {}
    match = matches[0]
    return {
        "document": match["document"],
        "chunk_id": match["chunk_id"],
        "excerpt": match["text"][:240],
    }


def _round_point(point: tuple[float, float]) -> tuple[int, int]:
    return (round(point[0]), round(point[1]))
