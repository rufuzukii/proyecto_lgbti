from __future__ import annotations

from typing import Any

import dash_leaflet as dl

from app.analytics.figures import (
    build_cached_matplotlib_ranking_image,
    build_fra_country_bar,
    build_ilga_mapbox_figure,
    build_ilga_ranking_bar,
)
from app.analytics.geography import build_ilga_geodataframe
from app.analytics.repository import (
    get_fra_categories,
    get_fra_indicator_answers,
    get_fra_mongo_indicators_by_category,
    get_latest_ilga_document,
)
from app.dash.compat import Dash, Input, Output, dcc, html
from app.dash.layouts.navigation import build_navbar


def build_statistics_layout() -> html.Div:
    categories = get_fra_categories()
    ilga_document = get_latest_ilga_document()
    geodataframe = build_ilga_geodataframe(ilga_document)

    return html.Div(
        [
            build_navbar(active="statistics"),
            html.Main(
                [
                    html.Header(
                        [
                            html.P("Panel exploratorio", className="stats-eyebrow"),
                            html.H1("Estadísticas europeas LGBTIQ+"),
                            html.P(
                                "",
                                className="stats-lead",
                            ),
                        ],
                        className="stats-header",
                    ),
                    html.Section(
                        [
                            html.Div(
                                [
                                    html.Label("Categoría", htmlFor="fra-category-select"),
                                    dcc.Dropdown(
                                        id="fra-category-select",
                                        options=[
                                            {"label": category, "value": category}
                                            for category in categories
                                        ],
                                        value=None,
                                        clearable=True,
                                        placeholder="Selecciona una categoría",
                                    ),
                                ],
                                className="stats-control-field",
                            ),
                            html.Div(
                                [
                                    html.Label(
                                        "Tópico",
                                        htmlFor="fra-indicator-select",
                                    ),
                                    dcc.Dropdown(
                                        id="fra-indicator-select",
                                        options=[],
                                        value=None,
                                        clearable=False,
                                        disabled=True,
                                        placeholder="Selecciona primero una categoría",
                                    ),
                                ],
                                className="stats-control-field",
                            ),
                            html.P(
                                "Selecciona una categoría y después un tópico",
                                id="fra-indicator-summary",
                                className="stats-control-summary",
                            ),
                        ],
                        className="stats-controls",
                    ),
                    html.Section(
                        [
                            _panel(
                                "Distribución FRA por país · Plotly",
                                dcc.Graph(
                                    id="fra-indicator-chart",
                                    figure=build_fra_country_bar(None),
                                    config={"displaylogo": False},
                                ),
                                "stats-panel stats-panel-wide",
                            ),
                            _panel(
                                "Ranking ILGA · Plotly",
                                dcc.Graph(
                                    figure=build_ilga_ranking_bar(ilga_document),
                                    config={"displaylogo": False},
                                ),
                            ),
                            _panel(
                                "Mapa de puntos · Dash-Leaflet",
                                dl.Map(
                                    [
                                        dl.TileLayer(),
                                        dl.LayerGroup(_leaflet_markers(geodataframe)),
                                    ],
                                    center=[53, 15],
                                    zoom=3,
                                    className="stats-leaflet-map",
                                ),
                            ),
                            _panel(
                                "Mapa cartográfico · Plotly Mapbox",
                                dcc.Graph(
                                    figure=build_ilga_mapbox_figure(ilga_document),
                                    className="stats-mapbox-graph",
                                    config={"displaylogo": False},
                                ),
                            ),
                            _panel(
                                "Vista exportable · Matplotlib",
                                html.Img(
                                    src=build_cached_matplotlib_ranking_image(
                                        ilga_document.get("year")
                                        if isinstance(ilga_document, dict)
                                        else None
                                    ),
                                    className="stats-matplotlib-image",
                                    alt="Ranking ILGA generado con Matplotlib",
                                ),
                            ),
                            _panel(
                                "Resumen espacial · GeoPandas",
                                _geopandas_summary(geodataframe),
                            ),
                        ],
                        className="stats-grid",
                    ),
                ],
                className="stats-shell",
            ),
        ]
    )


def register_statistics_callbacks(app: Dash) -> None:
    @app.callback(
        Output("fra-indicator-select", "options"),
        Output("fra-indicator-select", "value"),
        Output("fra-indicator-select", "disabled"),
        Output("fra-indicator-select", "placeholder"),
        Input("fra-category-select", "value"),
    )
    def update_fra_documents(category: str | None):
        if not category:
            return [], None, True, "Selecciona primero una categoría"

        indicators = get_fra_mongo_indicators_by_category(category)
        if not indicators:
            return [], None, True, "No hay documentos para esta categoría"

        options = [
            {"label": _fra_indicator_option_label(indicator), "value": indicator.code}
            for indicator in indicators
        ]
        return options, None, False, "Selecciona un tópico"

    @app.callback(
        Output("fra-indicator-chart", "figure"),
        Output("fra-indicator-summary", "children"),
        Input("fra-indicator-select", "value"),
    )
    def update_fra_indicator(code: str | None):
        if not code:
            return (
                build_fra_country_bar(None),
                "Selecciona una categoría y después un tópico.",
            )
        document = get_fra_indicator_answers(code or "")
        return build_fra_country_bar(document), _fra_summary(document)


def _panel(title: str, content: Any, class_name: str = "stats-panel") -> html.Section:
    return html.Section(
        [
            html.H2(title),
            content,
        ],
        className=class_name,
    )


def _leaflet_markers(geodataframe) -> list:
    markers = []
    for row in geodataframe.itertuples():
        markers.append(
            dl.CircleMarker(
                center=[row.latitude, row.longitude],
                radius=5 + (row.ranking / 25),
                color="#1f6759",
                fill=True,
                fillColor="#46a58e",
                fillOpacity=0.75,
                children=[
                    dl.Tooltip(f"{row.country}: {row.ranking:.2f}%"),
                ],
            )
        )
    return markers


def _geopandas_summary(geodataframe) -> html.Div:
    if geodataframe.empty:
        return html.P("No hay geometrías disponibles.")
    bounds = geodataframe.total_bounds
    return html.Div(
        [
            html.Div(
                [
                    html.Strong(str(len(geodataframe))),
                    html.Span("puntos geográficos"),
                ],
                className="stats-spatial-metric",
            ),
            html.P(
                f"CRS: {geodataframe.crs}. Extensión: "
                f"{bounds[0]:.1f}, {bounds[1]:.1f} - "
                f"{bounds[2]:.1f}, {bounds[3]:.1f}."
            ),
        ],
        className="stats-spatial-summary",
    )


def _fra_summary(document: dict[str, Any] | None) -> str:
    if not isinstance(document, dict):
        return "No se han encontrado valores FRA para este indicador."
    return (
        f"{document.get('category', '')} · "
        f"{document.get('specific_category', '')} · "
        f"{len(document.get('answers', []))} observaciones"
    )


def _fra_indicator_option_label(indicator) -> str:
    detail = indicator.specific_category.strip()
    if detail:
        return f"{detail} Â· {indicator.question}"
    return indicator.question or indicator.code
