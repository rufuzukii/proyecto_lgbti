from __future__ import annotations

from typing import Any

from dash import html
from dash.development.base_component import Component

SUPPORTED_LANGUAGES = {"es", "en"}
COUNTRY_NAMES: dict[str, tuple[str, str]] = {
    "AD": ("Andorra", "Andorra"),
    "AL": ("Albania", "Albania"),
    "AM": ("Armenia", "Armenia"),
    "AT": ("Austria", "Austria"),
    "AZ": ("Azerbaiyán", "Azerbaijan"),
    "BA": ("Bosnia y Herzegovina", "Bosnia and Herzegovina"),
    "BE": ("Bélgica", "Belgium"),
    "BG": ("Bulgaria", "Bulgaria"),
    "BY": ("Bielorrusia", "Belarus"),
    "CH": ("Suiza", "Switzerland"),
    "CY": ("Chipre", "Cyprus"),
    "CZ": ("República Checa", "Czechia"),
    "DE": ("Alemania", "Germany"),
    "DK": ("Dinamarca", "Denmark"),
    "EE": ("Estonia", "Estonia"),
    "ES": ("España", "Spain"),
    "FI": ("Finlandia", "Finland"),
    "FR": ("Francia", "France"),
    "GB": ("Reino Unido", "United Kingdom"),
    "GE": ("Georgia", "Georgia"),
    "GR": ("Grecia", "Greece"),
    "HR": ("Croacia", "Croatia"),
    "HU": ("Hungría", "Hungary"),
    "IE": ("Irlanda", "Ireland"),
    "IS": ("Islandia", "Iceland"),
    "IT": ("Italia", "Italy"),
    "LI": ("Liechtenstein", "Liechtenstein"),
    "LT": ("Lituania", "Lithuania"),
    "LU": ("Luxemburgo", "Luxembourg"),
    "LV": ("Letonia", "Latvia"),
    "MT": ("Malta", "Malta"),
    "MC": ("Mónaco", "Monaco"),
    "MD": ("Moldavia", "Moldova"),
    "ME": ("Montenegro", "Montenegro"),
    "MK": ("Macedonia del Norte", "North Macedonia"),
    "NL": ("Países Bajos", "Netherlands"),
    "NO": ("Noruega", "Norway"),
    "PL": ("Polonia", "Poland"),
    "PT": ("Portugal", "Portugal"),
    "RO": ("Rumanía", "Romania"),
    "RS": ("Serbia", "Serbia"),
    "RU": ("Rusia", "Russia"),
    "SM": ("San Marino", "San Marino"),
    "SE": ("Suecia", "Sweden"),
    "SI": ("Eslovenia", "Slovenia"),
    "SK": ("Eslovaquia", "Slovakia"),
    "TR": ("Turquía", "Türkiye"),
    "UA": ("Ucrania", "Ukraine"),
    "VA": ("Ciudad del Vaticano", "Vatican City"),
    "XK": ("Kosovo", "Kosovo"),
}
UI_TEXT = {
    "chart_value": {
        "es": "Valor",
        "en": "Value",
    },
    "chart_not_enough_information": {
        "es": "No hay suficiente información",
        "en": "There is not enough information",
    },
    "chart_percentage": {
        "es": "Porcentaje",
        "en": "Percentage",
    },
    "chart_no_data_grey": {
        "es": "Sin datos: gris",
        "en": "No data: grey",
    },
}


def text_attrs(es: str, en: str) -> dict[str, Any]:
    return {
        "data-i18n-es": es,
        "data-i18n-en": en,
    }


def attribute_attrs(attribute: str, es: str, en: str) -> dict[str, Any]:
    clean_attribute = str(attribute or "").strip().lower().replace("_", "-")
    if clean_attribute not in {"alt", "aria-label", "title"}:
        raise ValueError("Unsupported translatable attribute")
    return {
        f"data-i18n-{clean_attribute}-es": es,
        f"data-i18n-{clean_attribute}-en": en,
    }


def dash_attrs(attrs: dict[str, Any]) -> dict[str, Any]:
    return attrs


def text(
    es: str,
    en: str,
    *,
    class_name: str | None = None,
    language: str | None = None,
) -> Component:
    props = text_attrs(es, en)
    if class_name:
        props["className"] = class_name
    value = en if language == "en" else es
    return html.Span(value, **props)


def ui_text(key: str, language: str = "es") -> str:
    translations = UI_TEXT.get(key)
    if not translations:
        return key
    clean_language = language if language in SUPPORTED_LANGUAGES else "es"
    return translations.get(clean_language) or translations["es"]


def country_labels(country_code: str, fallback: str = "") -> tuple[str, str]:
    code = str(country_code or "").strip().upper()
    labels = COUNTRY_NAMES.get(code)
    if labels:
        return labels
    clean_fallback = str(fallback or code).strip()
    return clean_fallback, clean_fallback
