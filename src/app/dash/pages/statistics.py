from __future__ import annotations

from typing import Any

import pandas as pd
from dash import Dash, Input, Output, State, ctx, dash_table, dcc, html, no_update
from dash.development.base_component import Component

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
    build_combined_radar,
    build_combined_scatter,
    build_country_comparison_chart,
    build_eu_average_comparison_chart,
    build_europe_choropleth,
    build_europe_distribution_chart,
    build_fra_response_comparison_chart,
    build_ilga_criteria_heatmap,
    build_legal_reality_gap_chart,
    build_temporal_evolution_chart,
    empty_figure,
    summarize_response_comparison,
)
from app.analytics.statistics_models import (
    FRA_FILTER_GROUP_A,
    FRA_FILTER_GROUP_B,
    FraStatisticsQuery,
    IlgaStatisticsQuery,
)
from app.analytics.statistics_normalizers import normalize_country_code, normalize_text_key
from app.analytics.statistics_service import (
    get_fra_control_payload,
    get_fra_statistics,
    get_ilga_statistics,
)
from app.dash.i18n import text, text_attrs
from app.dash.layouts.navigation import build_navbar


DATA_TYPE_OPTIONS = [
    {
        "label": html.Span("Sociodemográficos", **text_attrs("Sociodemográficos", "Sociodemographic")),
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
            html.Main(
                [
                    _header(),
                    _controls(years, initial_year, categories),
                    dcc.Loading(
                        [
                            html.Div(id="stats-status-message", className="stats-status stats-status-warning"),
                            _map_panel(placeholder),
                            _block_header("Bloque A", "Estadísticas del conjunto de datos seleccionado", "Selected dataset statistics"),
                            html.Section(id="stats-metric-row", className="stats-metric-row stats-executive-grid"),
                            html.Section(
                                [
                                    html.Div(
                                        _graph_panel("Evolución temporal", "Temporal evolution", "stats-temporal-graph", placeholder),
                                        id="stats-temporal-panel",
                                        className="stats-panel-wrapper is-hidden",
                                    ),
                                    _graph_panel("Distribución europea", "European distribution", "stats-distribution-graph", placeholder),
                                    _graph_panel("Comparación con la media de la UE", "EU average comparison", "stats-average-graph", placeholder),
                                    _graph_panel("Comparación entre países", "Country comparison", "stats-country-comparison-graph", placeholder),
                                    html.Div(
                                        [
                                            html.H2(text("Detalles de respuestas", "Response details")),
                                            html.Div(id="stats-detail-summary", className="stats-detail-summary"),
                                            dcc.Graph(id="stats-response-detail-graph", figure=placeholder, config={"displaylogo": False}),
                                        ],
                                        id="stats-response-panel",
                                        className="stats-panel",
                                    ),
                                ],
                                className="stats-grid",
                            ),
                            html.Section(
                                [
                                    _block_header("Bloque B", "Relación entre datos sociodemográficos y legales", "Sociodemographic and legal relationship"),
                                    html.Section(id="stats-combined-metric-row", className="stats-metric-row stats-executive-grid"),
                                    html.Div(
                                        [
                                            _graph_panel("Protección legal vs experiencia real", "Legal protection vs lived experience", "stats-gap-graph", placeholder),
                                            _graph_panel("Scatter ILGA/FRA", "ILGA/FRA scatter", "stats-scatter-graph", placeholder),
                                            _graph_panel("Heatmap europeo", "European heatmap", "stats-combined-heatmap", placeholder),
                                            _graph_panel("Radar comparativo", "Comparative radar", "stats-radar-graph", placeholder),
                                        ],
                                        className="stats-grid",
                                    ),
                                ],
                                id="stats-combined-block",
                                className="stats-analytics-block is-hidden",
                            ),
                            html.Div(
                                [
                                    html.H2(text("Tabla resumida", "Summary table")),
                                    dash_table.DataTable(
                                        id="stats-results-table",
                                        columns=[],
                                        data=[],
                                        page_size=12,
                                        sort_action="native",
                                        filter_action="native",
                                        export_format="csv",
                                        style_table={"overflowX": "auto"},
                                        style_cell={"fontFamily": "Segoe UI, Arial, sans-serif", "fontSize": "0.88rem", "padding": "0.55rem", "textAlign": "left"},
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
        year_class = "stats-control-field stats-year-field" + (" is-hidden" if is_fra and len(years) <= 1 else "")
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
            return [], None, [], None, [], None, {}
        payload = get_fra_control_payload(code)
        answers = payload.get("answers") or []
        segmentations = _translated_segmentation_options(payload.get("segmentations") or [])
        demographic_options = [item for item in segmentations if item.get("value") in FRA_FILTER_GROUP_A]
        identity_options = [item for item in segmentations if item.get("value") in FRA_FILTER_GROUP_B]
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
                return _empty_data_result("Selecciona una categoría y una pregunta para cargar las estadísticas.")
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
                result["combined"] = _combine_rankings(result.get("ranking") or [], legal.get("ranking") or [])
            return result
        if not category:
            return _empty_data_result("Selecciona una categoría jurídica para cargar las estadísticas.")
        return get_ilga_statistics(
            IlgaStatisticsQuery(year=_safe_int(year), category=category, criterion=criterion)
        )

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
        return [country for country in selected if country != iso] if iso in selected else [*selected, iso]

    @app.callback(
        Output("stats-status-message", "children"),
        Output("stats-status-message", "className"),
        Output("stats-map-graph", "figure"),
        Output("stats-clear-countries", "disabled"),
        Output("stats-metric-row", "children"),
        Output("stats-temporal-graph", "figure"),
        Output("stats-temporal-panel", "className"),
        Output("stats-distribution-graph", "figure"),
        Output("stats-average-graph", "figure"),
        Output("stats-country-comparison-graph", "figure"),
        Output("stats-detail-summary", "children"),
        Output("stats-response-detail-graph", "figure"),
        Output("stats-response-panel", "className"),
        Output("stats-combined-metric-row", "children"),
        Output("stats-gap-graph", "figure"),
        Output("stats-scatter-graph", "figure"),
        Output("stats-combined-heatmap", "figure"),
        Output("stats-radar-graph", "figure"),
        Output("stats-combined-block", "className"),
        Output("stats-results-table", "columns"),
        Output("stats-results-table", "data"),
        Output("stats-methodology", "children"),
        Input("stats-data-store", "data"),
        Input("stats-selected-countries", "data"),
        Input("app-language-store", "data"),
    )
    def render_statistics(
        result: dict[str, Any] | None,
        countries: list[str] | None,
        language: str | None,
    ):
        return _render_dashboard(result or {}, _normalize_selected_countries(countries), language or "es")


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
                    html.A(text("Restablecer filtros", "Reset filters"), href="/statistics", className="stats-reset-link", role="button"),
                ],
                class_name="stats-filter-card stats-filter-card-compact",
            ),
            _control_group(
                "Indicador",
                [
                    _field(("Categoría", "Category"), dcc.Dropdown(id="stats-category-select", options=categories, value=None, clearable=False, placeholder="Selecciona una categoría")),
                    _field(("Año", "Year"), dcc.Dropdown(id="stats-year-select", options=years, value=initial_year, clearable=False), element_id="stats-year-field", class_name="stats-control-field stats-year-field"),
                    html.Div(
                        [
                            _field("Pregunta o indicador", dcc.Dropdown(id="fra-indicator-select", options=[], value=None, clearable=False, disabled=True, placeholder="Selecciona primero una categoría")),
                            _field("Respuesta", dcc.Dropdown(id="fra-answer-select", options=[], value=None, clearable=False)),
                        ],
                        id="stats-fra-controls",
                        className="stats-source-controls",
                    ),
                    html.Div(
                        [_field("Criterio jurídico", dcc.Dropdown(id="ilga-criterion-select", options=[], value=None, placeholder="Todos los criterios"))],
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
                            ),
                            _segmentation_group(
                                "Filtro de identidad",
                                "Identity filter",
                                "Orientación sexual, identidad o expresión de género y características sexuales.",
                                "Sexual orientation, gender identity or expression and sex characteristics.",
                                "fra-identity-type",
                                "fra-identity-value",
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
    label_node = html.Label(label[0], **text_attrs(label[0], label[1])) if isinstance(label, tuple) else html.Label(label, **text_attrs(label, LABELS_EN.get(label, label)))
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
            html.H2(title, className="stats-filter-card-title", **text_attrs(title, LABELS_EN.get(title, title))),
            html.Div(children, className="stats-filter-card-body"),
        ],
        **props,
    )


def _header() -> Component:
    return html.Header(
        [
            html.P("Panel de Estadísticas", className="stats-eyebrow", **text_attrs("Panel de Estadísticas", "Statistics panel")),
            html.H1(text("Estadísticas europeas LGBTIQ+", "European LGBTIQ+ statistics")),
            html.P(
                text(
                    "Explora la realidad sociodemográfica, la protección legal y la relación entre ambas.",
                    "Explore lived experience, legal protection and the relationship between them.",
                ),
                className="stats-lead",
            ),
        ],
        className="stats-header",
    )


def _map_panel(placeholder: Any) -> Component:
    return html.Div(
        [
            html.Div(
                [
                    html.H2(text("Mapa de Europa", "Map of Europe")),
                    html.Button(text("Deseleccionar todos", "Clear selection"), id="stats-clear-countries", disabled=True, className="stats-clear-selection"),
                ],
                className="stats-panel-heading",
            ),
            html.P(text("Pulsa sobre cada país para seleccionarlo o deseleccionarlo.", "Click each country to select or deselect it."), className="stats-panel-hint"),
            dcc.Graph(id="stats-map-graph", figure=placeholder, config={"displaylogo": False}, className="stats-mapbox-graph"),
        ],
        className="stats-panel stats-panel-wide stats-map-panel",
    )


def _graph_panel(title_es: str, title_en: str, graph_id: str, figure: Any | None = None) -> Component:
    return html.Div(
        [html.H2(text(title_es, title_en)), dcc.Graph(id=graph_id, figure=figure, config={"displaylogo": False, "responsive": True})],
        className="stats-panel",
    )


def _block_header(kicker: str, title_es: str, title_en: str) -> Component:
    return html.Header(
        [html.P(kicker, className="stats-block-kicker"), html.H2(text(title_es, title_en))],
        className="stats-block-header",
    )


def _year_options(source: str | None) -> list[dict[str, Any]]:
    years = get_fra_years() if source == "fra" else get_ilga_years()
    return [{"label": str(year), "value": year} for year in years]


def _category_options(source: str | None, year: int | None) -> list[dict[str, str]]:
    if source == "fra":
        return _visible_category_options(get_fra_categories())
    options = [{"label": "Ranking total", "value": "Ranking total"}]
    options.extend(
        {"label": category, "value": category}
        for category in _visible_categories(get_ilga_criteria_categories_by_year(year))
    )
    return options


def _visible_category_options(categories: list[str]) -> list[dict[str, str]]:
    return [{"label": category, "value": category} for category in _visible_categories(categories)]


def _visible_categories(categories: list[str]) -> list[str]:
    return [category for category in categories if normalize_text_key(category) not in EXCLUDED_CATEGORY_KEYS]


def _translated_segmentation_options(options: list[dict[str, Any]]) -> list[dict[str, Any]]:
    translated = []
    for option in options:
        value = str(option.get("value") or "")
        labels = SEGMENTATION_LABELS.get(value, (str(option.get("label") or value), str(option.get("label") or value)))
        translated.append({**option, "label": html.Span(labels[0], **text_attrs(labels[0], labels[1]))})
    return translated


def _default_option_value(options: list[dict[str, Any]]) -> Any:
    if any(item.get("value") == "All" for item in options):
        return "All"
    return options[0].get("value") if options else None


def _segmentation_group(
    title_es: str,
    title_en: str,
    description_es: str,
    description_en: str,
    type_id: str,
    value_id: str,
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
                    options=[],
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


def _render_dashboard(result: dict[str, Any], selected: list[str], language: str):
    if result.get("status") != "ok":
        message = str(result.get("message") or "Selecciona un indicador para cargar los resultados.")
        empty = empty_figure(message)
        return (
            html.Div([html.Strong(text("Sin resultados", "No results")), html.P(message)]),
            "stats-status stats-status-warning",
            empty,
            not bool(selected),
            [],
            empty,
            "stats-panel-wrapper is-hidden",
            empty,
            empty,
            empty,
            "",
            empty,
            "stats-panel is-hidden",
            [],
            empty,
            empty,
            empty,
            empty,
            "stats-analytics-block is-hidden",
            [],
            [],
            "",
        )

    source = str(result.get("source") or "")
    ranking = list(result.get("ranking") or [])
    data = list(result.get("data") or [])
    detail = list(result.get("detail_data") or data)
    history = list(result.get("history") or [])
    combined = list(result.get("combined") or [])
    scope = _selection_scope(ranking, selected)
    map_figure = build_europe_choropleth(ranking, source=source, selected_isos=selected, language=language)
    temporal = build_temporal_evolution_chart(history, selected, language)
    distribution = build_europe_distribution_chart(ranking, selected, language)
    average = build_eu_average_comparison_chart(ranking, selected, language)
    comparison = build_country_comparison_chart(ranking, selected, language)
    response = build_fra_response_comparison_chart(detail, selected_countries=selected, language=language) if source == "FRA" else build_ilga_criteria_heatmap(data, language=language)
    combined_metrics = _combined_metric_cards(combined)
    table_rows = _table_rows(result)
    status = html.Div(
        [
            html.Strong(text("Consulta cargada", "Query loaded")),
            html.P(f"{len(ranking)} países con datos · {scope['title']}"),
        ]
    )
    return (
        status,
        "stats-status stats-status-ok",
        map_figure,
        not bool(selected),
        _executive_metric_cards(ranking, selected, history),
        temporal,
        "stats-panel-wrapper" if source == "ILGA-Europe" else "stats-panel-wrapper is-hidden",
        distribution,
        average,
        comparison,
        _detail_summary(source, detail),
        response,
        "stats-panel" if source == "FRA" else "stats-panel is-hidden",
        combined_metrics,
        build_legal_reality_gap_chart(combined, selected, language),
        build_combined_scatter(combined, language),
        build_combined_heatmap(combined, language),
        build_combined_radar(combined, selected, language),
        "stats-analytics-block" if combined else "stats-analytics-block is-hidden",
        _table_columns(table_rows),
        table_rows,
        _methodology_text(result, source),
    )


def _executive_metric_cards(
    ranking: list[dict[str, Any]],
    selected: list[str],
    history: list[dict[str, Any]] | None = None,
) -> list[Any]:
    dataframe = pd.DataFrame(ranking)
    if dataframe.empty:
        return []
    dataframe["value"] = pd.to_numeric(dataframe["value"], errors="coerce")
    dataframe = dataframe.dropna(subset=["value"]).sort_values("value", ascending=False).reset_index(drop=True)
    if dataframe.empty:
        return []
    mean = float(dataframe["value"].mean())
    metrics: list[tuple[str | tuple[str, str], str]] = [
        (("Países analizados", "Countries analysed"), str(len(dataframe))),
        (("Media europea", "European average"), f"{mean:.2f}%"),
        (("Mayor valor", "Highest value"), f"{dataframe.iloc[0]['country']} · {dataframe.iloc[0]['value']:.2f}%"),
        (("Menor valor", "Lowest value"), f"{dataframe.iloc[-1]['country']} · {dataframe.iloc[-1]['value']:.2f}%"),
    ]
    if selected:
        focus = dataframe[dataframe["iso"].astype(str).str.upper() == selected[0]]
        if not focus.empty:
            row = focus.iloc[0]
            position = int(focus.index[0]) + 1
            metrics.extend([
                (("País seleccionado", "Selected country"), f"{row['value']:.2f}%"),
                (("Diferencia con la media", "Difference from average"), f"{row['value'] - mean:+.2f} pp"),
                (("Posición", "Rank"), f"{position}/{len(dataframe)}"),
            ])
            historical = pd.DataFrame(history or [])
            if not historical.empty and {"iso", "year", "value"}.issubset(historical.columns):
                country_history = historical[historical["iso"].astype(str).str.upper() == selected[0]].copy()
                country_history["value"] = pd.to_numeric(country_history["value"], errors="coerce")
                country_history = country_history.dropna(subset=["value"]).sort_values("year").drop_duplicates("year", keep="last")
                if len(country_history) >= 2:
                    variation = float(country_history.iloc[-1]["value"] - country_history.iloc[-2]["value"])
                    metrics.append((("Variación interanual", "Year-on-year change"), f"{variation:+.2f} pp"))
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
        _metric_card(("Mejor equilibrio", "Best balance"), f"{best['country']} · {best['gap']:.2f} pp"),
        _metric_card(("Mayor diferencia", "Largest gap"), f"{largest['country']} · {largest['gap']:.2f} pp"),
        _metric_card(("Media europea", "European average"), f"ILGA {legal_mean:.1f}% · FRA {fra_mean:.1f}%"),
        _metric_card(("Desviación de la brecha", "Gap standard deviation"), f"{gap_std:.2f} pp"),
        _metric_card(("Correlación ILGA/FRA", "ILGA/FRA correlation"), f"{correlation:.2f}" if pd.notna(correlation) else "—"),
        _metric_card(("Indicadores comparados", "Indicators compared"), "2"),
    ]


def _metric_card(label: str | tuple[str, str], value: str) -> Any:
    rendered_label = text(label[0], label[1]) if isinstance(label, tuple) else label
    return html.Div([html.Span(rendered_label), html.Strong(value)], className="stats-metric-card")


def _detail_summary(source: str, rows: list[dict[str, Any]]) -> Any:
    if source != "FRA":
        return ""
    summary = summarize_response_comparison(rows)
    distribution = summary.get("distribution") or []
    return html.Div(
        [
            html.Div([html.Span("Países comparados"), html.Strong(str(summary.get("countries") or 0))], className="stats-detail-summary-card"),
            html.Div([html.Span("Respuestas detectadas"), html.Strong(f"{summary.get('responses') or 0} {_plural(summary.get('responses'), 'respuesta', 'respuestas')}")], className="stats-detail-summary-card"),
            html.Div(
                [
                    html.Span("Distribución"),
                    html.Ul(
                        [
                            html.Li(
                                [
                                    html.Strong(str(item.get("label"))),
                                    html.Span(
                                        f"{item.get('value')}%"
                                        if item.get("unit") == "%"
                                        else f"{item.get('value')} {_plural(item.get('value'), 'país', 'países')}"
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


def _combine_rankings(fra_rows: list[dict[str, Any]], ilga_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    legal = {normalize_country_code(row.get("iso")): row for row in ilga_rows if normalize_country_code(row.get("iso"))}
    combined = []
    for row in fra_rows:
        iso = normalize_country_code(row.get("iso"))
        match = legal.get(iso)
        if not match or not isinstance(row.get("value"), (int, float)) or not isinstance(match.get("value"), (int, float)):
            continue
        combined.append({"country": row.get("country") or match.get("country"), "iso": iso, "fra_value": float(row["value"]), "ilga_value": float(match["value"])})
    return combined


def _table_rows(result: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "ranking": index,
            "country": row.get("country"),
            "iso": row.get("iso"),
            "source": _source_display_name(result.get("source")),
            "value": round(float(row["value"]), 2) if isinstance(row.get("value"), (int, float)) else None,
        }
        for index, row in enumerate(result.get("ranking") or [], start=1)
    ]


def _table_columns(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    labels = {"ranking": "Ranking", "country": "País", "iso": "ISO", "source": "Tipo de datos", "value": "Valor (%)"}
    return [{"name": labels.get(key, key), "id": key} for key in rows[0]] if rows else []


def _methodology_text(result: dict[str, Any], source: str) -> str:
    note = str(result.get("methodology") or "")
    if source == "FRA":
        note += " La puntuación ILGA mide leyes y políticas; FRA refleja respuestas de personas encuestadas. Las fuentes no son directamente equivalentes."
    return note


def _source_display_name(source: Any) -> str:
    return "Sociodemográficos" if source == "FRA" else "Legales" if source == "ILGA-Europe" else str(source or "")


def _selection_scope(ranking: list[dict[str, Any]], selected: list[str]) -> dict[str, Any]:
    if not selected:
        return {"kind": "all", "title": "Europa", "names": []}
    names = _selected_country_names(ranking, selected)
    if len(names) == 1:
        return {"kind": "one", "title": names[0], "names": names}
    return {"kind": "compare", "title": f"{len(names)} países seleccionados", "names": names}


def _selected_country_names(ranking: list[dict[str, Any]], selected: list[str]) -> list[str]:
    names = {normalize_country_code(row.get("iso")): str(row.get("country") or row.get("iso") or "") for row in ranking}
    return [names.get(normalize_country_code(country), country) for country in selected]


def _normalize_selected_countries(countries: list[str] | str | None) -> list[str]:
    values = countries if isinstance(countries, list) else [countries] if countries else []
    result: list[str] = []
    for value in values:
        clean = normalize_country_code(value) or str(value or "").strip()
        if clean and clean not in result:
            result.append(clean)
    return result


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
    return {"status": "empty", "message": message, "data": [], "ranking": [], "available_countries": []}


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _fra_indicator_option_label(indicator: Any) -> str:
    return str(getattr(indicator, "question", "") or getattr(indicator, "label", "") or getattr(indicator, "code", ""))


def _plural(value: Any, singular: str, plural: str) -> str:
    try:
        return singular if float(value or 0) == 1 else plural
    except (TypeError, ValueError):
        return plural
