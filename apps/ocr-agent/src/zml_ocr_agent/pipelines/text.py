from __future__ import annotations

import re


def clean_ocr_text(text: str) -> str | None:
    normalized = "\n".join(line.strip() for line in text.splitlines() if line.strip())
    return normalized or None


def digits_only(text: str) -> str:
    return "".join(ch for ch in text if "0" <= ch <= "9")


def last_int(text: str) -> int | None:
    matches = re.findall(r"\d+", text)
    if not matches:
        return None
    try:
        return int(matches[-1])
    except ValueError:
        return None


def normalize_ocr_text_for_parse(text: str) -> str:
    return " ".join(text.lower().replace("|", " ").replace(";", " ").split())
