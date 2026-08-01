from __future__ import annotations

import logging
import os
from typing import Any

import dash_ag_grid as dag
from dash import Dash, Input, Output, State, dcc, html, no_update
from dash.development.base_component import Component
from flask_login import current_user

from app.analytics.repository import (
    assert_analytics_databases_available,
    get_fra_categories,
    get_fra_mongo_indicators_by_category,
    get_fra_years,
    get_ilga_criteria_by_year,
    get_ilga_criteria_categories_by_year,
    get_ilga_years,
)
from app.analytics.statistics_exports import chart_graph_config
from app.analytics.statistics_normalizers import normalize_text_key
from app.auth.permissions import (
    Permission,
    can_configure_advanced_reports,
    user_has_permission,
)
from app.auth.rate_limit import create_rate_limiter
from app.dash.i18n import country_labels, dash_attrs, text, text_attrs
from app.dash.layouts.navigation import build_navbar
from app.dates import utc_today_iso
from app.http_security import rate_limit_key
from app.reports.models import (
    DEFAULT_REPORT_CHARTS,
    DEFAULT_REPORT_SECTIONS,
    ReportConfiguration,
)
from app.reports.service import (
    ReportGenerationError,
    build_report,
    generate_report_pdf,
)

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
    "methodology": ("Objetivo y metodología", "Objective and methodology"),
    "metrics": ("Métricas principales", "Key metrics"),
    "workplace": ("Entorno laboral", "Workplace"),
    "comparison": ("Comparaciones", "Comparisons"),
    "demographics": ("Diferencias sociodemográficas", "Sociodemographic differences"),
    "risks": ("Áreas de riesgo", "Risk areas"),
    "recommendations": ("Recomendaciones", "Recommendations"),
    "limitations": ("Limitaciones", "Limitations"),
    "sources": ("Fuentes", "Sources"),
}

CHART_LABELS = {
    "ranking": ("Ranking europeo", "European ranking"),
    "average": ("Comparación con la media", "Average comparison"),
    "countries": ("Comparación de respuestas", "Response comparison"),
    "responses": ("Detalle de respuestas o criterios", "Response or criteria detail"),
    "temporal": ("Evolución temporal", "Temporal evolution"),
    "radar": (
        "Experiencia real y protección legal",
        "Real-life experience and legal protection",
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
    if current_user.is_authenticated:
        values.setdefault("organization", getattr(current_user, "organization", "") or "")
        values.setdefault("author", getattr(current_user, "username", "") or "")
    config = _report_configuration_for_user(values)
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
                    html.Header(
                        [
                            html.P(
                                "Informes personalizados",
                                className="stats-eyebrow",
                                **text_attrs("Informes personalizados", "Custom reports"),
                            ),
                            html.H1(
                                text(
                                    "Informe de diversidad e inclusión",
                                    "Diversity and inclusion report",
                                )
                            ),
                            html.P(
                                text(
                                    "Configura, previsualiza y descarga un informe basado en las estadísticas europeas actuales.",
                                    "Configure, preview and download a report based on the current European statistics.",
                                ),
                                className="reports-lead",
                            ),
                        ],
                        className="reports-header",
                    ),
                    html.Div(
                        [
                            _configuration_panel(
                                config,
                                years,
                                year,
                                categories,
                                category,
                                indicators,
                                country_options,
                            ),
                            _content_panel(
                                config,
                                advanced_enabled=can_configure_advanced_reports(current_user),
                            ),
                        ],
                        className="reports-config-grid",
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
                        className="reports-actions",
                    ),
                    dcc.Loading(
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
                        type="circle",
                    ),
                ],
                className="reports-shell",
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
                        text("Volver a Estadísticas", "Back to Statistics"), href="/statistics"
                    ),
                ],
                className="reports-access-denied",
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
        Output("report-indicator-field", "className"),
        Output("report-criterion-field", "className"),
        Output("report-criterion-select", "options"),
        Output("report-criterion-select", "value"),
        Input("report-source-select", "value"),
        Input("report-category-select", "value"),
        Input("report-year-select", "value"),
        State("report-indicator-select", "value"),
        State("report-criterion-select", "value"),
    )
    def update_report_indicators(
        source: str | None,
        category: str | None,
        year: int | None,
        current_indicator: str | None,
        current_criterion: str | None,
    ):
        options = _indicator_options(source or "fra", category or "", year)
        values = {item["value"] for item in options}
        value = current_indicator if current_indicator in values else None
        is_fra = source == "fra"
        criterion_options = [] if is_fra else _criterion_options(year, category or "")
        criterion_values = {item["value"] for item in criterion_options}
        return (
            options,
            value,
            "reports-field" if is_fra else "reports-field is-hidden",
            "reports-field is-hidden" if is_fra else "reports-field",
            criterion_options,
            current_criterion if current_criterion in criterion_values else None,
        )

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
        State("report-criterion-select", "value"),
        State("report-year-select", "value"),
        State("report-primary-country", "value"),
        State("report-comparison-countries", "value"),
        State("report-language-select", "value"),
        State("report-mode-select", "value"),
        State("report-detail-select", "value"),
        State("report-sections-select", "value"),
        State("report-charts-select", "value"),
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
        criterion: str | None,
        year: int | None,
        primary_country: str | None,
        comparison_countries: list[str] | None,
        language: str | None,
        mode: str | None,
        detail_level: str | None,
        sections: list[str] | None,
        charts: list[str] | None,
        generated_on: str | None,
        inherited_configuration: dict[str, Any] | None,
    ):
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
        limiter_key = rate_limit_key(subject=current_user.get_id() or "", scope="report-preview")
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
        if not can_configure_advanced_reports(current_user):
            mode = "automatic"
            detail_level = "standard"
            sections = list(DEFAULT_REPORT_SECTIONS)
            charts = list(DEFAULT_REPORT_CHARTS)
        config = _configuration_from_controls(
            title=title,
            organization=organization,
            author=author,
            source=source,
            category=category,
            indicator=indicator,
            criterion=criterion,
            year=year,
            primary_country=primary_country,
            comparison_countries=comparison_countries,
            language=language,
            mode=mode,
            detail_level=detail_level,
            sections=sections,
            charts=charts,
            generated_on=generated_on,
            inherited_configuration=inherited_configuration,
        )
        try:
            content = build_report(config)
        except ReportGenerationError as exc:
            logger.warning("report_preview_failed", extra={"reason": str(exc)})
            return (
                _preview_error(config.language),
                "reports-preview-empty",
                _t(
                    config.language,
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
        Output("report-download", "data"),
        Output("report-status", "children", allow_duplicate=True),
        Output("report-status", "className", allow_duplicate=True),
        Input("report-download-button", "n_clicks"),
        State("report-config-store", "data"),
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
        limiter_key = rate_limit_key(subject=current_user.get_id() or "", scope="report-download")
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
            generated = generate_report_pdf(_report_configuration_for_user(stored_configuration))
        except ReportGenerationError:
            return (
                no_update,
                _t(
                    language,
                    "No se ha podido generar el informe.",
                    "The report could not be generated.",
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


def _report_configuration_for_user(values: dict[str, Any] | None) -> ReportConfiguration:
    payload = dict(values or {})
    if not can_configure_advanced_reports(current_user):
        payload.update(
            {
                "mode": "automatic",
                "detail_level": "standard",
                "sections": list(DEFAULT_REPORT_SECTIONS),
                "charts": list(DEFAULT_REPORT_CHARTS),
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
    return html.Section(
        [
            html.H2(text("1. Configuración", "1. Configuration")),
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
                "Organización",
                "Organisation",
                dcc.Input(
                    id="report-organization-input",
                    value=config.organization,
                    type="text",
                    maxLength=120,
                    debounce=True,
                ),
            ),
            _field(
                "Autor o departamento",
                "Author or department",
                dcc.Input(
                    id="report-author-input",
                    value=config.author,
                    type="text",
                    maxLength=120,
                    debounce=True,
                ),
            ),
            _field(
                "Tipo de datos",
                "Data type",
                dcc.RadioItems(
                    id="report-source-select",
                    options=[
                        {"label": "FRA", "value": "fra"},
                        {"label": "ILGA-Europe", "value": "ilga"},
                    ],
                    value=config.source,
                    inline=True,
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
                "Indicador FRA",
                "FRA indicator",
                dcc.Dropdown(
                    id="report-indicator-select",
                    options=indicators,
                    value=config.indicator_id or None,
                    clearable=False,
                ),
                element_id="report-indicator-field",
                class_name="reports-field" if config.source == "fra" else "reports-field is-hidden",
            ),
            _field(
                "Criterio ILGA-Europe",
                "ILGA-Europe criterion",
                dcc.Dropdown(
                    id="report-criterion-select",
                    options=([] if config.source == "fra" else _criterion_options(year, category)),
                    value=config.criterion or None,
                    clearable=True,
                ),
                element_id="report-criterion-field",
                class_name="reports-field is-hidden" if config.source == "fra" else "reports-field",
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
                    value=list(config.countries),
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
        className="reports-card",
    )


def _content_panel(
    config: ReportConfiguration,
    *,
    advanced_enabled: bool,
) -> Component:
    return html.Section(
        [
            html.H2(text("2. Selección de contenido", "2. Content selection")),
            html.P(
                text(
                    "Las opciones avanzadas están disponibles para perfiles RRHH, Político y ONG.",
                    "Advanced options are available to HR, Policy maker and NGO profiles.",
                ),
                className="reports-advanced-notice" if not advanced_enabled else "is-hidden",
            ),
            _field(
                "Modo",
                "Mode",
                dcc.RadioItems(
                    id="report-mode-select",
                    options=[
                        {
                            "label": text("Automático", "Automatic"),
                            "value": "automatic",
                            "disabled": not advanced_enabled,
                        },
                        {
                            "label": text("Personalizado", "Custom"),
                            "value": "custom",
                            "disabled": not advanced_enabled,
                        },
                    ],
                    value=config.mode,
                ),
            ),
            _field(
                "Nivel de detalle",
                "Detail level",
                dcc.RadioItems(
                    id="report-detail-select",
                    options=[
                        {
                            "label": text("Estándar", "Standard"),
                            "value": "standard",
                            "disabled": not advanced_enabled,
                        },
                        {
                            "label": text("Detallado", "Detailed"),
                            "value": "detailed",
                            "disabled": not advanced_enabled,
                        },
                    ],
                    value=config.detail_level,
                    inline=True,
                ),
            ),
            _field(
                "Secciones",
                "Sections",
                dcc.Checklist(
                    id="report-sections-select",
                    options=[
                        {
                            "label": text(*SECTION_LABELS[key]),
                            "value": key,
                            "disabled": not advanced_enabled,
                        }
                        for key in DEFAULT_REPORT_SECTIONS
                    ],
                    value=list(config.sections),
                    className="reports-checklist",
                ),
            ),
            _field(
                "Gráficos",
                "Charts",
                dcc.Checklist(
                    id="report-charts-select",
                    options=[
                        {
                            "label": text(*CHART_LABELS[key]),
                            "value": key,
                            "disabled": not advanced_enabled,
                        }
                        for key in DEFAULT_REPORT_CHARTS
                    ],
                    value=list(config.charts),
                    className="reports-checklist",
                ),
            ),
            html.Div(
                [
                    html.H3(text("Filtros heredados", "Inherited filters")),
                    html.P(
                        _inherited_filter_summary(config),
                        className="reports-filter-summary",
                    ),
                ],
                className="reports-inherited-filters",
            ),
        ],
        className="reports-card",
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
                dcc.Graph(
                    figure=chart.figure,
                    config=chart_graph_config(),
                    responsive=True,
                ),
            ],
            className="reports-preview-chart",
        )
        for chart in content.charts
    ]
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
        defaultColDef={"sortable": True, "filter": True, "resizable": True},
        dashGridOptions={
            "pagination": True,
            "paginationPageSize": 10,
            "paginationPageSizeSelector": False,
            "domLayout": "autoHeight",
        },
        className="ag-theme-quartz reports-preview-grid",
        style={"width": "100%"},
    )
    components: list[Component] = [
        html.Header(
            [
                html.P(content.configuration.organization, className="reports-preview-org"),
                html.H2(content.configuration.title),
                html.P(
                    f"{content.indicator} - {content.configuration.year or ''}",
                    className="reports-preview-subtitle",
                ),
            ]
        ),
    ]
    if "executive" in enabled:
        components.append(
            _preview_section(
                "Resumen ejecutivo" if language == "es" else "Executive summary",
                content.executive_summary,
            )
        )
    if "methodology" in enabled:
        components.append(
            _preview_section(
                "Metodología" if language == "es" else "Methodology",
                content.methodology,
            )
        )
    if "metrics" in enabled and content.metrics:
        components.append(metrics)
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
    components.extend(charts)
    if "comparison" in enabled and content.table_rows:
        components.append(
            html.Div(
                [
                    html.H3("Comparación" if language == "es" else "Comparison"),
                    table,
                ],
                className="reports-preview-section",
            )
        )
    if "risks" in enabled and content.conclusions:
        components.append(
            _preview_section(
                "Áreas de riesgo" if language == "es" else "Risk areas",
                content.conclusions,
            )
        )
    if "recommendations" in enabled and content.recommendations:
        components.append(_preview_recommendations(content))
    if "limitations" in enabled and content.limitations:
        components.append(
            _preview_section(
                "Limitaciones" if language == "es" else "Limitations",
                content.limitations,
            )
        )
    if "sources" in enabled and content.sources:
        components.append(
            _preview_section(
                "Fuentes" if language == "es" else "Sources",
                content.sources,
            )
        )
    return components


def _preview_recommendations(content) -> Component:
    language = content.configuration.language
    derived = [item.text for item in content.recommendations if item.derived_from_metrics]
    general = [item.text for item in content.recommendations if not item.derived_from_metrics]
    return html.Div(
        [
            html.H3("Recomendaciones" if language == "es" else "Recommendations"),
            html.H4("Derivadas de las métricas" if language == "es" else "Derived from metrics")
            if derived
            else None,
            html.Ul([html.Li(item) for item in derived]),
            html.H4("Buenas prácticas generales" if language == "es" else "General good practices"),
            html.Ul([html.Li(item) for item in general]),
        ],
        className="reports-preview-section",
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


def _year_options(source: str) -> list[dict[str, Any]]:
    values = get_fra_years() if source == "fra" else get_ilga_years()
    return [{"label": str(year), "value": year} for year in values]


def _category_options(source: str, year: int | None) -> list[dict[str, Any]]:
    if source == "fra":
        values = get_fra_categories()
    else:
        values = ["Ranking total", *get_ilga_criteria_categories_by_year(year)]
    return [
        {
            "label": (
                text("Ranking total", "Overall ranking")
                if category == "Ranking total"
                else category
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
    if source != "fra" or not category:
        return []
    return [
        {"label": indicator.label, "value": indicator.code}
        for indicator in get_fra_mongo_indicators_by_category(category)
    ]


def _criterion_options(
    year: int | None,
    category: str,
) -> list[dict[str, str]]:
    if not category or category == "Ranking total":
        return []
    return [
        {"label": str(item["indicator"]), "value": str(item["indicator"])}
        for item in get_ilga_criteria_by_year(year, category)
        if item.get("indicator")
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


def _inherited_filter_summary(config: ReportConfiguration) -> str:
    filters = [
        config.answer,
        f"{config.filter_a_name}: {config.filter_a_value}"
        if config.filter_a_name != "All" or config.filter_a_value != "All"
        else "",
        f"{config.filter_b_name}: {config.filter_b_value}"
        if config.filter_b_name != "All" or config.filter_b_value != "All"
        else "",
    ]
    return " · ".join(value for value in filters if value) or (
        "No additional filters" if config.language == "en" else "Sin filtros adicionales"
    )


def _field(
    label_es: str,
    label_en: str,
    component: Component,
    *,
    element_id: str | None = None,
    class_name: str = "reports-field",
) -> Component:
    props: dict[str, Any] = {"className": class_name}
    if element_id:
        props["id"] = element_id
    return html.Div(
        [
            html.Label(label_es, **text_attrs(label_es, label_en)),
            component,
        ],
        **props,
    )


def _t(language: str | None, es: str, en: str) -> str:
    return en if language == "en" else es
