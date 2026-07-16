from __future__ import annotations

from typing import Any

from dash import dash_table

from app.analytics.repository import (
    assert_analytics_databases_available,
    get_fra_categories,
    get_fra_indicator_answers,
    get_fra_mongo_indicators_by_category,
    get_fra_years,
    get_ilga_criteria_by_year,
    get_ilga_criteria_categories_by_year,
    get_ilga_document_by_year,
    get_ilga_years,
)
from app.analytics.statistics_charts import (
    build_comparison_chart,
    build_europe_choropleth,
    build_fra_distribution_chart,
    build_fra_ilga_scatter,
    build_ilga_criteria_heatmap,
    build_ranking_chart,
    empty_figure,
)
from app.analytics.statistics_models import FraStatisticsQuery, IlgaStatisticsQuery
from app.analytics.statistics_normalizers import normalize_country_code
from app.analytics.statistics_service import (
    build_fra_answer_options,
    build_fra_country_options,
    build_fra_filter_type_options,
    build_fra_filter_value_options,
    build_ilga_country_options,
    get_fra_statistics,
    get_ilga_statistics,
    ilga_document_to_dataframe,
)
from app.dash.compat import Dash, Input, Output, State, dcc, html
from app.dash.layouts.navigation import build_navbar


DATA_TYPE_OPTIONS = [
    {"label": "Sociodemográficos", "value": "fra"},
    {"label": "Legales", "value": "ilga"},
]

QUERY_MODE_OPTIONS = [
    {"label": "Todos los países", "value": "all"},
    {"label": "Un país", "value": "one"},
    {"label": "Comparar países", "value": "compare"},
]

FRA_VISUALIZATION_OPTIONS = [
    {"label": "Ranking", "value": "ranking"},
    {"label": "Distribución de respuestas", "value": "distribution"},
    {"label": "Comparación sociodemográfica/legal", "value": "fra_ilga"},
]

ILGA_VISUALIZATION_OPTIONS = [
    {"label": "Ranking", "value": "ranking"},
    {"label": "Criterios jurídicos", "value": "criteria"},
]

GROUP_BY_OPTIONS = [
    {"label": "País", "value": "country"},
    {"label": "Respuesta", "value": "answer"},
    {"label": "Categoría", "value": "category"},
    {"label": "Pregunta", "value": "question"},
    {"label": "Año", "value": "year"},
    {"label": "Filtro A", "value": "filter_a"},
    {"label": "Filtro B", "value": "filter_b"},
]


def build_statistics_layout() -> html.Div:
    assert_analytics_databases_available()
    years = _year_options("ilga")
    initial_year = years[0]["value"] if years else None
    categories = _category_options("ilga", initial_year)

    return html.Div(
        [
            build_navbar(active="statistics"),
            html.Main(
                [
                    _header(),
                    _controls(years, initial_year, categories),
                    dcc.Loading(
                        [
                            html.Div(id="stats-status-message", className="stats-status"),
                            html.Section(id="stats-metric-row", className="stats-metric-row"),
                            html.Section(
                                [
                                    html.Div(
                                        [
                                            html.H2("Mapa europeo"),
                                            dcc.Graph(
                                                id="stats-map-graph",
                                                figure=empty_figure("Selecciona un tipo de datos para empezar."),
                                                config={"displaylogo": False},
                                                className="stats-mapbox-graph",
                                            ),
                                            html.P(
                                                "Mapa Plotly sin Mapbox: se mantiene la solución existente porque no requiere token privado y ya esta integrada con Dash.",
                                                className="stats-methodology-note",
                                            ),
                                        ],
                                        className="stats-panel stats-panel-wide",
                                    ),
                                    html.Div(
                                        [
                                            html.H2("Gráfico principal"),
                                            dcc.Graph(
                                                id="stats-primary-graph",
                                                figure=empty_figure("Los resultados apareceran aqui."),
                                                config={"displaylogo": False},
                                            ),
                                        ],
                                        className="stats-panel",
                                    ),
                                    html.Div(
                                        [
                                            html.H2("Detalle"),
                                            dcc.Graph(
                                                id="stats-secondary-graph",
                                                figure=empty_figure("Selecciona filtros para ver el detalle."),
                                                config={"displaylogo": False},
                                            ),
                                        ],
                                        className="stats-panel",
                                    ),
                                    html.Div(
                                        [
                                            html.H2("Tabla resumida"),
                                            dash_table.DataTable(
                                                id="stats-results-table",
                                                columns=[],
                                                data=[],
                                                page_size=12,
                                                sort_action="native",
                                                filter_action="native",
                                                export_format="csv",
                                                style_table={"overflowX": "auto"},
                                                style_cell={
                                                    "fontFamily": "Segoe UI, Arial, sans-serif",
                                                    "fontSize": "0.88rem",
                                                    "padding": "0.55rem",
                                                    "textAlign": "left",
                                                },
                                            ),
                                        ],
                                        className="stats-panel stats-panel-wide",
                                    ),
                                    html.P(id="stats-methodology", className="stats-methodology-note"),
                                ],
                                className="stats-grid",
                            ),
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
        Output("stats-category-select", "options"),
        Output("stats-category-select", "value"),
        Output("stats-fra-controls", "className"),
        Output("stats-ilga-controls", "className"),
        Output("stats-fra-segmentation-card", "className"),
        Output("stats-fra-grouping-controls", "className"),
        Output("stats-visualization-select", "options"),
        Output("stats-visualization-select", "value"),
        Output("stats-source-select", "className"),
        Input("stats-source-select", "value"),
    )
    def update_source_controls(source: str | None):
        years = _year_options(source)
        year = years[0]["value"] if years else None
        categories = _category_options(source, year)
        category = categories[0]["value"] if categories else None
        if source == "fra":
            return (
                years,
                year,
                categories,
                category,
                "stats-source-controls",
                "stats-source-controls is-hidden",
                "stats-filter-card stats-filter-card-wide stats-fra-only",
                "stats-source-controls stats-fra-only",
                FRA_VISUALIZATION_OPTIONS,
                "ranking",
                _data_type_selector_class("fra"),
            )
        return (
            years,
            year,
            categories,
            category,
            "stats-source-controls is-hidden",
            "stats-source-controls",
            "stats-filter-card stats-filter-card-wide stats-fra-only is-hidden",
            "stats-source-controls stats-fra-only is-hidden",
            ILGA_VISUALIZATION_OPTIONS,
            "ranking",
            _data_type_selector_class("ilga"),
        )

    @app.callback(
        Output("stats-category-select", "options", allow_duplicate=True),
        Output("stats-category-select", "value", allow_duplicate=True),
        Input("stats-source-select", "value"),
        Input("stats-year-select", "value"),
        prevent_initial_call=True,
    )
    def update_categories_for_year(source: str | None, year: int | None):
        categories = _category_options(source, year)
        return categories, categories[0]["value"] if categories else None

    @app.callback(
        Output("fra-indicator-select", "options"),
        Output("fra-indicator-select", "value"),
        Input("stats-source-select", "value"),
        Input("stats-category-select", "value"),
    )
    def update_fra_indicators(source: str | None, category: str | None):
        if source != "fra" or not category:
            return [], None
        indicators = get_fra_mongo_indicators_by_category(category)
        options = [
            {"label": _fra_indicator_option_label(indicator), "value": indicator.code}
            for indicator in indicators
        ]
        return options, options[0]["value"] if options else None

    @app.callback(
        Output("fra-answer-select", "options"),
        Output("fra-answer-select", "value"),
        Output("fra-filter-a-type", "options"),
        Output("fra-filter-a-type", "value"),
        Output("fra-filter-b-type", "options"),
        Output("fra-filter-b-type", "value"),
        Input("fra-indicator-select", "value"),
    )
    def update_fra_answer_and_filter_types(code: str | None):
        document = get_fra_indicator_answers(code or "")
        answers = build_fra_answer_options(document)
        filter_a = build_fra_filter_type_options(document, "a")
        filter_b = build_fra_filter_type_options(document, "b")
        return (
            answers,
            answers[0]["value"] if answers else None,
            filter_a,
            "All",
            filter_b,
            "All",
        )

    @app.callback(
        Output("fra-filter-a-value", "options"),
        Output("fra-filter-a-value", "value"),
        Input("fra-indicator-select", "value"),
        Input("fra-filter-a-type", "value"),
    )
    def update_fra_filter_a_values(code: str | None, filter_type: str | None):
        options = build_fra_filter_value_options(get_fra_indicator_answers(code or ""), filter_type)
        return options, options[0]["value"] if options else None

    @app.callback(
        Output("fra-filter-b-value", "options"),
        Output("fra-filter-b-value", "value"),
        Input("fra-indicator-select", "value"),
        Input("fra-filter-b-type", "value"),
    )
    def update_fra_filter_b_values(code: str | None, filter_type: str | None):
        options = build_fra_filter_value_options(get_fra_indicator_answers(code or ""), filter_type)
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
        criteria = get_ilga_criteria_by_year(year, category)
        options = [
            {"label": item["indicator"], "value": item["indicator"]}
            for item in criteria
            if item.get("indicator")
        ]
        return options, None

    @app.callback(
        Output("stats-country-select", "options"),
        Output("stats-country-select", "value"),
        Input("stats-source-select", "value"),
        Input("stats-year-select", "value"),
        Input("fra-indicator-select", "value"),
        State("stats-country-select", "value"),
    )
    def update_country_options(
        source: str | None,
        year: int | None,
        fra_code: str | None,
        current_countries: list[str] | None,
    ):
        if source == "fra":
            options = build_fra_country_options(get_fra_indicator_answers(fra_code or ""))
        else:
            options = build_ilga_country_options(get_ilga_document_by_year(year))
        available = {str(option.get("value")) for option in options}
        preserved = [
            country
            for country in current_countries or []
            if str(country) in available or normalize_country_code(country) in available
        ]
        return options, preserved

    @app.callback(
        Output("stats-country-select", "value", allow_duplicate=True),
        Input("stats-map-graph", "clickData"),
        State("stats-country-select", "value"),
        State("stats-query-mode-select", "value"),
        prevent_initial_call=True,
    )
    def select_country_from_map(click_data: dict[str, Any] | None, current: list[str] | None, mode: str | None):
        points = (click_data or {}).get("points") or []
        if not points:
            return current or []
        customdata = points[0].get("customdata")
        iso = customdata[0] if isinstance(customdata, list) and customdata else None
        iso = normalize_country_code(iso)
        if not iso:
            return current or []
        if mode == "compare":
            selected = list(current or [])
            if iso not in selected:
                selected.append(iso)
            return selected
        return [iso]

    @app.callback(
        Output("stats-status-message", "children"),
        Output("stats-status-message", "className"),
        Output("stats-metric-row", "children"),
        Output("stats-map-graph", "figure"),
        Output("stats-primary-graph", "figure"),
        Output("stats-secondary-graph", "figure"),
        Output("stats-results-table", "columns"),
        Output("stats-results-table", "data"),
        Output("stats-methodology", "children"),
        Input("stats-source-select", "value"),
        Input("stats-year-select", "value"),
        Input("stats-category-select", "value"),
        Input("fra-indicator-select", "value"),
        Input("fra-answer-select", "value"),
        Input("fra-filter-a-type", "value"),
        Input("fra-filter-a-value", "value"),
        Input("fra-filter-b-type", "value"),
        Input("fra-filter-b-value", "value"),
        Input("fra-group-by-select", "value"),
        Input("stats-query-mode-select", "value"),
        Input("stats-country-select", "value"),
        Input("stats-visualization-select", "value"),
        Input("ilga-criterion-select", "value"),
    )
    def update_results(
        source: str | None,
        year: int | None,
        category: str | None,
        fra_code: str | None,
        answer: str | None,
        filter_a_type: str | None,
        filter_a_value: str | None,
        filter_b_type: str | None,
        filter_b_value: str | None,
        group_by: list[str] | None,
        mode: str | None,
        countries: list[str] | None,
        visualization: str | None,
        ilga_criterion: str | None,
    ):
        selected_countries = _normalize_selected_countries(countries)
        effective_mode = _effective_query_mode(mode, selected_countries)

        if source == "fra":
            query = FraStatisticsQuery(
                year=_safe_int(year),
                countries=selected_countries,
                category=category,
                question_code=fra_code,
                answer=answer,
                filter_a_name=filter_a_type,
                filter_a_value=filter_a_value,
                filter_b_name=filter_b_type,
                filter_b_value=filter_b_value,
                group_by=group_by or ["country"],
                mode=effective_mode,
                visualization=visualization or "ranking",
            )
            result = get_fra_statistics(query)
            return _render_result(result, query.mode, query.visualization, selected_countries)

        query = IlgaStatisticsQuery(
            year=_safe_int(year),
            countries=selected_countries,
            category=category,
            criterion=ilga_criterion,
            mode=effective_mode,
            visualization=visualization or "ranking",
        )
        result = get_ilga_statistics(query)
        return _render_result(result, query.mode, query.visualization, selected_countries)


def _header() -> html.Header:
    return html.Header(
        [
            html.P("Panel exploratorio", className="stats-eyebrow"),
            html.H1("Estadisticas europeas LGBTIQ+"),
            html.P(
                "Consulta datos sociodemográficos y legales por país, año, categoría y filtros comparables.",
                className="stats-lead",
            ),
        ],
        className="stats-header",
    )


def _controls(
    years: list[dict[str, Any]],
    initial_year: int | None,
    categories: list[dict[str, Any]],
) -> html.Section:
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
                            value="ilga",
                            className=_data_type_selector_class("ilga"),
                            inputClassName="stats-segmented-input",
                            labelClassName="stats-segmented-label",
                        ),
                    ),
                    html.A("Restablecer filtros", href="/statistics", className="stats-reset-link", role="button"),
                ],
                class_name="stats-filter-card stats-filter-card-compact",
            ),
            _control_group(
                "Localización",
                [
                    _field("Año", dcc.Dropdown(id="stats-year-select", options=years, value=initial_year, clearable=False)),
                    _field(
                        "País o países",
                        dcc.Dropdown(
                            id="stats-country-select",
                            options=[],
                            value=[],
                            multi=True,
                            placeholder="Selecciona en el mapa o aquí",
                            className="stats-country-dropdown",
                        ),
                    ),
                ],
                class_name="stats-filter-card stats-filter-card-wide",
            ),
            _control_group(
                "Indicador",
                [
                    _field("Categoría", dcc.Dropdown(id="stats-category-select", options=categories, value=categories[0]["value"] if categories else None, clearable=False)),
                    html.Div(
                        [
                            _field("Pregunta o indicador", dcc.Dropdown(id="fra-indicator-select", options=[], value=None, clearable=False)),
                            _field("Respuesta", dcc.Dropdown(id="fra-answer-select", options=[], value=None, clearable=False)),
                        ],
                        id="stats-fra-controls",
                        className="stats-source-controls is-hidden",
                    ),
                    html.Div(
                        [
                            _field("Criterio jurídico", dcc.Dropdown(id="ilga-criterion-select", options=[], value=None, placeholder="Todos los criterios de la categoría")),
                        ],
                        id="stats-ilga-controls",
                        className="stats-source-controls",
                    ),
                ],
                class_name="stats-filter-card stats-filter-card-wide",
            ),
            _control_group(
                "Segmentación sociodemográfica",
                [
                    _field("Filtro demográfico", dcc.Dropdown(id="fra-filter-a-type", options=[], value="All", clearable=False)),
                    _field("Valor demográfico", dcc.Dropdown(id="fra-filter-a-value", options=[], value="All", clearable=False)),
                    _field("Filtro de identidad", dcc.Dropdown(id="fra-filter-b-type", options=[], value="All", clearable=False)),
                    _field("Valor de identidad", dcc.Dropdown(id="fra-filter-b-value", options=[], value="All", clearable=False)),
                ],
                element_id="stats-fra-segmentation-card",
                class_name="stats-filter-card stats-filter-card-wide stats-fra-only",
            ),
            _control_group(
                "Visualizacion",
                [
                    _field(
                        "Modo de consulta",
                        dcc.RadioItems(
                            id="stats-query-mode-select",
                            options=QUERY_MODE_OPTIONS,
                            value="all",
                            className="stats-segmented-control",
                            inputClassName="stats-segmented-input",
                            labelClassName="stats-segmented-label",
                        ),
                    ),
                    _field(
                        "Modo de visualizacion",
                        dcc.RadioItems(
                            id="stats-visualization-select",
                            options=ILGA_VISUALIZATION_OPTIONS,
                            value="ranking",
                            className="stats-segmented-control",
                            inputClassName="stats-segmented-input",
                            labelClassName="stats-segmented-label",
                        ),
                    ),
                    html.Div(
                        [
                            _field("Agrupación", dcc.Dropdown(id="fra-group-by-select", options=GROUP_BY_OPTIONS, value=["country"], multi=True)),
                        ],
                        id="stats-fra-grouping-controls",
                        className="stats-source-controls stats-fra-only",
                    ),
                ],
                class_name="stats-filter-card stats-filter-card-wide",
            ),
        ],
        className="stats-controls",
    )


def _field(label: str, component: Any) -> html.Div:
    return html.Div([html.Label(label), component], className="stats-control-field")


def _control_group(
    title: str,
    children: list[Any],
    class_name: str = "stats-filter-card",
    element_id: str | None = None,
) -> html.Section:
    props: dict[str, Any] = {"className": class_name}
    if element_id is not None:
        props["id"] = element_id
    return html.Section(
        [
            html.H2(title, className="stats-filter-card-title"),
            html.Div(children, className="stats-filter-card-body"),
        ],
        **props,
    )


def _year_options(source: str | None) -> list[dict[str, Any]]:
    years = get_fra_years() if source == "fra" else get_ilga_years()
    return [{"label": str(year), "value": year} for year in years]


def _category_options(source: str | None, year: int | None) -> list[dict[str, str]]:
    if source == "fra":
        return [{"label": category, "value": category} for category in get_fra_categories()]
    options = [{"label": "Ranking total", "value": "Ranking total"}]
    options.extend(
        {"label": category, "value": category}
        for category in get_ilga_criteria_categories_by_year(year)
    )
    return options


def _render_result(
    result: dict[str, Any],
    mode: str,
    visualization: str,
    selected_countries: list[str],
):
    status = result.get("status")
    if status != "ok":
        message = result.get("message") or "No hay datos para mostrar."
        empty = empty_figure(message)
        return (
            html.Div([html.Strong("Sin resultados"), html.P(message), html.A("Restablecer filtros", href="/statistics")]),
            "stats-status stats-status-warning",
            [],
            empty,
            empty,
            empty,
            [],
            [],
            "",
        )

    source = result.get("source") or ""
    ranking = result.get("ranking") or []
    data = result.get("data") or []
    scope = _selection_scope(ranking, selected_countries)
    selected_iso = normalize_country_code(selected_countries[0]) if len(selected_countries) == 1 else None
    map_figure = build_europe_choropleth(ranking, source=source, selected_iso=selected_iso)
    _set_figure_title(map_figure, f"Mapa europeo - {scope['title']}")

    if mode == "compare":
        primary = build_comparison_chart(ranking, source=source)
    elif visualization == "distribution" and source == "FRA":
        primary = build_fra_distribution_chart(data)
    elif visualization == "criteria" and source == "ILGA-Europe":
        primary = build_ilga_criteria_heatmap(data)
    else:
        primary = build_ranking_chart(ranking, source=source)
    _set_figure_title(primary, _primary_figure_title(source, visualization, scope))

    if source == "FRA" and visualization == "fra_ilga":
        ilga_rows = ilga_document_to_dataframe(get_ilga_document_by_year(_first_year(data))).to_dict("records")
        secondary = build_fra_ilga_scatter(data, ilga_rows)
    elif source == "FRA":
        secondary = build_fra_distribution_chart(data)
    else:
        secondary = build_ilga_criteria_heatmap(data)
    _set_figure_title(secondary, _secondary_figure_title(source, visualization, scope))

    table_rows = _table_rows(result)
    return (
        _status_message(result, scope),
        "stats-status stats-status-ok",
        _metric_cards(result.get("metrics") or {}),
        map_figure,
        primary,
        secondary,
        _table_columns(table_rows),
        table_rows,
        _methodology_text(result, source),
    )


def _status_message(result: dict[str, Any], scope: dict[str, Any]) -> html.Div:
    rows = result.get("ranking") or []
    subtitle = f"Ámbito: {scope['subtitle']}" if scope.get("subtitle") else f"Ámbito: {scope['title']}"
    return html.Div(
        [
            html.Strong(f"Consulta cargada - {scope['title']}"),
            html.P(f"{len(rows)} países con datos. {subtitle}. Los valores nulos no se representan como cero."),
        ]
    )


def _metric_cards(metrics: dict[str, Any]) -> list[Any]:
    labels = {
        "mean": "Media",
        "median": "Mediana",
        "max": "Máximo",
        "min": "Mínimo",
        "countries": "Países",
    }
    return [
        html.Div([html.Span(labels[key]), html.Strong(f"{value}%" if key != "countries" else str(value))], className="stats-metric-card")
        for key, value in metrics.items()
        if key in labels and value is not None
    ]


def _table_rows(result: dict[str, Any]) -> list[dict[str, Any]]:
    source = result.get("source")
    rows = result.get("ranking") or []
    output = []
    for index, row in enumerate(rows, start=1):
        output.append(
            {
                "ranking": index,
                "country": row.get("country"),
                "iso": row.get("iso"),
                "source": _source_display_name(source),
                "value": round(float(row.get("value")), 2) if isinstance(row.get("value"), (int, float)) else None,
            }
        )
    return output


def _table_columns(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    if not rows:
        return []
    labels = {
        "ranking": "Ranking",
        "country": "País",
        "iso": "ISO",
        "source": "Tipo de datos",
        "value": "Valor (%)",
    }
    return [{"name": labels.get(key, key), "id": key} for key in rows[0].keys()]


def _methodology_text(result: dict[str, Any], source: str) -> str:
    note = result.get("methodology") or ""
    if source == "FRA":
        note += " La puntuación de ILGA-Europe mide leyes y políticas. Los datos de la FRA proceden de respuestas de personas encuestadas. Ambas fuentes no son directamente equivalentes."
    return note


def _source_display_name(source: Any) -> str:
    if source == "FRA":
        return "Sociodemográficos"
    if source == "ILGA-Europe":
        return "Legales"
    return str(source or "")


def _data_type_selector_class(source: str | None) -> str:
    clean_source = source if source in {"fra", "ilga"} else "ilga"
    return f"stats-segmented-control stats-data-type-control stats-data-type-control--{clean_source}"


def _normalize_selected_countries(countries: list[str] | str | None) -> list[str]:
    values = countries if isinstance(countries, list) else [countries] if countries else []
    selected: list[str] = []
    seen: set[str] = set()
    for country in values:
        clean = str(country or "").strip()
        if not clean:
            continue
        key = normalize_country_code(clean) or clean
        if key in seen:
            continue
        seen.add(key)
        selected.append(clean)
    return selected


def _effective_query_mode(mode: str | None, selected_countries: list[str]) -> str:
    if len(selected_countries) > 1:
        return "compare"
    if len(selected_countries) == 1:
        return "one"
    return "all"


def _selection_scope(ranking: list[dict[str, Any]], selected_countries: list[str]) -> dict[str, Any]:
    if not selected_countries:
        return {"kind": "all", "title": "Europa", "subtitle": "Todos los países", "names": []}

    names = _selected_country_names(ranking, selected_countries)
    if len(names) == 1:
        return {"kind": "one", "title": names[0], "subtitle": names[0], "names": names}
    if len(names) <= 4:
        title = f"Comparación entre {', '.join(names)}"
        return {"kind": "compare", "title": title, "subtitle": ", ".join(names), "names": names}
    return {
        "kind": "compare",
        "title": f"Comparación de {len(names)} países seleccionados",
        "subtitle": ", ".join(names),
        "names": names,
    }


def _selected_country_names(ranking: list[dict[str, Any]], selected_countries: list[str]) -> list[str]:
    rows_by_iso = {
        normalize_country_code(row.get("iso")): str(row.get("country") or row.get("iso") or "").strip()
        for row in ranking
        if row.get("iso") or row.get("country")
    }
    rows_by_country = {
        str(row.get("country") or "").strip(): str(row.get("country") or "").strip()
        for row in ranking
        if row.get("country")
    }
    names: list[str] = []
    for country in selected_countries:
        iso = normalize_country_code(country)
        name = rows_by_iso.get(iso) or rows_by_country.get(str(country).strip()) or str(country).strip()
        if name and name not in names:
            names.append(name)
    return names


def _primary_figure_title(source: str, visualization: str, scope: dict[str, Any]) -> str:
    if source == "FRA" and visualization == "distribution":
        return f"Distribución de respuestas - {scope['title']}"
    if source == "ILGA-Europe" and visualization == "criteria":
        return f"Criterios jurídicos - {scope['title']}"
    if scope.get("kind") == "compare":
        return scope["title"]
    return f"Ranking - {scope['title']}"


def _secondary_figure_title(source: str, visualization: str, scope: dict[str, Any]) -> str:
    if source == "FRA" and visualization == "fra_ilga":
        return f"Relación sociodemográfica/legal - {scope['title']}"
    if source == "FRA":
        return f"Detalle de respuestas - {scope['title']}"
    return f"Detalle jurídico - {scope['title']}"


def _set_figure_title(figure: Any, title: str) -> None:
    figure.update_layout(
        title={
            "text": title,
            "x": 0.01,
            "xanchor": "left",
            "font": {"size": 16},
        },
        margin={**figure.layout.margin.to_plotly_json(), "t": 52},
    )


def _first_year(rows: list[dict[str, Any]]) -> int | None:
    for row in rows:
        year = _safe_int(row.get("year"))
        if year:
            return year
    return None


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _fra_indicator_option_label(indicator: Any) -> str:
    detail = str(indicator.specific_category or "").strip()
    if detail:
        return f"{detail} - {indicator.question}"
    return indicator.question or indicator.code
