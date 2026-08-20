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
from app.analytics.statistics_service import get_fra_control_payload
from app.auth.permissions import Permission, user_has_permission
from app.auth.rate_limit import create_rate_limiter
from app.dash.components.loading import contextual_loading
from app.dash.i18n import (
    country_labels,
    dash_attrs,
    text,
    text_attrs,
    ui_text,
    ui_text_component,
)
from app.dash.layouts.navigation import build_navbar
from app.dash.routes import route_path
from app.dates import utc_today_iso
from app.http_security import rate_limit_key
from app.reports.models import ReportConfiguration, normalize_report_countries
from app.reports.service import (
    ReportGenerationError,
    build_report,
    generate_report_pdf,
)
from app.reports.templates import (
    ReportTemplate,
    apply_template_defaults,
    find_report_template,
    report_objective,
    report_profile,
    report_profile_for_template,
    report_profile_for_user,
    report_profile_key,
    report_templates_for_user,
)
from app.taxonomy import taxonomy_pair

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
    "education": ("Actividad didáctica", "Learning activity"),
    "data_quality": ("Disponibilidad de datos", "Data availability"),
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
    language = "en" if values.get("language") == "en" else "es"
    templates = report_templates_for_user(current_user)
    selected_template = find_report_template(current_user, str(values.get("template_id") or ""))
    values = apply_template_defaults(values, selected_template, language=language)
    config = _report_configuration_for_user(values)
    profile = report_profile(config.profile_key)
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
                                ui_text("report_generation_eyebrow", "es"),
                                className="stats-eyebrow",
                                **text_attrs(
                                    ui_text("report_generation_eyebrow", "es"),
                                    ui_text("report_generation_eyebrow", "en"),
                                ),
                            ),
                            html.H1(text("Crear informe", "Create report")),
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
                                templates,
                                selected_template,
                            ),
                            _profile_panel(config, profile),
                        ],
                        className="reports-config-grid",
                    ),
                    html.Section(
                        [
                            html.H2(text("Resumen de la configuración", "Configuration summary")),
                            html.Div(id="report-plan-summary"),
                            html.P(
                                text(
                                    "El informe incluirá resultados, comparaciones, interpretación, conclusiones y posibles actuaciones adaptadas al uso seleccionado.",
                                    "The report will include results, comparisons, interpretation, conclusions and possible actions adapted to the selected use.",
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
                        className="reports-actions",
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
                className="reports-shell app-page-container",
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
        Output("report-title-input", "value"),
        Output("report-source-select", "value"),
        Output("report-profile-description", "children"),
        Output("report-template-description", "children"),
        Input("report-template-select", "value"),
        Input("report-language-select", "value"),
        prevent_initial_call=True,
    )
    def apply_selected_report_template(template_id: str | None, language: str | None):
        clean_language = "en" if language == "en" else "es"
        template = find_report_template(current_user, template_id)
        defaults = template.defaults(clean_language)
        profile = (
            report_profile_for_template(template.id)
            if report_profile_key(current_user) == "admin"
            else report_profile_for_user(current_user)
        ) or report_profile_for_user(current_user)
        return (
            defaults["title"],
            defaults["source"],
            profile.description(clean_language),
            template.description(clean_language),
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
        is_social = source in {"fra", "combined"}
        criterion_options = [] if is_social else _criterion_options(year, category or "")
        criterion_values = {item["value"] for item in criterion_options}
        return (
            options,
            value,
            "reports-field" if is_social else "reports-field is-hidden",
            "reports-field is-hidden" if is_social else "reports-field",
            criterion_options,
            current_criterion if current_criterion in criterion_values else None,
        )

    @app.callback(
        Output("report-answer-select", "options"),
        Output("report-answer-select", "value"),
        Output("report-answer-select", "disabled"),
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
        enabled = source in {"fra", "combined"} and bool(indicator)
        payload = (
            get_fra_control_payload(indicator or "", category, year) if enabled else {}
        )
        answers = list(payload.get("answers") or [])
        answer_values = {item["value"] for item in answers}
        answer = (
            current_answer
            if current_answer in answer_values
            else payload.get("default_answer")
        )
        segmentations = list(payload.get("segmentations") or [])
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
        b_enabled = enabled and a_name == "All"
        if not b_enabled:
            b_name, b_value, b_options = "All", "All", list(values_by_type.get("All") or [])
        return (
            answers, answer, not enabled, segmentations, a_name, not enabled,
            a_options, a_value, not enabled or a_name == "All",
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
        Input("report-template-select", "value"),
    )
    def update_report_plan_summary(
        source: str | None,
        year: int | None,
        primary_country: str | None,
        comparison_countries: list[str] | None,
        answer: str | None,
        language: str | None,
        template_id: str | None,
    ):
        clean_language = "en" if language == "en" else "es"
        profile_key = report_profile_key(current_user)
        profile = (
            report_profile_for_template(template_id)
            if profile_key == "admin"
            else report_profile(profile_key)
        ) or report_profile(profile_key)
        profile_key = profile.key
        source_label = {
            "fra": _t(clean_language, "Datos sociales", "Social data"),
            "ilga": _t(clean_language, "Datos legales", "Legal data"),
            "combined": _t(clean_language, "Análisis combinado", "Combined analysis"),
        }.get(source or "fra", source or "")
        countries = [country for country in [primary_country, *(comparison_countries or [])] if country]
        return html.Dl(
            [
                html.Dt(_t(clean_language, "Perfil", "Profile")),
                html.Dd(profile.name(clean_language)),
                html.Dt(_t(clean_language, "Tipo de información", "Information type")),
                html.Dd(source_label),
                html.Dt(_t(clean_language, "Encuesta / año", "Survey / year")),
                html.Dd(str(year or "—")),
                html.Dt(_t(clean_language, "Países", "Countries")),
                html.Dd(", ".join(countries) or _t(clean_language, "Europa", "Europe")),
                html.Dt(_t(clean_language, "Respuesta", "Answer")),
                html.Dd(answer or "—"),
            ],
            className="reports-plan-list",
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
        State("report-template-select", "value"),
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
        State("report-answer-select", "value"),
        State("report-filter-a-name", "value"),
        State("report-filter-a-value", "value"),
        State("report-filter-b-name", "value"),
        State("report-filter-b-value", "value"),
        State("report-spanish-context", "value"),
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
        template_id: str | None,
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
        answer: str | None,
        filter_a_name: str | None,
        filter_a_value: str | None,
        filter_b_name: str | None,
        filter_b_value: str | None,
        spanish_context: list[str] | None,
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
        config = _configuration_from_controls(
            title=title,
            template_id=template_id,
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
            answer=answer,
            filter_a_name=filter_a_name,
            filter_a_value=filter_a_value,
            filter_b_name=filter_b_name,
            filter_b_value=filter_b_value,
            include_spanish_context="include" in (spanish_context or []),
            generated_on=generated_on,
            inherited_configuration=inherited_configuration,
        )
        config = _report_configuration_for_user(config.to_dict())
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
    authenticated_profile_key = report_profile_key(current_user)
    template = find_report_template(current_user, str(payload.get("template_id") or ""))
    target_profile = report_profile(authenticated_profile_key)
    if authenticated_profile_key == "admin":
        target_profile = report_profile_for_template(template.id) or target_profile
    objective = report_objective(target_profile.key, str(payload.get("objective") or ""))
    source = str(payload.get("source") or template.source)
    if source == "combined":
        combined_charts = {
            "comun": ("scatter", "median_difference"),
            "anonymous": ("scatter", "median_difference"),
            "docente": ("scatter", "quadrants", "median_difference"),
            "rrhh": ("scatter", "median_difference", "availability"),
            "ong": ("quadrants", "median_difference", "availability"),
            "politico": ("scatter", "quadrants", "median_difference"),
            "sociologo": ("scatter", "quadrants", "median_difference", "availability"),
            "admin": ("scatter", "quadrants", "median_difference", "availability"),
        }
        charts = combined_charts.get(target_profile.key, ("scatter", "median_difference"))
    else:
        charts = tuple(
            key
            for key in target_profile.recommended_charts
            if key not in {"scatter", "quadrants", "median_difference", "availability"}
        )
    selected_countries = set(normalize_report_countries(payload.get("countries")))
    spanish_context = (
        bool(payload.get("include_spanish_context"))
        and target_profile.supports_spanish_context
        and "ES" in selected_countries
    )
    payload.update(
        {
            "template_id": template.id,
            "profile_key": target_profile.key,
            "objective": objective.id,
            "detail_level": "detailed"
            if target_profile.key in {"sociologo", "admin"}
            else template.detail_level,
            "sections": list(target_profile.recommended_sections),
            "charts": list(charts),
            "include_spanish_context": spanish_context,
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
    templates: tuple[ReportTemplate, ...],
    selected_template: ReportTemplate,
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
                "Plantilla para tu perfil",
                "Template for your profile",
                dcc.Dropdown(
                    id="report-template-select",
                    options=[
                        {
                            "label": text(template.name_es, template.name_en),
                            "value": template.id,
                        }
                        for template in templates
                    ],
                    value=selected_template.id,
                    clearable=False,
                ),
            ),
            html.P(
                text(selected_template.description_es, selected_template.description_en),
                id="report-template-description",
                className="reports-template-description",
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
                "Organización (opcional; aparecerá en el PDF)",
                "Organisation (optional; shown in the PDF)",
                dcc.Input(
                    id="report-organization-input",
                    value=config.organization,
                    type="text",
                    maxLength=120,
                    debounce=True,
                ),
            ),
            _field(
                "Autor o departamento (opcional; aparecerá en el PDF)",
                "Author or department (optional; shown in the PDF)",
                dcc.Input(
                    id="report-author-input",
                    value=config.author,
                    type="text",
                    maxLength=120,
                    debounce=True,
                ),
            ),
            _field(
                "¿Qué información quieres analizar?",
                "What information do you want to analyse?",
                dcc.RadioItems(
                    id="report-source-select",
                    options=[
                        {"label": text("Datos sociales", "Social data"), "value": "fra"},
                        {"label": text("Datos legales", "Legal data"), "value": "ilga"},
                        {"label": text("Análisis combinado", "Combined analysis"), "value": "combined"},
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
                    clearable=False,
                ),
                element_id="report-indicator-field",
                class_name="reports-field" if social_source else "reports-field is-hidden",
            ),
            _field(
                "Criterio legal",
                "Legal criterion",
                dcc.Dropdown(
                    id="report-criterion-select",
                    options=([] if social_source else _criterion_options(year, category)),
                    value=config.criterion or None,
                    clearable=True,
                ),
                element_id="report-criterion-field",
                class_name="reports-field is-hidden" if social_source else "reports-field",
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
            ),
            html.H3(text("Segmentación", "Segmentation"), className="reports-subheading"),
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
                className="reports-segmentation-grid",
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
            _field(
                "Contexto español complementario",
                "Complementary Spanish context",
                dcc.Checklist(
                    id="report-spanish-context",
                    options=[
                        {
                            "label": text("Incluir referencias FELGTBI+ cuando España esté seleccionada", "Include FELGTBI+ references when Spain is selected"),
                            "value": "include",
                            "disabled": not report_profile(config.profile_key).supports_spanish_context,
                        }
                    ],
                    value=["include"] if config.include_spanish_context else [],
                ),
            ),
        ],
        className="reports-card reports-card-configuration",
    )


def _profile_panel(config: ReportConfiguration, profile) -> Component:
    return html.Section(
        [
            html.P(
                text("Recomendado para tu perfil", "Recommended for your profile"),
                className="stats-eyebrow",
            ),
            html.H2(
                text("Personaliza el informe", "Personalise the report"),
                className="reports-section-title",
            ),
            html.P(
                text(profile.description_es, profile.description_en),
                id="report-profile-description",
                className="reports-profile-description",
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
                            "El contenido, el nivel de detalle y las posibles líneas de actuación se adaptan automáticamente a las necesidades del perfil que tienes configurado en la aplicación.",
                            "The content, level of detail and possible courses of action are automatically adapted to the needs of the profile configured in your account.",
                        )
                    ),
                ],
                className="reports-profile-explanation",
            ),
            html.Div(
                [
                    html.H3(text("Qué incluirá", "What it will include")),
                    html.Ul(
                        [
                            html.Li(text(*SECTION_LABELS.get(key, (key, key))))
                            for key in profile.recommended_sections
                        ]
                    ),
                ],
                className="reports-profile-output",
            ),
            html.P(
                text(
                    "Las conclusiones y posibles actuaciones se construirán mediante reglas verificables a partir de las métricas. No se utilizará una IA externa para redactarlas.",
                    "Conclusions and possible actions will be built from metrics using verifiable rules. No external AI is used to write them.",
                ),
                className="reports-method-note",
            ),
        ],
        className="reports-card reports-card-profile",
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
                html.Details(
                    [
                        html.Summary(text("¿Cómo interpretar esta gráfica?", "How should I read this chart?")),
                        html.H4(text("¿Qué muestra?", "What does it show?")),
                        html.P(chart.what_shows),
                        html.H4(text("¿Cómo se interpreta?", "How is it interpreted?")),
                        html.P(chart.how_to_read),
                        html.H4(text("¿Qué podemos observar?", "What can we observe?")),
                        html.P(chart.observation),
                    ],
                    className="reports-chart-help",
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
                    content.profile_label,
                    className="reports-preview-profile",
                ),
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
    if "context" in enabled:
        components.append(
            _preview_section(
                "Contexto" if language == "es" else "Context",
                [
                    (
                        f"El informe analiza «{content.indicator}» para {content.configuration.year or 'el periodo disponible'}."
                        if language == "es"
                        else f"The report analyses “{content.indicator}” for {content.configuration.year or 'the available period'}."
                    )
                ],
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
    if "education" in enabled and content.educational_content:
        components.append(
            _preview_section(
                "Propuesta didáctica" if language == "es" else "Learning activity",
                content.educational_content,
            )
        )
    if "data_quality" in enabled and content.data_quality:
        components.append(
            _preview_section(
                "Disponibilidad y calidad de los datos"
                if language == "es"
                else "Data availability and quality",
                content.data_quality,
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
        components.append(_preview_recommendations(content))
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


def _preview_recommendations(content) -> Component:
    language = content.configuration.language
    derived = [item.text for item in content.recommendations if item.derived_from_metrics]
    general = [item.text for item in content.recommendations if not item.derived_from_metrics]
    return html.Div(
        [
            html.H3("Posibles líneas de actuación" if language == "es" else "Possible courses of action"),
            html.H4("Relacionadas con los resultados" if language == "es" else "Related to the results")
            if derived
            else None,
            html.Ul([html.Li(item) for item in derived]),
            html.H4("Orientaciones generales" if language == "es" else "General guidance"),
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


def _current_user_id() -> str:
    get_id = getattr(current_user, "get_id", None)
    return str(get_id() or "") if callable(get_id) else ""


def _year_options(source: str) -> list[dict[str, Any]]:
    values = get_fra_years() if source in {"fra", "combined"} else get_ilga_years()
    if source in {"fra", "combined"}:
        labels = {2023: "Encuesta III · 2023", 2019: "Encuesta II · 2019", 2012: "Encuesta I · 2012"}
        return [{"label": labels.get(year, str(year)), "value": year} for year in values]
    return [{"label": str(year), "value": year} for year in values]


def _category_options(source: str, year: int | None) -> list[dict[str, Any]]:
    if source in {"fra", "combined"}:
        values = get_fra_categories()
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
    control_id = getattr(component, "id", None)
    is_group = component.__class__.__name__ in {
        "Checklist",
        "DatePickerRange",
        "DatePickerSingle",
        "RadioItems",
        "RangeSlider",
        "Slider",
    }
    if is_group and control_id:
        label_id = f"{control_id}-label"
        label_node = html.Span(
            label_es,
            id=label_id,
            className="reports-field-label",
            **text_attrs(label_es, label_en),
        )
        props.update({"role": "group", "aria-labelledby": label_id})
    else:
        label_node = html.Label(
            label_es,
            htmlFor=control_id,
            **text_attrs(label_es, label_en),
        )
    return html.Div(
        [label_node, component],
        **dash_attrs(props),
    )


def _t(language: str | None, es: str, en: str) -> str:
    return en if language == "en" else es
