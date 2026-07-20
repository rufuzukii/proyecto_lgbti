from __future__ import annotations

from typing import Any

from dash import html
from dash.development.base_component import Component

SUPPORTED_LANGUAGES = {"es", "en"}
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


def dash_attrs(attrs: dict[str, Any]) -> dict[str, Any]:
    return attrs


def text(es: str, en: str, *, class_name: str | None = None) -> Component:
    props = text_attrs(es, en)
    if class_name:
        props["className"] = class_name
    return html.Span(es, **props)


def ui_text(key: str, language: str = "es") -> str:
    translations = UI_TEXT.get(key)
    if not translations:
        return key
    clean_language = language if language in SUPPORTED_LANGUAGES else "es"
    return translations.get(clean_language) or translations["es"]
