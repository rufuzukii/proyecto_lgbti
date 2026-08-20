from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from pymongo import UpdateOne

from app.analytics.country_status_admin_service import (
    COUNTRY_LGBTI_STATUS_DATASET,
    validate_country_lgbti_status_payload,
)
from app.analytics.repository import invalidate_analytics_cache
from app.cache import cache
from app.mongo import get_mongo_collection

COUNTRY_STATUS_COLLECTION = "country_lgbti_status"

_COUNTRY_HEADING = re.compile(r"^##\s+(.+?)\s+\(([A-Z]{2})\)\s*$", re.MULTILINE)
_REVIEW_YEAR = re.compile(r"Annual Review\s+(20\d{2})", re.IGNORECASE)
_FIELD_LABELS = {
    "Estado general": "title",
    "Descripción": "summary",
    "Contexto legal": "legal_context",
    "Contexto social": "social_context",
    "Organización o informe": "source_name",
    "Enlace de la fuente": "source_url",
    "Fecha de actualización": "reviewed_at",
    "Observaciones": "observations",
}
_LIST_LABELS = {
    "Avances destacados": "positive_developments",
    "Retos principales": "main_challenges",
}


class CountryStatusMarkdownError(ValueError):
    """Raised when the country-context Markdown does not match the expected schema."""


def parse_country_status_markdown(path: str | Path) -> list[dict[str, Any]]:
    source_path = Path(path)
    return parse_country_status_markdown_text(source_path.read_text(encoding="utf-8"))


def parse_country_status_markdown_text(markdown: str) -> list[dict[str, Any]]:
    year_match = _REVIEW_YEAR.search(markdown)
    if not year_match:
        raise CountryStatusMarkdownError("No se encontró el año de Annual Review.")
    year = int(year_match.group(1))

    headings = list(_COUNTRY_HEADING.finditer(markdown))
    if not headings:
        raise CountryStatusMarkdownError("No se encontraron fichas de países.")

    records: list[dict[str, Any]] = []
    seen_codes: set[str] = set()
    for index, heading in enumerate(headings):
        country = heading.group(1).strip()
        country_code = heading.group(2)
        if country_code in seen_codes:
            raise CountryStatusMarkdownError(f"Código de país duplicado: {country_code}.")
        seen_codes.add(country_code)

        end = headings[index + 1].start() if index + 1 < len(headings) else len(markdown)
        block = markdown[heading.end() : end]
        payload: dict[str, Any] = {
            "dataset": COUNTRY_LGBTI_STATUS_DATASET,
            "country": country,
            "country_code": country_code,
            "year": year,
            "active": True,
        }
        missing_fields: list[str] = []

        for label, key in _FIELD_LABELS.items():
            value = _extract_text_field(block, label)
            if not value:
                missing_fields.append(label)
            payload[key] = value

        for label, key in _LIST_LABELS.items():
            values = _extract_list_field(block, label)
            if not values:
                missing_fields.append(label)
            payload[key] = values

        if missing_fields:
            joined = ", ".join(missing_fields)
            raise CountryStatusMarkdownError(
                f"La ficha de {country} ({country_code}) no contiene: {joined}."
            )

        try:
            records.append(validate_country_lgbti_status_payload(payload))
        except ValueError as exc:
            raise CountryStatusMarkdownError(
                f"La ficha de {country} ({country_code}) no es válida."
            ) from exc

    return records


def import_country_status_records(records: list[dict[str, Any]]) -> dict[str, int]:
    if not records:
        return {"matched": 0, "modified": 0, "upserted": 0}

    operations = [
        UpdateOne(
            {"country_code": record["country_code"], "year": record["year"]},
            {"$set": record},
            upsert=True,
        )
        for record in records
    ]
    result = get_mongo_collection(COUNTRY_STATUS_COLLECTION).bulk_write(
        operations,
        ordered=False,
    )
    if getattr(cache, "app", None):
        invalidate_analytics_cache("country_status")
    return {
        "matched": int(result.matched_count),
        "modified": int(result.modified_count),
        "upserted": int(result.upserted_count),
    }


def _extract_text_field(block: str, label: str) -> str:
    pattern = re.compile(
        rf"^\*\*{re.escape(label)}:\*\*\s*(.+?)\s*$",
        re.MULTILINE,
    )
    match = pattern.search(block)
    return match.group(1).strip() if match else ""


def _extract_list_field(block: str, label: str) -> list[str]:
    pattern = re.compile(
        rf"^\*\*{re.escape(label)}:\*\*\s*$\n(?P<body>.*?)(?=\n\s*\n|\n###|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(block)
    if not match:
        return []
    return [
        item.strip()
        for item in re.findall(r"^-\s+(.+?)\s*$", match.group("body"), re.MULTILINE)
        if item.strip()
    ]
