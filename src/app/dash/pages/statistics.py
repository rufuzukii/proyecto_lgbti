from __future__ import annotations

import logging
import time
from typing import Any
from urllib.parse import urlencode

import dash_ag_grid as dag
import pandas as pd
from dash import ALL, Dash, Input, Output, Patch, State, ctx, dcc, html, no_update
from dash.development.base_component import Component
from dash.exceptions import PreventUpdate
from flask_login import current_user

from app.analytics.repository import (
    assert_analytics_databases_available,
    get_fra_categories,
    get_fra_mongo_indicators_by_category,
    get_fra_years,
    get_ilga_criteria_by_year,
    get_ilga_criteria_categories_by_year,
    get_ilga_document_by_year,
    get_ilga_years,
)
from app.analytics.statistics.ranking import paginate_ranking
from app.analytics.statistics_charts import (
    build_combined_heatmap,
    build_combined_scatter,
    build_comparative_ranking_chart,
    build_eu_average_comparison_chart,
    build_europe_choropleth,
    build_europe_distribution_chart,
    build_experience_legal_radar,
    build_fra_response_comparison_chart,
    build_ilga_response_details_chart,
    build_legal_reality_gap_chart,
    build_response_country_comparison_chart,
    build_temporal_evolution_chart,
    empty_figure,
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
    ExperienceLegalRadarQuery,
    FraStatisticsQuery,
    IlgaStatisticsQuery,
    StatisticsFilters,
    validate_statistics_filter_combination,
)
from app.analytics.statistics_normalizers import (
    normalize_country_code,
    normalize_filter_value,
    normalize_text_key,
)
from app.analytics.statistics_service import (
    get_experience_legal_radar,
    get_fra_control_payload,
    get_fra_statistics,
    get_ilga_statistics,
)
from app.dash.components.dropdown_options import (
    build_dropdown_options,
    option_value_or_none,
)
from app.dash.components.empty_state import build_empty_state
from app.dash.components.ilga_methodology import (
    build_ilga_normalization_note,
    build_ilga_series_normalization_note,
)
from app.dash.components.loading import contextual_loading
from app.dash.components.source_attribution import build_source_attribution
from app.dash.graph_config import fixed_europe_map_config
from app.dash.i18n import attribute_attrs, country_labels, dash_attrs, text, text_attrs, ui_text
from app.dash.layouts.navigation import build_navbar
from app.dash.routes import route_path
from app.dash.statistics_state import StatisticsViewState, resolve_statistics_view_state
from app.taxonomy import taxonomy_label, taxonomy_pair

logger = logging.getLogger(__name__)

DATA_TYPE_OPTIONS = [
    {
        "label": html.Span(label_es, **text_attrs(label_es, label_en)),
        "value": value,
    }
    for value in ("fra", "ilga")
    for label_es, label_en in [taxonomy_pair("data_type", value)]
]

EXCLUDED_CATEGORY_KEYS = {
    normalize_text_key("Political Participation"),
    normalize_text_key("Spanish LGBTI+ indicators"),
    normalize_text_key("Spanish LGBTIQ+ indicators"),
}

LABELS_EN = {
    "Tipo de datos": "Data type",
    "Indicador": "Indicator",
    "Pregunta o indicador": "Question or indicator",
    "Respuesta": "Answer",
    "Criterio jurídico": "Legal criterion",
    "Segmentación sociodemográfica": "Sociodemographic segmentation",
    "Valores del filtro activo": "Active filter values",
}

CHART_EXPORT_TITLES = {
    "map": ("Mapa de Europa", "Map of Europe"),
    "temporal": ("Evolución temporal", "Temporal evolution"),
    "ranking": ("Ranking comparativo", "Comparative ranking"),
    "distribution": ("Distribución europea", "European distribution"),
    "average": ("Comparación con la media de la UE", "EU average comparison"),
    "response_comparison": ("Comparación de respuestas", "Response comparison"),
    "experience_legal_radar": (
        "Experiencia real y protección legal",
        "Real-life experience and legal protection",
    ),
    "responses": ("Detalles de respuestas", "Response details"),
    "gap": ("Protección legal vs experiencia real", "Legal protection vs lived experience"),
    "scatter": (
        "Relaci\u00f3n entre protecci\u00f3n legal y experiencia reportada",
        "Legal protection and reported experience relationship",
    ),
    "heatmap": ("Heatmap europeo", "European heatmap"),
}


def build_statistics_layout() -> Component:
    assert_analytics_databases_available()
    years: list[dict[str, Any]] = []
    initial_year = None
    categories: list[dict[str, Any]] = []
    placeholder: dict[str, Any] = {}
    return html.Div(
        [
            build_navbar(active="statistics"),
            dcc.Store(id="stats-fra-control-store", storage_type="memory"),
            dcc.Store(id="stats-ranking-page", data=0, storage_type="memory"),
            dcc.Store(id="stats-selected-countries", data=[], storage_type="session"),
            dcc.Download(id="stats-summary-table-download"),
            html.Main(
                [
                    _header(),
                    _controls(years, initial_year, categories),
                    html.Div(
                        contextual_loading(
                            [
                                dcc.Store(id="stats-data-store", storage_type="memory"),
                                html.Div(
                                    build_empty_state(
                                        ui_text("statistics_initial_prompt", "es"),
                                        class_name="stats-query-state-card",
                                    ),
                                    id="stats-query-state",
                                    className="stats-query-state",
                                ),
                                html.Div(
                                    [
                                        html.Div(
                                            id="stats-status-message",
                                            className="stats-status stats-status-warning",
                                        ),
                                        _map_panel(placeholder),
                                        _block_header(
                                            "Bloque A",
                                            "Estadísticas del conjunto de datos seleccionado",
                                            "Selected dataset statistics",
                                        ),
                                        html.Section(
                                            id="stats-metric-row",
                                            className="stats-metric-row stats-executive-grid",
                                        ),
                                        html.Section(
                                            [
                                                html.Div(
                                                    _temporal_panel(placeholder),
                                                    id="stats-temporal-panel",
                                                    className=(
                                                        "stats-panel-wrapper stats-temporal-wrapper is-hidden"
                                                    ),
                                                ),
                                                _graph_panel(
                                                    "Ranking comparativo",
                                                    "Comparative ranking",
                                                    "stats-ranking-graph",
                                                    placeholder,
                                                    panel_id="stats-ranking-panel",
                                                    panel_class_name=(
                                                        "stats-panel stats-panel-wide stats-ranking-panel"
                                                    ),
                                                    footer=_ranking_pagination_controls(),
                                                ),
                                                _graph_panel(
                                                    "Distribución europea",
                                                    "European distribution",
                                                    "stats-distribution-graph",
                                                    placeholder,
                                                ),
                                                _graph_panel(
                                                    "Comparación con la media de la UE",
                                                    "EU average comparison",
                                                    "stats-average-graph",
                                                    placeholder,
                                                ),
                                                html.Div(
                                                    [
                                                        _chart_panel_heading(
                                                            "Comparación de respuestas",
                                                            "Response comparison",
                                                            "stats-response-comparison-graph",
                                                        ),
                                                        html.Div(
                                                            dcc.Graph(
                                                                id="stats-response-comparison-graph",
                                                                figure=placeholder,
                                                                responsive=True,
                                                                config=chart_graph_config(),
                                                                className="stats-chart-graph",
                                                                style={"width": "100%"},
                                                            ),
                                                            className="stats-response-comparison-scroll",
                                                        ),
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
                                                            "Experiencia real y protección legal",
                                                            "Real-life experience and legal protection",
                                                            "stats-experience-legal-radar-graph",
                                                        ),
                                                        _field(
                                                            (
                                                                "País seleccionado",
                                                                "Selected country",
                                                            ),
                                                            dcc.Dropdown(
                                                                id="stats-experience-legal-country-select",
                                                                options=[],
                                                                value=None,
                                                                clearable=False,
                                                            ),
                                                            class_name="stats-control-field stats-radar-country-field",
                                                        ),
                                                        html.P(
                                                            id="stats-experience-legal-metadata",
                                                            className="stats-radar-metadata",
                                                        ),
                                                        html.Div(
                                                            dcc.Graph(
                                                                id="stats-experience-legal-radar-graph",
                                                                figure=placeholder,
                                                                responsive=True,
                                                                config=chart_graph_config(),
                                                                className="stats-chart-graph",
                                                                style={
                                                                    "width": "100%",
                                                                    "height": "650px",
                                                                },
                                                            ),
                                                            id="stats-experience-legal-radar-wrapper",
                                                            className="is-hidden",
                                                        ),
                                                        html.P(
                                                            id="stats-experience-legal-empty",
                                                            className="stats-radar-empty",
                                                        ),
                                                        html.P(
                                                            id="stats-experience-legal-interpretation",
                                                            className="stats-radar-interpretation",
                                                        ),
                                                        _combined_source_attribution(
                                                            "experience-legal-radar"
                                                        ),
                                                    ],
                                                    id="stats-experience-legal-radar-panel",
                                                    className=(
                                                        "stats-panel stats-panel-wide "
                                                        "stats-experience-legal-radar-section"
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
                                                            dcc.Graph(
                                                                id="stats-response-detail-graph",
                                                                figure=placeholder,
                                                                responsive=True,
                                                                config=chart_graph_config(),
                                                                style=_response_detail_graph_style(
                                                                    placeholder
                                                                ),
                                                            ),
                                                            className="stats-response-detail-scroll",
                                                        ),
                                                        _dynamic_source_attribution(
                                                            "response-detail"
                                                        ),
                                                    ],
                                                    id="stats-response-panel",
                                                    className="stats-panel stats-panel-wide stats-response-panel",
                                                ),
                                            ],
                                            className="stats-grid",
                                        ),
                                        html.Section(
                                            [
                                                _block_header(
                                                    "Bloque B",
                                                    "Relación entre datos sociodemográficos y legales",
                                                    "Sociodemographic and legal relationship",
                                                ),
                                                html.Section(
                                                    id="stats-combined-metric-row",
                                                    className="stats-metric-row stats-executive-grid",
                                                ),
                                                html.Div(
                                                    [
                                                        _graph_panel(
                                                            "Protección legal vs experiencia real",
                                                            "Legal protection vs lived experience",
                                                            "stats-gap-graph",
                                                            placeholder,
                                                            combined_sources=True,
                                                        ),
                                                        _graph_panel(
                                                            "Relaci\u00f3n entre protecci\u00f3n legal y experiencia reportada",
                                                            "Legal protection and reported experience relationship",
                                                            "stats-scatter-graph",
                                                            placeholder,
                                                            combined_sources=True,
                                                        ),
                                                        _graph_panel(
                                                            "Heatmap europeo",
                                                            "European heatmap",
                                                            "stats-combined-heatmap",
                                                            placeholder,
                                                            panel_class_name=(
                                                                "stats-panel stats-panel-wide "
                                                                "stats-heatmap-panel"
                                                            ),
                                                            scrollable=True,
                                                            combined_sources=True,
                                                        ),
                                                    ],
                                                    className="stats-grid",
                                                ),
                                            ],
                                            id="stats-combined-block",
                                            className="stats-analytics-block is-hidden",
                                        ),
                                        html.Div(
                                            [
                                                html.Div(
                                                    [
                                                        html.H2(
                                                            text("Tabla resumida", "Summary table")
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
                                        html.P(
                                            id="stats-methodology",
                                            className="stats-methodology-note",
                                        ),
                                    ],
                                    id="stats-results-content",
                                    className="stats-results-content is-hidden",
                                ),
                            ],
                            "loading_statistics",
                            element_id="stats-dashboard-loading",
                            message_id="stats-loading-message",
                            target_components={
                                "stats-data-store": "data",
                                "stats-map-graph": "figure",
                            },
                            hide_content_while_loading=True,
                        ),
                        id="stats-dashboard-region",
                        className="stats-dashboard-region",
                        role="region",
                        **dash_attrs({"aria-live": "polite"}),
                    ),
                ],
                className="stats-shell app-page-container",
            ),
        ]
    )


def register_statistics_callbacks(app: Dash) -> None:
    @app.callback(
        Output("stats-query-state", "children"),
        Output("stats-query-state", "className"),
        Output("stats-results-content", "className"),
        Input("stats-data-store", "data"),
        Input("app-language-store", "data"),
    )
    def update_statistics_query_state(
        result: dict[str, Any] | None,
        language: str | None,
    ) -> tuple[Component, str, str]:
        clean_language = "en" if language == "en" else "es"
        query_state = resolve_statistics_view_state(result)
        if query_state is StatisticsViewState.READY:
            return (
                build_empty_state(
                    ui_text("statistics_initial_prompt", clean_language),
                    class_name="stats-query-state-card",
                ),
                "stats-query-state is-hidden",
                "stats-results-content",
            )
        if query_state is StatisticsViewState.ERROR:
            message_key = "statistics_error"
        elif query_state is StatisticsViewState.NO_DATA:
            message_key = "statistics_no_data"
        else:
            message_key = "statistics_initial_prompt"
        return (
            build_empty_state(
                ui_text(message_key, clean_language),
                class_name="stats-query-state-card",
            ),
            "stats-query-state",
            "stats-results-content is-hidden",
        )

    @app.callback(
        Output("stats-loading-message", "children"),
        Input("stats-category-select", "value"),
        Input("fra-indicator-select", "value"),
        Input("fra-answer-select", "value"),
        Input("fra-demographic-type", "value"),
        Input("fra-demographic-value", "value"),
        Input("fra-identity-type", "value"),
        Input("fra-identity-value", "value"),
        Input("ilga-criterion-select", "value"),
        Input("app-language-store", "data"),
        prevent_initial_call=True,
    )
    def update_statistics_loading_message(*values: Any) -> Component:
        triggered = ctx.triggered_id
        if triggered == "stats-category-select":
            message_key = "loading_indicators"
        elif triggered in {"fra-indicator-select", "ilga-criterion-select"}:
            message_key = "loading_statistics"
        else:
            message_key = "updating_visualisations"
        return text(ui_text(message_key, "es"), ui_text(message_key, "en"))

    @app.callback(
        Output({"type": "stats-source-attribution", "index": ALL}, "children"),
        Input("stats-source-select", "value"),
        Input("stats-year-select", "value"),
        Input("app-language-store", "data"),
        State({"type": "stats-source-attribution", "index": ALL}, "id"),
    )
    def update_statistics_attributions(
        source: str | None,
        year: int | None,
        language: str | None,
        targets: list[dict[str, str]] | None,
    ) -> list[Component]:
        source_key = "ilga" if source == "ilga" else "fra"
        return [
            build_source_attribution(
                source_key,
                year=year,
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
        payload = (result or {}).get("experience_legal_radar") or {}
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
        Output("stats-category-select", "placeholder"),
        Output("fra-indicator-select", "placeholder"),
        Output("ilga-criterion-select", "placeholder"),
        Input("app-language-store", "data"),
    )
    def translate_statistics_controls(language: str | None) -> tuple[str, str, str]:
        if language == "en":
            return (
                "Select a category",
                "Select a category first",
                "All criteria",
            )
        return (
            "Selecciona una categoría",
            "Selecciona primero una categoría",
            "Todos los criterios",
        )

    @app.callback(
        Output("stats-create-report-link", "href"),
        Input("stats-source-select", "value"),
        Input("stats-year-select", "value"),
        Input("stats-category-select", "value"),
        Input("fra-indicator-select", "value"),
        Input("fra-answer-select", "value"),
        Input("fra-demographic-type", "value"),
        Input("fra-demographic-value", "value"),
        Input("fra-identity-type", "value"),
        Input("fra-identity-value", "value"),
        Input("ilga-criterion-select", "value"),
        Input("stats-selected-countries", "data"),
        Input("app-language-store", "data"),
    )
    def update_create_report_link(
        source: str | None,
        year: int | None,
        category: str | None,
        indicator: str | None,
        answer: str | None,
        filter_a_name: str | None,
        filter_a_value: str | None,
        filter_b_name: str | None,
        filter_b_value: str | None,
        criterion: str | None,
        countries: list[str] | None,
        language: str | None,
    ) -> str:
        selected_countries = _normalize_selected_countries(countries)
        filters = _resolved_ui_filters(
            filter_a_name,
            filter_a_value,
            filter_b_name,
            filter_b_value,
        )
        params = {
            "source": source or "fra",
            "year": year,
            "category": category,
            "indicator_id": indicator,
            "answer": answer,
            **filters.as_query_fields(),
            "criterion": criterion,
            "countries": ",".join(selected_countries),
            "primary_country": selected_countries[0] if selected_countries else None,
            "language": "en" if language == "en" else "es",
            "mode": "automatic",
            "charts": "ranking,average,countries,responses,temporal,radar",
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
        Output("stats-year-select", "options"),
        Output("stats-year-select", "value"),
        Output("stats-fra-controls", "className"),
        Output("stats-ilga-controls", "className"),
        Output("stats-fra-segmentation-card", "className"),
        Output("stats-year-field", "className"),
        Input("stats-source-select", "value"),
    )
    def update_source_controls(source: str | None):
        years = _year_options(source)
        year = years[0]["value"] if years else None
        is_fra = source == "fra"
        year_class = "stats-control-field stats-year-field" + (
            " is-hidden" if is_fra and len(years) <= 1 else ""
        )
        return (
            years,
            year,
            "stats-source-controls" if is_fra else "stats-source-controls is-hidden",
            "stats-source-controls is-hidden" if is_fra else "stats-source-controls",
            _fra_segmentation_card_class(source),
            year_class,
        )

    @app.callback(
        Output("stats-ilga-normalization-note", "children"),
        Output("stats-ilga-normalization-note", "className"),
        Input("stats-source-select", "value"),
        Input("stats-year-select", "value"),
        Input("app-language-store", "data"),
    )
    def update_ilga_normalization_note(
        source: str | None,
        year: int | None,
        language: str | None,
    ):
        if source != "ilga" or year is None:
            return None, "stats-ilga-normalization-note is-hidden"
        document = get_ilga_document_by_year(year)
        normalization = document.get("normalization") if isinstance(document, dict) else None
        note = build_ilga_normalization_note(
            normalization,
            language="en" if language == "en" else "es",
            class_name="stats-ilga-normalization-callout",
        )
        if note is None:
            return None, "stats-ilga-normalization-note is-hidden"
        return note, "stats-ilga-normalization-note"

    @app.callback(
        Output("stats-temporal-normalization-note", "children"),
        Output("stats-temporal-normalization-note", "className"),
        Input("stats-data-store", "data"),
        Input("app-language-store", "data"),
    )
    def update_ilga_temporal_normalization_note(
        payload: dict[str, Any] | None,
        language: str | None,
    ):
        result = payload or {}
        if result.get("source") != "ILGA-Europe":
            return None, "stats-temporal-normalization-note is-hidden"
        note = build_ilga_series_normalization_note(
            result.get("history") or [],
            language="en" if language == "en" else "es",
            class_name="stats-temporal-normalization-callout",
        )
        if note is None:
            return None, "stats-temporal-normalization-note is-hidden"
        return note, "stats-temporal-normalization-note"

    @app.callback(
        Output("stats-category-select", "options"),
        Output("stats-category-select", "value"),
        Input("stats-source-select", "value"),
        Input("stats-year-select", "value"),
        Input("app-language-store", "data"),
        State("stats-category-select", "value"),
    )
    def update_categories_for_year(
        source: str | None,
        year: int | None,
        language: str | None,
        current: str | None,
    ):
        if not source or year is None:
            return [], None
        options = _category_options(source, year, language or "es")
        return options, _selected_category_value(
            source,
            options,
            current,
            reset_to_default=ctx.triggered_id == "stats-source-select",
        )

    @app.callback(
        Output("fra-indicator-select", "options"),
        Output("fra-indicator-select", "value"),
        Output("fra-indicator-select", "disabled"),
        Output("stats-data-store", "data", allow_duplicate=True),
        Input("stats-source-select", "value"),
        Input("stats-category-select", "value"),
        Input("stats-year-select", "value"),
        prevent_initial_call=True,
    )
    def update_fra_indicators(source: str | None, category: str | None, year: int | None):
        if source != "fra" or not category:
            return [], None, True, None
        options = build_dropdown_options(
            (
                {"label": _fra_indicator_option_label(indicator), "value": indicator.code}
                for indicator in get_fra_mongo_indicators_by_category(category, year)
            ),
            context="statistics-fra-indicator",
        )
        return options, None, not bool(options), None

    @app.callback(
        Output("fra-answer-select", "options"),
        Output("fra-answer-select", "value"),
        Output("fra-demographic-type", "options"),
        Output("fra-demographic-type", "value"),
        Output("stats-fra-control-store", "data"),
        Output("stats-fra-response-help", "children"),
        Output("stats-fra-response-help", "className"),
        Input("fra-indicator-select", "value"),
        Input("app-language-store", "data"),
        State("stats-category-select", "value"),
        State("stats-year-select", "value"),
    )
    def update_fra_controls(
        code: str | None,
        language: str | None,
        category: str | None,
        year: int | None,
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
            )
        payload = get_fra_control_payload(code, category, _safe_int(year))
        answers = _translated_taxonomy_options(
            payload.get("answers") or [],
            "fra_response",
            language or "es",
        )
        segmentations = _translated_segmentation_options(
            payload.get("segmentations") or [], language or "es"
        )
        demographic_options = _segmentation_catalog_options(
            FRA_FILTER_GROUP_A, segmentations, language or "es"
        )
        return (
            answers,
            answers[0]["value"] if answers else None,
            demographic_options,
            _default_option_value(demographic_options),
            payload,
            _fra_response_help(payload.get("response_type"), language or "es"),
            (
                "stats-response-help"
                if payload.get("response_type") == "ranked_reason"
                else "stats-response-help is-hidden"
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
        disabled = _is_active_filter_type(demographic_type)
        if disabled:
            options = [{**option, "disabled": True} for option in options]
            value = "All"
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
            return [{"label": "All", "value": "All", "disabled": True}], "All"
        options = build_dropdown_options(
            values.get(segmentation or "All") or [],
            context="statistics-fra-identity-value",
        )
        return options, _explicit_filter_value(segmentation, options, current)

    @app.callback(
        Output("ilga-criterion-select", "options"),
        Output("ilga-criterion-select", "value"),
        Output("ilga-criterion-select", "disabled"),
        Input("stats-source-select", "value"),
        Input("stats-year-select", "value"),
        Input("stats-category-select", "value"),
    )
    def update_ilga_criteria(source: str | None, year: int | None, category: str | None):
        return _ilga_criterion_control(source, year, category)

    @app.callback(
        Output("stats-data-store", "data"),
        Input("stats-source-select", "value"),
        Input("stats-year-select", "value"),
        Input("stats-category-select", "value"),
        Input("fra-indicator-select", "value"),
        Input("fra-answer-select", "value"),
        Input("fra-demographic-type", "value"),
        Input("fra-demographic-value", "value"),
        Input("fra-identity-type", "value"),
        Input("fra-identity-value", "value"),
        Input("ilga-criterion-select", "value"),
        State("stats-fra-control-store", "data"),
        prevent_initial_call=True,
    )
    def load_statistics_data(
        source: str | None,
        year: int | None,
        category: str | None,
        fra_code: str | None,
        answer: str | None,
        demographic_type: str | None,
        demographic_value: str | None,
        identity_type: str | None,
        identity_value: str | None,
        criterion: str | None,
        control_payload: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        query_started_at = time.perf_counter()
        if source == "fra":
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
                return None
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
                return _empty_data_result(filter_validation.message)
            query_started = time.perf_counter()
            try:
                result = get_fra_statistics(
                    FraStatisticsQuery(
                        year=_safe_int(year),
                        category=category,
                        question_code=fra_code,
                        answer=answer,
                        filter_a_name=filters.demographic_type,
                        filter_a_value=filters.demographic_value,
                        filter_b_name=filters.identity_type,
                        filter_b_value=filters.identity_value,
                    )
                )
                query_ms = (time.perf_counter() - query_started) * 1000
                enrichment_started = time.perf_counter()
                if result.get("status") == "ok":
                    legal = get_ilga_statistics(
                        IlgaStatisticsQuery(category="Ranking total"),
                        include_history=False,
                    )
                    result["combined"] = _combine_rankings(
                        result.get("ranking") or [], legal.get("ranking") or []
                    )
                    result["experience_legal_radar"] = get_experience_legal_radar(
                        ExperienceLegalRadarQuery(
                            fra_year=_safe_int(year),
                            filter_a_name=filters.demographic_type,
                            filter_a_value=filters.demographic_value,
                            filter_b_name=filters.identity_type,
                            filter_b_value=filters.identity_value,
                        )
                    )
                enrichment_ms = (time.perf_counter() - enrichment_started) * 1000
            except Exception:
                logger.exception("statistics_query_failed source=fra indicator=%s", fra_code)
                return _error_data_result()
            logger.info(
                "statistics_query_completed source=fra status=%s query_ms=%.2f "
                "enrichment_ms=%.2f total_ms=%.2f",
                result.get("status"),
                query_ms,
                enrichment_ms,
                (time.perf_counter() - query_started_at) * 1000,
            )
            return _browser_statistics_payload(result)
        if not category:
            return None
        try:
            result = get_ilga_statistics(
                IlgaStatisticsQuery(year=_safe_int(year), category=category, criterion=criterion)
            )
            if result.get("status") == "ok":
                result["experience_legal_radar"] = get_experience_legal_radar(
                    ExperienceLegalRadarQuery(ilga_year=_safe_int(year))
                )
        except Exception:
            logger.exception("statistics_query_failed source=ilga category=%s", category)
            return _error_data_result()
        logger.info(
            "statistics_query_completed source=ilga status=%s total_ms=%.2f",
            result.get("status"),
            (time.perf_counter() - query_started_at) * 1000,
        )
        return _browser_statistics_payload(result)

    @app.callback(
        Output("stats-selected-countries", "data"),
        Input("stats-map-graph", "clickData"),
        Input("stats-clear-countries", "n_clicks"),
        Input("stats-data-store", "data"),
        State("stats-selected-countries", "data"),
        prevent_initial_call=True,
    )
    def update_country_selection(
        click_data: dict[str, Any] | None,
        _clear_clicks: int | None,
        data: dict[str, Any] | None,
        current: list[str] | None,
    ) -> list[str] | Any:
        selected = _normalize_selected_countries(current)
        if ctx.triggered_id == "stats-clear-countries":
            return []
        if ctx.triggered_id == "stats-data-store":
            available = set((data or {}).get("available_countries") or [])
            return [country for country in selected if not available or country in available]
        points = (click_data or {}).get("points") or []
        if not points:
            return no_update
        customdata = points[0].get("customdata")
        iso = customdata[0] if isinstance(customdata, (list, tuple)) and customdata else customdata
        iso = normalize_country_code(iso)
        if not iso:
            return no_update
        return (
            [country for country in selected if country != iso]
            if iso in selected
            else [*selected, iso]
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
        Output("stats-clear-countries", "disabled"),
        Output("stats-metric-row", "children"),
        Output("stats-temporal-graph", "figure"),
        Output("stats-temporal-panel", "className"),
        Output("stats-ranking-graph", "figure"),
        Output("stats-distribution-graph", "figure"),
        Output("stats-average-graph", "figure"),
        Output("stats-response-comparison-graph", "figure"),
        Output("stats-response-comparison-panel", "className"),
        Output("stats-detail-summary", "children"),
        Output("stats-response-detail-graph", "figure"),
        Output("stats-response-detail-graph", "style"),
        Output("stats-response-panel", "className"),
        Output("stats-combined-metric-row", "children"),
        Output("stats-gap-graph", "figure"),
        Output("stats-scatter-graph", "figure"),
        Output("stats-combined-heatmap", "figure"),
        Output("stats-combined-block", "className"),
        Output("stats-results-table", "columnDefs"),
        Output("stats-results-table", "rowData"),
        Output("stats-methodology", "children"),
        Output("stats-ranking-graph", "style"),
        Output("stats-response-comparison-graph", "style"),
        Output("stats-table-download-button", "disabled"),
        Output("stats-table-export-status", "children"),
        Output("stats-table-export-status", "className"),
        Input("stats-data-store", "data"),
        Input("stats-selected-countries", "data"),
        Input("stats-temporal-country-select", "value"),
        Input("app-language-store", "data"),
        Input("stats-ranking-page", "data"),
        State("stats-map-graph", "figure"),
        prevent_initial_call=True,
    )
    def render_statistics(
        result: dict[str, Any] | None,
        countries: list[str] | None,
        temporal_countries: list[str] | None,
        language: str | None,
        ranking_page: int | None,
        current_map: dict[str, Any] | None,
    ):
        if not result or result.get("status") != "ok":
            raise PreventUpdate
        selected = _normalize_selected_countries(countries)
        language = language or "es"
        if ctx.triggered_id == "stats-temporal-country-select":
            return _render_temporal_dashboard_update(
                result,
                selected,
                language,
                _normalize_selected_countries(temporal_countries),
            )
        if ctx.triggered_id == "stats-ranking-page":
            return _render_ranking_dashboard_update(
                result,
                selected,
                language,
                ranking_page,
            )
        dashboard = _render_dashboard(
            result,
            selected,
            language,
            temporal_countries=_normalize_selected_countries(temporal_countries),
            ranking_page=ranking_page,
        )
        if ctx.triggered_id == "stats-selected-countries":
            dashboard = list(dashboard)
            dashboard[2] = _map_selection_patch(dashboard[2])
            return tuple(dashboard)
        if _map_contains_static_geojson(current_map):
            dashboard = list(dashboard)
            dashboard[2] = _map_data_patch(dashboard[2])
            return tuple(dashboard)
        return dashboard

    @app.callback(
        Output("stats-experience-legal-country-select", "options"),
        Output("stats-experience-legal-country-select", "value"),
        Input("stats-data-store", "data"),
        Input("stats-selected-countries", "data"),
        Input("app-language-store", "data"),
        State("stats-experience-legal-country-select", "value"),
    )
    def update_experience_legal_country(
        result: dict[str, Any] | None,
        selected_countries: list[str] | None,
        language: str | None,
        current_country: str | None,
    ) -> tuple[list[dict[str, str]], str | None]:
        options = _radar_country_options(
            (result or {}).get("experience_legal_radar") or {}, language or "es"
        )
        available = {option["value"] for option in options}
        selected = [
            country
            for country in _normalize_selected_countries(selected_countries)
            if country in available
        ]
        if selected:
            value = selected[0]
        elif current_country in available:
            value = current_country
        else:
            value = options[0]["value"] if options else None
        return options, value

    @app.callback(
        Output("stats-experience-legal-radar-graph", "figure"),
        Output("stats-experience-legal-radar-wrapper", "className"),
        Output("stats-experience-legal-empty", "children"),
        Output("stats-experience-legal-metadata", "children"),
        Output("stats-experience-legal-interpretation", "children"),
        Input("stats-data-store", "data"),
        Input("stats-experience-legal-country-select", "value"),
        Input("app-language-store", "data"),
    )
    def render_experience_legal_radar(
        result: dict[str, Any] | None,
        country_iso: str | None,
        language: str | None,
    ) -> tuple[Any, str, str, str, str]:
        language = language or "es"
        payload = (result or {}).get("experience_legal_radar") or {}
        figure, compatible, metadata, interpretation = build_experience_legal_radar(
            payload, country_iso, language
        )
        if not compatible:
            return figure, "is-hidden", interpretation, "", ""
        country_name = next(
            (
                option["label"]
                for option in _radar_country_options(payload, language)
                if option["value"] == country_iso
            ),
            str(country_iso or ""),
        )
        prepare_figure_for_export(
            figure,
            chart_type="experience-legal-radar",
            chart_title=(
                "Real-life experience and legal protection"
                if language == "en"
                else "Experiencia real y protección legal"
            ),
            indicator=metadata,
            countries=[country_name],
            year=None,
            source="FRA + ILGA-Europe",
            filters=_export_filter_labels(result or {}, language),
            language=language,
        )
        return figure, "", "", metadata, interpretation


def _controls(
    years: list[dict[str, Any]],
    initial_year: int | None,
    categories: list[dict[str, Any]],
) -> Component:
    return html.Section(
        [
            _control_group(
                "Tipo de datos",
                [
                    _field(
                        "Tipo de datos",
                        dcc.RadioItems(
                            id="stats-source-select",
                            options=DATA_TYPE_OPTIONS,
                            value="fra",
                            className="stats-segmented-control stats-data-type-control",
                            inputClassName="stats-segmented-input",
                            labelClassName="stats-segmented-label",
                        ),
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
                    _field(
                        ("Año", "Year"),
                        dcc.Dropdown(
                            id="stats-year-select",
                            options=years,
                            value=initial_year,
                            clearable=False,
                        ),
                        element_id="stats-year-field",
                        class_name="stats-control-field stats-year-field",
                    ),
                    html.Div(
                        id="stats-ilga-normalization-note",
                        className="stats-ilga-normalization-note is-hidden",
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
                                    id="fra-answer-select", options=[], value=None, clearable=False
                                ),
                            ),
                            html.Aside(
                                id="stats-fra-response-help",
                                className="stats-response-help is-hidden",
                                **dash_attrs({"aria-live": "polite"}),
                            ),
                        ],
                        id="stats-fra-controls",
                        className="stats-source-controls",
                    ),
                    html.Div(
                        [
                            _field(
                                "Criterio jurídico",
                                dcc.Dropdown(
                                    id="ilga-criterion-select",
                                    options=[],
                                    value=None,
                                    disabled=True,
                                    placeholder="Todos los criterios",
                                ),
                            )
                        ],
                        id="stats-ilga-controls",
                        className="stats-source-controls is-hidden",
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
                class_name=_fra_segmentation_card_class("fra"),
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
    is_group = component.__class__.__name__ in {"RadioItems", "Checklist"}
    props: dict[str, Any] = {"className": class_name}
    if element_id:
        props["id"] = element_id
    if is_group and control_id:
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


def _fra_segmentation_card_class(source: str | None) -> str:
    classes = [
        "stats-filter-card",
        "stats-filter-card-wide",
        "stats-fra-only",
        "stats-segmentation-card",
    ]
    if source != "fra":
        classes.append("is-hidden")
    return " ".join(classes)


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
    return html.Header(
        [
            html.P(
                "Panel de Estadísticas",
                className="stats-eyebrow",
                **text_attrs("Panel de Estadísticas", "Statistics panel"),
            ),
            html.H1(text("Estadísticas europeas LGBTIQ+", "European LGBTIQ+ statistics")),
            html.P(
                text(
                    "Explora la realidad sociodemográfica, la protección legal y la relación entre ambas.",
                    "Explore lived experience, legal protection and the relationship between them.",
                ),
                className="stats-lead",
            ),
            dcc.Link(
                text(
                    "Crear informe con esta selección",
                    "Create report from this selection",
                ),
                id="stats-create-report-link",
                href=route_path("reports"),
                className="stats-create-report-link",
            ),
        ],
        className="stats-header",
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


def _map_panel(placeholder: Any) -> Component:
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
            dcc.Graph(
                id="stats-map-graph",
                figure=placeholder,
                responsive=True,
                config=fixed_europe_map_config(extra_mode_bar_buttons_to_remove=("toImage",)),
                className="stats-mapbox-graph",
                style={"width": "100%"},
            ),
            _dynamic_source_attribution("map"),
        ],
        className="stats-panel stats-panel-wide stats-map-panel",
    )


def _temporal_panel(placeholder: Any) -> Component:
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
                id="stats-temporal-normalization-note",
                className="stats-temporal-normalization-note is-hidden",
            ),
            html.Div(
                dcc.Graph(
                    id="stats-temporal-graph",
                    figure=placeholder,
                    responsive=True,
                    config=chart_graph_config(),
                    className="stats-chart-graph",
                    style={"width": "100%", "minWidth": "860px", "height": "680px"},
                ),
                className="stats-temporal-chart-scroll",
            ),
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
    graph = dcc.Graph(
        id=graph_id,
        figure=figure,
        responsive=True,
        config=chart_graph_config(),
        className="stats-chart-graph",
        style={"width": "100%"},
    )
    graph_content: Component = (
        html.Div(graph, className="stats-chart-horizontal-scroll") if scrollable else graph
    )
    return html.Div(
        [
            _chart_panel_heading(title_es, title_en, graph_id),
            graph_content,
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


def _response_detail_graph_style(figure: Any) -> dict[str, str]:
    style = _dynamic_graph_style(figure, min_height=520)
    meta = getattr(getattr(figure, "layout", None), "meta", None)
    minimum_width = meta.get("minimum_width") if isinstance(meta, dict) else None
    if isinstance(minimum_width, (int, float)) and minimum_width > 760:
        style["minWidth"] = f"{int(minimum_width)}px"
    return style


def _ranking_graph_style(figure: Any) -> dict[str, str]:
    return _dynamic_graph_style(figure, min_height=500)


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
                title="Descargar PNG / Download PNG",
                **dash_attrs(
                    {
                        "data-chart-export": "true",
                        "data-chart-export-target": graph_id,
                        "data-export-format": EXPORT_FORMAT,
                        "data-export-width": str(EXPORT_WIDTH),
                        "data-export-height": str(EXPORT_HEIGHT),
                        "data-export-scale": str(EXPORT_SCALE),
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


def _year_options(source: str | None) -> list[dict[str, Any]]:
    years = get_fra_years() if source == "fra" else get_ilga_years()
    return build_dropdown_options(
        ({"label": str(year), "value": year} for year in years),
        context="statistics-year",
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
        if not iso or iso == "EU27":
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
    source: str | None,
    year: int | None,
    language: str = "es",
) -> list[dict[str, Any]]:
    if source == "fra":
        return _visible_category_options(get_fra_categories(year), language)
    options: list[dict[str, Any]] = [
        {
            "label": taxonomy_pair("ilga_category", "Ranking total")[1 if language == "en" else 0],
            "value": "Ranking total",
        }
    ]
    options.extend(
        {
            "label": label_en if language == "en" else label_es,
            "value": category,
        }
        for category in _visible_categories(get_ilga_criteria_categories_by_year(year))
        for label_es, label_en in [taxonomy_pair("ilga_category", category)]
    )
    return build_dropdown_options(options, context="statistics-ilga-category")


def _selected_category_value(
    source: str | None,
    options: list[dict[str, Any]],
    current: str | None,
    *,
    reset_to_default: bool = False,
) -> str | None:
    selected = option_value_or_none(options, current)
    values = {item["value"] for item in options}
    if source == "ilga" and reset_to_default and "Ranking total" in values:
        return "Ranking total"
    if selected in values:
        return str(selected)
    if source == "ilga" and "Ranking total" in values:
        return "Ranking total"
    return None


def _ilga_criterion_control(
    source: str | None,
    year: int | None,
    category: str | None,
) -> tuple[list[dict[str, Any]], None, bool]:
    if source != "ilga" or not category or category == "Ranking total":
        return [], None, True
    options = build_dropdown_options(
        (
            {"label": item["indicator"], "value": item["indicator"]}
            for item in get_ilga_criteria_by_year(year, category)
            if item.get("indicator")
        ),
        context="statistics-ilga-criterion",
    )
    return options, None, not bool(options)


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
            className="stats-segmentation-row",
        )
    return html.Section(children, className="stats-segmentation-row")


def _map_selection_patch(figure: Any) -> Patch:
    """Update only selection markers so the static GeoJSON stays in the browser."""
    patch = Patch()
    marker_index = 1
    marker = figure.data[marker_index]
    patch["data"][marker_index]["lat"] = list(marker.lat or [])
    patch["data"][marker_index]["lon"] = list(marker.lon or [])
    patch["data"][marker_index]["text"] = list(marker.text or [])
    patch["data"][marker_index]["customdata"] = list(marker.customdata or [])
    return patch


def _map_data_patch(figure: Any) -> Patch:
    """Update map values and labels while retaining the browser's static geometry."""
    patch = Patch()
    choropleth = figure.data[0]
    for property_name in (
        "locations",
        "z",
        "text",
        "hovertext",
        "customdata",
        "colorscale",
        "zmin",
        "zmax",
        "colorbar",
        "hovertemplate",
    ):
        value = getattr(choropleth, property_name)
        patch["data"][0][property_name] = (
            value.to_plotly_json() if hasattr(value, "to_plotly_json") else value
        )
    marker = figure.data[1]
    for property_name in ("lat", "lon", "text", "customdata", "hovertemplate"):
        value = getattr(marker, property_name)
        if property_name in {"lat", "lon", "text", "customdata"}:
            value = list(value or [])
        patch["data"][1][property_name] = value
    patch["layout"]["annotations"] = [
        annotation.to_plotly_json() for annotation in figure.layout.annotations
    ]
    patch["layout"]["uirevision"] = figure.layout.uirevision
    return patch


def _map_contains_static_geojson(figure: dict[str, Any] | None) -> bool:
    data = (figure or {}).get("data") or []
    return bool(data and isinstance(data[0], dict) and data[0].get("geojson"))


def _render_temporal_dashboard_update(
    result: dict[str, Any],
    selected: list[str],
    language: str,
    temporal_countries: list[str],
) -> tuple[Any, ...]:
    started_at = time.perf_counter()
    if result.get("status") != "ok":
        return _render_dashboard(
            result,
            selected,
            language,
            temporal_countries=temporal_countries,
        )
    source = str(result.get("source") or "")
    temporal = build_temporal_evolution_chart(
        list(result.get("history") or []),
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
    outputs: list[Any] = [no_update] * 29
    outputs[5] = temporal
    outputs[6] = (
        "stats-panel-wrapper stats-temporal-wrapper"
        if source == "ILGA-Europe"
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
    if result.get("status") != "ok":
        return _render_dashboard(result, selected, language, ranking_page=ranking_page)
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
        focus_rows=visible_ranking,
    )
    _prepare_dashboard_exports(
        {"ranking": comparative_ranking, "average": average},
        result=result,
        selected_names=_selection_scope(ranking, selected, language)["names"],
        language=language,
    )
    outputs: list[Any] = [no_update] * 29
    outputs[7] = comparative_ranking
    outputs[9] = average
    outputs[24] = _ranking_graph_style(comparative_ranking)
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
    render_started_at = time.perf_counter()
    if result.get("status") != "ok":
        message = str(
            result.get("message") or "Selecciona un indicador para cargar los resultados."
        )
        empty = empty_figure(message)
        return (
            html.Div([html.Strong(text("Sin resultados", "No results")), html.P(message)]),
            "stats-status stats-status-warning",
            empty,
            not bool(selected),
            [],
            empty,
            "stats-panel-wrapper stats-temporal-wrapper is-hidden",
            empty,
            empty,
            empty,
            empty,
            "stats-panel stats-panel-wide stats-response-comparison-section is-hidden",
            "",
            empty,
            _response_detail_graph_style(empty),
            "stats-panel stats-panel-wide stats-response-panel is-hidden",
            [],
            empty,
            empty,
            empty,
            "stats-analytics-block is-hidden",
            [],
            [],
            "",
            _ranking_graph_style(empty),
            _response_comparison_graph_style(empty),
            True,
            ui_text("no_export_data", language),
            "stats-table-export-status",
        )

    source = str(result.get("source") or "")
    ranking = list(result.get("ranking") or [])
    data = list(result.get("data") or [])
    detail = list(result.get("detail_data") or data)
    history = list(result.get("history") or [])
    combined = list(result.get("combined") or [])
    normalization_started_at = time.perf_counter()
    response_dataframe = (
        prepare_fra_response_comparison_data(
            detail,
            list(result.get("country_universe") or []),
            language=language,
        )
        if source == "FRA"
        else None
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
    temporal = build_temporal_evolution_chart(
        history,
        selected,
        language,
        visible_countries=temporal_countries,
    )
    comparative_ranking = build_comparative_ranking_chart(
        visible_ranking,
        selected,
        language,
        indicator=str(result.get("indicator") or ""),
        year=result.get("year"),
    )
    distribution = build_europe_distribution_chart(ranking, selected, language)
    average = build_eu_average_comparison_chart(
        ranking,
        selected,
        language,
        focus_rows=visible_ranking,
    )
    comparison = (
        build_response_country_comparison_chart(
            detail,
            selected,
            language,
            indicator=str(result.get("indicator") or ""),
            year=result.get("year"),
            prepared_data=response_dataframe,
        )
        if source == "FRA"
        else empty_figure(
            "Las fuentes jurídicas no contienen distribuciones de respuestas."
            if language != "en"
            else "Legal sources do not contain response distributions."
        )
    )
    response = (
        build_fra_response_comparison_chart(
            detail,
            available_countries=list(result.get("country_universe") or []),
            selected_countries=selected,
            selected_response=str(result.get("answer") or "") or None,
            language=language,
            prepared_data=response_dataframe,
        )
        if source == "FRA"
        else build_ilga_response_details_chart(
            detail,
            selected,
            language=language,
            indicator=str(result.get("indicator") or ""),
            year=result.get("year"),
        )
    )
    gap = build_legal_reality_gap_chart(combined, selected, language)
    scatter = build_combined_scatter(combined, language, selected)
    heatmap = build_combined_heatmap(combined, language, selected)
    charts_ms = (time.perf_counter() - charts_started_at) * 1000
    _prepare_dashboard_exports(
        {
            "map": map_figure,
            "temporal": temporal,
            "ranking": comparative_ranking,
            "distribution": distribution,
            "average": average,
            "response_comparison": comparison,
            "responses": response,
            "gap": gap,
            "scatter": scatter,
            "heatmap": heatmap,
        },
        result=result,
        selected_names=scope["names"],
        language=language,
    )
    combined_metrics = _combined_metric_cards(combined)
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
        "chart_count=10",
        normalization_ms,
        map_ms,
        charts_ms,
        (time.perf_counter() - render_started_at) * 1000,
    )
    return (
        status,
        "stats-status stats-status-ok",
        map_figure,
        not bool(selected),
        _executive_metric_cards(ranking, selected, history),
        temporal,
        (
            "stats-panel-wrapper stats-temporal-wrapper"
            if source == "ILGA-Europe"
            else "stats-panel-wrapper stats-temporal-wrapper is-hidden"
        ),
        comparative_ranking,
        distribution,
        average,
        comparison,
        (
            "stats-panel stats-panel-wide stats-response-comparison-section"
            if source == "FRA"
            else "stats-panel stats-panel-wide stats-response-comparison-section is-hidden"
        ),
        _detail_summary(
            source,
            detail,
            language,
            available_countries=list(result.get("country_universe") or []),
            prepared_data=response_dataframe,
        ),
        response,
        _response_detail_graph_style(response),
        "stats-panel stats-panel-wide stats-response-panel",
        combined_metrics,
        gap,
        scatter,
        heatmap,
        "stats-analytics-block" if combined else "stats-analytics-block is-hidden",
        _table_columns(table_rows, language),
        table_rows,
        _methodology_text(result, source, language),
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
    for chart_type, figure in figures.items():
        title_es, title_en = CHART_EXPORT_TITLES[chart_type]
        prepare_figure_for_export(
            figure,
            chart_type=chart_type,
            chart_title=title_en if language == "en" else title_es,
            indicator=indicator,
            countries=[] if chart_type == "responses" else selected_names,
            year=year,
            source=("combined" if chart_type in {"gap", "scatter", "heatmap"} else source),
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
    metrics: list[tuple[str | tuple[str, str], str]] = [
        (("Países analizados", "Countries analysed"), str(len(dataframe))),
        (("Media europea", "European average"), f"{mean:.2f}%"),
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


def _combined_metric_cards(rows: list[dict[str, Any]]) -> list[Any]:
    dataframe = pd.DataFrame(rows)
    if dataframe.empty:
        return []
    dataframe["gap"] = (dataframe["ilga_value"] - dataframe["fra_value"]).abs()
    correlation = dataframe["ilga_value"].corr(dataframe["fra_value"])
    best = dataframe.nsmallest(1, "gap").iloc[0]
    largest = dataframe.nlargest(1, "gap").iloc[0]
    legal_mean = float(dataframe["ilga_value"].mean())
    fra_mean = float(dataframe["fra_value"].mean())
    gap_std = float(dataframe["gap"].std(ddof=0))
    return [
        _metric_card(
            ("Mejor equilibrio", "Best balance"), f"{best['country']} · {best['gap']:.2f} pp"
        ),
        _metric_card(
            ("Mayor diferencia", "Largest gap"), f"{largest['country']} · {largest['gap']:.2f} pp"
        ),
        _metric_card(
            ("Media europea", "European average"), f"ILGA {legal_mean:.1f}% · FRA {fra_mean:.1f}%"
        ),
        _metric_card(("Desviación de la brecha", "Gap standard deviation"), f"{gap_std:.2f} pp"),
        _metric_card(
            ("Correlación ILGA/FRA", "ILGA/FRA correlation"),
            f"{correlation:.2f}" if pd.notna(correlation) else "—",
        ),
        _metric_card(("Indicadores comparados", "Indicators compared"), "2"),
    ]


def _metric_card(label: str | tuple[str, str], value: str) -> Any:
    rendered_label = text(label[0], label[1]) if isinstance(label, tuple) else label
    return html.Div([html.Span(rendered_label), html.Strong(value)], className="stats-metric-card")


def _detail_summary(
    source: str,
    rows: list[dict[str, Any]],
    language: str = "es",
    *,
    available_countries: list[dict[str, Any]] | None = None,
    prepared_data: pd.DataFrame | None = None,
) -> Any:
    if source != "FRA":
        dataframe = pd.DataFrame(rows)
        required = {"country_code", "response"}
        if dataframe.empty or not required.issubset(dataframe.columns):
            return ""
        dataframe = dataframe.copy()
        dataframe["country_code"] = dataframe["country_code"].fillna("").astype(str)
        dataframe["response"] = dataframe["response"].fillna("not_available").astype(str)
        dataframe["response_order"] = pd.to_numeric(
            dataframe.get(
                "response_order",
                pd.Series(index=dataframe.index, dtype=float),
            ),
            errors="coerce",
        ).fillna(99)
        countries = int(dataframe.loc[dataframe["country_code"].ne(""), "country_code"].nunique())
        responses = (
            dataframe[["response", "response_order"]]
            .drop_duplicates()
            .sort_values(["response_order", "response"], kind="stable")["response"]
            .tolist()
        )
        labels = [taxonomy_label("legal_status", response, language) for response in responses]
        return html.Div(
            [
                html.Div(
                    [
                        html.Span(
                            "Countries compared" if language == "en" else "Países comparados"
                        ),
                        html.Strong(str(countries)),
                    ],
                    className="stats-detail-summary-card stats-detail-summary-card-wide",
                ),
                html.Div(
                    [
                        html.Span(
                            "Legal responses detected"
                            if language == "en"
                            else "Respuestas legales detectadas"
                        ),
                        html.Ul([html.Li(label) for label in labels]),
                    ],
                    className="stats-detail-summary-card stats-detail-summary-card-wide",
                ),
            ]
        )
    summary = summarize_response_comparison(
        rows,
        available_countries=available_countries,
        language=language,
        prepared_data=prepared_data,
    )
    distribution = summary.get("distribution") or []
    countries_label = "Countries compared" if language == "en" else "Países comparados"
    distribution_label = "Distribution" if language == "en" else "Distribución"
    country_singular = "country" if language == "en" else "país"
    country_plural = "countries" if language == "en" else "países"
    return html.Div(
        [
            html.Div(
                [
                    html.Span(countries_label),
                    html.Strong(str(summary.get("countries") or 0)),
                ],
                className="stats-detail-summary-card stats-detail-summary-card-wide",
            ),
            html.Div(
                [
                    html.Span(distribution_label),
                    html.Ul(
                        [
                            html.Li(
                                [
                                    html.Strong(str(item.get("label"))),
                                    html.Span(
                                        f"{item.get('value')}%"
                                        if item.get("unit") == "%"
                                        else f"{item.get('value')} {_plural(item.get('value'), country_singular, country_plural)}"
                                    ),
                                ]
                            )
                            for item in distribution[:8]
                        ]
                    ),
                ],
                className="stats-detail-summary-card stats-detail-summary-card-wide",
            ),
        ]
    )


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
    source = str(result.get("source") or "")
    indicator = str(result.get("indicator") or result.get("category") or "")
    answer = str(result.get("answer") or "").strip()
    return f"{indicator} \u00b7 {answer}" if source == "FRA" and answer else indicator


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


def _methodology_text(result: dict[str, Any], source: str, language: str = "es") -> str:
    if source == "FRA":
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
    return str(result.get("methodology") or "")


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


def _radar_country_options(payload: dict[str, Any], language: str) -> list[dict[str, Any]]:
    dataframe = pd.DataFrame(payload.get("rows") or [])
    required = {"iso", "country", "dimension", "experience_score", "legal_score"}
    if dataframe.empty or not required.issubset(dataframe.columns):
        return []
    dataframe["experience_score"] = pd.to_numeric(dataframe["experience_score"], errors="coerce")
    dataframe["legal_score"] = pd.to_numeric(dataframe["legal_score"], errors="coerce")
    comparable = dataframe.dropna(subset=["experience_score", "legal_score"])
    coverage = comparable.groupby(["iso", "country"], as_index=False).agg(
        comparable_dimensions=("dimension", "nunique")
    )
    coverage = coverage[coverage["comparable_dimensions"] >= 3]
    options: list[dict[str, str]] = []
    for row in coverage.itertuples(index=False):
        iso = normalize_country_code(row.iso, row.country)
        if not iso or iso == "EU27":
            continue
        labels = country_labels(iso, str(row.country))
        options.append({"label": labels[1 if language == "en" else 0], "value": iso})
    return build_dropdown_options(
        sorted(options, key=lambda option: option["label"].casefold()),
        context="statistics-radar-country",
    )


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
