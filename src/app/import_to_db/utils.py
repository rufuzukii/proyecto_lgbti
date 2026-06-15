from __future__ import annotations

import re
import unicodedata


def parse_float(value: str | None) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    cleaned = text.replace("%", "").replace(" ", "")
    cleaned = cleaned.replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def normalize_header(text: str) -> str:
    ascii_text = (
        unicodedata.normalize("NFKD", text.strip().lower())
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    return re.sub(r"[^a-z0-9]+", "_", ascii_text).strip("_")


def clean_cell(row: list[str], index: int) -> str:
    if index >= len(row):
        return ""
    return row[index].strip()

