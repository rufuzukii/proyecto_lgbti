from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

import dash_ag_grid as dag
import pandas as pd
from dash import Dash, Input, Output, State, ctx, dcc, html, no_update
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
    get_ilga_years,
)
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
)
from app.analytics.statistics_normalizers import (
    normalize_country_code,
    normalize_text_key,
)
from app.analytics.statistics_service import (
    get_experience_legal_radar,
    get_fra_control_payload,
    get_fra_statistics,
    get_ilga_statistics,
)
from app.dash.graph_config import fixed_europe_map_config
from app.dash.i18n import attribute_attrs, country_labels, dash_attrs, text, text_attrs, ui_text
from app.dash.layouts.navigation import build_navbar

DATA_TYPE_OPTIONS = [
    {
        "label": html.Span(
            "Sociodemográficos", **text_attrs("Sociodemográficos", "Sociodemographic")
        ),
        "value": "fra",
    },
    {
        "label": html.Span("Legales", **text_attrs("Legales", "Legal")),
        "value": "ilga",
    },
]

EXCLUDED_CATEGORY_KEYS = {
    normalize_text_key("Political Participation"),
    normalize_text_key("Spanish LGBTI+ indicators"),
    normalize_text_key("Spanish LGBTIQ+ indicators"),
}

LEGAL_RESPONSE_LABELS = {
    "not_met": ("No reconocido", "Not met"),
    "partially_met": ("Cumplimiento parcial", "Partially met"),
    "fully_met": ("Cumplimiento completo", "Fully met"),
    "not_available": ("Sin datos", "No data"),
    "overall_score": ("Puntuación legal", "Legal score"),
}

SEGMENTATION_LABELS = {
    "All": ("Todos", "All"),
    "Age": ("Edad", "Age"),
    "Sexual Orientation": ("Orientación sexual", "Sexual orientation"),
    "Education": ("Educación", "Education"),
    "Employment status": ("Situación laboral", "Employment status"),
    "Belonging to a minority group": ("Pertenencia a una minoría", "Minority status"),
    "Openness about being LGBTIQ+": ("Apertura sobre ser LGBTIQ+", "Openness about being LGBTIQ+"),
    "Place of residence": ("Lugar de residencia", "Place of residence"),
    "Activity limitation": ("Limitación de actividad", "Activity limitation"),
    "Making ends meet": ("Capacidad para llegar a fin de mes", "Making ends meet"),
    "Gender Expression": ("Identidad o expresión de género", "Gender identity or expression"),
    "Sex Characteristics": ("Características sexuales", "Sex characteristics"),
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
    years = _year_options("fra")
    initial_year = years[0]["value"] if years else None
    categories = _category_options("fra", initial_year)
    placeholder = empty_figure("Selecciona una categoría y un indicador para comenzar.")
    return html.Div(
        [
            build_navbar(active="statistics"),
            dcc.Store(id="stats-data-store", storage_type="memory"),
            dcc.Store(id="stats-fra-control-store", storage_type="memory"),
            dcc.Store(id="stats-selected-countries", data=[], storage_type="session"),
            dcc.Download(id="stats-summary-table-download"),
            html.Main(
                [
                    _header(),
                    _controls(years, initial_year, categories),
                    dcc.Loading(
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
                                                ("País seleccionado", "Selected country"),
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
                                                    style={"width": "100%", "height": "650px"},
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
                                                    style=_response_detail_graph_style(placeholder),
                                                ),
                                                className="stats-response-detail-scroll",
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
                                            ),
                                            _graph_panel(
                                                "Relaci\u00f3n entre protecci\u00f3n legal y experiencia reportada",
                                                "Legal protection and reported experience relationship",
                                                "stats-scatter-graph",
                                                placeholder,
                                            ),
                                            _graph_panel(
                                                "Heatmap europeo",
                                                "European heatmap",
                                                "stats-combined-heatmap",
                                                placeholder,
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
                                            html.H2(text("Tabla resumida", "Summary table")),
                                            html.Div(
                                                [
                                                    html.Button(
                                                        text(
                                                            ui_text("download_table", "es"),
                                                            ui_text("download_table", "en"),
                                                        ),
                                                        id="stats-table-download-button",
                                                        type="button",
                                                        n_clicks=0,
                                                        disabled=True,
                                                        className=(
                                                            "stats-chart-export-button "
                                                            "stats-table-export-button"
                                                        ),
                                                        title=ui_text("download_csv", "es"),
                                                        **attribute_attrs(
                                                            "title",
                                                            ui_text("download_csv", "es"),
                                                            ui_text("download_csv", "en"),
                                                        ),
                                                    ),
                                                    html.Span(
                                                        text(
                                                            ui_text("no_export_data", "es"),
                                                            ui_text("no_export_data", "en"),
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
                                            {"aria-label": "Tabla resumida / Summary table"}
                                        ),
                                    ),
                                ],
                                className="stats-panel stats-results-table-panel",
                            ),
                            html.P(id="stats-methodology", className="stats-methodology-note"),
                        ],
                        type="circle",
                    ),
                ],
                className="stats-shell",
            ),
        ]
    )


def register_statistics_callbacks(app: Dash) -> None:
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
        params = {
            "source": source or "fra",
            "year": year,
            "category": category,
            "indicator_id": indicator,
            "answer": answer,
            "filter_a_name": filter_a_name or "All",
            "filter_a_value": filter_a_value or "All",
            "filter_b_name": filter_b_name or "All",
            "filter_b_value": filter_b_value or "All",
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
        path = "/reports" if language == "en" else "/informes"
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
        Output("stats-category-select", "options"),
        Output("stats-category-select", "value"),
        Input("stats-source-select", "value"),
        Input("stats-year-select", "value"),
        State("stats-category-select", "value"),
    )
    def update_categories_for_year(source: str | None, year: int | None, current: str | None):
        options = _category_options(source, year)
        values = {item["value"] for item in options}
        return options, current if current in values else None

    @app.callback(
        Output("fra-indicator-select", "options"),
        Output("fra-indicator-select", "value"),
        Output("fra-indicator-select", "disabled"),
        Input("stats-source-select", "value"),
        Input("stats-category-select", "value"),
    )
    def update_fra_indicators(source: str | None, category: str | None):
        if source != "fra" or not category:
            return [], None, True
        options = [
            {"label": _fra_indicator_option_label(indicator), "value": indicator.code}
            for indicator in get_fra_mongo_indicators_by_category(category)
        ]
        return options, None, not bool(options)

    @app.callback(
        Output("fra-answer-select", "options"),
        Output("fra-answer-select", "value"),
        Output("fra-demographic-type", "options"),
        Output("fra-demographic-type", "value"),
        Output("fra-identity-type", "options"),
        Output("fra-identity-type", "value"),
        Output("stats-fra-control-store", "data"),
        Input("fra-indicator-select", "value"),
    )
    def update_fra_controls(code: str | None):
        if not code:
            return (
                [],
                None,
                _segmentation_catalog_options(FRA_FILTER_GROUP_A, []),
                None,
                _segmentation_catalog_options(FRA_FILTER_GROUP_B, []),
                None,
                {},
            )
        payload = get_fra_control_payload(code)
        answers = payload.get("answers") or []
        segmentations = _translated_segmentation_options(payload.get("segmentations") or [])
        demographic_options = _segmentation_catalog_options(FRA_FILTER_GROUP_A, segmentations)
        identity_options = _segmentation_catalog_options(FRA_FILTER_GROUP_B, segmentations)
        return (
            answers,
            answers[0]["value"] if answers else None,
            demographic_options,
            _default_option_value(demographic_options),
            identity_options,
            _default_option_value(identity_options),
            payload,
        )

    @app.callback(
        Output("fra-demographic-value", "options"),
        Output("fra-demographic-value", "value"),
        Input("fra-demographic-type", "value"),
        Input("stats-fra-control-store", "data"),
    )
    def update_demographic_values(segmentation: str | None, payload: dict[str, Any] | None):
        values = (payload or {}).get("values") or {}
        options = values.get(segmentation or "All") or []
        return options, options[0]["value"] if options else None

    @app.callback(
        Output("fra-identity-value", "options"),
        Output("fra-identity-value", "value"),
        Input("fra-identity-type", "value"),
        Input("stats-fra-control-store", "data"),
    )
    def update_identity_values(segmentation: str | None, payload: dict[str, Any] | None):
        values = (payload or {}).get("values") or {}
        options = values.get(segmentation or "All") or []
        return options, options[0]["value"] if options else None

    @app.callback(
        Output("ilga-criterion-select", "options"),
        Output("ilga-criterion-select", "value"),
        Input("stats-source-select", "value"),
        Input("stats-year-select", "value"),
        Input("stats-category-select", "value"),
    )
    def update_ilga_criteria(source: str | None, year: int | None, category: str | None):
        if source != "ilga" or not category or category == "Ranking total":
            return [], None
        options = [
            {"label": item["indicator"], "value": item["indicator"]}
            for item in get_ilga_criteria_by_year(year, category)
            if item.get("indicator")
        ]
        return options, None

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
    ) -> dict[str, Any]:
        if source == "fra":
            if not _has_valid_fra_selection(category, fra_code):
                return _empty_data_result(
                    "Selecciona una categoría y una pregunta para cargar las estadísticas."
                )
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
                return _empty_data_result("Preparando los controles de la pregunta seleccionada.")
            result = get_fra_statistics(
                FraStatisticsQuery(
                    year=_safe_int(year),
                    category=category,
                    question_code=fra_code,
                    answer=answer,
                    filter_a_name=demographic_type or "All",
                    filter_a_value=demographic_value or "All",
                    filter_b_name=identity_type or "All",
                    filter_b_value=identity_value or "All",
                )
            )
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
                        filter_a_name=demographic_type or "All",
                        filter_a_value=demographic_value or "All",
                        filter_b_name=identity_type or "All",
                        filter_b_value=identity_value or "All",
                    )
                )
            return result
        if not category:
            return _empty_data_result(
                "Selecciona una categoría jurídica para cargar las estadísticas."
            )
        result = get_ilga_statistics(
            IlgaStatisticsQuery(year=_safe_int(year), category=category, criterion=criterion)
        )
        if result.get("status") == "ok":
            result["experience_legal_radar"] = get_experience_legal_radar(
                ExperienceLegalRadarQuery(ilga_year=_safe_int(year))
            )
        return result

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
    )
    def render_statistics(
        result: dict[str, Any] | None,
        countries: list[str] | None,
        temporal_countries: list[str] | None,
        language: str | None,
    ):
        return _render_dashboard(
            result or {},
            _normalize_selected_countries(countries),
            language or "es",
            temporal_countries=_normalize_selected_countries(temporal_countries),
        )

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
                        href="/statistics",
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
                                "Orientación sexual, identidad o expresión de género y características sexuales.",
                                "Sexual orientation, gender identity or expression and sex characteristics.",
                                "fra-identity-type",
                                "fra-identity-value",
                                FRA_FILTER_GROUP_B,
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
    label_node = (
        html.Label(label[0], **text_attrs(label[0], label[1]))
        if isinstance(label, tuple)
        else html.Label(label, **text_attrs(label, LABELS_EN.get(label, label)))
    )
    props: dict[str, Any] = {"className": class_name}
    if element_id:
        props["id"] = element_id
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
                href="/informes",
                className="stats-create-report-link",
            ),
        ],
        className="stats-header",
    )


def _report_destination(report_href: str, *, authenticated: bool) -> str:
    if authenticated:
        return report_href
    return f"/login?{urlencode({'next': report_href, 'notice': 'report_login_required'})}"


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
) -> Component:
    panel_props: dict[str, Any] = {"className": panel_class_name}
    if panel_id:
        panel_props["id"] = panel_id
    return html.Div(
        [
            _chart_panel_heading(title_es, title_en, graph_id),
            dcc.Graph(
                id=graph_id,
                figure=figure,
                responsive=True,
                config=chart_graph_config(),
                className="stats-chart-graph",
                style={"width": "100%"},
            ),
        ],
        **panel_props,
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
    return [{"label": str(year), "value": year} for year in years]


def _temporal_country_options(
    result: dict[str, Any],
    language: str,
) -> list[dict[str, str]]:
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
    return [
        {"label": label, "value": iso}
        for iso, label in sorted(countries.items(), key=lambda item: item[1].casefold())
    ]


def _category_options(source: str | None, year: int | None) -> list[dict[str, Any]]:
    if source == "fra":
        return _visible_category_options(get_fra_categories())
    options: list[dict[str, Any]] = [
        {
            "label": text("Ranking total", "Overall ranking"),
            "value": "Ranking total",
        }
    ]
    options.extend(
        {"label": category, "value": category}
        for category in _visible_categories(get_ilga_criteria_categories_by_year(year))
    )
    return options


def _visible_category_options(categories: list[str]) -> list[dict[str, Any]]:
    return [{"label": category, "value": category} for category in _visible_categories(categories)]


def _visible_categories(categories: list[str]) -> list[str]:
    return [
        category
        for category in categories
        if normalize_text_key(category) not in EXCLUDED_CATEGORY_KEYS
    ]


def _translated_segmentation_options(options: list[dict[str, Any]]) -> list[dict[str, Any]]:
    translated = []
    for option in options:
        value = str(option.get("value") or "")
        labels = SEGMENTATION_LABELS.get(
            value, (str(option.get("label") or value), str(option.get("label") or value))
        )
        translated.append(
            {**option, "label": html.Span(labels[0], **text_attrs(labels[0], labels[1]))}
        )
    return translated


def _default_option_value(options: list[dict[str, Any]]) -> Any:
    enabled = [item for item in options if not item.get("disabled", False)]
    if any(item.get("value") == "All" for item in enabled):
        return "All"
    return enabled[0].get("value") if enabled else None


def _segmentation_catalog_options(
    catalog: tuple[str, ...],
    available_options: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Keep the FRA filter catalog stable while disabling unavailable entries."""
    available = {
        str(option.get("value") or "")
        for option in available_options
        if option.get("value") and not option.get("disabled", False)
    }
    options: list[dict[str, Any]] = []
    for value in catalog:
        labels = SEGMENTATION_LABELS.get(value, (value, value))
        options.append(
            {
                "label": html.Span(labels[0], **text_attrs(labels[0], labels[1])),
                "value": value,
                "disabled": value not in available,
            }
        )
    return options


def _segmentation_group(
    title_es: str,
    title_en: str,
    description_es: str,
    description_en: str,
    type_id: str,
    value_id: str,
    type_catalog: tuple[str, ...],
) -> Component:
    return html.Section(
        [
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
        ],
        className="stats-segmentation-row",
    )


def _render_dashboard(
    result: dict[str, Any],
    selected: list[str],
    language: str,
    *,
    temporal_countries: list[str] | None = None,
):
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
    scope = _selection_scope(ranking, selected, language)
    map_figure = build_europe_choropleth(
        ranking, source=source, selected_isos=selected, language=language
    )
    temporal = build_temporal_evolution_chart(
        history,
        selected,
        language,
        visible_countries=temporal_countries,
    )
    comparative_ranking = build_comparative_ranking_chart(
        ranking,
        selected,
        language,
        indicator=str(result.get("indicator") or ""),
        year=result.get("year"),
    )
    distribution = build_europe_distribution_chart(ranking, selected, language)
    average = build_eu_average_comparison_chart(ranking, selected, language)
    comparison = (
        build_response_country_comparison_chart(
            detail,
            selected,
            language,
            indicator=str(result.get("indicator") or ""),
            year=result.get("year"),
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

    rows = result.get("data") or []
    first_row = rows[0] if rows and isinstance(rows[0], dict) else {}
    for key in ("filter_a", "filter_b"):
        value = str(first_row.get(key) or "").strip()
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
        labels = [
            LEGAL_RESPONSE_LABELS.get(response, (response, response))[1 if language == "en" else 0]
            for response in responses
        ]
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


def _source_display_name(source: Any) -> str:
    return (
        "Sociodemográficos"
        if source == "FRA"
        else "Legales"
        if source == "ILGA-Europe"
        else str(source or "")
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


def _radar_country_options(payload: dict[str, Any], language: str) -> list[dict[str, str]]:
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
    return sorted(options, key=lambda option: option["label"].casefold())


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
