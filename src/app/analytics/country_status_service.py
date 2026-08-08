from __future__ import annotations

from typing import Any

import bleach

from app.analytics.repository import get_country_lgbti_status_records
from app.analytics.statistics_normalizers import (
    normalize_country_code,
    repair_text_encoding,
)
from app.source_attribution import ILGA_ANNUAL_REVIEW_2026_PDF_URL

ILGA_ANNUAL_REVIEW_2026_URL = ILGA_ANNUAL_REVIEW_2026_PDF_URL
MISSING_STATUS_SUMMARY_ES = "Todavía no hay información disponible para este país."
MISSING_STATUS_SUMMARY_EN = "No information is available for this country yet."


def get_country_lgbti_status(
    country_codes: list[str],
    requested_year: int | None = None,
) -> list[dict[str, Any]]:
    clean_codes = _normalize_country_codes(country_codes)
    if not clean_codes:
        return []

    records = get_country_lgbti_status_records(tuple(clean_codes), requested_year)
    records_by_code = {
        str(record.get("country_code") or "").strip().upper(): _clean_status_record(record)
        for record in records
        if record.get("country_code")
    }
    return [
        records_by_code.get(country_code) or _missing_status(country_code, requested_year)
        for country_code in clean_codes
    ]


def _normalize_country_codes(country_codes: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for country_code in country_codes:
        clean_code = (
            normalize_country_code(country_code)
            or repair_text_encoding(country_code).strip().upper()
        )
        if not clean_code or clean_code in seen:
            continue
        seen.add(clean_code)
        output.append(clean_code)
    return output


def _clean_status_record(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "available": True,
        "country_code": _plain_text(record.get("country_code")).upper(),
        "country": _plain_text(record.get("country")),
        "year": _safe_int(record.get("year")),
        "title": _plain_text(record.get("title")),
        "summary": _plain_text(record.get("summary")),
        "legal_context": _plain_text(record.get("legal_context")),
        "social_context": _plain_text(record.get("social_context")),
        "observations": _plain_text(record.get("observations")),
        "positive_developments": _plain_text_list(record.get("positive_developments")),
        "main_challenges": _plain_text_list(record.get("main_challenges")),
        "source_name": _plain_text(record.get("source_name")),
        "source_url": _plain_text(record.get("source_url")) or ILGA_ANNUAL_REVIEW_2026_URL,
        "reviewed_at": _plain_text(record.get("reviewed_at")),
        "active": bool(record.get("active", True)),
    }


def _missing_status(country_code: str, requested_year: int | None) -> dict[str, Any]:
    return {
        "available": False,
        "country_code": country_code,
        "country": country_code,
        "year": requested_year,
        "title": "",
        "summary": MISSING_STATUS_SUMMARY_ES,
        "summary_i18n": {
            "es": MISSING_STATUS_SUMMARY_ES,
            "en": MISSING_STATUS_SUMMARY_EN,
        },
        "legal_context": "",
        "social_context": "",
        "observations": "",
        "positive_developments": [],
        "main_challenges": [],
        "source_name": "",
        "source_url": "",
        "reviewed_at": "",
        "active": True,
    }


def _plain_text(value: Any) -> str:
    return bleach.clean(repair_text_encoding(value).strip(), tags=[], attributes={}, strip=True)


def _plain_text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_plain_text(item) for item in value if _plain_text(item)]


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except TypeError, ValueError:
        return None
