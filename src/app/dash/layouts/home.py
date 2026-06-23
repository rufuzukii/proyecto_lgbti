from __future__ import annotations

from typing import Any

from app.analytics.figures import build_fra_choropleth, build_ilga_choropleth
from app.analytics.repository import (
    FraIndicator,
    get_fra_categories,
    get_fra_indicator_answers,
    get_fra_mongo_indicators_by_category,
    get_ilga_document_by_year,
    get_ilga_years,
    get_latest_ilga_document,
)
from app.dash.compat import Dash, Input, Output, dcc, html
from app.dash.i18n import text, text_attrs
from app.dash.layouts.navigation import build_navbar


MAP_MODE_OPTIONS = [
    {"label": "Situacion legal LGBTIQ+ en Europa", "value": "ilga"},
    {"label": "FRA: discriminacion y datos sociales", "value": "fra"},
]


def build_home_layout() -> html.Div:
    ilga_document = get_latest_ilga_document()
    ilga_years = get_ilga_years()
    current_year = ilga_document.get("year") if isinstance(ilga_document, dict) else None
    if current_year and current_year not in ilga_years:
        ilga_years = [int(current_year), *ilga_years]

    categories = get_fra_categories()

    return html.Div(
        [
            build_navbar(active="home"),
            html.Main(
                [
                    html.Section(
                        [
                            html.Div(
                                [
                                    html.Div(
                                        [
                                            html.P(
                                                "RainbowLens",
                                                className="home-map-eyebrow",
                                                **text_attrs("RainbowLens", "RainbowLens"),
                                            ),
                                            html.H1(
                                                text("Mapa europeo LGBTIQ+", "European LGBTIQ+ map"),
                                                id="home-map-title",
                                                className="home-map-heading",
                                            ),
                                            html.P(
                                                _ilga_copy(ilga_document),
                                                id="home-map-copy",
                                                className="home-map-copy",
                                            ),
                                        ],
                                        className="home-map-intro",
                                    ),
                                    html.Div(
                                        _ilga_metrics(ilga_document),
                                        id="home-map-metrics",
                                        className="home-map-metrics",
                                    ),
                                ],
                                className="home-map-header",
                            ),
                            html.Div(
                                [
                                    _control_field(
                                        ("Vista del mapa", "Map view"),
                                        dcc.Dropdown(
                                            id="home-map-mode",
                                            options=MAP_MODE_OPTIONS,
                                            value="ilga",
                                            clearable=False,
                                            className="home-dropdown",
                                        ),
                                    ),
                                    _control_field(
                                        ("Año ILGA", "ILGA year"),
                                        dcc.Dropdown(
                                            id="home-ilga-year",
                                            options=[
                                                {"label": str(year), "value": year}
                                                for year in ilga_years
                                            ],
                                            value=current_year,
                                            clearable=False,
                                            disabled=not bool(ilga_years),
                                            className="home-dropdown",
                                        ),
                                        "home-ilga-control",
                                        "home-ilga-control",
                                    ),
                                    _control_field(
                                        ("Categoria FRA", "FRA category"),
                                        dcc.Dropdown(
                                            id="home-fra-category",
                                            options=[
                                                {"label": category, "value": category}
                                                for category in categories
                                            ],
                                            value=None,
                                            clearable=True,
                                            placeholder="Selecciona una categoria",
                                            disabled=True,
                                            className="home-dropdown",
                                        ),
                                        "home-fra-control",
                                        "home-fra-category-control",
                                    ),
                                    _control_field(
                                        ("Topico FRA", "FRA topic"),
                                        dcc.Dropdown(
                                            id="home-fra-indicator",
                                            options=[],
                                            value=None,
                                            clearable=False,
                                            disabled=True,
                                            placeholder="Selecciona primero una categoria",
                                            className="home-dropdown",
                                        ),
                                        "home-fra-control",
                                        "home-fra-indicator-control",
                                    ),
                                ],
                                className="home-map-controls",
                            ),
                            dcc.Graph(
                                id="home-main-map",
                                figure=build_ilga_choropleth(ilga_document),
                                className="home-europe-map",
                                config={
                                    "displayModeBar": True,
                                    "displaylogo": False,
                                    "scrollZoom": True,
                                    "modeBarButtonsToRemove": ["lasso2d", "select2d"],
                                },
                            ),
                            html.Div(
                                [
                                    html.Span(
                                        _ilga_source(ilga_document),
                                        id="home-map-source",
                                        className="home-map-source",
                                    ),
                                    html.A(
                                        text("Abrir estadisticas", "Open statistics"),
                                        href="/statistics",
                                        className="home-map-link",
                                    ),
                                ],
                                className="home-map-footer",
                            ),
                        ],
                        className="home-map-stage",
                    ),
                    html.Section(
                        [
                            _source_summary(
                                "ILGA Europe",
                                (
                                    "ILGA Europe analiza el marco legal y politico que afecta a "
                                    "las personas LGBTIQ+ en Europa. Su Rainbow Map resume areas "
                                    "como igualdad, familia, delitos de odio, reconocimiento legal "
                                    "de genero, integridad corporal, asilo y espacio de sociedad civil."
                                ),
                                (
                                    "ILGA Europe analyses the legal and policy framework affecting "
                                    "LGBTIQ+ people in Europe. Its Rainbow Map summarises areas such "
                                    "as equality, family, hate crime, legal gender recognition, bodily "
                                    "integrity, asylum and civil society space."
                                ),
                                ("Explorar el contexto legal", "Explore the legal context"),
                            ),
                            _source_summary(
                                "FRA",
                                (
                                    "La Agencia de los Derechos Fundamentales de la Union Europea "
                                    "recoge datos de encuesta sobre experiencias de discriminacion, "
                                    "seguridad, visibilidad, vida cotidiana y condiciones sociales. "
                                    "Estos indicadores ayudan a complementar el analisis legal con "
                                    "evidencia social."
                                ),
                                (
                                    "The European Union Agency for Fundamental Rights collects survey "
                                    "data on discrimination, safety, visibility, daily life and social "
                                    "conditions. These indicators complement legal analysis with social "
                                    "evidence."
                                ),
                                ("Ampliar metodologia FRA", "Expand FRA methodology"),
                            ),
                        ],
                        className="home-source-grid",
                    ),
                ],
                className="home-data-shell",
            ),
        ]
    )


def register_home_callbacks(app: Dash) -> None:
    @app.callback(
        Output("home-ilga-year", "disabled"),
        Output("home-fra-category", "disabled"),
        Output("home-ilga-control", "className"),
        Output("home-fra-category-control", "className"),
        Output("home-fra-indicator-control", "className"),
        Input("home-map-mode", "value"),
    )
    def update_home_control_state(mode: str | None):
        is_fra = mode == "fra"
        ilga_class = _control_class("home-ilga-control", inactive=is_fra)
        fra_category_class = _control_class("home-fra-control", inactive=not is_fra)
        fra_indicator_class = _control_class("home-fra-control", inactive=not is_fra)
        return is_fra, not is_fra, ilga_class, fra_category_class, fra_indicator_class

    @app.callback(
        Output("home-fra-indicator", "options"),
        Output("home-fra-indicator", "value"),
        Output("home-fra-indicator", "disabled"),
        Output("home-fra-indicator", "placeholder"),
        Input("home-map-mode", "value"),
        Input("home-fra-category", "value"),
    )
    def update_home_fra_indicators(mode: str | None, category: str | None):
        if mode != "fra":
            return [], None, True, "Activa la vista FRA"
        if not category:
            return [], None, True, "Selecciona primero una categoria"

        indicators = get_fra_mongo_indicators_by_category(category)
        if not indicators:
            return [], None, True, "No hay documentos para esta categoria"

        options = [
            {"label": _fra_indicator_option_label(indicator), "value": indicator.code}
            for indicator in indicators
        ]
        return options, None, False, "Selecciona un topico"

    @app.callback(
        Output("home-main-map", "figure"),
        Output("home-map-title", "children"),
        Output("home-map-copy", "children"),
        Output("home-map-source", "children"),
        Output("home-map-metrics", "children"),
        Input("home-map-mode", "value"),
        Input("home-ilga-year", "value"),
        Input("home-fra-indicator", "value"),
    )
    def update_home_map(mode: str | None, ilga_year: int | None, fra_code: str | None):
        if mode == "fra":
            document = get_fra_indicator_answers(fra_code or "")
            return (
                build_fra_choropleth(document),
                text("Mapa europeo de indicadores FRA", "European FRA indicators map"),
                _fra_copy(document),
                _fra_source(document),
                _fra_metrics(document),
            )

        document = get_ilga_document_by_year(ilga_year)
        return (
            build_ilga_choropleth(document),
            text("Situacion legal LGBTIQ+ en Europa", "LGBTIQ+ legal situation in Europe"),
            _ilga_copy(document),
            _ilga_source(document),
            _ilga_metrics(document),
        )


def _control_field(
    label: tuple[str, str],
    control: Any,
    class_name: str = "",
    field_id: str | None = None,
) -> html.Div:
    classes = ["home-control-field"]
    if class_name:
        classes.append(class_name)
    props = {"className": " ".join(classes)}
    if field_id:
        props["id"] = field_id
    return html.Div(
        [
            html.Label(text(label[0], label[1])),
            control,
        ],
        **props,
    )


def _control_class(base_class: str, *, inactive: bool) -> str:
    classes = ["home-control-field", base_class]
    if inactive:
        classes.append("is-inactive")
    return " ".join(classes)


def _metric(value: str, label_es: str, label_en: str) -> html.Div:
    return html.Div(
        [
            html.Strong(value),
            html.Span(label_es, **text_attrs(label_es, label_en)),
        ],
        className="home-map-metric",
    )


def _source_summary(
    title: str,
    body_es: str,
    body_en: str,
    link_label: tuple[str, str],
) -> html.Article:
    return html.Article(
        [
            html.H2(title),
            html.P(body_es, **text_attrs(body_es, body_en)),
            html.A(text(link_label[0], link_label[1]), href="/about", className="home-analysis-link"),
        ],
        className="home-source-card",
    )


def _ilga_copy(document: dict[str, Any] | None):
    if not isinstance(document, dict):
        return text("No hay un Rainbow Map disponible.", "No Rainbow Map is available.")
    year = document.get("year")
    if year:
        return text(
            f"Ranking oficial de {year}, leido desde Indicator_ilga en MongoDB.",
            f"Official {year} ranking, read from Indicator_ilga in MongoDB.",
        )
    return text(
        "Ranking legal LGBTIQ+ leido desde Indicator_ilga en MongoDB.",
        "LGBTIQ+ legal ranking read from Indicator_ilga in MongoDB.",
    )


def _ilga_source(document: dict[str, Any] | None):
    year = document.get("year") if isinstance(document, dict) else None
    if year:
        return text(f"Fuente: ILGA Europe - {year}", f"Source: ILGA Europe - {year}")
    return text("Fuente: ILGA Europe", "Source: ILGA Europe")


def _ilga_metrics(document: dict[str, Any] | None) -> list[html.Div]:
    countries = (
        document.get("countries", [])
        if isinstance(document, dict) and isinstance(document.get("countries"), list)
        else []
    )
    rankings = [
        float(country["ranking"])
        for country in countries
        if isinstance(country, dict) and isinstance(country.get("ranking"), (int, float))
    ]
    average = f"{sum(rankings) / len(rankings):.1f}%" if rankings else "-"
    year = document.get("year") if isinstance(document, dict) else None
    return [
        _metric(str(year or "-"), "Año", "Year"),
        _metric(str(len(countries)), "Paises", "Countries"),
        _metric(average, "Media ILGA", "ILGA average"),
    ]


def _fra_copy(document: dict[str, Any] | None):
    if not isinstance(document, dict):
        return text(
            "Selecciona una categoria y un topico FRA para representar sus valores por pais.",
            "Select a FRA category and topic to map values by country.",
        )
    label = (
        f"{document.get('category', '')} - "
        f"{document.get('specific_category', '')}"
    ).strip(" -")
    return text(label, label)


def _fra_source(document: dict[str, Any] | None):
    if not isinstance(document, dict):
        return text("Fuente: FRA", "Source: FRA")
    code = document.get("code", "indicador")
    return text(f"Fuente: FRA - {code}", f"Source: FRA - {code}")


def _fra_metrics(document: dict[str, Any] | None) -> list[html.Div]:
    answers = document.get("answers", []) if isinstance(document, dict) else []
    countries = {
        str(answer.get("country") or "").strip()
        for answer in answers
        if isinstance(answer, dict) and answer.get("country")
    }
    percentages = [
        float(answer["percentage"])
        for answer in answers
        if isinstance(answer, dict) and isinstance(answer.get("percentage"), (int, float))
    ]
    average = f"{sum(percentages) / len(percentages):.1f}%" if percentages else "-"
    return [
        _metric(str(len(countries)), "Paises", "Countries"),
        _metric(str(len(percentages)), "Observaciones", "Observations"),
        _metric(average, "Media FRA", "FRA average"),
    ]


def _fra_indicator_option_label(indicator: FraIndicator) -> str:
    detail = indicator.specific_category.strip()
    if detail:
        return f"{detail} - {indicator.question}"
    return indicator.question or indicator.code
