from __future__ import annotations

import re

from zml_ocr_worker.pipelines.mining_finder.model import FinderStatusKind
from zml_ocr_worker.pipelines.text import (
    clean_ocr_text,
    last_int,
    normalize_ocr_text_for_parse,
)


def classify_status(text: str) -> FinderStatusKind | None:
    normalized = normalize_ocr_text_for_parse(text)
    if not normalized:
        return None
    if "sending" in normalized and "probe" in normalized:
        return "sending_probe"
    if "searching" in normalized:
        return "searching"
    if "no resources found" in normalized:
        return "no_resources"
    if "found" in normalized and "resource" in normalized:
        return "found"
    if "press" in normalized and "survey" in normalized:
        return "idle"
    return None


def parse_units_text(text: str) -> tuple[int | None, int | None]:
    normalized = normalize_ocr_text_for_parse(text)
    number = last_int(text)
    if number is None:
        return None, None
    if "probe" in normalized and "ammo" not in normalized:
        return number, None
    return None, number


def parse_hit_size(text: str) -> tuple[str | None, int | None]:
    match = re.search(
        r"(?:estimated\s+)?size\s*:\s*([a-z ]+?)\s*\(?\s*(\d+)\s*\)?",
        normalize_ocr_text_for_parse(text),
    )
    if match is None:
        return None, None

    label = " ".join(word.capitalize() for word in match.group(1).split())
    try:
        return label, int(match.group(2))
    except ValueError:
        return label, None


def parse_details_text(text: str) -> tuple[float | None, float | None, str | None]:
    cleaned = clean_ocr_text(text) or ""
    normalized = normalize_ocr_text_for_parse(cleaned)

    range_m = _parse_float_after_label(normalized, "range")
    depth_m = _parse_float_after_label(normalized, "depth")
    resource_name = _parse_resource_name(cleaned)

    return range_m, depth_m, resource_name


def _parse_float_after_label(text: str, label: str) -> float | None:
    match = re.search(rf"{label}\s*([0-9]+(?:[\.,][0-9]+)?)\s*m?", text)
    if match is None:
        return None
    try:
        return float(match.group(1).replace(",", "."))
    except ValueError:
        return None


def _parse_resource_name(text: str) -> str | None:
    for line in text.splitlines():
        match = re.search(r"\bTYPE\s+(.+)$", line.strip(), flags=re.IGNORECASE)
        if match is not None:
            value = " ".join(match.group(1).split())
            return value or None
    return None
