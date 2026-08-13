from __future__ import annotations

from pathlib import Path

from .models import CadEntity, DrawingModel


ENTITY_TYPES = {
    "LINE",
    "LWPOLYLINE",
    "POLYLINE",
    "VERTEX",
    "TEXT",
    "MTEXT",
    "INSERT",
    "DIMENSION",
    "CIRCLE",
    "ARC",
}


def read_dxf(path: Path) -> DrawingModel:
    raw_text = path.read_text(errors="ignore")
    pairs = _parse_group_pairs(raw_text)
    entities = _extract_entities(pairs)
    return DrawingModel(filename=path.name, raw_text=raw_text, entities=entities)


def _parse_group_pairs(raw_text: str) -> list[tuple[str, str]]:
    lines = raw_text.splitlines()
    pairs: list[tuple[str, str]] = []
    for index in range(0, len(lines) - 1, 2):
        pairs.append((lines[index].strip(), lines[index + 1].rstrip("\n")))
    return pairs


def _extract_entities(pairs: list[tuple[str, str]]) -> list[CadEntity]:
    entities: list[CadEntity] = []
    current: list[tuple[str, str]] | None = None
    current_type = ""

    for code, value in pairs:
        if code == "0" and value in ENTITY_TYPES:
            if current and current_type:
                parsed = _entity_from_pairs(current_type, current)
                if parsed:
                    entities.append(parsed)
            current_type = value
            current = [(code, value)]
            continue

        if code == "0" and value in {"ENDSEC", "EOF", "SEQEND"}:
            if current and current_type:
                parsed = _entity_from_pairs(current_type, current)
                if parsed:
                    entities.append(parsed)
            current = None
            current_type = ""
            continue

        if current is not None:
            current.append((code, value))

    if current and current_type:
        parsed = _entity_from_pairs(current_type, current)
        if parsed:
            entities.append(parsed)

    return entities


def _entity_from_pairs(entity_type: str, pairs: list[tuple[str, str]]) -> CadEntity | None:
    layer = _first(pairs, "8") or "0"
    handle = _first(pairs, "5") or f"{entity_type}-{abs(hash(tuple(pairs))) % 1000000}"
    text = _first(pairs, "1") or _first(pairs, "3") or ""
    height = _float_or_none(_first(pairs, "40"))

    xs = [_float(v) for code, v in pairs if code == "10"]
    ys = [_float(v) for code, v in pairs if code == "20"]
    x2s = [_float(v) for code, v in pairs if code == "11"]
    y2s = [_float(v) for code, v in pairs if code == "21"]

    points: list[tuple[float, float]] = []
    if entity_type == "LINE" and xs and ys:
        points.append((xs[0], ys[0]))
        if x2s and y2s:
            points.append((x2s[0], y2s[0]))
    elif xs and ys:
        points.extend((x, y) for x, y in zip(xs, ys))

    insert = points[0] if entity_type in {"TEXT", "MTEXT", "INSERT"} and points else None
    return CadEntity(
        handle=handle,
        type=entity_type,
        layer=layer,
        text=_clean_mtext(text),
        points=points,
        insert=insert,
        height=height,
        raw=pairs,
    )


def _first(pairs: list[tuple[str, str]], code: str) -> str | None:
    for pair_code, value in pairs:
        if pair_code == code:
            return value.strip()
    return None


def _float(value: str) -> float:
    try:
        return float(value.strip())
    except ValueError:
        return 0.0


def _float_or_none(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value.strip())
    except ValueError:
        return None


def _clean_mtext(text: str) -> str:
    return (
        text.replace("\\P", " ")
        .replace("{", "")
        .replace("}", "")
        .replace("\\~", " ")
        .strip()
    )
