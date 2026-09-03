from __future__ import annotations

import logging
import os
from typing import Any

import dash_ag_grid as dag
from dash import ALL, Dash, Input, Output, State, ctx, dcc, html, no_update
from dash.development.base_component import Component
from flask_login import current_user

from app.core.auth.permissions import Permission, user_has_permission
from app.core.auth.rate_limit import create_rate_limiter
from app.core.dates import utc_today_iso
from app.core.http_security import rate_limit_key
from app.modules.reports.hr_reporting import (
    HR_REPORT_SECTIONS,
    hr_report_charts,
    hr_report_objective,
)
from app.modules.reports.models import ReportConfiguration
from app.modules.reports.service import (
    ReportGenerationError,
    build_report,
    default_section_narrative,
    generate_report_pdf,
)
from app.modules.statistics.exports import chart_graph_config
from app.modules.statistics.service import get_fra_control_payload
from app.shared.components.loading import contextual_loading
from app.shared.components.page_structure import build_page_header
from app.shared.data.normalization import normalize_text_key
from app.shared.data.repository import (
    assert_analytics_databases_available,
    get_fra_categories,
    get_fra_mongo_indicators_by_category,
    get_fra_years,
    get_ilga_criteria_categories_by_year,
    get_ilga_years,
)
from app.shared.data.taxonomy import taxonomy_pair
from app.web.i18n import (
    country_labels,
    dash_attrs,
    text,
    text_attrs,
    ui_text,
    ui_text_component,
)
from app.web.navigation import build_navbar
from app.web.routes import route_path

logger = logging.getLogger(__name__)

EXCLUDED_CATEGORIES = {
    normalize_text_key("Political Participation"),
    normalize_text_key("Spanish LGBTI+ indicators"),
    normalize_text_key("Spanish LGBTIQ+ indicators"),
}

REPORT_COUNTRY_CODES = (
    "AT",
    "BE",
    "BG",
    "HR",
    "CY",
    "CZ",
    "DK",
    "EE",
    "FI",
    "FR",
    "DE",
    "GR",
    "HU",
    "IE",
    "IT",
    "LV",
    "LT",
    "LU",
    "MT",
    "NL",
    "PL",
    "PT",
    "RO",
    "SK",
    "SI",
    "ES",
    "SE",
    "GB",
    "NO",
    "IS",
    "CH",
)

SECTION_LABELS = {
    "executive": ("Resumen ejecutivo", "Executive summary"),
    "context": ("Contexto", "Context"),
    "metrics": ("Métricas principales", "Key metrics"),
    "analysis": ("Resultados y gráficas", "Results and charts"),
    "workplace": ("Entorno laboral", "Workplace"),
    "comparison": ("Comparaciones", "Comparisons"),
    "demographics": ("Diferencias sociodemográficas", "Sociodemographic differences"),
    "interpretation": ("Interpretación", "Interpretation"),
    "recommendations": ("Posibles actuaciones", "Possible actions"),
    "methodology": ("Metodología", "Methodology"),
    "limitations": ("Limitaciones", "Limitations"),
    "sources": (
        "Fuentes, metodología y atribuciones",
        "Sources, methodology and attributions",
    ),
}

def build_reports_layout(
    initial_values: dict[str, Any] | None = None,
    *,
    default_language: str = "es",
) -> Component:
    assert_analytics_databases_available()
    values = {**(initial_values or {})}
    values.setdefault("language", default_language)
    config = _hr_report_configuration(values)
    years = _year_options(config.source)
    year = config.year or (years[0]["value"] if years else None)
    categories = _category_options(config.source, year)
    category = config.category or (
        categories[0]["value"] if config.source == "ilga" and categories else ""
    )
    indicators = _indicator_options(config.source, category, year)
    if config.indicator_id and config.indicator_id not in {item["value"] for item in indicators}:
        indicators.append(
            {
                "label": config.indicator_label or config.indicator_id,
                "value": config.indicator_id,
            }
        )
    country_options = _country_options(config.countries)

    return html.Div(
        [
            build_navbar(active="reports"),
            dcc.Store(
                id="report-config-store",
                data=config.to_dict(),
                storage_type="memory",
            ),
            dcc.Download(id="report-download"),
            html.Main(
                [
                    build_page_header(
                        eyebrow=text(
                            ui_text("report_generation_eyebrow", "es"),
                            ui_text("report_generation_eyebrow", "en"),
                        ),
                        title=text("Informe de inclusión LGBTIQ+", "LGBTIQ+ inclusion report"),
                        description=text(
                            "Genera un informe basado en datos para comprender el contexto LGBTIQ+, detectar posibles áreas de atención y apoyar la mejora de las políticas de diversidad e inclusión.",
                            "Generate a data-informed report to understand the LGBTIQ+ context, identify possible areas for attention and support improvements to diversity and inclusion policies.",
                        ),
                        class_name="reports-header",
                    ),
                    html.Div(
                        [
                            _hr_purpose_panel(),
                            _configuration_panel(
                                config,
                                years,
                                year,
                                categories,
                                category,
                                indicators,
                                country_options,
                            ),
                            html.Section(
                                [
                                    html.H2(
                                        text(
                                            "Resumen de la configuración",
                                            "Configuration summary",
                                        )
                                    ),
                                    html.Div(id="report-plan-summary"),
                                    html.P(
                                        text(
                                            "El informe incluirá resultados, comparaciones y posibles líneas de actuación para RRHH cuando los datos permitan sustentarlas.",
                                            "The report will include results, comparisons and possible courses of action for HR when supported by the data.",
                                        )
                                    ),
                                ],
                                className="reports-card reports-plan-summary",
                            ),
                            html.Div(
                                [
                                    html.Button(
                                        text("Generar vista previa", "Generate preview"),
                                        id="report-preview-button",
                                        type="button",
                                        className="reports-primary-button",
                                        n_clicks=0,
                                    ),
                                    html.Button(
                                        text("Descargar informe PDF", "Download PDF report"),
                                        id="report-download-button",
                                        type="button",
                                        className="reports-secondary-button",
                                        disabled=True,
                                        n_clicks=0,
                                    ),
                                    html.Span(
                                        "",
                                        id="report-status",
                                        role="status",
                                        className="reports-status",
                                        **dash_attrs({"aria-live": "polite"}),
                                    ),
                                ],
                                className="reports-actions reports-final-actions",
                            ),
                            contextual_loading(
                                html.Section(
                                    [
                                        html.Div(
                                            [
                                                html.H2(text("Vista previa", "Preview")),
                                                html.P(
                                                    text(
                                                        "Genera la vista previa para comprobar métricas, textos, gráficos, recomendaciones y fuentes.",
                                                        "Generate the preview to check metrics, text, charts, recommendations and sources.",
                                                    )
                                                ),
                                            ],
                                            id="report-preview-content",
                                            className="reports-preview-empty",
                                        )
                                    ],
                                    className="reports-preview-shell",
                                ),
                                "generating_report",
                                element_id="report-preview-loading",
                            ),
                        ],
                        className="reports-workflow",
                    ),
                ],
                className="reports-shell app-page app-page-container",
            ),
        ]
    )


def build_reports_access_denied_layout() -> Component:
    return html.Div(
        [
            build_navbar(active="reports"),
            html.Main(
                [
                    html.H1(text("Acceso no autorizado", "Access denied")),
                    html.P(
                        text(
                            "Tu cuenta no dispone de permiso para generar informes.",
                            "Your account is not allowed to generate reports.",
                        )
                    ),
                    dcc.Link(
                        text("Volver a Estadísticas", "Back to Statistics"),
                        href=route_path("statistics"),
                    ),
                ],
                className="reports-access-denied app-page app-page-container",
            ),
        ]
    )


def register_reports_callbacks(app: Dash) -> None:
    preview_rate_limiter = create_rate_limiter(
        max_attempts=max(1, int(os.getenv("REPORT_PREVIEW_MAX_ATTEMPTS", "30"))),
        window_seconds=max(60, int(os.getenv("REPORT_RATE_WINDOW_SECONDS", "3600"))),
        namespace="report-previews",
    )
    download_rate_limiter = create_rate_limiter(
        max_attempts=max(1, int(os.getenv("REPORT_DOWNLOAD_MAX_ATTEMPTS", "10"))),
        window_seconds=max(60, int(os.getenv("REPORT_RATE_WINDOW_SECONDS", "3600"))),
        namespace="report-downloads",
    )

    @app.callback(
        Output("report-year-select", "options"),
        Output("report-year-select", "value"),
        Input("report-source-select", "value"),
        State("report-year-select", "value"),
    )
    def update_report_years(source: str | None, current_year: int | None):
        options = _year_options(source or "fra")
        values = {item["value"] for item in options}
        return options, current_year if current_year in values else (
            options[0]["value"] if options else None
        )

    @app.callback(
        Output("report-category-select", "options"),
        Output("report-category-select", "value"),
        Input("report-source-select", "value"),
        Input("report-year-select", "value"),
        State("report-category-select", "value"),
    )
    def update_report_categories(
        source: str | None,
        year: int | None,
        current_category: str | None,
    ):
        options = _category_options(source or "fra", year)
        values = {item["value"] for item in options}
        default = options[0]["value"] if source == "ilga" and options else None
        return options, current_category if current_category in values else default

    @app.callback(
        Output("report-indicator-select", "options"),
        Output("report-indicator-select", "value"),
        Output("report-indicator-select", "disabled"),
        Input("report-source-select", "value"),
        Input("report-category-select", "value"),
        Input("report-year-select", "value"),
        State("report-indicator-select", "value"),
    )
    def update_report_indicators(
        source: str | None,
        category: str | None,
        year: int | None,
        current_indicator: str | None,
    ):
        options = _indicator_options(source or "fra", category or "", year)
        values = {item["value"] for item in options}
        value = current_indicator if current_indicator in values else None
        enabled = _requires_social_indicator(source) and bool(category) and bool(options)
        return options, value, not enabled

    @app.callback(
        Output("report-indicator-field", "className"),
        Output("report-indicator-error", "children"),
        Output("report-indicator-error", "className"),
        Input("report-source-select", "value"),
        Input("report-category-select", "value"),
        Input("report-indicator-select", "value"),
        Input("report-preview-button", "n_clicks"),
        Input("report-language-select", "value"),
    )
    def update_report_indicator_validation(
        source: str | None,
        category: str | None,
        indicator: str | None,
        preview_clicks: int | None,
        language: str | None,
    ) -> tuple[str, str, str]:
        if not _requires_social_indicator(source):
            return "reports-field is-hidden", "", "reports-field-error is-hidden"
        invalid = bool(category) and not indicator
        attempted = ctx.triggered_id == "report-preview-button" and bool(preview_clicks)
        if invalid and attempted:
            return (
                "reports-field has-error",
                _t(
                    language,
                    "Selecciona un indicador social para continuar.",
                    "Select a social indicator to continue.",
                ),
                "reports-field-error",
            )
        return "reports-field", "", "reports-field-error is-hidden"

    @app.callback(
        Output("report-answer-select", "options"),
        Output("report-answer-select", "value"),
        Output("report-answer-select", "disabled"),
        Output("report-answer-field", "className"),
        Output("report-filters-section", "className"),
        Output("report-filter-a-name", "options"),
        Output("report-filter-a-name", "value"),
        Output("report-filter-a-name", "disabled"),
        Output("report-filter-a-value", "options"),
        Output("report-filter-a-value", "value"),
        Output("report-filter-a-value", "disabled"),
        Output("report-filter-b-name", "options"),
        Output("report-filter-b-name", "value"),
        Output("report-filter-b-name", "disabled"),
        Output("report-filter-b-value", "options"),
        Output("report-filter-b-value", "value"),
        Output("report-filter-b-value", "disabled"),
        Input("report-source-select", "value"),
        Input("report-indicator-select", "value"),
        Input("report-category-select", "value"),
        Input("report-year-select", "value"),
        State("report-answer-select", "value"),
        State("report-filter-a-name", "value"),
        State("report-filter-a-value", "value"),
        State("report-filter-b-name", "value"),
        State("report-filter-b-value", "value"),
    )
    def update_report_social_controls(
        source: str | None,
        indicator: str | None,
        category: str | None,
        year: int | None,
        current_answer: str | None,
        current_a_name: str | None,
        current_a_value: str | None,
        current_b_name: str | None,
        current_b_value: str | None,
    ):
        social_enabled = _requires_social_indicator(source) and bool(indicator)
        filters_enabled = source == "fra" and bool(indicator)
        payload = (
            get_fra_control_payload(indicator or "", category, year)
            if social_enabled
            else {}
        )
        answers = list(payload.get("answers") or [])
        answer_values = {item["value"] for item in answers}
        answer = (
            current_answer
            if current_answer in answer_values
            else payload.get("default_answer")
        )
        segmentations = list(payload.get("segmentations") or []) if filters_enabled else []
        segmentation_values = {item["value"] for item in segmentations}
        a_name = current_a_name if current_a_name in segmentation_values else "All"
        b_name = current_b_name if current_b_name in segmentation_values else "All"
        values_by_type = dict(payload.get("values") or {})
        a_options = list(values_by_type.get(a_name) or [])
        b_options = list(values_by_type.get(b_name) or [])
        a_values = {item["value"] for item in a_options}
        b_values = {item["value"] for item in b_options}
        a_value = current_a_value if current_a_value in a_values else "All"
        b_value = current_b_value if current_b_value in b_values else "All"
        b_enabled = filters_enabled and a_name == "All"
        if not filters_enabled:
            a_name, a_value, a_options = "All", "All", []
            b_name, b_value, b_options = "All", "All", []
        if not b_enabled:
            b_name, b_value, b_options = "All", "All", list(values_by_type.get("All") or [])
        return (
            answers, answer, not social_enabled,
            "reports-field" if _requires_social_indicator(source) else "reports-field is-hidden",
            "reports-filters-section" if source == "fra" else "reports-filters-section is-hidden",
            segmentations, a_name, not filters_enabled,
            a_options, a_value, not filters_enabled or a_name == "All",
            segmentations, b_name, not b_enabled,
            b_options, b_value, not b_enabled or b_name == "All",
        )

    @app.callback(
        Output("report-plan-summary", "children"),
        Input("report-source-select", "value"),
        Input("report-year-select", "value"),
        Input("report-primary-country", "value"),
        Input("report-comparison-countries", "value"),
        Input("report-answer-select", "value"),
        Input("report-language-select", "value"),
        Input("report-category-select", "value"),
        Input("report-indicator-select", "value"),
        Input("report-indicator-select", "options"),
        Input("report-filter-a-name", "value"),
        Input("report-filter-a-value", "value"),
        Input("report-filter-b-name", "value"),
        Input("report-filter-b-value", "value"),
    )
    def update_report_plan_summary(
        source: str | None,
        year: int | None,
        primary_country: str | None,
        comparison_countries: list[str] | None,
        answer: str | None,
        language: str | None,
        category: str | None,
        indicator: str | None,
        indicator_options: list[dict[str, Any]] | None,
        filter_a_name: str | None,
        filter_a_value: str | None,
        filter_b_name: str | None,
        filter_b_value: str | None,
    ):
        clean_language = "en" if language == "en" else "es"
        indicator_label = _selected_option_label(indicator_options, indicator) or indicator
        source_label = {
            "fra": _t(clean_language, "Datos sociales", "Social data"),
            "ilga": _t(clean_language, "Datos legales", "Legal data"),
            "combined": _t(clean_language, "Análisis combinado", "Combined analysis"),
        }.get(source or "fra", source or "")
        countries = [country for country in [primary_country, *(comparison_countries or [])] if country]
        filters = [
            f"{name}: {value}"
            for name, value in (
                (filter_a_name, filter_a_value),
                (filter_b_name, filter_b_value),
            )
            if name and name != "All" and value
        ]
        sections = ", ".join(
            _t(clean_language, *SECTION_LABELS.get(key, (key, key)))
            for key in HR_REPORT_SECTIONS
        )
        summary_items: list[Component] = [
                html.Dt(_t(clean_language, "Enfoque", "Focus")),
                html.Dd(_t(clean_language, "RRHH y diversidad e inclusión", "HR and diversity and inclusion")),
                html.Dt(_t(clean_language, "Tipo de información", "Information type")),
                html.Dd(source_label),
                html.Dt(_t(clean_language, "Encuesta / año", "Survey / year")),
                html.Dd(str(year or "—")),
                html.Dt(_t(clean_language, "Categoría", "Category")),
                html.Dd(category or "—"),
        ]
        if _requires_social_indicator(source):
            summary_items.extend(
                [
                    html.Dt(_t(clean_language, "Indicador social", "Social indicator")),
                    html.Dd(indicator_label or "—"),
                    html.Dt(_t(clean_language, "Respuesta", "Answer")),
                    html.Dd(answer or "—"),
                ]
            )
        summary_items.extend(
            [
                html.Dt(_t(clean_language, "Países", "Countries")),
                html.Dd(", ".join(countries) or _t(clean_language, "Europa", "Europe")),
            ]
        )
        if source == "fra":
            summary_items.extend(
                [
                    html.Dt(_t(clean_language, "Filtros", "Filters")),
                    html.Dd(", ".join(filters) or _t(clean_language, "Ninguno", "None")),
                ]
            )
        summary_items.extend(
            [
                html.Dt(_t(clean_language, "Secciones incluidas", "Included sections")),
                html.Dd(sections),
            ]
        )
        return html.Dl(summary_items, className="reports-plan-list")

    @app.callback(
        Output("report-preview-content", "children"),
        Output("report-preview-content", "className"),
        Output("report-status", "children"),
        Output("report-status", "className"),
        Output("report-config-store", "data"),
        Output("report-download-button", "disabled"),
        Input("report-preview-button", "n_clicks"),
        State("report-title-input", "value"),
        State("report-organization-input", "value"),
        State("report-author-input", "value"),
        State("report-source-select", "value"),
        State("report-category-select", "value"),
        State("report-indicator-select", "value"),
        State("report-year-select", "value"),
        State("report-primary-country", "value"),
        State("report-comparison-countries", "value"),
        State("report-language-select", "value"),
        State("report-answer-select", "value"),
        State("report-filter-a-name", "value"),
        State("report-filter-a-value", "value"),
        State("report-filter-b-name", "value"),
        State("report-filter-b-value", "value"),
        State("report-generated-on", "date"),
        State("report-config-store", "data"),
        prevent_initial_call=True,
        running=[
            (Output("report-preview-button", "disabled"), True, False),
            (
                Output("report-preview-button", "children"),
                text("Generando vista previa…", "Generating preview…"),
                text("Generar vista previa", "Generate preview"),
            ),
        ],
    )
    def preview_report(
        _clicks: int | None,
        title: str | None,
        organization: str | None,
        author: str | None,
        source: str | None,
        category: str | None,
        indicator: str | None,
        year: int | None,
        primary_country: str | None,
        comparison_countries: list[str] | None,
        language: str | None,
        answer: str | None,
        filter_a_name: str | None,
        filter_a_value: str | None,
        filter_b_name: str | None,
        filter_b_value: str | None,
        generated_on: str | None,
        inherited_configuration: dict[str, Any] | None,
    ):
        if _missing_social_indicator(source, category, indicator):
            return (
                no_update,
                no_update,
                _t(
                    language,
                    "Selecciona un indicador social para continuar.",
                    "Select a social indicator to continue.",
                ),
                "reports-status reports-status-error",
                no_update,
                True,
            )
        if not user_has_permission(current_user, Permission.GENERATE_REPORTS):
            return (
                no_update,
                no_update,
                _t(
                    language,
                    "No tienes permiso para generar informes.",
                    "You are not allowed to generate reports.",
                ),
                "reports-status reports-status-error",
                no_update,
                True,
            )
        limiter_key = rate_limit_key(subject=_current_user_id(), scope="report-preview")
        if preview_rate_limiter.is_blocked(limiter_key):
            return (
                no_update,
                no_update,
                _t(
                    language,
                    "Has alcanzado el límite temporal de vistas previas.",
                    "You have reached the temporary preview limit.",
                ),
                "reports-status reports-status-error",
                no_update,
                True,
            )
        preview_rate_limiter.record_failure(limiter_key)
        try:
            config = _configuration_from_controls(
                title=title,
                organization=organization,
                author=author,
                source=source,
                category=category,
                indicator=indicator,
                year=year,
                primary_country=primary_country,
                comparison_countries=comparison_countries,
                language=language,
                answer=answer,
                filter_a_name=filter_a_name,
                filter_a_value=filter_a_value,
                filter_b_name=filter_b_name,
                filter_b_value=filter_b_value,
                generated_on=generated_on,
                inherited_configuration=inherited_configuration,
            )
            config = _hr_report_configuration(config.to_dict())
            content = build_report(config)
        except ReportGenerationError as exc:
            safe_language = "en" if language == "en" else "es"
            logger.warning("report_preview_failed", extra={"reason": str(exc)})
            return (
                _preview_error(safe_language),
                "reports-preview-empty",
                _t(
                    safe_language,
                    "No se ha podido generar la vista previa.",
                    "The preview could not be generated.",
                ),
                "reports-status reports-status-error",
                no_update,
                True,
            )
        return (
            _preview_content(content),
            "reports-preview-document",
            _t(config.language, "Vista previa actualizada.", "Preview updated."),
            "reports-status reports-status-ok",
            config.to_dict(),
            False,
        )

    @app.callback(
        Output("report-download-button", "disabled", allow_duplicate=True),
        Input("report-source-select", "value"),
        Input("report-year-select", "value"),
        Input("report-category-select", "value"),
        Input("report-indicator-select", "value"),
        Input("report-answer-select", "value"),
        Input("report-primary-country", "value"),
        Input("report-comparison-countries", "value"),
        Input("report-filter-a-name", "value"),
        Input("report-filter-a-value", "value"),
        Input("report-filter-b-name", "value"),
        Input("report-filter-b-value", "value"),
        prevent_initial_call=True,
    )
    def invalidate_report_download(*_values: Any) -> bool:
        """A PDF is only valid for the exact configuration last previewed."""
        return True

    @app.callback(
        Output("report-download", "data"),
        Output("report-status", "children", allow_duplicate=True),
        Output("report-status", "className", allow_duplicate=True),
        Input("report-download-button", "n_clicks"),
        State("report-config-store", "data"),
        State({"type": "report-chart-narrative", "chart": ALL, "field": ALL}, "value"),
        State({"type": "report-chart-narrative", "chart": ALL, "field": ALL}, "id"),
        State({"type": "report-section-narrative", "section": ALL}, "value"),
        State({"type": "report-section-narrative", "section": ALL}, "id"),
        prevent_initial_call=True,
        running=[
            (
                Output("report-download-button", "disabled", allow_duplicate=True),
                True,
                False,
            ),
            (
                Output("report-download-button", "children"),
                text("Generando informe…", "Generating report…"),
                text("Descargar informe PDF", "Download PDF report"),
            ),
        ],
    )
    def download_report(
        clicks: int | None,
        stored_configuration: dict[str, Any] | None,
        narrative_values: list[str | None],
        narrative_ids: list[dict[str, str]],
        section_values: list[str | None],
        section_ids: list[dict[str, str]],
    ):
        if not clicks or not stored_configuration:
            return no_update, no_update, no_update
        language = str(stored_configuration.get("language") or "es")
        if not user_has_permission(current_user, Permission.GENERATE_REPORTS):
            return (
                no_update,
                _t(
                    language,
                    "No tienes permiso para generar informes.",
                    "You are not allowed to generate reports.",
                ),
                "reports-status reports-status-error",
            )
        limiter_key = rate_limit_key(subject=_current_user_id(), scope="report-download")
        if download_rate_limiter.is_blocked(limiter_key):
            return (
                no_update,
                _t(
                    language,
                    "Has alcanzado el límite temporal de informes.",
                    "You have reached the temporary report limit.",
                ),
                "reports-status reports-status-error",
            )
        download_rate_limiter.record_failure(limiter_key)
        try:
            generated = generate_report_pdf(
                _hr_report_configuration(stored_configuration),
                chart_narratives=_chart_narratives_from_pattern(
                    narrative_values,
                    narrative_ids,
                ),
                section_narratives=_section_narratives_from_pattern(
                    section_values,
                    section_ids,
                ),
            )
        except ReportGenerationError:
            return (
                no_update,
                _t(
                    language,
                    "No se ha podido generar el informe. Inténtalo de nuevo más tarde.",
                    "The report could not be generated. Please try again later.",
                ),
                "reports-status reports-status-error",
            )
        return (
            dcc.send_bytes(
                generated.pdf_bytes,
                generated.filename,
                type="application/pdf",
            ),
            _t(language, "Informe generado correctamente.", "Report generated successfully."),
            "reports-status reports-status-ok",
        )


def _hr_report_configuration(values: dict[str, Any] | None) -> ReportConfiguration:
    payload = dict(values or {})
    requested_source = str(payload.get("source") or "fra").strip().casefold()
    source = requested_source if requested_source in {"fra", "ilga", "combined"} else "fra"
    objective = hr_report_objective(str(payload.get("objective") or ""))
    payload.update(
        {
            "source": source,
            "objective": objective.id,
            "detail_level": "standard",
            "sections": list(HR_REPORT_SECTIONS),
            "charts": list(hr_report_charts(source, objective.id)),
            "criterion": "",
            "filter_a_name": payload.get("filter_a_name", "All") if source == "fra" else "All",
            "filter_a_value": payload.get("filter_a_value", "All") if source == "fra" else "All",
            "filter_b_name": payload.get("filter_b_name", "All") if source == "fra" else "All",
            "filter_b_value": payload.get("filter_b_value", "All") if source == "fra" else "All",
        }
    )
    return ReportConfiguration.from_mapping(payload)


def _configuration_panel(
    config: ReportConfiguration,
    years: list[dict[str, Any]],
    year: int | None,
    categories: list[dict[str, Any]],
    category: str,
    indicators: list[dict[str, Any]],
    country_options: list[dict[str, Any]],
) -> Component:
    social_source = config.source in {"fra", "combined"}
    # Keep the layout query-free. The callback loads valid options after Dash
    # mounts the stable controls; inherited values remain visible meanwhile.
    controls: dict[str, Any] = {
        "answers": (
            [{"label": config.answer, "value": config.answer}] if config.answer else []
        ),
        "default_answer": config.answer or None,
    }
    segmentation_names = ["All", config.filter_a_name, config.filter_b_name]
    segmentations = [
        {"label": name, "value": name}
        for name in dict.fromkeys(name for name in segmentation_names if name)
    ]
    values_by_type = {
        "All": [{"label": "All", "value": "All"}],
        config.filter_a_name: [
            {"label": config.filter_a_value, "value": config.filter_a_value}
        ],
        config.filter_b_name: [
            {"label": config.filter_b_value, "value": config.filter_b_value}
        ],
    }
    return html.Section(
        [
            html.H2(
                ui_text_component("report_configuration"),
                className="reports-section-title",
            ),
            _field(
                "¿Qué información quieres analizar?",
                "What information do you want to analyse?",
                dcc.RadioItems(
                    id="report-source-select",
                    options=[
                        {
                            "label": text("Datos sociales", "Social data"),
                            "value": "fra",
                        },
                        {
                            "label": text("Datos legales", "Legal data"),
                            "value": "ilga",
                        },
                        {
                            "label": text("Análisis combinado", "Combined analysis"),
                            "value": "combined",
                        },
                    ],
                    value=config.source,
                    className="reports-source-options",
                ),
            ),
            html.Div(
                [
                    html.P(text("Datos sociales: experiencias, opiniones y condiciones de vida recogidas en encuestas europeas LGBTIQ+.", "Social data: experiences, opinions and living conditions gathered in European LGBTIQ+ surveys.")),
                    html.P(text("Datos legales: protección, reconocimiento y derechos legales en Europa.", "Legal data: legal protection, recognition and rights across Europe.")),
                    html.P(text("Análisis combinado: relaciona experiencias sociales y protección legal sin asumir causalidad.", "Combined analysis: links social experiences and legal protection without assuming causality.")),
                ],
                className="reports-source-help",
            ),
            _field(
                "Título",
                "Title",
                dcc.Input(
                    id="report-title-input",
                    value=config.title,
                    type="text",
                    maxLength=180,
                    debounce=True,
                ),
            ),
            _field(
                "Organización (opcional. Aparecerá en el PDF)",
                "Organisation (optional. It will appear in the PDF)",
                dcc.Input(
                    id="report-organization-input",
                    value=config.organization,
                    type="text",
                    maxLength=120,
                    debounce=True,
                ),
            ),
            _field(
                "Autor o departamento (opcional. Aparecerá en el PDF)",
                "Author or department (optional. It will appear in the PDF)",
                dcc.Input(
                    id="report-author-input",
                    value=config.author,
                    type="text",
                    maxLength=120,
                    debounce=True,
                ),
            ),
            _field(
                "Año",
                "Year",
                dcc.Dropdown(
                    id="report-year-select",
                    options=years,
                    value=year,
                    clearable=False,
                ),
            ),
            _field(
                "Categoría",
                "Category",
                dcc.Dropdown(
                    id="report-category-select",
                    options=categories,
                    value=category or None,
                    clearable=False,
                ),
            ),
            _field(
                "Indicador social",
                "Social indicator",
                dcc.Dropdown(
                    id="report-indicator-select",
                    options=indicators,
                    value=config.indicator_id or None,
                    disabled=not social_source or not bool(category and indicators),
                    clearable=False,
                ),
                element_id="report-indicator-field",
                class_name="reports-field" if social_source else "reports-field is-hidden",
                required=True,
                error_id="report-indicator-error",
            ),
            _field(
                "Respuesta",
                "Answer",
                dcc.Dropdown(
                    id="report-answer-select",
                    options=list(controls.get("answers") or []),
                    value=config.answer or controls.get("default_answer"),
                    disabled=not social_source or not config.indicator_id,
                    clearable=False,
                ),
                element_id="report-answer-field",
                class_name="reports-field" if social_source else "reports-field is-hidden",
            ),
            html.Section(
                [
                    html.H3(text("Filtros", "Filters"), className="reports-subheading"),
                    html.Div(
                        [
                            _field(
                                "Tipo de filtro",
                                "Filter type",
                                dcc.Dropdown(
                                    id="report-filter-a-name",
                                    options=segmentations,
                                    value=config.filter_a_name,
                                    disabled=not social_source or not config.indicator_id,
                                    clearable=False,
                                ),
                            ),
                            _field(
                                "Valor",
                                "Value",
                                dcc.Dropdown(
                                    id="report-filter-a-value",
                                    options=list(values_by_type.get(config.filter_a_name) or []),
                                    value=config.filter_a_value,
                                    disabled=not social_source or config.filter_a_name == "All",
                                    clearable=False,
                                ),
                            ),
                            _field(
                                "Segundo filtro",
                                "Second filter",
                                dcc.Dropdown(
                                    id="report-filter-b-name",
                                    options=segmentations,
                                    value=config.filter_b_name,
                                    disabled=not social_source or config.filter_a_name != "All",
                                    clearable=False,
                                ),
                            ),
                            _field(
                                "Valor del segundo filtro",
                                "Second filter value",
                                dcc.Dropdown(
                                    id="report-filter-b-value",
                                    options=list(values_by_type.get(config.filter_b_name) or []),
                                    value=config.filter_b_value,
                                    disabled=(not social_source or config.filter_a_name != "All" or config.filter_b_name == "All"),
                                    clearable=False,
                                ),
                            ),
                        ],
                        className="reports-filters-grid",
                    ),
                ],
                id="report-filters-section",
                className=(
                    "reports-filters-section"
                    if config.source == "fra"
                    else "reports-filters-section is-hidden"
                ),
            ),
            _field(
                "País principal",
                "Main country",
                dcc.Dropdown(
                    id="report-primary-country",
                    options=country_options,
                    value=config.primary_country or None,
                    clearable=True,
                ),
            ),
            _field(
                "Países de comparación",
                "Comparison countries",
                dcc.Dropdown(
                    id="report-comparison-countries",
                    options=country_options,
                    value=[
                        country
                        for country in config.countries
                        if country != config.primary_country
                    ],
                    multi=True,
                ),
            ),
            _field(
                "Idioma",
                "Language",
                dcc.RadioItems(
                    id="report-language-select",
                    options=[
                        {"label": "Español", "value": "es"},
                        {"label": "English", "value": "en"},
                    ],
                    value=config.language,
                    inline=True,
                ),
            ),
            _field(
                "Fecha de generación",
                "Generation date",
                dcc.DatePickerSingle(
                    id="report-generated-on",
                    date=config.generated_on or utc_today_iso(),
                    display_format="YYYY-MM-DD",
                ),
            ),
        ],
        className="reports-card reports-card-configuration",
    )


def _hr_purpose_panel() -> Component:
    return html.Section(
        [
            html.H2(
                text("Informe orientado a RRHH", "HR-oriented report"),
                className="reports-section-title",
            ),
            html.P(
                text(
                    "El informe ayuda a interpretar el contexto externo LGBTIQ+ y a identificar posibles áreas de mejora en diversidad e inclusión.",
                    "The report helps interpret the external LGBTIQ+ context and identify possible areas for improving diversity and inclusion.",
                ),
                className="reports-generation-description",
            ),
            html.Div(
                [
                    html.H3(text("¿Qué se generará?", "What will be generated?")),
                    html.P(
                        text(
                            "RainbowLens creará un informe profesional con un resumen ejecutivo, los resultados y comparaciones más útiles, explicaciones de las gráficas, conclusiones prudentes, metodología, limitaciones y fuentes.",
                            "RainbowLens will create a professional report with an executive summary, the most useful results and comparisons, chart explanations, cautious conclusions, methodology, limitations and sources.",
                        )
                    ),
                    html.P(
                        text(
                            "Los resultados de FRA describen el contexto social de la población encuestada y del país. No constituyen una auditoría ni una medición de la plantilla de una empresa concreta.",
                            "FRA results describe the social context of the surveyed population and country. They are not an audit or measurement of a specific organisation's workforce.",
                        )
                    ),
                ],
                className="reports-hr-explanation",
            ),
            html.P(
                text(
                    "Las conclusiones y posibles actuaciones se construirán mediante reglas verificables a partir de las métricas. No se utilizará una IA externa para redactarlas.",
                    "Conclusions and possible actions will be built from metrics using verifiable rules. No external AI is used to write them.",
                ),
                className="reports-method-note",
            ),
        ],
        className="reports-card reports-card-purpose",
    )


def _preview_content(content) -> list[Component]:
    language = content.configuration.language
    enabled = set(content.configuration.sections)
    metrics = html.Div(
        [
            html.Div(
                [html.Span(metric.label), html.Strong(metric.display_value)],
                className="reports-preview-metric",
            )
            for metric in content.metrics[:7]
        ],
        className="reports-preview-metrics",
    )
    charts = [
        html.Div(
            [
                html.H3(chart.title),
                *[
                    html.Div(
                        [
                            html.H4(
                                f"{chart.title} ({page_index}/{len(chart.figures)})",
                                className="reports-preview-chart-page-title",
                            )
                            if len(chart.figures) > 1
                            else None,
                            dcc.Graph(
                                figure=figure,
                                config=chart_graph_config(),
                                responsive=True,
                                className="reports-preview-graph",
                            ),
                        ],
                        className="reports-preview-chart-page",
                    )
                    for page_index, figure in enumerate(chart.figures, start=1)
                ],
                html.Div(
                    [
                        html.P(
                            text(
                                "Puedes revisar estos textos antes de descargar el PDF. Los cambios no modifican los datos ni las gráficas.",
                                "You can review these texts before downloading the PDF. Changes do not alter the data or charts.",
                            ),
                            className="reports-chart-editor-note",
                        ),
                        _chart_narrative_field(
                            chart.key,
                            "what_shows",
                            text("¿Qué muestra?", "What does it show?"),
                            chart.what_shows,
                        ),
                        _chart_narrative_field(
                            chart.key,
                            "how_to_read",
                            text("¿Cómo se interpreta?", "How is it interpreted?"),
                            chart.how_to_read,
                        ),
                        _chart_narrative_field(
                            chart.key,
                            "observation",
                            text("¿Qué observamos?", "What do we observe?"),
                            chart.observation,
                        ),
                    ],
                    className="reports-chart-editor",
                ),
            ],
            className="reports-preview-chart",
        )
        for chart in content.charts
    ]
    map_chart_count = sum(chart.key.startswith("map_") for chart in content.charts)
    table = dag.AgGrid(
        columnDefs=[
            {"headerName": "Country" if language == "en" else "País", "field": "country"},
            {
                "headerName": "Value" if language == "en" else "Valor",
                "field": "value",
                "type": "numericColumn",
            },
            {
                "headerName": "Rank" if language == "en" else "Posición",
                "field": "position",
                "type": "numericColumn",
            },
            {
                "headerName": "EU difference" if language == "en" else "Diferencia UE",
                "field": "difference",
                "type": "numericColumn",
            },
            {
                "headerName": "Year" if language == "en" else "Año",
                "field": "year",
                "type": "numericColumn",
            },
        ],
        rowData=content.table_rows,
        defaultColDef={
            "sortable": True,
            "filter": True,
            "resizable": True,
            "wrapText": True,
            "autoHeight": True,
            "minWidth": 110,
            "flex": 1,
        },
        dashGridOptions={
            "pagination": True,
            "paginationPageSize": 10,
            "paginationPageSizeSelector": False,
            "domLayout": "autoHeight",
        },
        className="ag-theme-quartz reports-preview-grid",
        style={"width": "100%", "maxWidth": "100%"},
    )
    components: list[Component] = [
        html.Header(
            [
                html.P(content.configuration.organization, className="reports-preview-org"),
                html.H2(content.configuration.title),
                html.P(
                    content.focus_label,
                    className="reports-preview-focus",
                ),
                html.P(
                    f'"{content.indicator}" - {content.configuration.year or ""}',
                    className="reports-preview-subtitle",
                ),
            ]
        ),
    ]
    if "executive" in enabled:
        components.append(
            _preview_editable_section(
                "Resumen ejecutivo" if language == "es" else "Executive summary",
                "executive",
                default_section_narrative(content, "executive"),
            )
        )
    components.extend(charts[:map_chart_count])
    if "metrics" in enabled and content.metrics:
        components.append(metrics)
    components.extend(charts[map_chart_count:])
    if "context" in enabled:
        components.append(
            _preview_editable_section(
                "Contexto" if language == "es" else "Context",
                "context",
                default_section_narrative(content, "context"),
            )
        )
    if "workplace" in enabled and content.workplace_analysis:
        components.append(
            _preview_section(
                "Entorno laboral" if language == "es" else "Workplace",
                content.workplace_analysis,
            )
        )
    if "demographics" in enabled and content.demographic_analysis:
        components.append(
            _preview_section(
                "Diferencias sociodemográficas"
                if language == "es"
                else "Sociodemographic differences",
                content.demographic_analysis,
            )
        )
    if "comparison" in enabled and content.table_rows:
        components.append(
            html.Div(
                [
                    html.H3("Comparación" if language == "es" else "Comparison"),
                    html.Div(table, className="reports-preview-table-scroll"),
                ],
                className="reports-preview-section",
            )
        )
    if "interpretation" in enabled and content.conclusions:
        components.append(
            _preview_section(
                "Interpretación y conclusiones"
                if language == "es"
                else "Interpretation and conclusions",
                content.conclusions,
            )
        )
    if "recommendations" in enabled and content.recommendations:
        components.append(
            _preview_editable_section(
                (
                    "Posibles líneas de actuación"
                    if language == "es"
                    else "Possible courses of action"
                ),
                "recommendations",
                default_section_narrative(content, "recommendations"),
            )
        )
    if "limitations" in enabled and content.limitations:
        components.append(
            _preview_section(
                "Limitaciones" if language == "es" else "Limitations",
                content.limitations,
            )
        )
    if "methodology" in enabled:
        components.append(
            _preview_section(
                "Metodología" if language == "es" else "Methodology",
                content.methodology,
            )
        )
    # Source attribution is not an optional report section: every generated
    # preview must identify the external dataset it actually contains.
    if content.sources:
        components.append(
            _preview_section(
                (
                    "Fuentes, metodología y atribuciones"
                    if language == "es"
                    else "Sources, methodology and attributions"
                ),
                content.sources,
            )
        )
    return components


def _chart_narrative_field(
    chart_key: str,
    field: str,
    label: Component,
    value: str,
) -> Component:
    return html.Label(
        [
            html.Span(label),
            dcc.Textarea(
                id={
                    "type": "report-chart-narrative",
                    "chart": chart_key,
                    "field": field,
                },
                value=value,
                maxLength=2_000,
                rows=4,
                className="reports-chart-narrative",
            ),
        ],
        className="reports-chart-editor-field",
    )


def _chart_narratives_from_pattern(
    values: list[str | None] | None,
    ids: list[dict[str, str]] | None,
) -> dict[str, dict[str, str]]:
    narratives: dict[str, dict[str, str]] = {}
    allowed_fields = {"what_shows", "how_to_read", "observation"}
    for value, component_id in zip(values or [], ids or [], strict=False):
        chart = str(component_id.get("chart") or "").strip()
        field = str(component_id.get("field") or "").strip()
        if chart and field in allowed_fields:
            narratives.setdefault(chart, {})[field] = str(value or "")
    return narratives


def _section_narratives_from_pattern(
    values: list[str | None] | None,
    ids: list[dict[str, str]] | None,
) -> dict[str, str]:
    allowed_sections = {"executive", "context", "recommendations"}
    return {
        section: str(value or "")
        for value, component_id in zip(values or [], ids or [], strict=False)
        if (section := str(component_id.get("section") or "").strip())
        in allowed_sections
    }


def _preview_editable_section(title: str, section: str, value: str) -> Component:
    return html.Label(
        [
            html.Span(title, className="reports-section-editor-title"),
            dcc.Textarea(
                id={"type": "report-section-narrative", "section": section},
                value=value,
                maxLength=8_000,
                rows=max(5, min(12, value.count("\n") + 4)),
                className="reports-section-narrative",
            ),
        ],
        className="reports-preview-section reports-section-editor",
    )


def _preview_section(title: str, values: list[str]) -> Component:
    return html.Div(
        [html.H3(title), *[html.P(value) for value in values]],
        className="reports-preview-section",
    )


def _preview_error(language: str) -> Component:
    return html.Div(
        [
            html.H2("Error de vista previa" if language == "es" else "Preview error"),
            html.P(
                "No se ha podido generar el contenido con la selección actual."
                if language == "es"
                else "The content could not be generated from the current selection."
            ),
        ]
    )


def _configuration_from_controls(**values: Any) -> ReportConfiguration:
    inherited = dict(values.pop("inherited_configuration", None) or {})
    comparison = list(values.pop("comparison_countries") or [])
    primary = values.get("primary_country")
    countries = ([primary] if primary else []) + comparison
    return ReportConfiguration.from_mapping(
        {
            **inherited,
            **values,
            "indicator_id": values.pop("indicator", None),
            "countries": countries,
        }
    )


def _selected_option_label(
    options: list[dict[str, Any]] | None,
    selected_value: Any,
) -> str:
    clean_value = str(selected_value or "").strip()
    for option in options or []:
        if str(option.get("value") or "").strip() != clean_value:
            continue
        label = option.get("label")
        return str(label).strip() if isinstance(label, str) else ""
    return ""


def _current_user_id() -> str:
    get_id = getattr(current_user, "get_id", None)
    return str(get_id() or "") if callable(get_id) else ""


def _year_options(source: str) -> list[dict[str, Any]]:
    values = get_fra_years() if source in {"fra", "combined"} else get_ilga_years()
    if source in {"fra", "combined"}:
        return [
            {
                "label": text(f"Encuesta {year}", f"Survey {year}"),
                "value": year,
            }
            for year in values
            if year in {2023, 2019}
        ]
    return [{"label": str(year), "value": year} for year in values]


def _category_options(source: str, year: int | None) -> list[dict[str, Any]]:
    if source in {"fra", "combined"}:
        values = get_fra_categories(year)
    else:
        values = ["Ranking total", *get_ilga_criteria_categories_by_year(year)]
    return [
        {
            "label": text(
                *taxonomy_pair(
                    "fra_category" if source in {"fra", "combined"} else "ilga_category",
                    category,
                )
            ),
            "value": category,
        }
        for category in values
        if normalize_text_key(category) not in EXCLUDED_CATEGORIES
    ]


def _indicator_options(
    source: str,
    category: str,
    year: int | None,
) -> list[dict[str, str]]:
    if source not in {"fra", "combined"} or not category:
        return []
    return [
        {"label": indicator.label, "value": indicator.code}
        for indicator in get_fra_mongo_indicators_by_category(category, year)
    ]


def _country_options(selected: tuple[str, ...]) -> list[dict[str, Any]]:
    known = set(REPORT_COUNTRY_CODES)
    values = [
        {"label": text(label_es, label_en), "value": code}
        for code in REPORT_COUNTRY_CODES
        for label_es, label_en in [country_labels(code)]
    ]
    values.extend({"label": code, "value": code} for code in selected if code not in known)
    return values


def _field(
    label_es: str,
    label_en: str,
    component: Component,
    *,
    element_id: str | None = None,
    class_name: str = "reports-field",
    required: bool = False,
    error_id: str | None = None,
) -> Component:
    props: dict[str, Any] = {"className": class_name}
    if element_id:
        props["id"] = element_id
    control_id = getattr(component, "id", None)
    is_native_form_control = component.__class__.__name__ in {"Input", "Textarea"}
    label_content: Component | list[Component] = html.Span(
        label_es,
        **text_attrs(label_es, label_en),
    )
    if required:
        label_content = [
            label_content,
            html.Span(
                " *",
                className="reports-required-marker",
                title="Obligatorio / Required",
                **dash_attrs({"aria-hidden": "true"}),
            ),
        ]
        props["aria-required"] = "true"
    if control_id and not is_native_form_control:
        label_id = f"{control_id}-label"
        label_node = html.Span(
            label_content,
            id=label_id,
            className="reports-field-label",
        )
        props.update({"role": "group", "aria-labelledby": label_id})
    else:
        label_node = html.Label(
            label_content,
            htmlFor=control_id,
        )
    children: list[Component] = [label_node, component]
    if error_id:
        children.append(
            html.P(
                "",
                id=error_id,
                className="reports-field-error is-hidden",
                role="alert",
                **dash_attrs({"aria-live": "polite"}),
            )
        )
    return html.Div(
        children,
        **dash_attrs(props),
    )


def _requires_social_indicator(source: str | None) -> bool:
    return source in {"fra", "combined"}


def _missing_social_indicator(
    source: str | None,
    category: str | None,
    indicator: str | None,
) -> bool:
    return _requires_social_indicator(source) and bool(category) and not indicator


def _t(language: str | None, es: str, en: str) -> str:
    return en if language == "en" else es
