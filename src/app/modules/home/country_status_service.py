from __future__ import annotations

import hashlib
import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

import bleach

from app.shared.data.normalization import (
    normalize_country_code,
    repair_text_encoding,
)
from app.shared.data.repository import get_country_lgbti_status_records
from app.shared.data.source_attribution import ILGA_ANNUAL_REVIEW_2026_PDF_URL

ILGA_ANNUAL_REVIEW_2026_URL = ILGA_ANNUAL_REVIEW_2026_PDF_URL
MISSING_STATUS_SUMMARY_ES = "Todavía no hay información disponible para este país."
MISSING_STATUS_SUMMARY_EN = "No information is available for this country yet."
COUNTRY_STATUS_EN_CATALOG_PATH = (
    Path(__file__).with_name("data") / "country_status_2026_en.json"
)
_TEXT_FIELDS = (
    "title",
    "summary",
    "legal_context",
    "social_context",
    "observations",
)
_LIST_FIELDS = ("positive_developments", "main_challenges")
logger = logging.getLogger(__name__)


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
    cleaned = {
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
    for key in _TEXT_FIELDS:
        translations = _plain_text_translations(record.get(f"{key}_i18n"))
        if translations:
            cleaned[f"{key}_i18n"] = translations
    for key in _LIST_FIELDS:
        translations = _plain_text_list_translations(record.get(f"{key}_i18n"))
        if translations:
            cleaned[f"{key}_i18n"] = translations
    _merge_versioned_english_content(cleaned)
    return cleaned


def _merge_versioned_english_content(record: dict[str, Any]) -> None:
    catalog_year, records = _load_english_catalog()
    if record.get("year") != catalog_year:
        return

    country_code = str(record.get("country_code") or "").upper()
    catalog_record = records.get(country_code)
    if not isinstance(catalog_record, dict):
        return
    fingerprints = catalog_record.get("_source_fingerprints")
    if not isinstance(fingerprints, dict):
        return

    for key in _TEXT_FIELDS:
        translations = record.get(f"{key}_i18n")
        if not isinstance(translations, dict):
            translations = {}
        if translations.get("en") or not _source_matches(
            record.get(key), fingerprints.get(key)
        ):
            continue
        english_text = _plain_text(catalog_record.get(key))
        if english_text:
            record[f"{key}_i18n"] = translations
            translations["en"] = english_text

    for key in _LIST_FIELDS:
        translations = record.get(f"{key}_i18n")
        if not isinstance(translations, dict):
            translations = {}
        if translations.get("en") or not _source_matches(
            record.get(key), fingerprints.get(key)
        ):
            continue
        english_items = _plain_text_list(catalog_record.get(key))
        if english_items:
            record[f"{key}_i18n"] = translations
            translations["en"] = english_items


def _source_matches(value: Any, expected_fingerprint: Any) -> bool:
    if not isinstance(expected_fingerprint, str) or not expected_fingerprint:
        return False
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest() == expected_fingerprint


@lru_cache(maxsize=1)
def _load_english_catalog() -> tuple[int | None, dict[str, dict[str, Any]]]:
    try:
        payload = json.loads(COUNTRY_STATUS_EN_CATALOG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.exception("country_status_english_catalog_load_failed")
        return None, {}

    try:
        year = int(payload.get("year"))
    except (AttributeError, TypeError, ValueError):
        logger.error("country_status_english_catalog_invalid_year")
        return None, {}
    raw_records = payload.get("records")
    if not isinstance(raw_records, dict):
        logger.error("country_status_english_catalog_invalid_records")
        return None, {}
    return year, {
        str(code).strip().upper(): record
        for code, record in raw_records.items()
        if isinstance(record, dict)
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


def _plain_text_translations(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {
        language: cleaned
        for language in ("es", "en")
        if (cleaned := _plain_text(value.get(language)))
    }


def _plain_text_list_translations(value: Any) -> dict[str, list[str]]:
    if not isinstance(value, dict):
        return {}
    return {
        language: cleaned
        for language in ("es", "en")
        if (cleaned := _plain_text_list(value.get(language)))
    }


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except TypeError, ValueError:
        return None
