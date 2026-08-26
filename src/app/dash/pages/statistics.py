from __future__ import annotations

import hashlib
import json
import logging
import math
import time
from typing import Any
from urllib.parse import urlencode

import dash_ag_grid as dag
import pandas as pd
from dash import ALL, Dash, Input, Output, State, ctx, dcc, html, no_update
from dash.development.base_component import Component
from dash.exceptions import PreventUpdate
from flask_login import current_user

from app.analytics.combined_analysis import (
    get_combined_analysis_capabilities,
    quadrant_eligibility,
    ranking_position_rows,
)
from app.analytics.percentage_display import format_percentage
from app.analytics.repository import (
    assert_analytics_databases_available as assert_analytics_databases_available,
)
from app.analytics.repository import get_fra_categories, get_fra_mongo_indicators_by_category
from app.analytics.statistics.ranking import paginate_ranking
from app.analytics.statistics_charts import (
    build_combined_quadrant_chart,
    build_comparative_ranking_chart,
    build_eu_average_comparison_chart,
    build_europe_choropleth,
    build_fra_response_comparison_chart,
    build_ranking_position_gap_chart,
    build_response_country_comparison_chart,
    build_temporal_evolution_chart,
    prepare_fra_response_comparison_data,
    summarize_response_comparison,
)
from app.analytics.statistics_exports import (
    EXPORT_FORMAT,
    EXPORT_HEIGHT,
    EXPORT_SCALE,
    EXPORT_WIDTH,
    chart_graph_config,
    export_summary_table,
    prepare_figure_for_export,
)
from app.analytics.statistics_models import (
    FRA_FILTER_GROUP_A,
    FRA_FILTER_GROUP_B,
    FraStatisticsQuery,
    StatisticsFilters,
    validate_statistics_filter_combination,
)
from app.analytics.statistics_normalizers import (
    normalize_country_code,
    normalize_filter_value,
    normalize_text_key,
)
from app.analytics.statistics_service import (
    get_combined_statistics_analysis,
    get_fra_control_payload,
    get_fra_statistics,
)
from app.cache import cache
from app.dash.components.dropdown_options import (
    build_dropdown_options,
    option_value_or_none,
)
from app.dash.components.empty_state import build_empty_state
from app.dash.components.loading import contextual_loading
from app.dash.components.page_structure import build_page_header
from app.dash.components.source_attribution import build_source_attribution
from app.dash.graph_config import fixed_europe_map_config
from app.dash.i18n import attribute_attrs, country_labels, dash_attrs, text, text_attrs, ui_text
from app.dash.layouts.navigation import build_navbar
from app.dash.routes import route_path
from app.dash.statistics_state import StatisticsViewState, resolve_statistics_view_state
from app.fra_surveys import FRA_SURVEYS, default_fra_survey, get_fra_survey
from app.taxonomy import taxonomy_pair

logger = logging.getLogger(__name__)
STATISTICS_DASHBOARD_CACHE_SECONDS = 300
STATISTICS_DASHBOARD_CACHE_VERSION = 1

FRA_SURVEY_OPTIONS = [
    {
        "label": html.Span(
            [
                html.Strong(
                    f"Encuesta {survey.year}",
                    **text_attrs(f"Encuesta {survey.year}", f"{survey.year} Survey"),
                ),
            ],
            className="stats-survey-option",
        ),
        "value": survey.survey_id,
    }
    for survey in FRA_SURVEYS
    if survey.enabled
]

EXCLUDED_CATEGORY_KEYS = {
    normalize_text_key("Political Participation"),
    normalize_text_key("Spanish LGBTI+ indicators"),
    normalize_text_key("Spanish LGBTIQ+ indicators"),
}

LABELS_EN = {
    "Encuesta": "Survey",
    "Datos Sociales": "Social Data",
    "Indicador": "Indicator",
    "Pregunta o indicador": "Question or indicator",
    "Respuesta": "Answer",
    "Segmentación sociodemográfica": "Sociodemographic segmentation",
    "Valores del filtro activo": "Active filter values",
}

CHART_EXPORT_TITLES = {
    "map": ("Mapa de Europa", "Map of Europe"),
    "temporal": ("Evolución temporal", "Temporal evolution"),
    "ranking": ("Ranking comparativo", "Comparative ranking"),
    "average": ("Comparación con la media europea", "Comparison with the European average"),
    "response_comparison": ("Comparación de respuestas", "Response comparison"),
    "responses": ("Detalles de respuestas", "Response details"),
    "quadrants": ("Cuadrantes FRA e ILGA-Europe", "FRA and ILGA-Europe quadrants"),
    "ranking_gap": (
        "Diferencia de posiciones entre rankings",
        "Difference in ranking positions",
    ),
}


def build_statistics_layout() -> Component:
    categories: list[dict[str, Any]] = []
    return html.Div(
        [
            build_navbar(active="statistics"),
            dcc.Store(id="stats-fra-control-store", storage_type="memory"),
            dcc.Store(id="stats-ranking-page", data=0, storage_type="memory"),
            dcc.Store(id="stats-selected-countries", data=[], storage_type="session"),
            dcc.Download(id="stats-summary-table-download"),
            dcc.Download(id="stats-combined-download"),
            html.Main(
                [
                    _header(),
                    _controls(categories),
                    html.Div(
                        contextual_loading(
                            [
                                dcc.Store(id="stats-data-store", storage_type="memory"),
                                dcc.Store(id="stats-dashboard-ready-store", storage_type="memory"),
                                dcc.Store(id="stats-active-query-store", storage_type="memory"),
                                dcc.Store(id="stats-survey-catalog-store", storage_type="memory"),
                                dcc.Store(id="stats-indicator-catalog-store", storage_type="memory"),
                                html.Div(
                                    id="stats-query-state",
                                    className="stats-query-state is-hidden",
                                ),
                                html.Div(
                                    [
                                        html.Div(
                                            id="stats-status-message",
                                            className="stats-status stats-status-warning",
                                        ),
                                        _block_header(
                                            "FRA",
                                            "Análisis de la encuesta FRA",
                                            "FRA survey analysis",
                                        ),
                                        html.P(
                                            text(
                                                "Estas visualizaciones representan las respuestas de la encuesta FRA seleccionada y permiten comparar las experiencias de las personas LGBTIQ+ entre países y segmentos de población.",
                                                "These visualisations represent responses to the selected FRA survey and compare LGBTIQ+ people's experiences across countries and population segments.",
                                            ),
                                            className="stats-block-description",
                                        ),
                                        _map_panel(),
                                        html.Section(
                                            id="stats-metric-row",
                                            className="stats-metric-row stats-executive-grid",
                                        ),
                                        html.Section(
                                            [
                                                html.Div(
                                                    _temporal_panel(),
                                                    id="stats-temporal-panel",
                                                    className=(
                                                        "stats-panel-wrapper stats-temporal-wrapper is-hidden"
                                                    ),
                                                ),
                                                _graph_panel(
                                                    "Ranking comparativo",
                                                    "Comparative ranking",
                                                    "stats-ranking-graph",
                                                    panel_id="stats-ranking-panel",
                                                    panel_class_name=(
                                                        "stats-panel stats-panel-wide stats-ranking-panel"
                                                    ),
                                                    footer=_ranking_pagination_controls(),
                                                ),
                                                html.Div(
                                                    [
                                                        _chart_panel_heading(
                                                            "Comparación de respuestas",
                                                            "Response comparison",
                                                            "stats-response-comparison-graph",
                                                        ),
                                                        html.Div(
                                                            _deferred_graph_slot(
                                                                "stats-response-comparison-graph"
                                                            ),
                                                            className="stats-response-comparison-scroll",
                                                        ),
                                                        _chart_help("response_comparison"),
                                                        _dynamic_source_attribution(
                                                            "response-comparison"
                                                        ),
                                                    ],
                                                    id="stats-response-comparison-panel",
                                                    className=(
                                                        "stats-panel stats-panel-wide "
                                                        "stats-response-comparison-section is-hidden"
                                                    ),
                                                ),
                                                html.Div(
                                                    [
                                                        _chart_panel_heading(
                                                            "Detalles de respuestas",
                                                            "Response details",
                                                            "stats-response-detail-graph",
                                                        ),
                                                        html.Div(
                                                            id="stats-detail-summary",
                                                            className="stats-detail-summary",
                                                        ),
                                                        html.Div(
                                                            _deferred_graph_slot(
                                                                "stats-response-detail-graph"
                                                            ),
                                                            className="stats-response-detail-scroll",
                                                        ),
                                                        _chart_help("response"),
                                                        _dynamic_source_attribution(
                                                            "response-detail"
                                                        ),
                                                    ],
                                                    id="stats-response-panel",
                                                    className="stats-panel stats-panel-wide stats-response-panel",
                                                ),
                                                _graph_panel(
                                                    "Comparación con la media europea",
                                                    "Comparison with the European average",
                                                    "stats-average-graph",
                                                    panel_id="stats-average-panel",
                                                    panel_class_name=(
                                                        "stats-panel stats-panel-wide "
                                                        "stats-average-panel is-hidden"
                                                    ),
                                                ),
                                            ],
                                            className="stats-grid",
                                        ),
                                        html.Div(
                                            [
                                                html.Div(
                                                    [
                                                        html.H2(
                                                            text("Tabla FRA resumida", "FRA summary table")
                                                        ),
                                                        html.Div(
                                                            [
                                                                html.Button(
                                                                    text(
                                                                        ui_text(
                                                                            "download_table", "es"
                                                                        ),
                                                                        ui_text(
                                                                            "download_table", "en"
                                                                        ),
                                                                    ),
                                                                    id="stats-table-download-button",
                                                                    type="button",
                                                                    n_clicks=0,
                                                                    disabled=True,
                                                                    className=(
                                                                        "stats-chart-export-button "
                                                                        "stats-table-export-button"
                                                                    ),
                                                                    title=ui_text(
                                                                        "download_csv", "es"
                                                                    ),
                                                                    **attribute_attrs(
                                                                        "title",
                                                                        ui_text(
                                                                            "download_csv", "es"
                                                                        ),
                                                                        ui_text(
                                                                            "download_csv", "en"
                                                                        ),
                                                                    ),
                                                                ),
                                                                html.Span(
                                                                    text(
                                                                        ui_text(
                                                                            "no_export_data", "es"
                                                                        ),
                                                                        ui_text(
                                                                            "no_export_data", "en"
                                                                        ),
                                                                    ),
                                                                    id="stats-table-export-status",
                                                                    className="stats-table-export-status",
                                                                    role="status",
                                                                ),
                                                            ],
                                                            className=(
                                                                "stats-panel-actions stats-table-export-actions"
                                                            ),
                                                        ),
                                                    ],
                                                    className="stats-panel-heading stats-table-heading",
                                                ),
                                                html.Div(
                                                    dag.AgGrid(
                                                        id="stats-results-table",
                                                        columnDefs=[],
                                                        rowData=[],
                                                        defaultColDef={
                                                            "sortable": True,
                                                            "filter": True,
                                                            "resizable": True,
                                                            "minWidth": 120,
                                                        },
                                                        dashGridOptions={
                                                            "pagination": True,
                                                            "paginationPageSize": 12,
                                                            "paginationPageSizeSelector": False,
                                                            "domLayout": "autoHeight",
                                                            "getRowStyle": {
                                                                "styleConditions": [
                                                                    {
                                                                        "condition": "params.data.status === 'Sin datos' || params.data.status === 'No data'",
                                                                        "style": {
                                                                            "color": "#6b7280",
                                                                            "fontStyle": "italic",
                                                                        },
                                                                    }
                                                                ]
                                                            },
                                                        },
                                                        className="ag-theme-quartz stats-results-grid",
                                                        style={"width": "100%"},
                                                    ),
                                                    id="stats-results-table-wrapper",
                                                    className="stats-results-table-scroll",
                                                    role="region",
                                                    tabIndex=0,
                                                    **dash_attrs(
                                                        {
                                                            "aria-label": "Tabla resumida / Summary table"
                                                        }
                                                    ),
                                                ),
                                                _dynamic_source_attribution("summary-table"),
                                            ],
                                            className="stats-panel stats-results-table-panel",
                                        ),
                                        _combined_analysis_panel(),
                                    ],
                                    id="stats-results-content",
                                    className="stats-results-content is-hidden",
                                ),
                            ],
                            "loading_statistics",
                            element_id="stats-dashboard-loading",
                            target_components={
                                "stats-data-store": "data",
                                "stats-dashboard-ready-store": "data",
                                "stats-active-query-store": "data",
                                "stats-survey-catalog-store": "data",
                                "stats-indicator-catalog-store": "data",
                            },
                            hide_content_while_loading=True,
                            show_message=False,
                        ),
                        id="stats-dashboard-region",
                        className="stats-dashboard-region",
                        role="region",
                        **dash_attrs({"aria-live": "polite"}),
                    ),
                ],
                className="stats-shell app-page app-page-container",
            ),
        ]
    )


def register_statistics_callbacks(app: Dash) -> None:
    app.clientside_callback(
        """
        function(surveyId, category, indicator, answer,
                 demographicType, demographicValue, identityType, identityValue,
                 catalog, indicatorCatalog) {
            const catalogReady = Boolean(
                catalog && catalog.survey_id === surveyId && catalog.loaded
            );
            const year = catalogReady ? catalog.year : null;
            const hasCategory = Boolean(category);
            const hasIndicator = Boolean(indicator);
            const indicatorCatalogReady = Boolean(
                indicatorCatalog && indicatorCatalog.survey_id === surveyId &&
                indicatorCatalog.category === category && indicatorCatalog.loaded
            );
            let phase = "loading_indicators";
            if (catalogReady && !catalog.has_data) {
                phase = "survey_empty";
            } else if (catalogReady && !hasCategory) {
                phase = "initial";
            } else if (catalogReady && indicatorCatalogReady && !indicatorCatalog.has_data) {
                phase = "survey_empty";
            } else if (catalogReady && indicatorCatalogReady && !hasIndicator) {
                phase = "awaiting_indicator";
            } else if (catalogReady && hasIndicator) {
                phase = "loading_statistics";
            }
            return {
                query_token: JSON.stringify([
                    surveyId, year, category, indicator, answer,
                    demographicType, demographicValue, identityType, identityValue
                ]),
                phase: phase
            };
        }
        """,
        Output("stats-active-query-store", "data"),
        Input("stats-survey-select", "value"),
        Input("stats-category-select", "value"),
        Input("fra-indicator-select", "value"),
        Input("fra-answer-select", "value"),
        Input("fra-demographic-type", "value"),
        Input("fra-demographic-value", "value"),
        Input("fra-identity-type", "value"),
        Input("fra-identity-value", "value"),
        Input("stats-survey-catalog-store", "data"),
        Input("stats-indicator-catalog-store", "data"),
    )

    @app.callback(
        Output("stats-query-state", "children"),
        Output("stats-query-state", "className"),
        Output("stats-results-content", "className"),
        Input("stats-data-store", "data"),
        Input("stats-dashboard-ready-store", "data"),
        Input("stats-active-query-store", "data"),
        Input("stats-category-select", "value"),
        Input("fra-indicator-select", "value"),
        Input("app-language-store", "data"),
    )
    def update_statistics_query_state(
        result: dict[str, Any] | None,
        ready_payload: dict[str, Any] | None,
        active_payload: dict[str, Any] | None,
        category: str | None,
        indicator: str | None,
        language: str | None,
    ) -> tuple[Component | None, str, str]:
        clean_language = "en" if language == "en" else "es"
        query_state = resolve_statistics_view_state(
            result,
            ready_payload,
            active_payload,
            category=category,
            indicator=indicator,
        )
        if query_state is StatisticsViewState.READY:
            return (
                None,
                "stats-query-state is-hidden",
                "stats-results-content",
            )
        if query_state in {
            StatisticsViewState.INITIAL,
            StatisticsViewState.LOADING_INDICATORS,
            StatisticsViewState.AWAITING_INDICATOR,
            StatisticsViewState.LOADING_STATISTICS,
        }:
            return (
                None,
                "stats-query-state is-hidden",
                "stats-results-content is-hidden",
            )
        if query_state is StatisticsViewState.ERROR:
            message_key = "statistics_error"
        elif query_state is StatisticsViewState.SURVEY_EMPTY:
            message_key = "statistics_survey_empty"
        elif query_state is StatisticsViewState.NO_DATA:
            message_key = "statistics_no_data"
        else:
            return (
                None,
                "stats-query-state is-hidden",
                "stats-results-content is-hidden",
            )
        return (
            build_empty_state(
                ui_text(message_key, clean_language),
                class_name="stats-query-state-card",
            ),
            "stats-query-state",
            "stats-results-content is-hidden",
        )

    @app.callback(
        Output({"type": "stats-source-attribution", "index": ALL}, "children"),
        Input("stats-survey-select", "value"),
        Input("app-language-store", "data"),
        State({"type": "stats-source-attribution", "index": ALL}, "id"),
    )
    def update_statistics_attributions(
        survey_id: str | None,
        language: str | None,
        targets: list[dict[str, str]] | None,
    ) -> list[Component]:
        survey = get_fra_survey(survey_id) or default_fra_survey()
        return [
            build_source_attribution(
                "fra",
                year=survey.year,
                compact=True,
                language=language,
            )
            for _target in targets or []
        ]

    @app.callback(
        Output(
            {"type": "stats-combined-source-attribution", "index": ALL},
            "children",
        ),
        Input("stats-data-store", "data"),
        Input("app-language-store", "data"),
        State(
            {"type": "stats-combined-source-attribution", "index": ALL},
            "id",
        ),
    )
    def update_combined_statistics_attributions(
        result: dict[str, Any] | None,
        language: str | None,
        targets: list[dict[str, str]] | None,
    ) -> list[Component]:
        payload = (result or {}).get("combined_analysis") or {}
        fra_year = _safe_int(payload.get("fra_year"))
        ilga_year = _safe_int(payload.get("ilga_year"))
        attribution = html.Div(
            [
                build_source_attribution(
                    "fra",
                    year=fra_year,
                    compact=True,
                    language=language,
                ),
                build_source_attribution(
                    "ilga",
                    year=ilga_year,
                    compact=True,
                    language=language,
                ),
            ],
            className="stats-source-attribution-combined",
        )
        return [attribution for _target in targets or []]

    @app.callback(
        Output("stats-ranking-page", "data"),
        Output("stats-ranking-previous", "disabled"),
        Output("stats-ranking-next", "disabled"),
        Output("stats-ranking-page-label", "children"),
        Input("stats-data-store", "data"),
        Input("stats-selected-countries", "data"),
        Input("stats-ranking-previous", "n_clicks"),
        Input("stats-ranking-next", "n_clicks"),
        Input("app-language-store", "data"),
        State("stats-ranking-page", "data"),
    )
    def update_ranking_page(
        result: dict[str, Any] | None,
        selected_countries: list[str] | None,
        _previous_clicks: int | None,
        _next_clicks: int | None,
        language: str | None,
        current_page: int | None,
    ) -> tuple[int, bool, bool, str]:
        requested_page = (
            0
            if ctx.triggered_id
            in {
                None,
                "stats-data-store",
                "stats-selected-countries",
            }
            else int(current_page or 0)
        )
        if ctx.triggered_id == "stats-ranking-previous":
            requested_page -= 1
        elif ctx.triggered_id == "stats-ranking-next":
            requested_page += 1
        ranking_page = paginate_ranking(
            list((result or {}).get("ranking") or []),
            requested_page,
            selected_countries=_normalize_selected_countries(selected_countries),
        )
        if ranking_page.total_items:
            label = (
                f"Countries {ranking_page.start}\u2013{ranking_page.end} of {ranking_page.total_items}"
                if language == "en"
                else f"Pa\u00edses {ranking_page.start}\u2013{ranking_page.end} de {ranking_page.total_items}"
            )
        else:
            label = "No countries" if language == "en" else "Sin pa\u00edses"
        return (
            ranking_page.page,
            not ranking_page.has_previous,
            not ranking_page.has_next,
            label,
        )

    @app.callback(
        Output("stats-summary-table-download", "data"),
        Input("stats-table-download-button", "n_clicks"),
        State("stats-results-table", "virtualRowData"),
        State("stats-results-table", "rowData"),
        State("stats-results-table", "columnDefs"),
        State("stats-data-store", "data"),
        State("stats-selected-countries", "data"),
        State("app-language-store", "data"),
        prevent_initial_call=True,
    )
    def download_summary_table(
        _clicks: int | None,
        visible_rows: list[dict[str, Any]] | None,
        table_rows: list[dict[str, Any]] | None,
        columns: list[dict[str, Any]] | None,
        result: dict[str, Any] | None,
        selected_countries: list[str] | None,
        language: str | None,
    ):
        rows = visible_rows if visible_rows is not None else table_rows
        if not rows or not columns:
            raise PreventUpdate
        clean_result = result or {}
        clean_language = language or "es"
        scope = _selection_scope(
            list(clean_result.get("ranking") or []),
            _normalize_selected_countries(selected_countries),
            clean_language,
        )
        table_export = export_summary_table(
            rows,
            columns,
            language=clean_language,
            metadata={
                "indicator": _table_indicator_label(clean_result),
                "year": clean_result.get("year"),
                "countries": scope["names"],
                "source": clean_result.get("source"),
            },
        )
        return dcc.send_string(
            table_export.content,
            table_export.filename,
            type=table_export.mime_type,
        )

    @app.callback(
        Output("stats-combined-download", "data"),
        Input(
            {"type": "stats-combined-download-button", "index": ALL},
            "n_clicks",
        ),
        State("stats-data-store", "data"),
        State("app-language-store", "data"),
        prevent_initial_call=True,
    )
    def download_combined_table(
        clicks: list[int | None] | None,
        result: dict[str, Any] | None,
        language: str | None,
    ):
        if not clicks or not any(clicks):
            raise PreventUpdate
        analysis = dict((result or {}).get("combined_analysis") or {})
        rows = list(analysis.get("rows") or [])
        if not rows:
            raise PreventUpdate
        language = language or "es"
        gap_by_iso = {
            str(row.get("iso") or ""): row
            for row in (analysis.get("ranking_gap") or {}).get("rows") or []
        }
        export_rows = [
            {
                "country": row.get("country"),
                "country_code": row.get("iso"),
                "fra_value": row.get("fra_value"),
                "ilga_score": row.get("ilga_value"),
                "legal_rank": gap_by_iso.get(str(row.get("iso") or ""), {}).get("ilga_rank"),
                "social_rank": gap_by_iso.get(str(row.get("iso") or ""), {}).get("fra_rank"),
                "ranking_position_difference": gap_by_iso.get(
                    str(row.get("iso") or ""), {}
                ).get("absolute_rank_difference"),
            }
            for row in rows
        ]
        labels = {
            "country": ("País", "Country"),
            "country_code": ("Código del país", "Country code"),
            "fra_value": ("Valor FRA (%)", "FRA value (%)"),
            "ilga_score": ("Puntuación ILGA-Europe", "ILGA-Europe score"),
            "legal_rank": ("Posición legal", "Legal position"),
            "social_rank": ("Posición social", "Social position"),
            "ranking_position_difference": (
                "Diferencia de posiciones",
                "Difference in positions",
            ),
        }
        columns = [
            {
                "field": key,
                "headerName": pair[1 if language == "en" else 0],
            }
            for key, pair in labels.items()
        ]
        table_export = export_summary_table(
            export_rows,
            columns,
            language=language,
            metadata={
                "indicator": f"{analysis.get('indicator') or ''} · {analysis.get('answer') or ''}",
                "year": f"FRA {analysis.get('fra_year')} / ILGA {analysis.get('ilga_year')}",
                "countries": [],
                "source": "FRA + ILGA-Europe",
            },
        )
        return dcc.send_string(
            table_export.content,
            table_export.filename.replace("estadisticas", "fra-ilga"),
            type=table_export.mime_type,
        )

    @app.callback(
        Output("stats-category-select", "placeholder"),
        Output("fra-indicator-select", "placeholder"),
        Input("app-language-store", "data"),
        Input("stats-category-select", "value"),
    )
    def translate_statistics_controls(
        language: str | None,
        category: str | None,
    ) -> tuple[str, str]:
        if language == "en":
            return (
                "Select a category",
                "Select an indicator" if category else "Select a category first",
            )
        return (
            "Selecciona una categoría",
            "Selecciona un indicador" if category else "Selecciona primero una categoría",
        )

    @app.callback(
        Output("stats-create-report-link", "href"),
        Input("stats-survey-select", "value"),
        Input("stats-category-select", "value"),
        Input("fra-indicator-select", "value"),
        Input("fra-answer-select", "value"),
        Input("fra-demographic-type", "value"),
        Input("fra-demographic-value", "value"),
        Input("fra-identity-type", "value"),
        Input("fra-identity-value", "value"),
        Input("stats-selected-countries", "data"),
        Input("app-language-store", "data"),
    )
    def update_create_report_link(
        survey_id: str | None,
        category: str | None,
        indicator: str | None,
        answer: str | None,
        filter_a_name: str | None,
        filter_a_value: str | None,
        filter_b_name: str | None,
        filter_b_value: str | None,
        countries: list[str] | None,
        language: str | None,
    ) -> str:
        survey = get_fra_survey(survey_id) or default_fra_survey()
        selected_countries = _normalize_selected_countries(countries)
        filters = _resolved_ui_filters(
            filter_a_name,
            filter_a_value,
            filter_b_name,
            filter_b_value,
        )
        params = {
            "source": "fra",
            "year": survey.year,
            "category": category,
            "indicator_id": indicator,
            "answer": answer,
            **filters.as_query_fields(),
            "countries": ",".join(selected_countries),
            "primary_country": selected_countries[0] if selected_countries else None,
            "language": "en" if language == "en" else "es",
            "mode": "automatic",
            "charts": "ranking,average,countries,responses,temporal",
        }
        clean = {
            key: value for key, value in params.items() if value is not None and str(value).strip()
        }
        path = route_path("reports", language)
        report_href = f"{path}?{urlencode(clean)}"
        return _report_destination(
            report_href,
            authenticated=bool(getattr(current_user, "is_authenticated", False)),
        )

    @app.callback(
        Output("stats-category-select", "options"),
        Output("stats-category-select", "value"),
        Output("stats-survey-catalog-store", "data"),
        Input("stats-survey-select", "value"),
        Input("app-language-store", "data"),
        State("stats-category-select", "value"),
    )
    def update_categories_for_survey(
        survey_id: str | None,
        language: str | None,
        current: str | None,
    ):
        survey = get_fra_survey(survey_id)
        if survey is None or not survey.enabled:
            return [], None, {"survey_id": survey_id, "loaded": True, "has_data": False}
        options = _category_options(survey.year, language or "es")
        selected = (
            _selected_category_value(options, current)
            if ctx.triggered_id == "app-language-store"
            else None
        )
        return options, selected, {
            "survey_id": survey.survey_id,
            "year": survey.year,
            "loaded": True,
            "has_data": bool(options),
        }

    @app.callback(
        Output("fra-indicator-select", "options"),
        Output("fra-indicator-select", "value"),
        Output("fra-indicator-select", "disabled"),
        Output("stats-data-store", "data", allow_duplicate=True),
        Output("stats-indicator-catalog-store", "data"),
        Input("stats-survey-select", "value"),
        Input("stats-category-select", "value"),
        prevent_initial_call=True,
    )
    def update_fra_indicators(survey_id: str | None, category: str | None):
        survey = get_fra_survey(survey_id)
        if survey is None or not category:
            return [], None, True, None, {
                "survey_id": survey_id,
                "category": category,
                "loaded": bool(survey is not None and not category),
                "has_data": False,
            }
        options = build_dropdown_options(
            (
                {"label": _fra_indicator_option_label(indicator), "value": indicator.code}
                for indicator in get_fra_mongo_indicators_by_category(category, survey.year)
            ),
            context="statistics-fra-indicator",
        )
        return options, None, not bool(options), None, {
            "survey_id": survey.survey_id,
            "category": category,
            "loaded": True,
            "has_data": bool(options),
        }

    @app.callback(
        Output("fra-answer-select", "options"),
        Output("fra-answer-select", "value"),
        Output("fra-demographic-type", "options"),
        Output("fra-demographic-type", "value"),
        Output("stats-fra-control-store", "data"),
        Output("stats-fra-response-help", "children"),
        Output("stats-fra-response-help", "className"),
        Output("stats-fra-segmentation-card", "className"),
        Output("fra-answer-select", "disabled"),
        Output("stats-demographic-segmentation", "className"),
        Input("fra-indicator-select", "value"),
        Input("app-language-store", "data"),
        State("stats-category-select", "value"),
        State("stats-survey-select", "value"),
    )
    def update_fra_controls(
        code: str | None,
        language: str | None,
        category: str | None,
        survey_id: str | None,
    ):
        if not code:
            return (
                [],
                None,
                _segmentation_catalog_options(FRA_FILTER_GROUP_A, []),
                None,
                {},
                None,
                "stats-response-help is-hidden",
                f"{_fra_segmentation_card_class()} is-disabled",
                True,
                "stats-segmentation-row stats-demographic-segmentation is-disabled",
            )
        survey = get_fra_survey(survey_id)
        if survey is None:
            raise PreventUpdate
        payload = get_fra_control_payload(code, category, survey.year)
        # FRA indicators and answers stay in their canonical English wording
        # in both interfaces. Only category labels are localized.
        answers = build_dropdown_options(
            payload.get("answers") or [],
            context="statistics-fra-response",
        )
        segmentations = _translated_segmentation_options(
            payload.get("segmentations") or [], language or "es"
        )
        demographic_options = _segmentation_catalog_options(
            FRA_FILTER_GROUP_A, segmentations, language or "es"
        )
        has_demographic_segmentation = _has_real_segmentation_option(demographic_options)
        if not has_demographic_segmentation:
            demographic_options = _disable_all_options(demographic_options)
        has_real_segmentation = any(
            str(option.get("value") or "") != "All"
            for option in segmentations
            if isinstance(option, dict) and not option.get("disabled", False)
        )
        return (
            answers,
            payload.get("default_answer")
            or (answers[0]["value"] if len(answers) == 1 else None),
            demographic_options,
            _all_option_value(demographic_options),
            payload,
            _fra_response_help(payload.get("response_type"), language or "es"),
            (
                "stats-response-help"
                if payload.get("response_type") == "ranked_reason"
                else "stats-response-help is-hidden"
            ),
            (
                _fra_segmentation_card_class()
                if has_real_segmentation
                else f"{_fra_segmentation_card_class()} is-disabled"
            ),
            not bool(answers),
            (
                "stats-segmentation-row stats-demographic-segmentation"
                if has_demographic_segmentation
                else "stats-segmentation-row stats-demographic-segmentation is-disabled"
            ),
        )

    @app.callback(
        Output("fra-demographic-value", "options"),
        Output("fra-demographic-value", "value"),
        Input("fra-demographic-type", "value"),
        Input("stats-fra-control-store", "data"),
        State("fra-demographic-value", "value"),
    )
    def update_demographic_values(
        segmentation: str | None,
        payload: dict[str, Any] | None,
        current: str | None,
    ):
        values = (payload or {}).get("values") or {}
        options = build_dropdown_options(
            values.get(segmentation or "All") or [],
            context="statistics-fra-demographic-value",
        )
        if not _is_active_filter_type(segmentation):
            return _disable_all_options(options), _all_option_value(options)
        return options, _explicit_filter_value(segmentation, options, current)

    @app.callback(
        Output("fra-identity-type", "options"),
        Output("fra-identity-type", "value"),
        Output("stats-identity-segmentation", "className"),
        Input("fra-demographic-type", "value"),
        Input("stats-fra-control-store", "data"),
        Input("app-language-store", "data"),
        State("fra-identity-type", "value"),
    )
    def update_identity_filter_state(
        demographic_type: str | None,
        payload: dict[str, Any] | None,
        language: str | None,
        current_identity_type: str | None,
    ):
        segmentations = _translated_segmentation_options(
            (payload or {}).get("segmentations") or [], language or "es"
        )
        options = _segmentation_catalog_options(FRA_FILTER_GROUP_B, segmentations, language or "es")
        has_identity_segmentation = _has_real_segmentation_option(options)
        demographic_is_all = normalize_text_key(demographic_type) == "all"
        disabled = not demographic_is_all or not has_identity_segmentation
        if disabled:
            options = _disable_all_options(options)
            value = _all_option_value(options)
        else:
            value = option_value_or_none(options, current_identity_type) or _default_option_value(
                options
            )
        class_name = "stats-segmentation-row stats-identity-segmentation"
        if disabled:
            class_name += " is-disabled"
        return options, value, class_name

    @app.callback(
        Output("fra-identity-value", "options"),
        Output("fra-identity-value", "value"),
        Input("fra-identity-type", "value"),
        Input("stats-fra-control-store", "data"),
        Input("fra-demographic-type", "value"),
        State("fra-identity-value", "value"),
    )
    def update_identity_values(
        segmentation: str | None,
        payload: dict[str, Any] | None,
        demographic_type: str | None,
        current: str | None,
    ):
        values = (payload or {}).get("values") or {}
        if _is_active_filter_type(demographic_type):
            options = build_dropdown_options(
                values.get("All") or [],
                context="statistics-fra-identity-value",
            )
            return _disable_all_options(options), _all_option_value(options)
        if normalize_text_key(demographic_type) != "all":
            return [], None
        options = build_dropdown_options(
            values.get(segmentation or "All") or [],
            context="statistics-fra-identity-value",
        )
        if not _is_active_filter_type(segmentation):
            return _disable_all_options(options), _all_option_value(options)
        return options, _explicit_filter_value(segmentation, options, current)

    @app.callback(
        Output("stats-data-store", "data"),
        Input("stats-survey-select", "value"),
        Input("stats-category-select", "value"),
        Input("fra-indicator-select", "value"),
        Input("fra-answer-select", "value"),
        Input("fra-demographic-type", "value"),
        Input("fra-demographic-value", "value"),
        Input("fra-identity-type", "value"),
        Input("fra-identity-value", "value"),
        Input("stats-fra-control-store", "data"),
        prevent_initial_call=True,
    )
    def load_statistics_data(
        survey_id: str | None,
        category: str | None,
        fra_code: str | None,
        answer: str | None,
        demographic_type: str | None,
        demographic_value: str | None,
        identity_type: str | None,
        identity_value: str | None,
        control_payload: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        survey = get_fra_survey(survey_id)
        if survey is None or not survey.enabled:
            return None
        query_started_at = time.perf_counter()
        query_token = _statistics_query_token(
            survey.survey_id,
            survey.year,
            category,
            fra_code,
            answer,
            demographic_type,
            demographic_value,
            identity_type,
            identity_value,
        )
        if not _has_valid_fra_selection(category, fra_code):
            return None
        controls_ready = _fra_controls_are_ready(
            category,
            fra_code,
            control_payload,
            answer,
            demographic_type,
            demographic_value,
            identity_type,
            identity_value,
        )
        if ctx.triggered_id == "stats-category-select" or not controls_ready:
            return _result_with_query_token(
                {"status": StatisticsViewState.LOADING_STATISTICS.value},
                query_token,
            )
        filters = _resolved_ui_filters(
            demographic_type,
            demographic_value,
            identity_type,
            identity_value,
        )
        filter_validation = validate_statistics_filter_combination(
            filters,
            available_values=_payload_filter_values(control_payload),
        )
        if not filter_validation.ok:
            logger.warning(
                "statistics_query_rejected indicator=%s reason=%s",
                fra_code,
                filter_validation.message,
            )
            return _result_with_query_token(
                _empty_data_result(filter_validation.message), query_token
            )
        query_started = time.perf_counter()
        try:
            fra_query = FraStatisticsQuery(
                year=survey.year,
                category=category,
                question_code=fra_code,
                answer=answer,
                filter_a_name=filters.demographic_type,
                filter_a_value=filters.demographic_value,
                filter_b_name=filters.identity_type,
                filter_b_value=filters.identity_value,
            )
            logger.info(
                "indicator_query_started source=fra indicator=%s year=%s",
                fra_code,
                survey.year,
            )
            result = get_fra_statistics(fra_query)
            query_ms = (time.perf_counter() - query_started) * 1000
            logger.info(
                "indicator_query_completed source=fra indicator=%s status=%s query_ms=%.2f",
                fra_code,
                result.get("status"),
                query_ms,
            )
            enrichment_started = time.perf_counter()
            if result.get("status") == "ok":
                combined_analysis = get_combined_statistics_analysis(
                    fra_query,
                    fra_result=result,
                )
                result["combined_analysis"] = combined_analysis
            logger.info(
                "statistics_dataset_built source=fra indicator=%s countries=%d rows=%d",
                fra_code,
                len(result.get("ranking") or []),
                len(result.get("detail_data") or []),
            )
            enrichment_ms = (time.perf_counter() - enrichment_started) * 1000
        except Exception:
            logger.exception("statistics_query_failed source=fra indicator=%s", fra_code)
            return _result_with_query_token(_error_data_result(), query_token)
        logger.info(
            "statistics_query_completed source=fra status=%s query_ms=%.2f "
            "enrichment_ms=%.2f total_ms=%.2f",
            result.get("status"),
            query_ms,
            enrichment_ms,
            (time.perf_counter() - query_started_at) * 1000,
        )
        return _browser_statistics_payload(_result_with_query_token(result, query_token))

    @app.callback(
        Output("stats-selected-countries", "data"),
        Input("stats-map-graph", "clickData"),
        Input("stats-clear-countries", "n_clicks"),
        Input("stats-data-store", "data"),
        Input("stats-survey-select", "value"),
        State("stats-selected-countries", "data"),
        prevent_initial_call=True,
    )
    def update_country_selection(
        click_data: dict[str, Any] | None,
        _clear_clicks: int | None,
        data: dict[str, Any] | None,
        _survey_id: str | None,
        current: list[str] | None,
    ) -> list[str] | Any:
        return _next_country_selection(
            ctx.triggered_id,
            click_data=click_data,
            data=data,
            current=current,
        )

    @app.callback(
        Output("stats-temporal-country-select", "options"),
        Output("stats-temporal-country-select", "value"),
        Input("stats-data-store", "data"),
        Input("stats-temporal-select-all", "n_clicks"),
        Input("stats-temporal-deselect-all", "n_clicks"),
        Input("app-language-store", "data"),
        State("stats-temporal-country-select", "value"),
    )
    def update_temporal_country_selection(
        result: dict[str, Any] | None,
        _select_all_clicks: int | None,
        _deselect_all_clicks: int | None,
        language: str | None,
        current: list[str] | None,
    ) -> tuple[list[dict[str, str]], list[str]]:
        options = _temporal_country_options(result or {}, language or "es")
        available = [option["value"] for option in options]
        if ctx.triggered_id == "stats-temporal-deselect-all":
            return options, []
        if ctx.triggered_id in {"stats-temporal-select-all", "stats-data-store", None}:
            return options, available
        selected = [
            country
            for country in _normalize_selected_countries(current)
            if country in set(available)
        ]
        return options, selected

    @app.callback(
        Output("stats-status-message", "children"),
        Output("stats-status-message", "className"),
        Output("stats-map-graph", "figure"),
        Output("stats-map-graph", "style"),
        Output("stats-map-ranking", "children"),
        Output("stats-clear-countries", "disabled"),
        Output("stats-metric-row", "children"),
        Output("stats-temporal-graph-slot", "children"),
        Output("stats-temporal-panel", "className"),
        Output("stats-ranking-graph-slot", "children"),
        Output("stats-average-graph-slot", "children"),
        Output("stats-average-panel", "className"),
        Output("stats-response-comparison-graph-slot", "children"),
        Output("stats-response-comparison-panel", "className"),
        Output("stats-detail-summary", "children"),
        Output("stats-response-detail-graph-slot", "children"),
        Output("stats-response-panel", "className"),
        Output("stats-combined-metric-row", "children"),
        Output("stats-quadrant-graph-slot", "children"),
        Output("stats-quadrant-panel", "className"),
        Output("stats-ranking-gap-graph-slot", "children"),
        Output("stats-ranking-gap-panel", "className"),
        Output("stats-combined-compatibility-messages", "children"),
        Output("stats-combined-intro", "children"),
        Output("stats-combined-block", "className"),
        Output("stats-combined-download-action", "children"),
        Output("stats-results-table", "columnDefs"),
        Output("stats-results-table", "rowData"),
        Output("stats-table-download-button", "disabled"),
        Output("stats-table-export-status", "children"),
        Output("stats-table-export-status", "className"),
        Output("stats-dashboard-ready-store", "data"),
        Input("stats-data-store", "data"),
        Input("stats-selected-countries", "data"),
        Input("stats-temporal-country-select", "value"),
        Input("app-language-store", "data"),
        Input("stats-ranking-page", "data"),
        State("stats-active-query-store", "data"),
        prevent_initial_call=True,
    )
    def render_statistics(
        result: dict[str, Any] | None,
        countries: list[str] | None,
        temporal_countries: list[str] | None,
        language: str | None,
        ranking_page: int | None,
        active_payload: dict[str, Any] | None,
    ):
        if not result or result.get("status") != "ok":
            raise PreventUpdate
        result_token = str(result.get("query_token") or "")
        active_token = str((active_payload or {}).get("query_token") or "")
        if result_token and active_token and result_token != active_token:
            raise PreventUpdate
        selected = _normalize_selected_countries(countries)
        language = language or "es"
        ready_payload = {
            "query_token": str(result.get("query_token") or ""),
            "status": StatisticsViewState.READY.value,
        }
        if ctx.triggered_id == "stats-temporal-country-select":
            return (
                *_dashboard_component_outputs(
                    _render_temporal_dashboard_update(
                        result,
                        selected,
                        language,
                        _normalize_selected_countries(temporal_countries),
                    )
                ),
                no_update,
            )
        if ctx.triggered_id == "stats-ranking-page":
            return (
                *_dashboard_component_outputs(
                    _render_ranking_dashboard_update(
                        result,
                        selected,
                        language,
                        ranking_page,
                    )
                ),
                no_update,
            )
        try:
            dashboard = _render_dashboard(
                result,
                selected,
                language,
                temporal_countries=_normalize_selected_countries(temporal_countries),
                ranking_page=ranking_page,
            )
            component_outputs = _dashboard_component_outputs(dashboard)
        except Exception:
            logger.exception(
                "statistics_figures_failed indicator=%s query_token=%s",
                result.get("indicator_code"),
                result_token,
            )
            failed_ready = {
                "query_token": result_token,
                "status": StatisticsViewState.ERROR.value,
            }
            return (*([no_update] * 31), failed_ready)
        ready_state = (
            no_update if ctx.triggered_id == "stats-selected-countries" else ready_payload
        )
        return (*component_outputs, ready_state)

def _controls(categories: list[dict[str, Any]]) -> Component:
    return html.Section(
        [
            _control_group(
                "Datos Sociales",
                [
                    html.Div(
                        dcc.RadioItems(
                            id="stats-survey-select",
                            options=FRA_SURVEY_OPTIONS,
                            value=default_fra_survey().survey_id,
                            className="stats-segmented-control stats-survey-control",
                            inputClassName="stats-segmented-input",
                            labelClassName="stats-segmented-label",
                        ),
                        className="stats-control-field stats-survey-field",
                        role="group",
                        **{
                            "aria-label": "Datos Sociales",
                            **attribute_attrs("aria-label", "Datos Sociales", "Social Data"),
                        },
                    ),
                    html.A(
                        text("Restablecer filtros", "Reset filters"),
                        href=route_path("statistics"),
                        className="stats-reset-link",
                        role="button",
                    ),
                ],
                class_name="stats-filter-card stats-filter-card-compact",
            ),
            _control_group(
                "Indicador",
                [
                    _field(
                        ("Categoría", "Category"),
                        dcc.Dropdown(
                            id="stats-category-select",
                            options=categories,
                            value=None,
                            clearable=False,
                            placeholder="Selecciona una categoría",
                        ),
                    ),
                    html.Div(
                        [
                            _field(
                                "Pregunta o indicador",
                                dcc.Dropdown(
                                    id="fra-indicator-select",
                                    options=[],
                                    value=None,
                                    clearable=False,
                                    disabled=True,
                                    placeholder="Selecciona primero una categoría",
                                ),
                            ),
                            _field(
                                "Respuesta",
                                dcc.Dropdown(
                                    id="fra-answer-select",
                                    options=[],
                                    value=None,
                                    clearable=False,
                                    disabled=True,
                                ),
                            ),
                            html.Aside(
                                id="stats-fra-response-help",
                                className="stats-response-help is-hidden",
                                **dash_attrs({"aria-live": "polite"}),
                            ),
                        ],
                        id="stats-fra-controls",
                        className="stats-fra-controls",
                    ),
                ],
                class_name="stats-filter-card stats-filter-card-wide stats-indicator-card",
            ),
            _control_group(
                "Segmentación sociodemográfica",
                [
                    html.Div(
                        [
                            _segmentation_group(
                                "Filtro demográfico",
                                "Demographic filter",
                                "Edad, educación, empleo, residencia, minorías y situación económica.",
                                "Age, education, employment, residence, minorities and economic situation.",
                                "fra-demographic-type",
                                "fra-demographic-value",
                                FRA_FILTER_GROUP_A,
                                element_id="stats-demographic-segmentation",
                            ),
                            _segmentation_group(
                                "Filtro de identidad",
                                "Identity filter",
                                "Disponible cuando no se aplica una segmentación demográfica.",
                                "Available when no demographic segmentation is applied.",
                                "fra-identity-type",
                                "fra-identity-value",
                                FRA_FILTER_GROUP_B,
                                element_id="stats-identity-segmentation",
                            ),
                        ],
                        className="stats-segmentation-groups",
                    ),
                ],
                element_id="stats-fra-segmentation-card",
                class_name=f"{_fra_segmentation_card_class()} is-disabled",
            ),
        ],
        className="stats-controls",
    )


def _field(
    label: str | tuple[str, str],
    component: Any,
    *,
    element_id: str | None = None,
    class_name: str = "stats-control-field",
) -> Component:
    label_es, label_en = label if isinstance(label, tuple) else (label, LABELS_EN.get(label, label))
    control_id = getattr(component, "id", None)
    is_native_form_control = component.__class__.__name__ in {"Input", "Textarea"}
    props: dict[str, Any] = {"className": class_name}
    if element_id:
        props["id"] = element_id
    if control_id and not is_native_form_control:
        label_id = f"{control_id}-label"
        label_node = html.Span(
            label_es,
            id=label_id,
            className="stats-control-label",
            **text_attrs(label_es, label_en),
        )
        props.update({"role": "group", "aria-labelledby": label_id})
    else:
        label_node = html.Label(
            label_es,
            htmlFor=control_id,
            **text_attrs(label_es, label_en),
        )
    return html.Div([label_node, component], **props)


def _fra_segmentation_card_class() -> str:
    return "stats-filter-card stats-filter-card-wide stats-fra-only stats-segmentation-card"


def _control_group(
    title: str,
    children: list[Any],
    class_name: str = "stats-filter-card",
    element_id: str | None = None,
) -> Component:
    props: dict[str, Any] = {"className": class_name}
    if element_id:
        props["id"] = element_id
    return html.Section(
        [
            html.H2(
                title,
                className="stats-filter-card-title",
                **text_attrs(title, LABELS_EN.get(title, title)),
            ),
            html.Div(children, className="stats-filter-card-body"),
        ],
        **props,
    )


def _header() -> Component:
    return build_page_header(
        eyebrow=text("Panel de Estadísticas", "Statistics panel"),
        title=text("Estadísticas europeas LGBTIQ+", "European LGBTIQ+ statistics"),
        description=[
            text(
                "Explora la realidad sociodemográfica, la protección legal y la relación entre ambas.",
                "Explore the sociodemographic reality, legal protection and the relationship between both.",
            ),
            html.Br(),
            text(
                "Para generar una respuesta, selecciona una Categoría y un Indicador.",
                "To generate a result, select a Category and an Indicator.",
            ),
        ],
        actions=[
            dcc.Link(
                text(
                    "Crear informe con esta selección",
                    "Create report from this selection",
                ),
                id="stats-create-report-link",
                href=route_path("reports"),
                className="stats-create-report-link app-button app-button-primary",
            ),
        ],
        class_name="stats-header",
    )


def _report_destination(report_href: str, *, authenticated: bool) -> str:
    del authenticated
    return report_href


def _dynamic_source_attribution(index: str) -> Component:
    return html.Div(
        build_source_attribution("fra", compact=True),
        id={"type": "stats-source-attribution", "index": index},
        className="stats-source-attribution-slot",
    )


def _combined_source_attribution(index: str) -> Component:
    return html.Div(
        [
            build_source_attribution("fra", compact=True),
            build_source_attribution("ilga", compact=True),
        ],
        id={"type": "stats-combined-source-attribution", "index": index},
        className="stats-source-attribution-combined-slot",
    )


def _deferred_graph_slot(graph_id: str) -> Component:
    """Reserve layout space without mounting Plotly before a valid figure exists."""
    return html.Div(id=f"{graph_id}-slot", className="stats-deferred-graph-slot")


def _stable_map_graph_slot() -> Component:
    """Keep the interactive map mounted while deferring its first Plotly figure."""
    return html.Div(
        dcc.Graph(
            id="stats-map-graph",
            responsive=True,
            config=fixed_europe_map_config(extra_mode_bar_buttons_to_remove=("toImage",)),
            className="stats-mapbox-graph europe-map-container",
            style=_map_graph_style(visible=False),
        ),
        id="stats-map-graph-slot",
        className="stats-deferred-graph-slot",
    )


def _map_graph_style(*, visible: bool) -> dict[str, str]:
    style = {"width": "100%"}
    if not visible:
        style["display"] = "none"
    return style


def _map_ranking_content(
    ranking: list[dict[str, Any]], language: str = "es"
) -> list[Component]:
    """Build the map's accessible ranking from the already queried FRA rows."""
    language_index = 1 if language == "en" else 0
    available: list[dict[str, Any]] = []
    for row in ranking:
        value = row.get("value")
        if value is None or isinstance(value, bool):
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(number):
            continue
        label = country_labels(
            str(row.get("iso") or ""), str(row.get("country") or "")
        )[language_index]
        available.append({"country": label, "value": number})
    available.sort(key=lambda row: (-float(row["value"]), str(row["country"]).casefold()))
    title = text("Ranking de países", "Country ranking", language=language)
    if not available:
        return [
            html.H3(title, className="stats-map-ranking-title"),
            html.P(
                text("No hay países con datos.", "No countries have data.", language=language),
                className="stats-map-ranking-empty",
            ),
        ]
    rows = [
        html.Li(
            [
                html.Span(str(position), className="stats-map-ranking-position"),
                html.Span(str(row["country"]), className="stats-map-ranking-country"),
                html.Span(
                    (format_percentage(row["value"]) or "0%").replace("%", " %"),
                    className="stats-map-ranking-value",
                ),
            ],
            className="stats-map-ranking-row",
            **dash_attrs(
                {
                    "aria-label": (
                        f"{position}. {row['country']} — "
                        f"{(format_percentage(row['value']) or '0%').replace('%', ' %')}"
                    )
                }
            ),
        )
        for position, row in enumerate(available, start=1)
    ]
    return [
        html.Div(
            [
                html.H3(title, className="stats-map-ranking-title"),
                html.Span(
                    str(len(available)),
                    className="stats-map-ranking-count",
                    **dash_attrs(
                        {
                            "aria-label": (
                                f"{len(available)} countries"
                                if language == "en"
                                else f"{len(available)} países"
                            )
                        }
                    ),
                ),
            ],
            className="stats-map-ranking-header",
        ),
        html.Ol(rows, className="stats-map-ranking-list"),
    ]


def _graph_component(
    graph_id: str,
    figure: Any,
    *,
    style: dict[str, str] | None = None,
    class_name: str = "stats-chart-graph",
    config: dcc.Graph.Config | None = None,
) -> Component | Any:
    if figure is no_update:
        return no_update
    if figure is None:
        raise ValueError(f"{graph_id}_requires_a_complete_figure")
    return dcc.Graph(
        id=graph_id,
        figure=figure,
        responsive=True,
        config=config or chart_graph_config(),
        className=class_name,
        style=style or {"width": "100%"},
    )


def _optional_graph_component(
    graph_id: str,
    figure: Any,
    *,
    style: dict[str, str] | None = None,
    class_name: str = "stats-chart-graph",
    config: dcc.Graph.Config | None = None,
) -> Component | Any | None:
    """Mount an optional graph, preserving partial updates and allowing cleanup."""
    if figure is no_update:
        return no_update
    if figure is None:
        return None
    return _graph_component(
        graph_id,
        figure,
        style=style,
        class_name=class_name,
        config=config,
    )


def _response_comparison_component(figure: Any, style: dict[str, str]) -> Component | Any:
    """Render the country key outside Plotly's plotting canvas."""
    if figure is no_update:
        return no_update
    legend_items: list[Component] = []
    for trace in getattr(figure, "data", ()):
        name = str(getattr(trace, "name", "") or "").strip()
        color = getattr(getattr(trace, "marker", None), "color", None)
        if not name or not isinstance(color, str):
            continue
        legend_items.append(
            html.Span(
                [
                    html.Span(
                        className="stats-country-legend-swatch",
                        style={"backgroundColor": color},
                    ),
                    html.Span(name),
                ],
                className="stats-country-legend-item",
            )
        )
    figure.update_layout(showlegend=False)
    return html.Div(
        [
            _graph_component("stats-response-comparison-graph", figure, style=style),
            html.Div(
                [
                    html.Span(
                        text("Países", "Countries"),
                        className="stats-country-legend-title",
                    ),
                    html.Div(legend_items, className="stats-country-legend-items"),
                ],
                className=(
                    "stats-country-legend" if legend_items else "stats-country-legend is-hidden"
                ),
            ),
        ],
        className="stats-response-comparison-layout",
    )


def _map_panel() -> Component:
    return html.Div(
        [
            html.Div(
                [
                    html.H2(text("Mapa de Europa", "Map of Europe")),
                    html.Div(
                        [
                            html.Button(
                                text("Deseleccionar todos", "Clear selection"),
                                id="stats-clear-countries",
                                disabled=True,
                                className="stats-clear-selection",
                            ),
                            _chart_export_control("stats-map-graph"),
                        ],
                        className="stats-panel-actions",
                    ),
                ],
                className="stats-panel-heading",
            ),
            html.P(
                text(
                    "Pulsa sobre cada país para seleccionarlo o deseleccionarlo.",
                    "Click each country to select or deselect it.",
                ),
                className="stats-panel-hint",
            ),
            html.Div(
                [
                    _stable_map_graph_slot(),
                    html.Aside(
                        _map_ranking_content([]),
                        id="stats-map-ranking",
                        className="stats-map-ranking",
                        **dash_attrs(
                            {
                                "aria-label": "Ranking de países",
                                "aria-live": "polite",
                                **attribute_attrs(
                                    "aria-label",
                                    "Ranking de países",
                                    "Country ranking",
                                ),
                            }
                        ),
                    ),
                ],
                className="stats-map-visual-grid",
            ),
            _chart_help("map"),
            _dynamic_source_attribution("map"),
        ],
        className="stats-panel stats-panel-wide stats-map-panel",
    )


def _combined_analysis_panel() -> Component:
    combined_block = html.Section(
        [
            _block_header(
                "FRA + ILGA-Europe",
                "Análisis combinado: FRA + ILGA-Europe",
                "Combined analysis: FRA + ILGA-Europe",
            ),
            html.P(
                text(
                    "Comparación de la experiencia social y la protección legal mediante cuadrantes.",
                    "Comparison of social experience and legal protection using quadrants.",
                ),
                className="stats-block-description",
            ),
            html.Div(id="stats-combined-intro", className="stats-combined-intro"),
            html.Div(id="stats-combined-download-action"),
            html.Section(
                id="stats-combined-metric-row",
                className="stats-metric-row stats-executive-grid",
            ),
            html.Div(
                [
                    _graph_panel(
                        "Cuadrantes FRA e ILGA-Europe",
                        "FRA and ILGA-Europe quadrants",
                        "stats-quadrant-graph",
                        panel_id="stats-quadrant-panel",
                        combined_sources=True,
                        scrollable=True,
                        panel_class_name=(
                            "stats-panel stats-panel-wide stats-combined-chart-panel"
                        ),
                    ),
                    _graph_panel(
                        "Diferencia de posiciones entre rankings",
                        "Difference in ranking positions",
                        "stats-ranking-gap-graph",
                        panel_id="stats-ranking-gap-panel",
                        combined_sources=True,
                        scrollable=True,
                        panel_class_name=(
                            "stats-panel stats-panel-wide stats-combined-chart-panel is-hidden"
                        ),
                    ),
                ],
                className="stats-grid",
            ),
        ],
        id="stats-combined-block",
        className="stats-analytics-block is-hidden",
    )
    return html.Div(
        [
            html.Div(
                id="stats-combined-compatibility-messages",
                className="stats-combined-compatibility-messages",
                **dash_attrs({"aria-live": "polite"}),
            ),
            combined_block,
        ],
        className="stats-combined-region",
    )


def _combined_download_action(available: bool) -> Component | None:
    if not available:
        return None
    return html.Button(
        text(
            "Descargar datos combinados (CSV)",
            "Download combined data (CSV)",
        ),
        id={"type": "stats-combined-download-button", "index": "available"},
        type="button",
        n_clicks=0,
        className="stats-chart-export-button stats-combined-download-button",
    )


def _temporal_panel() -> Component:
    return html.Div(
        [
            _chart_panel_heading(
                "Evolución temporal",
                "Temporal evolution",
                "stats-temporal-graph",
            ),
            html.Details(
                [
                    html.Summary(
                        text(
                            "Países visibles en la evolución",
                            "Countries visible in the evolution",
                        )
                    ),
                    html.Div(
                        [
                            html.Button(
                                text("Seleccionar todos", "Select all"),
                                id="stats-temporal-select-all",
                                type="button",
                                n_clicks=0,
                                className="stats-temporal-selection-button",
                            ),
                            html.Button(
                                text("Deseleccionar todos", "Deselect all"),
                                id="stats-temporal-deselect-all",
                                type="button",
                                n_clicks=0,
                                className="stats-temporal-selection-button",
                            ),
                        ],
                        className="stats-temporal-selection-actions",
                    ),
                    dcc.Checklist(
                        id="stats-temporal-country-select",
                        options=[],
                        value=[],
                        className="stats-temporal-country-list",
                        inputClassName="stats-temporal-country-input",
                        labelClassName="stats-temporal-country-option",
                    ),
                ],
                className="stats-temporal-country-controls",
            ),
            html.P(
                text(
                    "La selección del mapa destaca series, pero no elimina otros países.",
                    "The map selection highlights series without removing other countries.",
                ),
                className="stats-panel-hint",
            ),
            html.Div(
                _deferred_graph_slot("stats-temporal-graph"),
                className="stats-temporal-chart-scroll",
            ),
            _chart_help("temporal"),
            _dynamic_source_attribution("temporal"),
        ],
        className="stats-panel stats-panel-wide stats-temporal-section",
    )


def _graph_panel(
    title_es: str,
    title_en: str,
    graph_id: str,
    figure: Any | None = None,
    *,
    panel_id: str | None = None,
    panel_class_name: str = "stats-panel",
    footer: Component | None = None,
    combined_sources: bool = False,
    scrollable: bool = False,
) -> Component:
    panel_props: dict[str, Any] = {"className": panel_class_name}
    if panel_id:
        panel_props["id"] = panel_id
    if figure is not None:
        raise ValueError("statistics_graph_panels_must_defer_plotly_mounting")
    graph = _deferred_graph_slot(graph_id)
    graph_content: Component = (
        html.Div(graph, className="stats-chart-horizontal-scroll") if scrollable else graph
    )
    help_kind = {
        "stats-ranking-graph": "ranking",
        "stats-average-graph": "average",
        "stats-quadrant-graph": "quadrants",
        "stats-ranking-gap-graph": "ranking_gap",
    }.get(graph_id)
    return html.Div(
        [
            _chart_panel_heading(title_es, title_en, graph_id),
            graph_content,
            _chart_help(help_kind) if help_kind else None,
            footer,
            (
                _combined_source_attribution(graph_id)
                if combined_sources
                else _dynamic_source_attribution(graph_id)
            ),
        ],
        **panel_props,
    )


def _ranking_pagination_controls() -> Component:
    return html.Nav(
        [
            html.Button(
                text("Anterior", "Previous"),
                id="stats-ranking-previous",
                type="button",
                disabled=True,
                className="stats-ranking-page-button",
            ),
            html.Span(
                text("Sin pa\u00edses", "No countries"),
                id="stats-ranking-page-label",
                className="stats-ranking-page-label",
                **dash_attrs({"aria-live": "polite"}),
            ),
            html.Button(
                text("Siguiente", "Next"),
                id="stats-ranking-next",
                type="button",
                disabled=True,
                className="stats-ranking-page-button",
            ),
        ],
        className="stats-ranking-pagination",
        **dash_attrs(
            {
                "aria-label": "Paginaci\u00f3n del ranking / Ranking pagination",
            }
        ),
    )


def _chart_panel_heading(title_es: str, title_en: str, graph_id: str) -> Component:
    return html.Div(
        [
            html.H2(text(title_es, title_en)),
            _chart_export_control(graph_id),
        ],
        className="stats-panel-heading",
    )


def _chart_help(kind: str) -> Component:
    copy = {
        "map": (
            "El color representa el porcentaje de la respuesta FRA seleccionada en cada país sobre una escala 0-100. Un país sin dato no equivale a 0. La selección solo resalta países para compararlos.",
            "Colour represents the selected FRA response percentage in each country on a 0-100 scale. A country with no data is not zero. Selection only highlights countries for comparison.",
        ),
        "temporal": (
            "Cada línea sigue un país entre ediciones disponibles. Solo debe interpretarse como evolución cuando el indicador, la respuesta, los filtros y la metodología son comparables entre encuestas.",
            "Each line follows a country across available editions. It should be read as change over time only when the indicator, response, filters and methodology are comparable between surveys.",
        ),
        "ranking": (
            "Ordena los países por el porcentaje FRA seleccionado. La posición describe esta consulta concreta y no constituye una clasificación general de bienestar o derechos.",
            "Countries are ordered by the selected FRA percentage. Rank describes this specific query and is not a general ranking of wellbeing or rights.",
        ),
        "average": (
            "Compara cada país seleccionado con la media simple de países participantes que tienen un valor válido para la misma encuesta, indicador, respuesta y filtros. Los valores nulos se excluyen y los ceros reales se conservan.",
            "Selected countries are compared with the simple mean of participating countries with a valid value for the same survey, indicator, response and filters. Null values are excluded and genuine zeros are retained.",
        ),
        "response_comparison": (
            "Compara el reparto de respuestas FRA entre países. Cada serie mantiene la misma pregunta, año y segmentación. Los porcentajes no disponibles no se convierten en cero.",
            "This compares the FRA response distribution across countries. Every series keeps the same question, year and segmentation. Unavailable percentages are not converted to zero.",
        ),
        "response": (
            "Muestra el detalle de las opciones de respuesta para el universo de países de la consulta. Lee conjuntamente porcentajes, países disponibles y ausencias de datos.",
            "This shows response-option detail for the query's country universe. Read percentages together with the available-country count and missing data.",
        ),
        "quadrants": (
            "¿Qué muestra? Compara la protección legal y el resultado FRA de cada país. Solo aparece para respuestas Sí/No cuya interpretación sea clara o para respuestas cuantitativas. ¿Cómo se interpreta? Las líneas marcan las medianas: el valor que deja aproximadamente a la mitad de los países a cada lado. Los valores exactamente iguales quedan en el lado igual o superior. En respuestas numéricas sin una orientación clara se habla únicamente de valores FRA altos o bajos, sin calificarlos como mejores o peores. ¿Qué podemos observar? Países donde ambos resultados ocupan posiciones distintas dentro del conjunto, sin restar ni equiparar las escalas.",
            "What does it show? It compares each country's legal protection and FRA result. It is only shown for yes/no answers with a clear interpretation or for quantitative answers. How should it be read? The lines mark the medians: the value leaving roughly half the countries on either side. Values exactly on a median belong to the at-or-above side. Numeric answers without a clear direction are described only as higher or lower FRA values, without calling them better or worse. What can we observe? Countries where both results occupy different positions within the group, without subtracting or treating the scales as equivalent.",
        ),
        "ranking_gap": (
            "¿Qué muestra? Compara la posición de cada país en el ranking legal de ILGA-Europe con su posición según el resultado FRA seleccionado. ¿Cómo se interpreta? Una separación pequeña indica posiciones parecidas. Los países con mayor diferencia aparecen primero. Para experiencias desfavorables, una proporción FRA menor ocupa una posición social mejor. ¿Qué podemos observar? Posiciones legales y sociales distintas, sin afirmar que una dimensión cause la otra.",
            "What does it show? It compares each country's ILGA-Europe legal rank with its position for the selected FRA result. How should it be read? A small separation means similar positions. Countries with the largest difference appear first. For adverse experiences, a lower FRA percentage receives a better social position. What can we observe? Different legal and social positions, without claiming that one dimension causes the other.",
        ),
    }
    es, en = copy[kind]
    return html.Details(
        [
            html.Summary(text("¿Cómo interpretar esta gráfica?", "How should I read this chart?")),
            html.P(text(es, en)),
        ],
        className="stats-chart-help",
    )


def _response_detail_graph_style(figure: Any) -> dict[str, str]:
    style = _dynamic_graph_style(figure, min_height=520)
    meta = getattr(getattr(figure, "layout", None), "meta", None)
    minimum_width = meta.get("minimum_width") if isinstance(meta, dict) else None
    if isinstance(minimum_width, (int, float)) and minimum_width > 760:
        style["minWidth"] = f"{int(minimum_width)}px"
    return style


def _ranking_graph_style(figure: Any) -> dict[str, str]:
    return _dynamic_graph_style(figure, min_height=500)


def _average_panel_class(selected: list[str]) -> str:
    base = "stats-panel stats-panel-wide stats-average-panel"
    return base if selected else f"{base} is-hidden"


def _response_comparison_graph_style(figure: Any) -> dict[str, str]:
    style = _dynamic_graph_style(figure, min_height=560)
    meta = getattr(getattr(figure, "layout", None), "meta", None)
    minimum_width = meta.get("minimum_width") if isinstance(meta, dict) else None
    if isinstance(minimum_width, (int, float)) and minimum_width > 760:
        style["minWidth"] = f"{int(minimum_width)}px"
    return style


def _dynamic_graph_style(figure: Any, *, min_height: int) -> dict[str, str]:
    raw_height = getattr(getattr(figure, "layout", None), "height", None)
    try:
        height = max(min_height, int(raw_height or min_height))
    except TypeError, ValueError:
        height = min_height
    return {
        "width": "100%",
        "height": f"{height}px",
        "minHeight": f"{min_height}px",
    }


def _chart_export_control(graph_id: str) -> Component:
    return html.Div(
        [
            html.Button(
                text("Descargar PNG", "Download PNG"),
                type="button",
                className="stats-chart-export-button",
                title="Descargar PNG",
                **dash_attrs(
                    {
                        "data-chart-export": "true",
                        "data-chart-export-target": graph_id,
                        "data-export-format": EXPORT_FORMAT,
                        "data-export-width": str(EXPORT_WIDTH),
                        "data-export-height": str(EXPORT_HEIGHT),
                        "data-export-scale": str(EXPORT_SCALE),
                        **attribute_attrs(
                            "title",
                            "Descargar PNG",
                            "Download PNG",
                        ),
                        "aria-controls": graph_id,
                    }
                ),
            ),
            html.Span(
                text(
                    "No se ha podido generar la imagen.",
                    "The image could not be generated.",
                ),
                className="stats-chart-export-error",
                hidden=True,
                role="alert",
                **dash_attrs(
                    {
                        "data-chart-export-error": graph_id,
                        "aria-live": "polite",
                    }
                ),
            ),
        ],
        className="stats-chart-export-control",
    )


def _block_header(kicker: str, title_es: str, title_en: str) -> Component:
    return html.Header(
        [html.P(kicker, className="stats-block-kicker"), html.H2(text(title_es, title_en))],
        className="stats-block-header",
    )


def _temporal_country_options(
    result: dict[str, Any],
    language: str,
) -> list[dict[str, Any]]:
    countries: dict[str, str] = {}
    for row in result.get("history") or []:
        if not isinstance(row, dict):
            continue
        iso = normalize_country_code(
            row.get("country_code") or row.get("iso"),
            row.get("country_name") or row.get("country"),
        )
        if not iso or iso in {"EU27", "EU28"}:
            continue
        fallback = str(row.get("country_name") or row.get("country") or iso)
        countries[iso] = country_labels(iso, fallback)[1 if language == "en" else 0]
    return build_dropdown_options(
        (
            {"label": label, "value": iso}
            for iso, label in sorted(countries.items(), key=lambda item: item[1].casefold())
        ),
        context="statistics-temporal-country",
    )


def _category_options(
    year: int,
    language: str = "es",
) -> list[dict[str, Any]]:
    return _visible_category_options(get_fra_categories(year), language)


def _selected_category_value(
    options: list[dict[str, Any]],
    current: str | None,
) -> str | None:
    selected = option_value_or_none(options, current)
    values = {item["value"] for item in options}
    if selected in values:
        return str(selected)
    return None


def _visible_category_options(categories: list[str], language: str = "es") -> list[dict[str, Any]]:
    return build_dropdown_options(
        [
            {
                "label": label_en if language == "en" else label_es,
                "value": category,
            }
            for category in _visible_categories(categories)
            for label_es, label_en in [taxonomy_pair("fra_category", category)]
        ],
        context="statistics-fra-category",
    )


def _visible_categories(categories: list[str]) -> list[str]:
    return [
        category
        for category in categories
        if normalize_text_key(category) not in EXCLUDED_CATEGORY_KEYS
    ]


def _translated_segmentation_options(
    options: list[dict[str, Any]], language: str = "es"
) -> list[dict[str, Any]]:
    return _translated_taxonomy_options(options, "fra_filter", language)


def _translated_taxonomy_options(
    options: list[dict[str, Any]],
    namespace: str,
    language: str = "es",
) -> list[dict[str, Any]]:
    translated: list[dict[str, Any]] = []
    for option in options:
        value = str(option.get("value") or "")
        label_es, label_en = taxonomy_pair(namespace, value)
        translated.append({**option, "label": label_en if language == "en" else label_es})
    return build_dropdown_options(translated, context=f"statistics-{namespace}")


def _fra_response_help(response_type: Any, language: str) -> Component | None:
    if response_type != "ranked_reason":
        return None
    return html.Div(
        [
            html.Strong(ui_text("fra_ranked_reason_title", language)),
            html.P(ui_text("fra_ranked_reason_intro", language)),
            html.Ul(
                [
                    html.Li(ui_text("fra_ranked_reason_1st", language)),
                    html.Li(ui_text("fra_ranked_reason_2nd", language)),
                    html.Li(ui_text("fra_ranked_reason_3rd", language)),
                    html.Li(ui_text("fra_ranked_reason_not_selected", language)),
                ]
            ),
        ]
    )


def _default_option_value(options: list[dict[str, Any]]) -> Any:
    enabled = [item for item in options if not item.get("disabled", False)]
    if any(item.get("value") == "All" for item in enabled):
        return "All"
    return None


def _all_option_value(options: list[dict[str, Any]]) -> str | None:
    return "All" if any(item.get("value") == "All" for item in options) else None


def _has_real_segmentation_option(options: list[dict[str, Any]]) -> bool:
    return any(
        not option.get("disabled", False)
        and normalize_text_key(option.get("value")) != "all"
        for option in options
    )


def _disable_all_options(options: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{**option, "disabled": True} for option in options]


def _is_active_filter_type(value: Any) -> bool:
    return bool(value and normalize_text_key(value) != "all")


def _explicit_filter_value(
    filter_type: str | None,
    options: list[dict[str, Any]],
    current: Any,
) -> Any:
    """Keep an explicit value; never replace it with the first option."""
    if not _is_active_filter_type(filter_type):
        return option_value_or_none(options, "All")
    return option_value_or_none(options, current)


def _resolved_ui_filters(
    demographic_type: Any,
    demographic_value: Any,
    identity_type: Any,
    identity_value: Any,
) -> StatisticsFilters:
    filters = StatisticsFilters.from_raw(
        demographic_type,
        demographic_value,
        identity_type,
        identity_value,
    )
    if filters.demographic_active:
        return StatisticsFilters(
            demographic_type=filters.demographic_type,
            demographic_value=filters.demographic_value,
        )
    return filters


def _payload_filter_values(payload: dict[str, Any] | None) -> dict[str, set[str]]:
    values = (payload or {}).get("values") or {}
    available = {
        str(filter_type): {
            normalize_filter_value(option.get("value"))
            for option in options
            if isinstance(option, dict) and option.get("value") is not None
        }
        for filter_type, options in values.items()
        if isinstance(options, list)
    }
    available.setdefault("All", {"All"})
    return available


def _segmentation_catalog_options(
    catalog: tuple[str, ...],
    available_options: list[dict[str, Any]],
    language: str = "es",
) -> list[dict[str, Any]]:
    """Keep the FRA filter catalog stable while disabling unavailable entries."""
    available = {
        str(option.get("value") or "")
        for option in available_options
        if option.get("value") and not option.get("disabled", False)
    }
    options: list[dict[str, Any]] = []
    for value in catalog:
        labels = taxonomy_pair("fra_filter", value)
        options.append(
            {
                "label": labels[1] if language == "en" else labels[0],
                "value": value,
                "disabled": value not in available,
            }
        )
    return build_dropdown_options(options, context="statistics-fra-filter")


def _segmentation_group(
    title_es: str,
    title_en: str,
    description_es: str,
    description_en: str,
    type_id: str,
    value_id: str,
    type_catalog: tuple[str, ...],
    *,
    element_id: str | None = None,
) -> Component:
    children = [
        html.Header(
            [
                html.H3(text(title_es, title_en)),
                html.P(text(description_es, description_en)),
            ],
            className="stats-segmentation-row-heading",
        ),
        _field(
            ("Tipo de filtro", "Filter type"),
            dcc.RadioItems(
                id=type_id,
                options=_segmentation_catalog_options(type_catalog, []),
                value=None,
                className="stats-radio-card-grid",
                inputClassName="stats-radio-card-input",
                labelClassName="stats-radio-card-label",
            ),
        ),
        _field(
            ("Valor", "Value"),
            dcc.RadioItems(
                id=value_id,
                options=[],
                value=None,
                className="stats-radio-value-grid",
                inputClassName="stats-radio-card-input",
                labelClassName="stats-radio-card-label",
            ),
        ),
    ]
    if element_id:
        return html.Section(
            children,
            id=element_id,
            className="stats-segmentation-row is-disabled",
        )
    return html.Section(children, className="stats-segmentation-row")


def _dashboard_component_outputs(outputs: tuple[Any, ...] | list[Any]) -> tuple[Any, ...]:
    """Map render values to stable properties or first-mount visual graph slots."""
    if len(outputs) != 33:
        raise ValueError("statistics_dashboard_output_contract_changed")
    return (
        outputs[0],
        outputs[1],
        outputs[2],
        no_update if outputs[2] is no_update else _map_graph_style(visible=True),
        outputs[3],
        outputs[4],
        outputs[5],
        _optional_graph_component(
            "stats-temporal-graph",
            outputs[6],
            style={"width": "100%", "minWidth": "860px", "height": "680px"},
        ),
        outputs[7],
        _graph_component("stats-ranking-graph", outputs[8], style=outputs[28]),
        _optional_graph_component("stats-average-graph", outputs[9]),
        outputs[10],
        _response_comparison_component(outputs[11], outputs[29]),
        outputs[12],
        outputs[13],
        _graph_component("stats-response-detail-graph", outputs[14], style=outputs[15]),
        outputs[16],
        outputs[17],
        _optional_graph_component("stats-quadrant-graph", outputs[18]),
        outputs[19],
        _optional_graph_component("stats-ranking-gap-graph", outputs[20]),
        outputs[21],
        outputs[22],
        outputs[23],
        outputs[24],
        outputs[25],
        outputs[26],
        outputs[27],
        outputs[30],
        outputs[31],
        outputs[32],
    )


def _render_temporal_dashboard_update(
    result: dict[str, Any],
    selected: list[str],
    language: str,
    temporal_countries: list[str],
) -> tuple[Any, ...]:
    started_at = time.perf_counter()
    history = list(result.get("history") or [])
    temporal = build_temporal_evolution_chart(
        history,
        selected,
        language,
        visible_countries=temporal_countries,
    )
    _prepare_dashboard_exports(
        {"temporal": temporal},
        result=result,
        selected_names=_selection_scope(result.get("ranking") or [], selected, language)["names"],
        language=language,
    )
    outputs: list[Any] = [no_update] * 33
    outputs[6] = temporal
    outputs[7] = (
        "stats-panel-wrapper stats-temporal-wrapper"
        if history
        else "stats-panel-wrapper stats-temporal-wrapper is-hidden"
    )
    logger.info(
        "statistics_callback_completed scope=temporal total_ms=%.2f",
        (time.perf_counter() - started_at) * 1000,
    )
    return tuple(outputs)


def _render_ranking_dashboard_update(
    result: dict[str, Any],
    selected: list[str],
    language: str,
    ranking_page: int | None,
) -> tuple[Any, ...]:
    started_at = time.perf_counter()
    ranking = list(result.get("ranking") or [])
    visible_ranking = paginate_ranking(
        ranking,
        ranking_page,
        selected_countries=selected,
    ).rows
    comparative_ranking = build_comparative_ranking_chart(
        visible_ranking,
        selected,
        language,
        indicator=str(result.get("indicator") or ""),
        year=result.get("year"),
    )
    average = build_eu_average_comparison_chart(
        ranking,
        selected,
        language,
    )
    _prepare_dashboard_exports(
        {"ranking": comparative_ranking, "average": average},
        result=result,
        selected_names=_selection_scope(ranking, selected, language)["names"],
        language=language,
    )
    outputs: list[Any] = [no_update] * 33
    outputs[8] = comparative_ranking
    outputs[9] = average
    outputs[10] = _average_panel_class(selected)
    outputs[28] = _ranking_graph_style(comparative_ranking)
    logger.info(
        "statistics_callback_completed scope=ranking total_ms=%.2f",
        (time.perf_counter() - started_at) * 1000,
    )
    return tuple(outputs)


def _render_dashboard(
    result: dict[str, Any],
    selected: list[str],
    language: str,
    *,
    temporal_countries: list[str] | None = None,
    ranking_page: int | None = 0,
):
    cache_key = _statistics_dashboard_cache_key(
        result,
        selected,
        language,
        temporal_countries=temporal_countries,
        ranking_page=ranking_page,
    )
    if cache_key is None:
        return _render_dashboard_uncached(
            result,
            selected,
            language,
            temporal_countries=temporal_countries,
            ranking_page=ranking_page,
        )
    return cache.get_or_compute(
        cache_key,
        lambda: _render_dashboard_uncached(
            result,
            selected,
            language,
            temporal_countries=temporal_countries,
            ranking_page=ranking_page,
        ),
        timeout=STATISTICS_DASHBOARD_CACHE_SECONDS,
    )


def _statistics_dashboard_cache_key(
    result: dict[str, Any],
    selected: list[str],
    language: str,
    *,
    temporal_countries: list[str] | None,
    ranking_page: int | None,
) -> str | None:
    query_token = str(result.get("query_token") or "").strip()
    if not query_token or not getattr(cache, "app", None):
        return None
    result_payload = json.dumps(
        result,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        default=str,
    )
    identity = {
        "version": STATISTICS_DASHBOARD_CACHE_VERSION,
        "query_token": query_token,
        "result_digest": hashlib.sha256(result_payload.encode("utf-8")).hexdigest(),
        "selected": selected,
        "language": language,
        "temporal_countries": temporal_countries or [],
        "ranking_page": ranking_page,
    }
    serialized = json.dumps(identity, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return f"statistics-dashboard:{hashlib.sha256(serialized.encode('utf-8')).hexdigest()}"


def _render_dashboard_uncached(
    result: dict[str, Any],
    selected: list[str],
    language: str,
    *,
    temporal_countries: list[str] | None = None,
    ranking_page: int | None = 0,
):
    render_started_at = time.perf_counter()
    if result.get("status") != "ok":
        raise ValueError("statistics_dashboard_requires_ready_result")

    source = str(result.get("source") or "")
    ranking = list(result.get("ranking") or [])
    data = list(result.get("data") or [])
    detail = list(result.get("detail_data") or data)
    history = list(result.get("history") or [])
    combined_analysis = dict(result.get("combined_analysis") or {})
    combined = list(combined_analysis.get("rows") or result.get("combined") or [])
    normalization_started_at = time.perf_counter()
    response_dataframe = prepare_fra_response_comparison_data(
        detail,
        list(result.get("country_universe") or []),
        language=language,
    )
    normalization_ms = (time.perf_counter() - normalization_started_at) * 1000
    scope = _selection_scope(ranking, selected, language)
    visible_ranking = paginate_ranking(
        ranking,
        ranking_page,
        selected_countries=selected,
    ).rows
    raw_result_filters = result.get("filters")
    result_filters: dict[str, Any] = (
        raw_result_filters if isinstance(raw_result_filters, dict) else {}
    )
    map_started_at = time.perf_counter()
    map_figure = build_europe_choropleth(
        ranking,
        source=source,
        selected_isos=selected,
        language=language,
        filter_a_name=result_filters.get("filter_a_name", "All"),
        filter_a_value=result_filters.get("filter_a_value", "All"),
        filter_b_name=result_filters.get("filter_b_name", "All"),
        filter_b_value=result_filters.get("filter_b_value", "All"),
        response=str(result.get("answer") or "") or None,
        survey_year=_safe_int(result.get("year")),
    )
    map_ms = (time.perf_counter() - map_started_at) * 1000
    charts_started_at = time.perf_counter()
    logger.info(
        "statistics_figures_started indicator=%s countries=%d",
        result.get("indicator_code"),
        len(ranking),
    )
    temporal = (
        build_temporal_evolution_chart(
            history,
            selected,
            language,
            visible_countries=temporal_countries,
        )
        if history
        else None
    )
    comparative_ranking = build_comparative_ranking_chart(
        visible_ranking,
        selected,
        language,
        indicator=str(result.get("indicator") or ""),
        year=result.get("year"),
    )
    average = (
        build_eu_average_comparison_chart(
            ranking,
            selected,
            language,
        )
        if selected
        else None
    )
    comparison = build_response_country_comparison_chart(
        detail,
        selected,
        language,
        indicator=str(result.get("indicator") or ""),
        year=result.get("year"),
        prepared_data=response_dataframe,
    )
    response = build_fra_response_comparison_chart(
        detail,
        available_countries=list(result.get("country_universe") or []),
        selected_countries=selected,
        selected_response=str(result.get("answer") or "") or None,
        language=language,
        prepared_data=response_dataframe,
    )
    analysis_metrics = dict(combined_analysis.get("metrics") or {})
    semantics = dict(combined_analysis.get("semantics") or {})
    semantic_direction = str(semantics.get("direction") or "unknown")
    eligibility = dict(
        combined_analysis.get("quadrant_eligibility")
        or quadrant_eligibility(result.get("indicator"), result.get("answer"))
    )
    supported = dict(combined_analysis.get("supported_analyses") or {})
    if not supported:
        supported = get_combined_analysis_capabilities(
            question=result.get("indicator"),
            answer=result.get("answer"),
            rows=combined,
            semantics=semantics,
            quadrant=eligibility,
        )
    quadrants_eligible = bool(supported.get("quadrants"))
    ranking_gap_eligible = bool(supported.get("ranking_gap"))
    combined_visualizations_available = bool(
        supported.get("any_visualization")
        or quadrants_eligible
        or ranking_gap_eligible
    )
    combined_download_available = bool(
        supported.get("download") and combined_visualizations_available and combined
    )
    segmentation = " · ".join(_export_filter_labels(result, language)[1:])
    quadrants = (
        build_combined_quadrant_chart(
            combined,
            language,
            selected,
            semantic_direction=semantic_direction,
            answer=str(result.get("answer") or ""),
            metrics=analysis_metrics,
            segmentation=segmentation,
        )
        if quadrants_eligible
        else None
    )
    ranking_gap_data = dict(combined_analysis.get("ranking_gap") or {})
    if not ranking_gap_data:
        ranking_gap_data = ranking_position_rows(combined, semantic_direction)
    ranking_gap = (
        build_ranking_position_gap_chart(
            ranking_gap_data,
            language,
            answer=str(result.get("answer") or ""),
        )
        if ranking_gap_eligible
        else None
    )
    charts_ms = (time.perf_counter() - charts_started_at) * 1000
    logger.info(
        "statistics_figures_completed indicator=%s figure_ms=%.2f",
        result.get("indicator_code"),
        charts_ms,
    )
    figures = {
        "map": map_figure,
        "ranking": comparative_ranking,
        "response_comparison": comparison,
        "responses": response,
    }
    if temporal is not None:
        figures["temporal"] = temporal
    if average is not None:
        figures["average"] = average
    if quadrants is not None:
        figures["quadrants"] = quadrants
    if ranking_gap is not None:
        figures["ranking_gap"] = ranking_gap
    _prepare_dashboard_exports(
        figures,
        result=result,
        selected_names=scope["names"],
        language=language,
    )
    combined_metrics = (
        _combined_metric_cards(combined_analysis, language)
        if combined_visualizations_available
        else []
    )
    table_rows = _table_rows(result, selected, language)
    available_count = sum(1 for row in ranking if isinstance(row.get("value"), (int, float)))
    status_detail = (
        f"{available_count} countries with data · {scope['title']}"
        if language == "en"
        else f"{available_count} países con datos · {scope['title']}"
    )
    status = html.Div(
        [
            html.Strong(text("Consulta cargada", "Query loaded")),
            html.P(status_detail),
        ]
    )
    logger.info(
        "statistics_callback_completed scope=dashboard statistics_normalization_ms=%.2f "
        "statistics_geodata_ms=%.2f statistics_charts_ms=%.2f total_ms=%.2f "
        "chart_count=%d",
        normalization_ms,
        map_ms,
        charts_ms,
        (time.perf_counter() - render_started_at) * 1000,
        len(figures),
    )
    return (
        status,
        "stats-status stats-status-ok",
        map_figure,
        _map_ranking_content(ranking, language),
        not bool(selected),
        _executive_metric_cards(ranking, selected, history),
        temporal,
        (
            "stats-panel-wrapper stats-temporal-wrapper"
            if history
            else "stats-panel-wrapper stats-temporal-wrapper is-hidden"
        ),
        comparative_ranking,
        average,
        _average_panel_class(selected),
        comparison,
        (
            "stats-panel stats-panel-wide stats-response-comparison-section"
        ),
        _detail_summary(
            detail,
            language,
            available_countries=list(result.get("country_universe") or []),
            prepared_data=response_dataframe,
            ranking=ranking,
            selected_response=str(result.get("answer") or "") or None,
        ),
        response,
        _response_detail_graph_style(response),
        "stats-panel stats-panel-wide stats-response-panel",
        combined_metrics,
        quadrants,
        (
            "stats-panel stats-panel-wide stats-combined-chart-panel"
            if quadrants_eligible
            else "stats-panel stats-panel-wide stats-combined-chart-panel is-hidden"
        ),
        ranking_gap,
        (
            "stats-panel stats-panel-wide stats-combined-chart-panel"
            if ranking_gap_eligible
            else "stats-panel stats-panel-wide stats-combined-chart-panel is-hidden"
        ),
        _combined_compatibility_messages(combined_analysis, language),
        (
            _combined_intro(combined_analysis, language)
            if combined_visualizations_available
            else None
        ),
        (
            "stats-analytics-block"
            if combined_visualizations_available
            else "stats-analytics-block is-hidden"
        ),
        _combined_download_action(combined_download_available),
        _table_columns(table_rows, language),
        table_rows,
        _ranking_graph_style(comparative_ranking),
        _response_comparison_graph_style(comparison),
        not bool(table_rows),
        "",
        "stats-table-export-status is-hidden",
    )


def _prepare_dashboard_exports(
    figures: dict[str, Any],
    *,
    result: dict[str, Any],
    selected_names: list[str],
    language: str,
) -> None:
    source = str(result.get("source") or "")
    indicator = str(
        result.get("indicator")
        or result.get("category")
        or ("Statistics" if language == "en" else "Estadísticas")
    )
    year = result.get("year")
    filters = _export_filter_labels(result, language)
    combined_analysis = dict(result.get("combined_analysis") or {})
    for chart_type, figure in figures.items():
        title_es, title_en = CHART_EXPORT_TITLES[chart_type]
        is_combined = chart_type in {"quadrants", "ranking_gap"}
        export_year: int | str | None = year
        export_source = source
        if is_combined:
            export_year = (
                f"FRA-{combined_analysis.get('fra_year') or '—'}_"
                f"ILGA-{combined_analysis.get('ilga_year') or '—'}"
            )
            export_source = "FRA + ILGA-Europe"
        prepare_figure_for_export(
            figure,
            chart_type=chart_type,
            chart_title=title_en if language == "en" else title_es,
            indicator=indicator,
            countries=[] if chart_type == "responses" else selected_names,
            year=export_year,
            source=export_source,
            filters=filters,
            language=language,
        )


def _export_filter_labels(
    result: dict[str, Any],
    language: str,
) -> list[str]:
    labels: list[str] = []
    answer = str(result.get("answer") or "").strip()
    if answer:
        prefix = "Answer" if language == "en" else "Respuesta"
        labels.append(f"{prefix}: {answer}")

    raw_filters = result.get("filters")
    filters: dict[str, Any] = raw_filters if isinstance(raw_filters, dict) else {}
    rows = result.get("data") or []
    first_row = rows[0] if rows and isinstance(rows[0], dict) else {}
    for key, fallback_key in (
        ("filter_a_value", "filter_a"),
        ("filter_b_value", "filter_b"),
    ):
        value = str(filters.get(key) or first_row.get(fallback_key) or "").strip()
        if value and normalize_text_key(value) not in {"all", "todos"}:
            labels.append(value)
    return labels


def _executive_metric_cards(
    ranking: list[dict[str, Any]],
    selected: list[str],
    history: list[dict[str, Any]] | None = None,
) -> list[Any]:
    dataframe = pd.DataFrame(ranking)
    if dataframe.empty:
        return []
    dataframe["value"] = pd.to_numeric(dataframe["value"], errors="coerce")
    dataframe = (
        dataframe.dropna(subset=["value"])
        .sort_values("value", ascending=False)
        .reset_index(drop=True)
    )
    if dataframe.empty:
        return []
    mean = float(dataframe["value"].mean())
    median = float(dataframe["value"].median())
    standard_deviation = float(dataframe["value"].std(ddof=0))
    metrics: list[tuple[str | tuple[str, str], str]] = [
        (("Países analizados", "Countries analysed"), str(len(dataframe))),
        (("Media europea", "European average"), f"{mean:.2f}%"),
        (("Mediana", "Median"), f"{median:.2f}%"),
        (("Desviación estándar", "Standard deviation"), f"{standard_deviation:.2f} pp"),
        (
            ("Mayor valor", "Highest value"),
            f"{dataframe.iloc[0]['country']} · {dataframe.iloc[0]['value']:.2f}%",
        ),
        (
            ("Menor valor", "Lowest value"),
            f"{dataframe.iloc[-1]['country']} · {dataframe.iloc[-1]['value']:.2f}%",
        ),
    ]
    if selected:
        focus = dataframe[dataframe["iso"].astype(str).str.upper() == selected[0]]
        if not focus.empty:
            row = focus.iloc[0]
            position = int(focus.index[0]) + 1
            metrics.extend(
                [
                    (("País seleccionado", "Selected country"), f"{row['value']:.2f}%"),
                    (
                        ("Diferencia con la media", "Difference from average"),
                        f"{row['value'] - mean:+.2f} pp",
                    ),
                    (("Posición", "Rank"), f"{position}/{len(dataframe)}"),
                ]
            )
            historical = pd.DataFrame(history or [])
            if not historical.empty and {"iso", "year", "value"}.issubset(historical.columns):
                country_history = historical[
                    historical["iso"].astype(str).str.upper() == selected[0]
                ].copy()
                country_history["value"] = pd.to_numeric(country_history["value"], errors="coerce")
                country_history = (
                    country_history.dropna(subset=["value"])
                    .sort_values("year")
                    .drop_duplicates("year", keep="last")
                )
                if len(country_history) >= 2:
                    variation = float(
                        country_history.iloc[-1]["value"] - country_history.iloc[-2]["value"]
                    )
                    metrics.append(
                        (("Variación interanual", "Year-on-year change"), f"{variation:+.2f} pp")
                    )
    return [_metric_card(label, value) for label, value in metrics]


def _combined_metric_cards(analysis: dict[str, Any], language: str = "es") -> list[Any]:
    metrics = dict(analysis.get("metrics") or {})
    if not metrics:
        return []
    sample = {
        "insufficient": ("Insuficiente", "Insufficient"),
        "exploratory": ("Exploratoria", "Exploratory"),
        "normal": ("Adecuada", "Adequate"),
    }.get(str(metrics.get("sample_status")), ("—", "—"))
    sample_label = sample[1 if language == "en" else 0]
    fra_median = (metrics.get("fra") or {}).get("median")
    ilga_median = (metrics.get("ilga") or {}).get("median")
    return [
        _metric_card(("Países incluidos", "Countries included"), str(metrics.get("n", 0))),
        _metric_card(
            ("Mediana FRA", "FRA median"),
            f"{fra_median:.1f}%" if isinstance(fra_median, (int, float)) else "—",
        ),
        _metric_card(
            ("Mediana legal", "Legal median"),
            f"{ilga_median:.1f}" if isinstance(ilga_median, (int, float)) else "—",
        ),
        _metric_card(
            ("Años comparados", "Years compared"),
            f"FRA {analysis.get('fra_year') or '—'} · ILGA {analysis.get('ilga_year') or '—'}",
        ),
        _metric_card(("Cantidad de datos", "Amount of data"), sample_label),
    ]


def _metric_card(label: str | tuple[str, str], value: str) -> Any:
    rendered_label = text(label[0], label[1]) if isinstance(label, tuple) else label
    return html.Div([html.Span(rendered_label), html.Strong(value)], className="stats-metric-card")


def _combined_compatibility_messages(
    analysis: dict[str, Any], language: str = "es"
) -> list[Component]:
    indicator = str(analysis.get("indicator") or "—")
    answer = str(analysis.get("answer") or "—")
    semantics = dict(analysis.get("semantics") or {})
    eligibility = dict(
        analysis.get("quadrant_eligibility")
        or quadrant_eligibility(indicator, answer)
    )
    supported = dict(analysis.get("supported_analyses") or {})
    if not supported:
        supported = get_combined_analysis_capabilities(
            question=indicator,
            answer=answer,
            rows=list(analysis.get("rows") or []),
            semantics=semantics,
            quadrant=eligibility,
        )
    if not analysis.get("rows"):
        return [
            html.P(
                text(
                    "No hay suficientes datos compatibles para realizar un análisis combinado con esta selección.",
                    "There is not enough compatible data for a combined analysis with this selection.",
                    language=language,
                )
            )
        ]
    messages: list[Component] = []
    if not supported.get("quadrants"):
        reason = str(supported.get("quadrant_reason") or "")
        if reason == "insufficient_sample":
            copy = (
                "Los cuadrantes no se muestran porque hay menos de cinco países con datos FRA e ILGA-Europe comparables.",
                "The quadrants are not shown because fewer than five countries have comparable FRA and ILGA-Europe data.",
            )
        else:
            copy = (
                f'Los cuadrantes no se muestran para «{answer}» en «{indicator}» porque esta respuesta no puede interpretarse de forma segura como un dato Sí/No o cuantitativo con una dirección clara.',
                f'The quadrants are not shown for «{answer}» in «{indicator}» because this answer cannot be interpreted safely as yes/no or quantitative data with a clear direction.',
            )
        messages.append(html.P(text(*copy, language=language)))
    if not supported.get("ranking_gap"):
        reason = str(supported.get("ranking_gap_reason") or "")
        if reason == "insufficient_sample":
            copy = (
                "No se puede comparar posiciones porque se necesitan al menos dos países con datos válidos en ambas fuentes.",
                "Ranking positions cannot be compared because at least two countries need valid data in both sources.",
            )
        else:
            copy = (
                "No se puede construir una comparación de posiciones para esta respuesta porque un valor mayor o menor no representa claramente una situación más favorable o desfavorable.",
                "A ranking-position comparison cannot be built for this answer because a higher or lower value does not clearly represent a more or less favourable situation.",
            )
        messages.append(html.P(text(*copy, language=language)))
    return messages


def _combined_intro(analysis: dict[str, Any], language: str = "es") -> Component:
    indicator = str(analysis.get("indicator") or "—")
    answer = str(analysis.get("answer") or "—")
    fra_year = analysis.get("fra_year") or "—"
    ilga_year = analysis.get("ilga_year") or "—"
    semantics = dict(analysis.get("semantics") or {})
    direction = str(semantics.get("direction") or "unknown")
    supported = dict(analysis.get("supported_analyses") or {})
    if not supported:
        eligibility = quadrant_eligibility(indicator, answer)
        supported = get_combined_analysis_capabilities(
            question=indicator,
            answer=answer,
            rows=list(analysis.get("rows") or []),
            semantics=semantics,
            quadrant=eligibility,
        )
    quadrants_eligible = bool(supported.get("quadrants"))
    if language == "en":
        semantic_text = {
            "adverse": "A higher FRA percentage is interpreted as a potentially less favourable outcome for this question and answer.",
            "favourable": "A higher FRA percentage is interpreted as a potentially more favourable outcome for this question and answer.",
            "unknown": "The meaning of a high percentage cannot be determined reliably from the wording, so no favourable/adverse conclusion is automated.",
        }[direction]
        hypothesis = (
            f'This block compares the percentage for «{answer}» in «{indicator}» '
            "with each country's overall ILGA-Europe legal-protection score."
        )
        reading = (
            "Each point is a country. The central lines are the FRA and legal medians, so the chart compares positions within the available group without treating both scales as equivalent."
            if quadrants_eligible
            else "Only analyses that can be interpreted safely for the current answer are displayed."
        )
        timing = (
            f"Temporal context: FRA {fra_year} and ILGA-Europe {ilga_year}. "
            + (
                "The variables refer to different years, so this is an exploratory comparison rather than a simultaneous measurement."
                if str(fra_year) != str(ilga_year)
                else "Both sources use the same reference year, although their constructs and collection methods still differ."
            )
        )
        source_text = (
            "Sources: European Union Agency for Fundamental Rights (FRA) and ILGA-Europe "
            "Rainbow Map. Data processed and visualised by RainbowLens DataHub."
        )
        causality_text = (
            "A country's position in a quadrant does not show that one variable causes the other."
        )
    else:
        semantic_text = {
            "adverse": "Un porcentaje FRA mayor se interpreta como un resultado potencialmente menos favorable para esta pregunta y respuesta.",
            "favourable": "Un porcentaje FRA mayor se interpreta como un resultado potencialmente más favorable para esta pregunta y respuesta.",
            "unknown": "No puede determinarse con fiabilidad qué significa un porcentaje alto a partir del enunciado, por lo que no se automatiza una conclusión favorable o desfavorable.",
        }[direction]
        hypothesis = (
            f'Este bloque compara el porcentaje de la respuesta «{answer}» en «{indicator}» '
            "con la puntuación legal global ILGA-Europe de cada país."
        )
        reading = (
            "Cada punto representa un país. Las líneas centrales son las medianas FRA y legal, de modo que se comparan posiciones dentro del conjunto disponible sin equiparar ambas escalas."
            if quadrants_eligible
            else "Solo se muestran los análisis que pueden interpretarse de forma segura para la respuesta actual."
        )
        timing = (
            f"Contexto temporal: FRA {fra_year} e ILGA-Europe {ilga_year}. "
            + (
                "Las variables corresponden a años diferentes: es una comparación exploratoria, no una medición simultánea."
                if str(fra_year) != str(ilga_year)
                else "Ambas fuentes usan el mismo año de referencia, aunque miden conceptos y emplean metodologías diferentes."
            )
        )
        source_text = (
            "Fuentes: European Union Agency for Fundamental Rights (FRA) e ILGA-Europe "
            "Rainbow Map. Datos procesados y visualizados por RainbowLens DataHub."
        )
        causality_text = (
            "La posición de un país en un cuadrante no demuestra que una variable cause la otra."
        )
    children: list[Component] = [
        html.P(hypothesis),
        html.P(reading),
        html.P(causality_text, className="stats-methodology-warning"),
        html.P(timing, className="stats-methodology-warning"),
        html.P(source_text, className="stats-source-summary"),
    ]
    if quadrants_eligible:
        children.insert(2, html.P(semantic_text))
    normalization = dict(analysis.get("normalization") or {})
    if normalization.get("applied"):
        children.append(
            html.P(
                (
                    "La puntuación ILGA histórica se ha normalizado a una escala 0-100. Consulta la metodología de la fuente antes de comparar series."
                    if language != "en"
                    else "The historical ILGA score was normalised to a 0-100 scale. Consult the source methodology before comparing time series."
                ),
                className="stats-methodology-warning",
            )
        )
    return html.Div(children)


def _detail_summary(
    rows: list[dict[str, Any]],
    language: str = "es",
    *,
    available_countries: list[dict[str, Any]] | None = None,
    prepared_data: pd.DataFrame | None = None,
    ranking: list[dict[str, Any]] | None = None,
    selected_response: str | None = None,
) -> Any:
    summary = summarize_response_comparison(
        rows,
        available_countries=available_countries,
        language=language,
        prepared_data=prepared_data,
    )
    distribution = summary.get("distribution") or []
    countries_label = ui_text("statistics_countries_compared", language)
    distribution_label = ui_text("statistics_distribution", language)
    country_singular = "country" if language == "en" else "país"
    country_plural = "countries" if language == "en" else "países"
    valid_values = pd.to_numeric(
        pd.Series(
            [row.get("value") for row in (ranking or []) if isinstance(row, dict)],
            dtype=object,
        ),
        errors="coerce",
    ).dropna()
    european_mean = float(valid_values.mean()) if not valid_values.empty else None
    formatted_mean = (
        format_percentage(round(european_mean, 1)) if european_mean is not None else None
    )
    average_text = (
        formatted_mean.replace("%", " %") if formatted_mean else ui_text("no_data", language)
    )
    response_suffix = f" ({selected_response})" if selected_response else ""
    children: list[Any] = [
        html.Div(
            [
                html.Span(countries_label),
                html.Strong(str(summary.get("countries") or 0)),
            ],
            className="stats-detail-summary-card stats-detail-country-metric",
        ),
        html.Div(
            [
                html.Span(distribution_label),
                html.Ul(
                    [
                        html.Li(
                            [
                                html.Strong(
                                    str(item.get("label")),
                                    className="stats-response-distribution-label",
                                ),
                                html.Span(
                                    (format_percentage(item.get("value")) or "").replace("%", " %")
                                    if item.get("unit") == "%"
                                    else f"{item.get('value')} {_plural(item.get('value'), country_singular, country_plural)}",
                                    className="stats-response-distribution-value",
                                ),
                            ],
                            className="stats-response-distribution-item",
                        )
                        for item in distribution[:8]
                    ]
                ),
            ],
            className=(
                "stats-detail-summary-card stats-detail-summary-card-wide "
                "stats-response-distribution"
            ),
        ),
    ]
    children.append(
        html.Div(
            [
                html.Span(
                    f"{ui_text('statistics_european_average', language)}{response_suffix}"
                ),
                html.Strong(average_text),
            ],
            className=(
                "stats-detail-summary-card stats-european-average-reference"
            ),
        )
    )
    return children


def _combine_rankings(
    fra_rows: list[dict[str, Any]], ilga_rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    legal = {
        normalize_country_code(row.get("iso")): row
        for row in ilga_rows
        if normalize_country_code(row.get("iso"))
    }
    combined = []
    for row in fra_rows:
        iso = normalize_country_code(row.get("iso"))
        match = legal.get(iso)
        if (
            not match
            or not isinstance(row.get("value"), (int, float))
            or not isinstance(match.get("value"), (int, float))
        ):
            continue
        combined.append(
            {
                "country": row.get("country") or match.get("country"),
                "iso": iso,
                "fra_value": float(row["value"]),
                "ilga_value": float(match["value"]),
            }
        )
    return combined


def _table_rows(
    result: dict[str, Any],
    selected: list[str] | None = None,
    language: str = "es",
) -> list[dict[str, Any]]:
    rows = list(result.get("ranking") or [])
    selected_codes = _normalize_selected_countries(selected)
    if selected_codes:
        order = {code: index for index, code in enumerate(selected_codes)}
        rows = [row for row in rows if normalize_country_code(row.get("iso")) in order]
        rows.sort(
            key=lambda row: order.get(
                normalize_country_code(row.get("iso")),
                len(order),
            )
        )

    indicator = _table_indicator_label(result)
    available = "Available" if language == "en" else "Disponible"
    unavailable = "No data" if language == "en" else "Sin datos"
    return [
        {
            "country": row.get("country"),
            "country_code": normalize_country_code(row.get("iso"), row.get("country")),
            "response": str(result.get("answer") or ""),
            "value": _rounded_number(row.get("value")),
            "ranking": row.get("position"),
            "difference": _rounded_number(row.get("difference")),
            "difference_percentage": _rounded_number(row.get("percentage_difference")),
            "year": result.get("year"),
            "source": str(result.get("source") or ""),
            "indicator": indicator,
            "status": available if row.get("value") is not None else unavailable,
        }
        for row in rows
    ]


def _table_indicator_label(result: dict[str, Any]) -> str:
    indicator = str(result.get("indicator") or result.get("category") or "")
    answer = str(result.get("answer") or "").strip()
    return f"{indicator} \u00b7 {answer}" if answer else indicator


def _table_columns(
    rows: list[dict[str, Any]],
    language: str = "es",
) -> list[dict[str, Any]]:
    labels = {
        "country": ("País", "Country"),
        "value": ("Valor (%)", "Value (%)"),
        "ranking": ("Posición en Europa", "European rank"),
        "difference": ("Diferencia con la media (pp)", "Difference from average (pp)"),
        "difference_percentage": ("Diferencia porcentual (%)", "Percentage difference (%)"),
        "year": ("Año", "Year"),
        "indicator": ("Indicador", "Indicator"),
        "status": ("Estado", "Status"),
    }
    labels.update(
        {
            "country_code": ("C\u00f3digo del pa\u00eds", "Country code"),
            "response": ("Respuesta", "Answer"),
            "source": ("Fuente", "Source"),
        }
    )
    numeric = {
        "value",
        "ranking",
        "difference",
        "difference_percentage",
        "year",
    }
    return (
        [
            {
                "headerName": labels.get(key, (key, key))[1 if language == "en" else 0],
                "field": key,
                "type": "numericColumn" if key in numeric else None,
            }
            for key in rows[0]
        ]
        if rows
        else []
    )


def _methodology_text(language: str = "es") -> str:
    if language == "en":
        return (
            "FRA reflects responses from surveyed people. "
            "The ILGA score measures laws and policies. "
            "The sources are not directly equivalent."
        )
    return (
        "FRA refleja respuestas de personas encuestadas. "
        "La puntuación ILGA mide leyes y políticas. "
        "Las fuentes no son directamente equivalentes."
    )


def _selection_scope(
    ranking: list[dict[str, Any]],
    selected: list[str],
    language: str = "es",
) -> dict[str, Any]:
    if not selected:
        return {
            "kind": "all",
            "title": "Europe" if language == "en" else "Europa",
            "names": [],
        }
    names = _selected_country_names(ranking, selected)
    if len(names) == 1:
        return {"kind": "one", "title": names[0], "names": names}
    suffix = "selected countries" if language == "en" else "países seleccionados"
    return {
        "kind": "compare",
        "title": f"{len(names)} {suffix}",
        "names": names,
    }


def _selected_country_names(ranking: list[dict[str, Any]], selected: list[str]) -> list[str]:
    names = {
        normalize_country_code(row.get("iso")): str(row.get("country") or row.get("iso") or "")
        for row in ranking
    }
    return [names.get(normalize_country_code(country), country) for country in selected]


def _normalize_selected_countries(countries: list[str] | str | None) -> list[str]:
    values = countries if isinstance(countries, list) else [countries] if countries else []
    result: list[str] = []
    for value in values:
        clean = normalize_country_code(value) or str(value or "").strip()
        if clean and clean not in result:
            result.append(clean)
    return result


def _next_country_selection(
    triggered_id: str | None,
    *,
    click_data: dict[str, Any] | None,
    data: dict[str, Any] | None,
    current: list[str] | None,
) -> list[str] | Any:
    """Resolve map selection without coupling the state transition to Dash context."""
    selected = _normalize_selected_countries(current)
    if triggered_id in {"stats-clear-countries", "stats-survey-select"}:
        return []
    if triggered_id == "stats-data-store":
        available = set(
            _normalize_selected_countries((data or {}).get("available_countries") or [])
        )
        return [country for country in selected if not available or country in available]
    if triggered_id != "stats-map-graph":
        return no_update
    points = (click_data or {}).get("points") or []
    if not points:
        return no_update
    customdata = points[0].get("customdata")
    iso = customdata[0] if isinstance(customdata, (list, tuple)) and customdata else customdata
    iso = normalize_country_code(iso)
    if not iso:
        return no_update
    if iso in selected:
        return [country for country in selected if country != iso]
    return [*selected, iso]


def _effective_query_mode(_mode: str | None, selected_countries: list[str]) -> str:
    return "compare" if len(selected_countries) > 1 else "one" if selected_countries else "all"


def _has_valid_fra_selection(category: str | None, question_code: str | None) -> bool:
    return bool(str(category or "").strip() and str(question_code or "").strip())


def _fra_controls_are_ready(
    category: str | None,
    question_code: str | None,
    payload: dict[str, Any] | None,
    *values: Any,
) -> bool:
    controls = payload or {}
    return (
        str(controls.get("code") or "") == str(question_code or "")
        and str(controls.get("category") or "") == str(category or "")
        and all(value is not None for value in values)
    )


def _empty_data_result(message: str) -> dict[str, Any]:
    return {
        "status": "empty",
        "message": message,
        "data": [],
        "ranking": [],
        "available_countries": [],
    }


def _error_data_result() -> dict[str, Any]:
    return {
        "status": "error",
        "message": "No se han podido cargar las estadísticas.",
        "ranking": [],
        "available_countries": [],
    }


def _browser_statistics_payload(result: dict[str, Any]) -> dict[str, Any]:
    """Remove server-only intermediates before serializing data into ``dcc.Store``."""
    payload = dict(result)
    payload.pop("metrics", None)
    payload.pop("response_details_diagnostics", None)
    if payload.get("source") == "FRA" and "detail_data" in payload:
        payload.pop("data", None)
    return payload


def _result_with_query_token(result: dict[str, Any], query_token: str) -> dict[str, Any]:
    payload = dict(result)
    payload["query_token"] = query_token
    return payload


def _statistics_query_token(*values: Any) -> str:
    return json.dumps(values, ensure_ascii=False, separators=(",", ":"), default=str)


def _statistics_query_state(result: dict[str, Any] | None) -> str:
    return resolve_statistics_view_state(result).value


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except TypeError, ValueError:
        return None


def _rounded_number(value: Any) -> float | None:
    try:
        numeric = float(value)
    except TypeError, ValueError:
        return None
    return round(numeric, 2) if pd.notna(numeric) else None


def _fra_indicator_option_label(indicator: Any) -> str:
    return str(
        getattr(indicator, "question", "")
        or getattr(indicator, "label", "")
        or getattr(indicator, "code", "")
    )


def _plural(value: Any, singular: str, plural: str) -> str:
    try:
        return singular if float(value or 0) == 1 else plural
    except TypeError, ValueError:
        return plural
