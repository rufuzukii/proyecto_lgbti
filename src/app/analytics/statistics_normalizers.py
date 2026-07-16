from __future__ import annotations

from typing import Any

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
    "openness": "Openness about being LGBTIQ",
    "openness about being lgbtiq": "Openness about being LGBTIQ",
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


def normalize_text_key(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().replace("_", " ").split())


def normalize_filter_type(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return FILTER_TYPE_ALIASES.get(normalize_text_key(text), text)


def normalize_filter_value(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return VALUE_ALIASES.get(text, text)


def normalize_country_code(code: Any, country_name: Any | None = None) -> str:
    clean_code = str(code or "").strip().upper()
    if clean_code:
        return COUNTRY_CODE_ALIASES.get(clean_code, clean_code)
    return COUNTRY_NAME_ALIASES.get(normalize_text_key(country_name), "")


def display_option(label: Any, value: Any | None = None, disabled: bool = False) -> dict[str, Any]:
    clean_value = str(label if value is None else value)
    option: dict[str, Any] = {
        "label": str(label),
        "value": clean_value,
    }
    if disabled:
        option["disabled"] = True
    return option
