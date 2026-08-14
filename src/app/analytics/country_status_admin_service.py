from __future__ import annotations

import logging
from datetime import date
from typing import Any
from urllib.parse import urlparse

import bleach

from app.analytics.repository import (
    deactivate_country_lgbti_status_record,
    get_country_lgbti_status_record,
    invalidate_analytics_cache,
    upsert_country_lgbti_status_record,
)
from app.analytics.statistics_normalizers import (
    normalize_country_code,
    repair_text_encoding,
)
from app.auth.permissions import is_admin_user

logger = logging.getLogger(__name__)
COUNTRY_LGBTI_STATUS_DATASET = "country_lgbti_status"
MAX_TEXT_LENGTH = 6000
MIN_SUMMARY_LENGTH = 40


class CountryStatusAuthorizationError(PermissionError):
    pass


class CountryStatusValidationError(ValueError):
    def __init__(self, field_errors: dict[str, str]) -> None:
        super().__init__("invalid_country_lgbti_status")
        self.field_errors = field_errors


def load_country_lgbti_status_for_edit(
    country_code: str, year: int | None
) -> dict[str, Any] | None:
    clean_code = normalize_country_code(country_code)
    if not clean_code or year is None:
        return None
    record = get_country_lgbti_status_record(clean_code, int(year), active_only=False)
    return _clean_record(record) if record else None


def save_country_lgbti_status(
    payload: dict[str, Any],
    *,
    user: object,
    mode: str,
) -> dict[str, Any]:
    if not is_admin_user(user):
        raise CountryStatusAuthorizationError("country_lgbti_status_admin_required")

    record = validate_country_lgbti_status_payload(payload)
    existing = get_country_lgbti_status_record(
        record["country_code"],
        record["year"],
        active_only=False,
    )
    if mode == "create" and existing:
        raise CountryStatusValidationError(
            {"year": "Ya existe información para este país y año. Edita el registro existente."}
        )

    try:
        upsert_country_lgbti_status_record(record)
        invalidate_analytics_cache("country_status")
    except Exception as exc:
        logger.exception(
            "country_lgbti_status_save_failed",
            extra={"country_code": record["country_code"], "year": record["year"]},
        )
        raise RuntimeError("country_lgbti_status_save_failed") from exc
    return record


def delete_country_lgbti_status(
    country_code: str,
    year: int,
    *,
    user: object,
    confirmed: bool,
) -> None:
    if not is_admin_user(user):
        raise CountryStatusAuthorizationError("country_lgbti_status_admin_required")
    if not confirmed:
        raise CountryStatusValidationError(
            {"delete_confirm": "Confirma la eliminación antes de continuar."}
        )

    clean_code = normalize_country_code(country_code)
    if not clean_code:
        raise CountryStatusValidationError({"country_code": "Código de país inválido."})
    try:
        clean_year = int(year)
    except (TypeError, ValueError) as exc:
        raise CountryStatusValidationError({"year": "Año inválido."}) from exc

    try:
        deactivate_country_lgbti_status_record(clean_code, clean_year)
        invalidate_analytics_cache("country_status")
        logger.info(
            "country_lgbti_status_deactivated",
            extra={"country_code": clean_code, "year": clean_year},
        )
    except Exception as exc:
        logger.exception(
            "country_lgbti_status_delete_failed",
            extra={"country_code": clean_code, "year": clean_year},
        )
        raise RuntimeError("country_lgbti_status_delete_failed") from exc


def validate_country_lgbti_status_payload(payload: dict[str, Any]) -> dict[str, Any]:
    errors: dict[str, str] = {}
    country = _plain_text(payload.get("country"))
    country_code = normalize_country_code(payload.get("country_code"), country)
    if not country:
        errors["country"] = "El país es obligatorio."
    if not country_code or len(country_code) not in {2, 3}:
        errors["country_code"] = "Código de país inválido."

    year = _int_value(payload.get("year"))
    if year is None or year < 2000 or year > 2100:
        errors["year"] = "El año debe estar entre 2000 y 2100."

    summary = _plain_text(payload.get("summary"))
    if len(summary) < MIN_SUMMARY_LENGTH:
        errors["summary"] = "La descripción debe tener al menos 40 caracteres."

    source_name = _plain_text(payload.get("source_name"))
    if not source_name:
        errors["source_name"] = "La fuente es obligatoria."

    source_url = _plain_text(payload.get("source_url"))
    if source_url and not _is_valid_url(source_url):
        errors["source_url"] = "El enlace de la fuente debe ser una URL válida."
    elif not source_url:
        errors["source_url"] = "El enlace de la fuente es obligatorio."

    reviewed_at = _plain_text(payload.get("reviewed_at"))
    try:
        date.fromisoformat(reviewed_at)
    except ValueError:
        errors["reviewed_at"] = "La fecha debe usar el formato AAAA-MM-DD."

    text_fields = {
        "title": _plain_text(payload.get("title")),
        "legal_context": _plain_text(payload.get("legal_context")),
        "social_context": _plain_text(payload.get("social_context")),
        "observations": _plain_text(payload.get("observations")),
    }
    for field, value in text_fields.items():
        if len(value) > MAX_TEXT_LENGTH:
            errors[field] = "El texto es demasiado largo."
    if len(summary) > MAX_TEXT_LENGTH:
        errors["summary"] = "La descripcion es demasiado larga."

    positive_developments = _textarea_lines(payload.get("positive_developments"))
    main_challenges = _textarea_lines(payload.get("main_challenges"))

    if errors:
        raise CountryStatusValidationError(errors)

    if year is None:
        raise CountryStatusValidationError({"year": "El año debe estar entre 2000 y 2100."})
    return {
        "dataset": COUNTRY_LGBTI_STATUS_DATASET,
        "country_code": country_code,
        "country": country,
        "year": int(year),
        "title": text_fields["title"],
        "summary": summary,
        "legal_context": text_fields["legal_context"],
        "social_context": text_fields["social_context"],
        "observations": text_fields["observations"],
        "positive_developments": positive_developments,
        "main_challenges": main_challenges,
        "source_name": source_name,
        "source_url": source_url,
        "reviewed_at": reviewed_at,
        "active": bool(payload.get("active", True)),
    }


def _clean_record(record: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(record, dict):
        return None
    clean: dict[str, Any] = {
        key: _plain_text(value) for key, value in record.items() if isinstance(value, str)
    }
    clean.update(
        {
            "country_code": normalize_country_code(record.get("country_code")),
            "year": _int_value(record.get("year")),
            "active": bool(record.get("active", True)),
            "positive_developments": [
                _plain_text(item) for item in record.get("positive_developments", []) or []
            ],
            "main_challenges": [
                _plain_text(item) for item in record.get("main_challenges", []) or []
            ],
        }
    )
    return clean


def _plain_text(value: Any) -> str:
    return bleach.clean(repair_text_encoding(value).strip(), tags=[], attributes={}, strip=True)


def _textarea_lines(value: Any) -> list[str]:
    raw_lines = value if isinstance(value, list) else repair_text_encoding(value).splitlines()
    return [line for line in (_plain_text(raw) for raw in raw_lines) if line]


def _int_value(value: Any) -> int | None:
    try:
        return int(value)
    except TypeError, ValueError:
        return None


def _is_valid_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
