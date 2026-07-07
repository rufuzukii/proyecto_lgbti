from __future__ import annotations

from typing import Any

from app.analytics.figures import (
    build_fra_answer_distribution,
    build_fra_choropleth,
    build_fra_country_answer_bar,
    build_fra_filter_heatmap,
    build_ilga_category_heatmap,
    build_ilga_category_map,
    build_ilga_category_score_bar,
    build_ilga_indicator_coverage_bar,
)
from app.analytics.repository import (
    assert_analytics_databases_available,
    get_fra_categories,
    get_fra_indicator_answers,
    get_fra_mongo_indicators_by_category,
    get_latest_ilga_criteria_categories,
    get_latest_ilga_document,
)
from app.dash.compat import Dash, Input, Output, dcc, html
from app.dash.layouts.navigation import build_navbar


ILGA_CATEGORY_ALIASES = {
    "asylum": "Asylum",
    "civilsocietyspace": "Civil society space",
    "equalityandnondiscrimination": "Equality & non-discrimination",
    "equalitynondiscrimination": "Equality & non-discrimination",
    "family": "Family",
    "hatecrimeandhatespeech": "Hate crime & hate speech",
    "hatecrimehatespeech": "Hate crime & hate speech",
    "intersexrights": "Intersex bodily integrity",
    "intersexbodilyintegrity": "Intersex bodily integrity",
    "legalgenderrecognition": "Legal gender recognition",
}

STATS_VIEW_OPTIONS = [
    {"label": "Situacion legal LGBTIQ+ en Europa", "value": "ilga"},
    {"label": "Discriminacion y datos sociales", "value": "fra"},
]


def build_statistics_layout() -> html.Div:
    assert_analytics_databases_available()
    categories = _category_options_for_view("ilga")
    initial_category = categories[0]["value"] if categories else None

    return html.Div(
        [
            build_navbar(active="statistics"),
            html.Main(
                [
                    html.Header(
                        [
                            html.P("Panel exploratorio", className="stats-eyebrow"),
                            html.H1("Estadisticas europeas LGBTIQ+"),
                            html.P(
                                "Elige una vista y explora los graficos disponibles "
                                "para sus categorias.",
                                className="stats-lead",
                            ),
                        ],
                        className="stats-header",
                    ),
                    html.Section(
                        [
                            html.Div(
                                [
                                    html.Label("Vista", htmlFor="stats-view-select"),
                                    dcc.Dropdown(
                                        id="stats-view-select",
                                        options=STATS_VIEW_OPTIONS,
                                        value="ilga",
                                        clearable=False,
                                        placeholder="Selecciona una vista",
                                    ),
                                ],
                                className="stats-control-field",
                            ),
                            html.Div(
                                [
                                    html.Label("Categoria", htmlFor="stats-category-select"),
                                    dcc.Dropdown(
                                        id="stats-category-select",
                                        options=categories,
                                        value=initial_category,
                                        clearable=False,
                                        placeholder="Selecciona una categoria",
                                    ),
                                ],
                                className="stats-control-field",
                            ),
                            html.Div(
                                [
                                    html.Label("Topico", htmlFor="fra-indicator-select"),
                                    dcc.Dropdown(
                                        id="fra-indicator-select",
                                        options=[],
                                        value=None,
                                        clearable=False,
                                        disabled=True,
                                        placeholder="Elige una categoria de datos sociales",
                                    ),
                                ],
                                id="stats-topic-field",
                                className="stats-control-field",
                            ),
                            html.P(
                                "Elige una vista para cargar sus categorias y explorar los graficos disponibles.",
                                id="fra-indicator-summary",
                                className="stats-control-summary",
                            ),
                        ],
                        className="stats-controls",
                    ),
                    html.Section(
                        id="stats-visualization-grid",
                        className="stats-grid",
                        children=[
                            _empty_state(
                                "Selecciona una categoria",
                                "El panel mostrara graficos legales o sociales segun la vista elegida.",
                            )
                        ],
                    ),
                ],
                className="stats-shell",
            ),
        ]
    )


def register_statistics_callbacks(app: Dash) -> None:
    @app.callback(
        Output("stats-category-select", "options"),
        Output("stats-category-select", "value"),
        Output("stats-category-select", "placeholder"),
        Input("stats-view-select", "value"),
    )
    def update_category_selector(view: str | None):
        options = _category_options_for_view(view)
        value = options[0]["value"] if options else None
        if view == "fra":
            placeholder = "Selecciona una categoria de datos sociales"
        else:
            placeholder = "Selecciona una categoria legal"
        return options, value, placeholder

    @app.callback(
        Output("fra-indicator-select", "options"),
        Output("fra-indicator-select", "value"),
        Output("fra-indicator-select", "disabled"),
        Output("fra-indicator-select", "placeholder"),
        Output("stats-topic-field", "className"),
        Input("stats-view-select", "value"),
        Input("stats-category-select", "value"),
    )
    def update_topic_selector(view: str | None, category: str | None):
        if view != "fra":
            return (
                [],
                None,
                True,
                "Esta vista muestra categorias legales completas",
                "stats-control-field stats-control-field-hidden",
            )

        if not category:
            return [], None, True, "Selecciona una categoria", "stats-control-field"

        indicators = get_fra_mongo_indicators_by_category(category)
        if indicators:
            options = [
                {"label": _fra_indicator_option_label(indicator), "value": indicator.code}
                for indicator in indicators
            ]
            return options, indicators[0].code, False, "Selecciona un topico", "stats-control-field"

        return [], None, True, "No hay topicos para esta categoria", "stats-control-field"

    @app.callback(
        Output("stats-visualization-grid", "children"),
        Output("fra-indicator-summary", "children"),
        Input("stats-view-select", "value"),
        Input("stats-category-select", "value"),
        Input("fra-indicator-select", "value"),
    )
    def update_statistics_grid(view: str | None, category: str | None, code: str | None):
        if not category:
            return (
                [_empty_state("Sin categoria", "Selecciona una categoria para empezar.")],
                "Elige una vista para cargar sus categorias y explorar los graficos disponibles.",
            )

        if view == "fra":
            fra_indicators = get_fra_mongo_indicators_by_category(category)
            if not fra_indicators:
                return (
                    [
                        _empty_state(
                            "Datos no disponibles",
                            "Esta categoria todavia no tiene topicos importados.",
                        )
                    ],
                    f"{category}: sin topicos importados.",
                )
            resolved_code = code or fra_indicators[0].code
            document = get_fra_indicator_answers(resolved_code)
            return _fra_panels(document), _fra_summary(document)

        ilga_categories = get_latest_ilga_criteria_categories()
        ilga_category = _resolve_ilga_category(category, ilga_categories)
        if ilga_category is not None:
            document = get_latest_ilga_document()
            return (
                _ilga_panels(document, ilga_category, category),
                _ilga_summary(document, ilga_category, category),
            )

        return (
            [
                _empty_state(
                    "Datos no disponibles",
                    "Esta categoria todavia no tiene datos importados para la vista seleccionada.",
                )
            ],
            f"{category}: sin datos importados.",
        )


def _fra_panels(document: dict[str, Any] | None) -> list[Any]:
    selected_answer = _default_fra_answer(document)
    answer_suffix = f" - {selected_answer}" if selected_answer else ""
    return [
        _panel(
            "Resumen del topico",
            _fra_metric_cards(document),
            "stats-panel stats-panel-wide",
        ),
        _panel(
            "Distribucion de respuestas",
            dcc.Graph(
                figure=build_fra_answer_distribution(document),
                config={"displaylogo": False},
            ),
        ),
        _panel(
            f"Ranking por pais{answer_suffix}",
            dcc.Graph(
                figure=build_fra_country_answer_bar(document, selected_answer),
                config={"displaylogo": False},
            ),
        ),
        _panel(
            f"Mapa europeo{answer_suffix}",
            dcc.Graph(
                figure=build_fra_choropleth(document, selected_answer),
                config={"displaylogo": False},
            ),
            "stats-panel stats-panel-wide",
        ),
        _panel(
            "Cruce por filtro demografico",
            dcc.Graph(
                figure=build_fra_filter_heatmap(document),
                config={"displaylogo": False},
            ),
            "stats-panel stats-panel-wide",
        ),
    ]


def _ilga_panels(
    document: dict[str, Any] | None,
    ilga_category: str,
    selected_category: str,
) -> list[Any]:
    title_category = ilga_category or _display_category_name(selected_category)
    return [
        _panel(
            "Resumen legal",
            _ilga_metric_cards(document, ilga_category, selected_category),
            "stats-panel stats-panel-wide",
        ),
        _panel(
            f"Mapa legal - {title_category}",
            dcc.Graph(
                figure=build_ilga_category_map(document, ilga_category),
                config={"displaylogo": False},
            ),
            "stats-panel stats-panel-wide",
        ),
        _panel(
            "Ranking por pais",
            dcc.Graph(
                figure=build_ilga_category_score_bar(document, ilga_category),
                config={"displaylogo": False},
            ),
        ),
        _panel(
            "Cobertura por indicador",
            dcc.Graph(
                figure=build_ilga_indicator_coverage_bar(document, ilga_category),
                config={"displaylogo": False},
            ),
        ),
        _panel(
            "Matriz pais / indicador",
            dcc.Graph(
                figure=build_ilga_category_heatmap(document, ilga_category),
                config={"displaylogo": False},
            ),
            "stats-panel stats-panel-wide",
        ),
    ]


def _panel(title: str, content: Any, class_name: str = "stats-panel") -> html.Section:
    return html.Section(
        [
            html.H2(title),
            content,
        ],
        className=class_name,
    )


def _empty_state(title: str, message: str) -> html.Section:
    return html.Section(
        [
            html.H2(title),
            html.P(message),
        ],
        className="stats-panel stats-panel-wide stats-empty-state",
    )


def _fra_metric_cards(document: dict[str, Any] | None) -> html.Div:
    rows = _fra_answer_rows(document)
    countries = {row["country"] for row in rows}
    answers = {row["answer"] for row in rows}
    filter_types = {
        item["type"]
        for row in rows
        for item in row["filters"]
        if item["type"] != "All"
    }
    return _metric_row(
        [
            ("Fuente", "Datos sociales"),
            ("Paises", str(len(countries))),
            ("Respuestas", str(len(answers))),
            ("Observaciones", str(len(rows))),
            ("Filtros", str(len(filter_types))),
        ]
    )


def _ilga_metric_cards(
    document: dict[str, Any] | None,
    ilga_category: str,
    selected_category: str,
) -> html.Div:
    countries = document.get("countries", []) if isinstance(document, dict) else []
    criteria_count = 0
    for country in countries:
        if not isinstance(country, dict):
            continue
        for criterion in country.get("criteria") or []:
            if not isinstance(criterion, dict):
                continue
            if not ilga_category or _category_key(criterion.get("category")) == _category_key(ilga_category):
                criteria_count += 1
    return _metric_row(
        [
            ("Fuente", "Marco legal"),
            ("Categoria", ilga_category or _display_category_name(selected_category)),
            ("Ano", str(document.get("year", "-") if isinstance(document, dict) else "-")),
            ("Paises", str(len(countries))),
            ("Criterios", str(criteria_count)),
        ]
    )


def _metric_row(items: list[tuple[str, str]]) -> html.Div:
    return html.Div(
        [
            html.Div(
                [
                    html.Span(label),
                    html.Strong(value),
                ],
                className="stats-metric-card",
            )
            for label, value in items
        ],
        className="stats-metric-row",
    )


def _fra_summary(document: dict[str, Any] | None) -> str:
    if not isinstance(document, dict):
        return "No se han encontrado valores para este topico."
    return (
        f"Datos sociales - {document.get('category', '')} - "
        f"{document.get('specific_category', '')} - "
        f"{len(document.get('answers', []))} observaciones"
    )


def _ilga_summary(
    document: dict[str, Any] | None,
    ilga_category: str,
    selected_category: str,
) -> str:
    year = document.get("year") if isinstance(document, dict) else "-"
    return f"Situacion legal {year} - {ilga_category or _display_category_name(selected_category)}."


def _fra_indicator_option_label(indicator) -> str:
    detail = indicator.specific_category.strip()
    if detail:
        return f"{detail} - {indicator.question}"
    return indicator.question or indicator.code


def _resolve_ilga_category(
    selected_category: str | None,
    ilga_categories: list[str],
) -> str | None:
    if not selected_category:
        return None

    selected_key = _category_key(selected_category)
    if selected_key == "legal":
        return ""

    expected = ILGA_CATEGORY_ALIASES.get(selected_key, selected_category)
    expected_key = _category_key(expected)
    for category in ilga_categories:
        if _category_key(category) == expected_key:
            return category
    return None


def _category_options_for_view(view: str | None) -> list[dict[str, str]]:
    if view == "fra":
        return [
            {"label": category, "value": category}
            for category in get_fra_categories()
        ]

    options = [{"label": "Todas las categorias legales", "value": "legal"}]
    options.extend(
        {"label": category, "value": category}
        for category in get_latest_ilga_criteria_categories()
    )
    return options


def _display_category_name(category: str) -> str:
    if _category_key(category) == "legal":
        return "Todas las categorias legales"
    return category


def _category_key(value: Any) -> str:
    return "".join(ch for ch in str(value or "").lower() if ch.isalnum())


def _fra_answer_rows(document: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(document, dict):
        return []

    rows = []
    for answer in document.get("answers", []):
        if not isinstance(answer, dict):
            continue
        percentage = answer.get("percentage")
        country = str(answer.get("country") or "").strip()
        answer_value = str(answer.get("answer") or "").strip()
        if not country or not answer_value or not isinstance(percentage, (int, float)):
            continue
        rows.append(
            {
                "country": country,
                "answer": answer_value,
                "percentage": float(percentage),
                "filters": _clean_fra_filters(answer.get("filters")),
            }
        )
    return rows


def _clean_fra_filters(filters: Any) -> list[dict[str, str]]:
    if not isinstance(filters, list):
        return [{"type": "All", "value": "All"}]

    cleaned = []
    for item in filters:
        if not isinstance(item, dict):
            continue
        filter_type = str(item.get("type") or "").strip()
        filter_value = str(item.get("value") or "").strip()
        if filter_type and filter_value:
            cleaned.append({"type": filter_type, "value": filter_value})
    return cleaned or [{"type": "All", "value": "All"}]


def _default_fra_answer(document: dict[str, Any] | None) -> str | None:
    rows = _fra_answer_rows(document)
    answers = [row["answer"] for row in rows]
    for preferred in ("Yes", "Often", "Always", "Very often", "Never", "No"):
        if preferred in answers:
            return preferred
    return answers[0] if answers else None
