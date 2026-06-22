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
    get_fra_indicator_answers,
    get_fra_indicators,
    get_latest_ilga_document,
)
from app.dash.compat import Dash, Input, Output, dcc, html
from app.dash.layouts.navigation import build_navbar


def build_statistics_layout() -> html.Div:
    indicators = get_fra_indicators()
    ilga_document = get_latest_ilga_document()
    initial_code = indicators[0].code if indicators else None
    initial_fra = get_fra_indicator_answers(initial_code) if initial_code else None
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
                                "Catálogo FRA desde PostgreSQL y valores FRA/ILGA "
                                "desde MongoDB.",
                                className="stats-lead",
                            ),
                        ],
                        className="stats-header",
                    ),
                    html.Section(
                        [
                            html.Label("Indicador FRA", htmlFor="fra-indicator-select"),
                            dcc.Dropdown(
                                id="fra-indicator-select",
                                options=[
                                    {"label": indicator.label, "value": indicator.code}
                                    for indicator in indicators
                                ],
                                value=initial_code,
                                clearable=False,
                                placeholder="No hay indicadores disponibles",
                            ),
                            html.P(
                                _fra_summary(initial_fra),
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
                                    figure=build_fra_country_bar(initial_fra),
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
        Output("fra-indicator-chart", "figure"),
        Output("fra-indicator-summary", "children"),
        Input("fra-indicator-select", "value"),
    )
    def update_fra_indicator(code: str | None):
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
