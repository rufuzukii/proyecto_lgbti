from __future__ import annotations


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


def clean_cell(row: list[str], index: int) -> str:
    if index >= len(row):
        return ""
    return row[index].strip()
