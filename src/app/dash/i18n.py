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
    "navigation_home": {"es": "Inicio", "en": "Home"},
    "navigation_statistics": {"es": "Estadísticas", "en": "Statistics"},
    "navigation_trends": {"es": "Tendencias", "en": "Trends"},
    "navigation_spain": {"es": "España", "en": "Spain"},
    "navigation_didactics": {"es": "Didáctica", "en": "Learning"},
    "navigation_about": {"es": "Acerca de", "en": "About"},
    "home_sections_eyebrow": {
        "es": "Explora RainbowLens",
        "en": "Explore RainbowLens",
    },
    "home_sections_title": {
        "es": "Todo el DataHub a tu alcance",
        "en": "The whole DataHub at your fingertips",
    },
    "home_sections_lead": {
        "es": (
            "Accede directamente a los datos, análisis y recursos principales de la plataforma."
        ),
        "en": ("Go directly to the platform's main data, analysis and learning resources."),
    },
    "home_statistics_description": {
        "es": (
            "Explora indicadores sociodemográficos y legales del colectivo LGBTIQ+ en Europa "
            "mediante mapas interactivos, gráficos comparativos y paneles estadísticos."
        ),
        "en": (
            "Explore sociodemographic and legal indicators for LGBTIQ+ people in Europe "
            "through interactive maps, comparative charts and statistical dashboards."
        ),
    },
    "home_statistics_action": {
        "es": "Ir a Estadísticas",
        "en": "Go to Statistics",
    },
    "home_statistics_aria": {
        "es": "Abrir la sección Estadísticas",
        "en": "Open the Statistics section",
    },
    "home_trends_description": {
        "es": (
            "Analiza la evolución temporal de los indicadores disponibles y consulta tendencias "
            "históricas cuando existan datos suficientes."
        ),
        "en": (
            "Analyse how available indicators evolve over time and review historical trends "
            "when sufficient data exists."
        ),
    },
    "home_trends_action": {"es": "Ver Tendencias", "en": "View Trends"},
    "home_trends_aria": {
        "es": "Abrir la sección Tendencias",
        "en": "Open the Trends section",
    },
    "home_spain_description": {
        "es": (
            "Consulta informes nacionales, documentación procesada automáticamente y gráficos "
            "extraídos de publicaciones sobre la situación LGBTIQ+ en España."
        ),
        "en": (
            "Browse national reports, automatically processed documents and charts extracted "
            "from publications on the situation of LGBTIQ+ people in Spain."
        ),
    },
    "home_spain_action": {"es": "Explorar España", "en": "Explore Spain"},
    "home_spain_aria": {
        "es": "Abrir la sección España",
        "en": "Open the Spain section",
    },
    "home_didactics_description": {
        "es": (
            "Accede al glosario LGBTIQ+, recursos educativos, materiales docentes y juegos "
            "interactivos para aprender de forma sencilla."
        ),
        "en": (
            "Access the LGBTIQ+ glossary, educational resources, teaching materials and "
            "interactive games for an approachable learning experience."
        ),
    },
    "home_didactics_action": {
        "es": "Ir a Didáctica",
        "en": "Go to Learning",
    },
    "home_didactics_aria": {
        "es": "Abrir la sección Didáctica",
        "en": "Open the Learning section",
    },
    "home_about_description": {
        "es": (
            "Conoce el proyecto RainbowLens DataHub, las fuentes oficiales utilizadas, la "
            "metodología y los objetivos de la plataforma."
        ),
        "en": (
            "Discover the RainbowLens DataHub project, its official sources, methodology and "
            "the platform's goals."
        ),
    },
    "home_about_action": {"es": "Más información", "en": "More information"},
    "home_about_aria": {
        "es": "Abrir la sección Acerca de",
        "en": "Open the About section",
    },
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
    "trends_name": {"es": "Tendencias", "en": "Trends"},
    "trends_eyebrow": {"es": "Análisis temporal", "en": "Temporal analysis"},
    "trends_title": {
        "es": "Evolución histórica de indicadores",
        "en": "Historical indicator evolution",
    },
    "trends_lead": {
        "es": "Compara años equivalentes y explora una proyección lineal sencilla.",
        "en": "Compare equivalent years and explore a simple linear projection.",
    },
    "trends_source": {"es": "Fuente de datos", "en": "Data source"},
    "trends_category": {"es": "Categoría", "en": "Category"},
    "trends_indicator": {"es": "Indicador", "en": "Indicator"},
    "trends_country": {"es": "País", "en": "Country"},
    "trends_series_variant": {
        "es": "Respuesta y filtros comparables",
        "en": "Comparable response and filters",
    },
    "trends_historical_range": {"es": "Rango histórico", "en": "Historical range"},
    "trends_forecast_horizon": {
        "es": "Horizonte de proyección",
        "en": "Projection horizon",
    },
    "trends_historical_data": {"es": "Datos históricos", "en": "Historical data"},
    "trends_forecast": {"es": "Proyección", "en": "Projection"},
    "trends_real_data": {"es": "Datos reales", "en": "Observed data"},
    "trends_estimated_data": {"es": "Datos estimados", "en": "Estimated data"},
    "trends_upward": {"es": "Ascendente", "en": "Upward"},
    "trends_downward": {"es": "Descendente", "en": "Downward"},
    "trends_stable": {"es": "Estable", "en": "Stable"},
    "trends_not_enough": {
        "es": "No hay información suficiente.",
        "en": "There is not enough information.",
    },
    "trends_not_enough_detail": {
        "es": "Se necesitan datos de al menos dos años distintos para analizar una tendencia.",
        "en": "Data from at least two different years is required to analyse a trend.",
    },
    "trends_incomparable": {
        "es": "Los datos disponibles no forman una serie metodológicamente comparable.",
        "en": "The available data do not form a methodologically comparable series.",
    },
    "trends_error_loading_series": {
        "es": "Error al cargar la serie.",
        "en": "Error loading the series.",
    },
    "trends_error_analysis": {
        "es": "No se ha podido generar el análisis temporal.",
        "en": "The temporal analysis could not be generated.",
    },
    "trends_initial_prompt": {
        "es": "Selecciona una fuente, una categoría, un indicador y un país para comenzar.",
        "en": "Select a source, category, indicator and country to begin.",
    },
    "trends_select_source": {"es": "Selecciona una fuente", "en": "Select a source"},
    "trends_select_category": {
        "es": "Selecciona una categoría",
        "en": "Select a category",
    },
    "trends_select_indicator": {
        "es": "Selecciona un indicador",
        "en": "Select an indicator",
    },
    "trends_select_country": {"es": "Selecciona un país", "en": "Select a country"},
    "trends_select_series": {
        "es": "Selecciona una respuesta comparable",
        "en": "Select a comparable response",
    },
    "trends_year_singular": {"es": "1 año", "en": "1 year"},
    "trends_years_two": {"es": "2 años", "en": "2 years"},
    "trends_years_three": {"es": "3 años", "en": "3 years"},
    "trends_trend": {"es": "Tendencia", "en": "Trend"},
    "trends_total_change": {"es": "Cambio total", "en": "Total change"},
    "trends_historical_mean": {"es": "Media histórica", "en": "Historical mean"},
    "trends_years_analyzed": {"es": "Años analizados", "en": "Years analysed"},
    "trends_last_value": {"es": "Último valor", "en": "Latest value"},
    "trends_projected_value": {"es": "Valor proyectado", "en": "Projected value"},
    "trends_method_warning": {
        "es": "La proyección es una estimación estadística basada en los datos históricos disponibles. No garantiza futuros cambios sociales, políticos o legislativos.",
        "en": "The projection is a statistical estimate based on the available historical data. It does not guarantee future social, political or legal changes.",
    },
    "trends_ilga_warning": {
        "es": "Los cambios legales pueden producir variaciones abruptas que una tendencia lineal no puede anticipar.",
        "en": "Legal changes may produce abrupt variations that a linear trend cannot anticipate.",
    },
    "trends_fra_context": {
        "es": "Evolución de experiencias declaradas y cambios entre ediciones comparables de la encuesta.",
        "en": "Evolution of reported experiences and changes between comparable survey editions.",
    },
    "trends_ilga_context": {
        "es": "Evolución de la protección legal, la puntuación jurídica y el cambio legislativo.",
        "en": "Evolution of legal protection, legal scores and legislative change.",
    },
    "trends_exploratory": {
        "es": "Esta proyección es exploratoria porque solo se basa en dos observaciones.",
        "en": "This projection is exploratory because it is based on only two observations.",
    },
    "trends_model_metrics": {"es": "Calidad del ajuste", "en": "Model fit"},
    "trends_observations": {"es": "Observaciones", "en": "Observations"},
    "trends_slope": {"es": "Pendiente", "en": "Slope"},
    "trends_mae": {"es": "Error absoluto medio (MAE)", "en": "Mean absolute error (MAE)"},
    "trends_rmse": {
        "es": "Raíz del error cuadrático medio (RMSE)",
        "en": "Root mean squared error (RMSE)",
    },
    "trends_r_squared": {"es": "Coeficiente R²", "en": "R² coefficient"},
    "trends_value": {"es": "Valor", "en": "Value"},
    "trends_year": {"es": "Año", "en": "Year"},
    "trends_type": {"es": "Tipo", "en": "Type"},
    "trends_source_short": {"es": "Fuente", "en": "Source"},
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
