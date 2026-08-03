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
    "report_module_name": {
        "es": "Informe DataHub",
        "en": "DataHub Report",
    },
    "report_generation_eyebrow": {
        "es": "Generación de informes",
        "en": "Report generation",
    },
    "report_configuration": {
        "es": "Configuración",
        "en": "Configuration",
    },
    "report_advanced_options": {
        "es": "Opciones avanzadas",
        "en": "Advanced options",
    },
    "report_advanced_restricted": {
        "es": (
            "Las opciones avanzadas están disponibles únicamente para "
            "determinados perfiles profesionales."
        ),
        "en": ("Advanced options are available only to selected professional profiles."),
    },
    "report_advanced_toggle": {
        "es": "Mostrar u ocultar las opciones avanzadas",
        "en": "Show or hide advanced options",
    },
    "report_login_required": {
        "es": "Debes iniciar sesión para generar informes.",
        "en": "You must sign in to generate reports.",
    },
    "download_table": {
        "es": "Descargar tabla",
        "en": "Download table",
    },
    "download_csv": {
        "es": "Descargar CSV",
        "en": "Download CSV",
    },
    "download_excel": {
        "es": "Descargar Excel",
        "en": "Download Excel",
    },
    "no_export_data": {
        "es": "No hay datos para exportar",
        "en": "No data available to export",
    },
    "no_data": {
        "es": "Sin datos",
        "en": "No data",
    },
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
    "contact_success": {
        "es": "Tu mensaje se ha enviado correctamente.",
        "en": "Your message was sent successfully.",
    },
    "contact_validation_error": {
        "es": "Revisa los campos y los archivos adjuntos antes de volver a intentarlo.",
        "en": "Review the fields and attachments before trying again.",
    },
    "contact_delivery_error": {
        "es": "No se ha podido enviar el mensaje. Inténtalo de nuevo más tarde.",
        "en": "The message could not be sent. Try again later.",
    },
    "contact_rate_limited": {
        "es": "Has alcanzado el límite temporal de envíos. Inténtalo más tarde.",
        "en": "You have reached the temporary submission limit. Try again later.",
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


def ui_text_component(
    key: str,
    *,
    class_name: str | None = None,
    language: str | None = None,
) -> Component:
    return text(
        ui_text(key, "es"),
        ui_text(key, "en"),
        class_name=class_name,
        language=language,
    )


def ui_text_data_attrs(key: str) -> dict[str, Any]:
    return text_attrs(ui_text(key, "es"), ui_text(key, "en"))


def country_labels(country_code: str, fallback: str = "") -> tuple[str, str]:
    code = str(country_code or "").strip().upper()
    labels = COUNTRY_NAMES.get(code)
    if labels:
        return labels
    clean_fallback = str(fallback or code).strip()
    return clean_fallback, clean_fallback
