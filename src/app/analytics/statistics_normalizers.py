from __future__ import annotations

import unicodedata
from functools import lru_cache
from typing import Any

from app.analytics.geography import ISO2_TO_ISO3

MOJIBAKE_MARKERS = ("\u00c3", "\u00c2", "\u00e2\u20ac", "\ufeff", "\ufffd")

VALUE_ALIASES: dict[str, str] = {
    "Rairly open": "Fairly open",
    "Rarely opened": "Rarely open",
    "Heterosexual/Straighy": "Heterosexual/Straight",
    "Severy limited": "Severely limited",
    "Not limited al all": "Not limited at all",
    "The suburs or outskirts of a big city": "The suburbs or outskirts of a big city",
    "Non binary & gender-diverse": "Non-binary and gender-diverse",
    "Non-binary": "Non-binary and gender-diverse",
    "Gender-diverse": "Non-binary and gender-diverse",
}

FILTER_TYPE_ALIASES: dict[str, str] = {
    "all": "All",
    "age": "Age",
    "age group": "Age",
    "age_group": "Age",
    "belonging to a minority group": "Belonging to a minority group",
    "minority group": "Belonging to a minority group",
    "minority_group": "Belonging to a minority group",
    "education": "Education",
    "openness": "Openness about being LGBTIQ+",
    "openness about being lgbtiq": "Openness about being LGBTIQ+",
    "openness about being lgbtiq+": "Openness about being LGBTIQ+",
    "employment status": "Employment status",
    "employment_status": "Employment status",
    "place of residence": "Place of residence",
    "place_of_residence": "Place of residence",
    "activity limitation": "Activity limitation",
    "activity_limitation": "Activity limitation",
    "making ends meet": "Making ends meet",
    "making_ends_meet": "Making ends meet",
    "sexual orientation": "Sexual Orientation",
    "sexual_orientation": "Sexual Orientation",
    "gender expression": "Gender Expression",
    "gender identity": "Gender Expression",
    "gender_expression": "Gender Expression",
    "gender_identity": "Gender Expression",
    "sex characteristic": "Sex Characteristics",
    "sex characteristics": "Sex Characteristics",
    "sex_characteristic": "Sex Characteristics",
    "sex_characteristics": "Sex Characteristics",
}

COUNTRY_CODE_ALIASES: dict[str, str] = {
    "UK": "GB",
    "EL": "GR",
    "XKX": "XK",
}
ISO3_TO_ISO2: dict[str, str] = {iso3: iso2 for iso2, iso3 in ISO2_TO_ISO3.items()}

COUNTRY_NAME_ALIASES: dict[str, str] = {
    "bosnia & herzegovina": "BA",
    "bosnia and herzegovina": "BA",
    "czech republic": "CZ",
    "czechia": "CZ",
    "kosovo": "XK",
    "moldova": "MD",
    "moldova, republic of": "MD",
    "north macedonia": "MK",
    "republic of moldova": "MD",
    "russia": "RU",
    "russian federation": "RU",
    "turkey": "TR",
    "turkiye": "TR",
    "tuerkiye": "TR",
    "united kingdom": "GB",
}


def repair_text_encoding(value: Any) -> str:
    text = str(value or "")
    return _repair_text_encoding_cached(text)


@lru_cache(maxsize=8192)
def _repair_text_encoding_cached(text: str) -> str:
    if not text:
        return ""
    text = text.replace("\ufeff", "")
    for _ in range(2):
        if not any(marker in text for marker in MOJIBAKE_MARKERS):
            break
        repaired = _decode_mojibake_once(text)
        if repaired == text:
            break
        text = repaired
    return text


def normalize_text_key(value: Any) -> str:
    return _normalize_text_key_cached(repair_text_encoding(value))


@lru_cache(maxsize=4096)
def _normalize_text_key_cached(value: str) -> str:
    text = value.strip().casefold().replace("_", " ")
    text = "".join(
        character
        for character in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(character)
    )
    return " ".join(text.split())


def normalize_filter_type(value: Any) -> str:
    text = repair_text_encoding(value).strip()
    return _normalize_filter_type_cached(text)


@lru_cache(maxsize=1024)
def _normalize_filter_type_cached(text: str) -> str:
    if not text:
        return ""
    return FILTER_TYPE_ALIASES.get(normalize_text_key(text), text)


def normalize_filter_value(value: Any) -> str:
    text = repair_text_encoding(value).strip()
    return _normalize_filter_value_cached(text)


@lru_cache(maxsize=4096)
def _normalize_filter_value_cached(text: str) -> str:
    if not text:
        return ""
    return VALUE_ALIASES.get(text, text)


def normalize_country_code(code: Any, country_name: Any | None = None) -> str:
    clean_code = repair_text_encoding(code).strip().upper()
    clean_country_name = normalize_text_key(country_name) if not clean_code else ""
    return _normalize_country_code_cached(clean_code, clean_country_name)


@lru_cache(maxsize=1024)
def _normalize_country_code_cached(clean_code: str, clean_country_name: str) -> str:
    if clean_code:
        clean_code = COUNTRY_CODE_ALIASES.get(clean_code, clean_code)
        return ISO3_TO_ISO2.get(clean_code, clean_code)
    return COUNTRY_NAME_ALIASES.get(clean_country_name, "")


def display_option(label: Any, value: Any | None = None, disabled: bool = False) -> dict[str, Any]:
    clean_label = repair_text_encoding(label)
    clean_value = repair_text_encoding(label if value is None else value)
    option: dict[str, Any] = {
        "label": clean_label,
        "value": clean_value,
    }
    if disabled:
        option["disabled"] = True
    return option


def _decode_mojibake_once(text: str) -> str:
    for source_encoding in ("latin1", "cp1252"):
        try:
            return text.encode(source_encoding).decode("utf-8")
        except UnicodeEncodeError, UnicodeDecodeError:
            continue
    return text
