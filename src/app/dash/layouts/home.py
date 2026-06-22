from __future__ import annotations

from app.analytics.figures import build_ilga_choropleth
from app.analytics.repository import get_fra_indicators, get_latest_ilga_document
from app.dash.compat import dcc, html
from app.dash.i18n import text_attrs
from app.dash.layouts.navigation import build_navbar


def build_home_layout() -> html.Div:
    ilga_document = get_latest_ilga_document()
    indicators = get_fra_indicators()
    countries = (
        ilga_document.get("countries", [])
        if isinstance(ilga_document, dict)
        else []
    )
    year = ilga_document.get("year") if isinstance(ilga_document, dict) else None
    map_figure = build_ilga_choropleth(ilga_document)
    map_copy_es = (
        f"Ranking oficial de {year}, leído desde Indicator_ilga en MongoDB."
        if year
        else "No hay un Rainbow Map disponible."
    )
    map_copy_en = (
        f"Official {year} ranking, read from Indicator_ilga in MongoDB."
        if year
        else "No Rainbow Map is available yet."
    )

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
                                                "ILGA Europe Rainbow Map",
                                                className="home-map-eyebrow",
                                                **text_attrs(
                                                    "ILGA Europe Rainbow Map",
                                                    "ILGA Europe Rainbow Map",
                                                ),
                                            ),
                                            html.H1(
                                                "Situación legal LGBTIQ+ en Europa",
                                                className="home-map-heading",
                                                **text_attrs(
                                                    "Situación legal LGBTIQ+ en Europa",
                                                    "LGBTIQ+ legal situation in Europe",
                                                ),
                                            ),
                                            html.P(
                                                map_copy_es,
                                                className="home-map-copy",
                                                **text_attrs(map_copy_es, map_copy_en),
                                            ),
                                        ],
                                        className="home-map-intro",
                                    ),
                                    html.Div(
                                        [
                                            _metric(str(year or "-"), "Año", "Year"),
                                            _metric(
                                                str(len(countries)),
                                                "Países",
                                                "Countries",
                                            ),
                                            _metric(
                                                str(len(indicators)),
                                                "Indicadores FRA",
                                                "FRA indicators",
                                            ),
                                        ],
                                        className="home-map-metrics",
                                    ),
                                ],
                                className="home-map-header",
                            ),
                            dcc.Graph(
                                id="europe-map",
                                figure=map_figure,
                                className="home-europe-map",
                                config={
                                    "displayModeBar": True,
                                    "displaylogo": False,
                                    "scrollZoom": True,
                                    "modeBarButtonsToRemove": [
                                        "lasso2d",
                                        "select2d",
                                    ],
                                },
                            ),
                            html.Div(
                                [
                                    html.Span(
                                        "Fuente: ILGA Europe",
                                        className="home-map-source",
                                        **text_attrs(
                                            "Fuente: ILGA Europe",
                                            "Source: ILGA Europe",
                                        ),
                                    ),
                                    html.A(
                                        "Abrir estadísticas",
                                        href="/statistics",
                                        className="home-map-link",
                                        **text_attrs(
                                            "Abrir estadísticas",
                                            "Open statistics",
                                        ),
                                    ),
                                ],
                                className="home-map-footer",
                            ),
                        ],
                        className="home-map-stage",
                    ),
                    html.Section(
                        [
                            html.Div(
                                [
                                    html.H2(
                                        "Explora los indicadores FRA",
                                        **text_attrs(
                                            "Explora los indicadores FRA",
                                            "Explore FRA indicators",
                                        ),
                                    ),
                                    html.P(
                                        (
                                            "El catálogo se consulta en PostgreSQL y "
                                            "los porcentajes asociados se recuperan desde "
                                            "MongoDB mediante el código del indicador."
                                        ),
                                        **text_attrs(
                                            (
                                                "El catálogo se consulta en PostgreSQL y "
                                                "los porcentajes asociados se recuperan desde "
                                                "MongoDB mediante el código del indicador."
                                            ),
                                            (
                                                "The catalog is read from PostgreSQL and "
                                                "the related percentages are retrieved from "
                                                "MongoDB through the indicator code."
                                            ),
                                        ),
                                    ),
                                    html.A(
                                        "Ver panel de análisis",
                                        href="/statistics",
                                        className="home-analysis-link",
                                        **text_attrs(
                                            "Ver panel de análisis",
                                            "View analysis panel",
                                        ),
                                    ),
                                ],
                                className="home-analysis-band",
                            )
                        ]
                    ),
                ],
                className="home-data-shell",
            ),
        ]
    )


def _metric(value: str, label_es: str, label_en: str) -> html.Div:
    return html.Div(
        [
            html.Strong(value),
            html.Span(label_es, **text_attrs(label_es, label_en)),
        ],
        className="home-map-metric",
    )
