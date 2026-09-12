from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class FraCountryState(StrEnum):
    HAS_DATA = "has_data"
    NO_DATA = "no_data"
    OUTSIDE_SURVEY_SCOPE = "outside_survey_scope"


class FraResponseType(StrEnum):
    STANDARD = "standard"
    RANKED_REASON = "ranked_reason"


@dataclass(frozen=True)
class FraResponseMetadata:
    response_type: FraResponseType
    ordered_keys: tuple[str, ...]
    help_key: str | None = None


# Survey III abarca la UE-27 y los países candidatos Albania, Macedonia del Norte
# y Serbia. El ámbito depende de la edición, no de que una consulta concreta
# devuelva o no datos de un país.
FRA_SURVEY_PARTICIPANT_COUNTRY_CODES_BY_YEAR: dict[int, frozenset[str]] = {
    2023: frozenset(
        {
            "AL",
            "AT",
            "BE",
            "BG",
            "CY",
            "CZ",
            "DE",
            "DK",
            "EE",
            "ES",
            "FI",
            "FR",
            "GR",
            "HR",
            "HU",
            "IE",
            "IT",
            "LT",
            "LU",
            "LV",
            "MK",
            "MT",
            "NL",
            "PL",
            "PT",
            "RO",
            "RS",
            "SE",
            "SI",
            "SK",
        }
    ),
    # Survey II incluye la entonces UE-28, Macedonia del Norte y Serbia.
    2019: frozenset(
        {
            "AT",
            "BE",
            "BG",
            "CY",
            "CZ",
            "DE",
            "DK",
            "EE",
            "ES",
            "FI",
            "FR",
            "GB",
            "GR",
            "HR",
            "HU",
            "IE",
            "IT",
            "LT",
            "LU",
            "LV",
            "MK",
            "MT",
            "NL",
            "PL",
            "PT",
            "RO",
            "RS",
            "SE",
            "SI",
            "SK",
        }
    ),
}

RANKED_REASON_RESPONSE_KEYS = ("1st", "2nd", "3rd", "not selected")
RESPONSE_TYPES: dict[FraResponseType, FraResponseMetadata] = {
    FraResponseType.RANKED_REASON: FraResponseMetadata(
        response_type=FraResponseType.RANKED_REASON,
        ordered_keys=RANKED_REASON_RESPONSE_KEYS,
        help_key="fra_ranked_reason_help",
    )
}


def fra_survey_participant_codes(survey_year: int | None) -> frozenset[str] | None:
    """Devuelve el ámbito verificado de una edición, o ``None`` si no está registrado."""
    if survey_year is None:
        return None
    return FRA_SURVEY_PARTICIPANT_COUNTRY_CODES_BY_YEAR.get(int(survey_year))


def classify_fra_country_state(
    country_code: Any,
    has_value: bool,
    *,
    survey_year: int | None,
) -> FraCountryState:
    code = str(country_code or "").strip().upper()
    participants = fra_survey_participant_codes(survey_year)
    if participants is not None and code not in participants:
        return FraCountryState.OUTSIDE_SURVEY_SCOPE
    return FraCountryState.HAS_DATA if has_value else FraCountryState.NO_DATA


def normalize_fra_response_key(value: Any) -> str:
    return " ".join(str(value or "").strip().casefold().replace("_", " ").split())


def detect_fra_response_type(
    responses: Iterable[Any],
    *,
    question: Any = None,
    specific_category: Any = None,
) -> FraResponseType:
    """Clasifica la semántica de respuesta por sus valores; los títulos solo aportan contexto."""
    keys = {normalize_fra_response_key(value) for value in responses}
    ranked_keys = {normalize_fra_response_key(value) for value in RANKED_REASON_RESPONSE_KEYS}
    if ranked_keys.issubset(keys):
        return FraResponseType.RANKED_REASON

    title_supports_ranked_reason = any(
        normalize_fra_response_key(value).startswith("reason for")
        for value in (question, specific_category)
    )
    ranked_positions = ranked_keys.intersection(keys)
    if title_supports_ranked_reason and len(ranked_positions) >= 3:
        return FraResponseType.RANKED_REASON
    return FraResponseType.STANDARD


def order_fra_responses(
    responses: Iterable[Any],
    *,
    response_type: FraResponseType | str | None = None,
) -> list[Any]:
    values = list(responses)
    resolved = (
        FraResponseType(response_type)
        if response_type in {member.value for member in FraResponseType}
        else detect_fra_response_type(values)
    )
    if resolved is not FraResponseType.RANKED_REASON:
        return values
    order = {
        normalize_fra_response_key(value): index
        for index, value in enumerate(RANKED_REASON_RESPONSE_KEYS)
    }
    return sorted(
        values,
        key=lambda value: (
            order.get(normalize_fra_response_key(value), len(order)),
            normalize_fra_response_key(value),
        ),
    )
