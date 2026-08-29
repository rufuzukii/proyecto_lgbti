from __future__ import annotations

import math
import re
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit

from app.shared.data.normalization import normalize_header

FRA_METADATA_LABELS = frozenset(
    {
        "date",
        "fecha",
        "filters",
        "filtros",
        "general_disclaimer_of_the_fra_website",
        "hyperlink",
        "indicator_code",
        "link",
        "note",
        "nota",
        "question_code",
        "codigo_pregunta",
        "source",
        "fuente",
        "url",
    }
)

FRA_FOOTNOTE_SYMBOLS = frozenset({"¹", "‡"})

# ``ą`` is the mojibake value already found in MongoDB for the superscript ``¹``.
FRA_FOOTNOTE_MOJIBAKE = frozenset({"ą"})

INVALID_FRA_CATEGORIES = frozenset(
    {
        "Date:",
        "Filters:",
        "General Disclaimer of the FRA website:",
        "Hyperlink:",
        "Note:",
        "Question Code:",
        "Source:",
        *FRA_FOOTNOTE_SYMBOLS,
        *FRA_FOOTNOTE_MOJIBAKE,
    }
)


def fra_metadata_key(value: object) -> str | None:
    clean = _clean(value)
    if not clean:
        return None
    normalized = normalize_header(clean.rstrip(":"))
    return normalized if normalized in FRA_METADATA_LABELS else None


def is_fra_footnote_symbol(value: object) -> bool:
    clean = _clean(value)
    if clean in FRA_FOOTNOTE_SYMBOLS or clean in FRA_FOOTNOTE_MOJIBAKE:
        return True
    return bool(clean and len(clean) <= 4 and not any(character.isalnum() for character in clean))


def is_valid_fra_category(value: object) -> bool:
    clean = _clean(value)
    if not clean or clean in INVALID_FRA_CATEGORIES:
        return False
    if is_fra_footnote_symbol(clean) or fra_metadata_key(clean):
        return False
    return not _looks_like_url(clean)


def has_valid_fra_statistic_answer(document: Mapping[str, Any]) -> bool:
    code = _clean(document.get("code"))
    question = _clean(document.get("question"))
    answers = document.get("answers")
    if not code or not question or not isinstance(answers, list):
        return False
    return any(isinstance(answer, Mapping) and is_valid_fra_answer(answer) for answer in answers)


def is_valid_fra_answer(answer: Mapping[str, Any]) -> bool:
    country = _clean(answer.get("country"))
    country_code = _clean(answer.get("country_code"))
    response = _clean(answer.get("answer"))
    percentage = answer.get("percentage")
    if not (country or country_code) or not response or isinstance(percentage, bool):
        return False
    if percentage is None:
        return True
    try:
        numeric = float(percentage)
    except TypeError, ValueError:
        return False
    return math.isfinite(numeric) and 0 <= numeric <= 100


def _looks_like_url(value: str) -> bool:
    clean = value.strip()
    if re.match(r"^(?:https?://|www\.)", clean, flags=re.IGNORECASE):
        return True
    parsed = urlsplit(clean)
    return parsed.scheme.casefold() in {"http", "https"} and bool(parsed.netloc)


def _clean(value: object) -> str:
    return "" if value is None else str(value).strip()
