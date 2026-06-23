from __future__ import annotations

from io import BytesIO
import base64
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import plotly.graph_objects as go

from app.analytics.repository import get_latest_ilga_document
from app.cache import cache


def build_ilga_choropleth(document: dict[str, Any] | None) -> go.Figure:
    countries = _countries(document)
    figure = go.Figure()
    if countries:
        figure.add_trace(
            go.Choropleth(
                locations=[country["country"] for country in countries],
                locationmode="country names",
                z=[country["ranking"] for country in countries],
                customdata=[country["country_code"] for country in countries],
                zmin=0,
                zmax=100,
                colorscale=[
                    [0.0, "#d73027"],
                    [0.35, "#fdae61"],
                    [0.6, "#fee08b"],
                    [0.8, "#66c2a5"],
                    [1.0, "#177245"],
                ],
                marker={"line": {"color": "#ffffff", "width": 0.7}},
                colorbar={
                    "title": "Ranking",
                    "ticksuffix": "%",
                    "thickness": 13,
                },
                hovertemplate=(
                    "<b>%{location}</b><br>"
                    "Código: %{customdata}<br>"
                    "Ranking ILGA: %{z:.2f}%<extra></extra>"
                ),
            )
        )
    else:
        figure.add_annotation(
            text="No hay datos ILGA disponibles en MongoDB.",
            x=0.5,
            y=0.5,
            xref="paper",
            yref="paper",
            showarrow=False,
            font={"size": 18, "color": "#5f6672"},
        )

    figure.update_layout(
        margin={"l": 0, "r": 0, "t": 0, "b": 0},
        geo={
            "scope": "europe",
            "projection_type": "natural earth",
            "showframe": False,
            "showcoastlines": True,
            "coastlinecolor": "#b9c0ca",
            "showland": True,
            "landcolor": "#edf1f4",
            "showocean": True,
            "oceancolor": "#dcebf2",
            "bgcolor": "#ffffff",
        },
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        font={"family": "Segoe UI, Arial, sans-serif", "color": "#252a31"},
        uirevision="ilga-europe",
    )
    return figure


def build_ilga_ranking_bar(document: dict[str, Any] | None, limit: int = 12) -> go.Figure:
    countries = sorted(
        _countries(document),
        key=lambda country: country["ranking"],
        reverse=True,
    )[:limit]
    figure = go.Figure(
        go.Bar(
            x=[country["ranking"] for country in countries],
            y=[country["country"] for country in reversed(countries)],
            orientation="h",
            marker={"color": "#167d68"},
            hovertemplate="<b>%{y}</b><br>%{x:.2f}%<extra></extra>",
        )
    )
    figure.update_layout(
        margin={"l": 10, "r": 20, "t": 20, "b": 35},
        xaxis={"title": "Ranking ILGA (%)", "range": [0, 100]},
        yaxis={"title": ""},
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        showlegend=False,
    )
    return figure


def build_fra_country_bar(document: dict[str, Any] | None) -> go.Figure:
    answers = _aggregate_fra_answers(document)
    answers = sorted(answers, key=lambda item: item["percentage"], reverse=True)
    figure = go.Figure(
        go.Bar(
            x=[item["country"] for item in answers],
            y=[item["percentage"] for item in answers],
            marker={"color": "#a55233"},
            customdata=[item["observations"] for item in answers],
            hovertemplate=(
                "<b>%{x}</b><br>Media: %{y:.2f}%"
                "<br>Observaciones: %{customdata}<extra></extra>"
            ),
        )
    )
    figure.update_layout(
        margin={"l": 45, "r": 20, "t": 20, "b": 100},
        xaxis={"tickangle": -45, "title": ""},
        yaxis={"title": "Porcentaje medio", "range": [0, 100]},
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        showlegend=False,
    )
    return figure


def build_fra_choropleth(document: dict[str, Any] | None) -> go.Figure:
    answers = _aggregate_fra_answers(document)
    figure = go.Figure()
    if answers:
        figure.add_trace(
            go.Choropleth(
                locations=[item["country"] for item in answers],
                locationmode="country names",
                z=[item["percentage"] for item in answers],
                customdata=[item["observations"] for item in answers],
                zmin=0,
                zmax=100,
                colorscale=[
                    [0.0, "#f7fbff"],
                    [0.25, "#c6dbef"],
                    [0.5, "#6baed6"],
                    [0.75, "#2171b5"],
                    [1.0, "#08306b"],
                ],
                marker={"line": {"color": "#ffffff", "width": 0.7}},
                colorbar={
                    "title": "Media",
                    "ticksuffix": "%",
                    "thickness": 13,
                },
                hovertemplate=(
                    "<b>%{location}</b><br>"
                    "Media FRA: %{z:.2f}%<br>"
                    "Observaciones: %{customdata}<extra></extra>"
                ),
            )
        )
    else:
        figure.add_annotation(
            text="Selecciona un indicador FRA con valores por pais.",
            x=0.5,
            y=0.5,
            xref="paper",
            yref="paper",
            showarrow=False,
            font={"size": 18, "color": "#5f6672"},
        )

    figure.update_layout(
        margin={"l": 0, "r": 0, "t": 0, "b": 0},
        geo={
            "scope": "europe",
            "projection_type": "natural earth",
            "showframe": False,
            "showcoastlines": True,
            "coastlinecolor": "#b9c0ca",
            "showland": True,
            "landcolor": "#edf1f4",
            "showocean": True,
            "oceancolor": "#dcebf2",
            "bgcolor": "#ffffff",
        },
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        font={"family": "Segoe UI, Arial, sans-serif", "color": "#252a31"},
        uirevision="fra-europe",
    )
    return figure


def build_matplotlib_ranking_image(document: dict[str, Any] | None) -> str:
    countries = sorted(
        _countries(document),
        key=lambda country: country["ranking"],
        reverse=True,
    )[:8]
    figure, axis = plt.subplots(figsize=(7.2, 3.8))
    names = [country["country"] for country in reversed(countries)]
    values = [country["ranking"] for country in reversed(countries)]
    axis.barh(names, values, color="#287a6a")
    axis.set_xlim(0, 100)
    axis.set_xlabel("Ranking ILGA (%)")
    axis.spines[["top", "right", "left"]].set_visible(False)
    axis.grid(axis="x", alpha=0.2)
    figure.tight_layout()

    buffer = BytesIO()
    figure.savefig(buffer, format="png", dpi=130, transparent=False)
    plt.close(figure)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


@cache.memoize()
def build_cached_matplotlib_ranking_image(year: int | None) -> str:
    document = get_latest_ilga_document()
    if not isinstance(document, dict) or document.get("year") != year:
        document = None
    return build_matplotlib_ranking_image(document)


def build_ilga_mapbox_figure(document: dict[str, Any] | None) -> go.Figure:
    from app.analytics.geography import build_ilga_geodataframe

    geodataframe = build_ilga_geodataframe(document)
    figure = go.Figure()
    if not geodataframe.empty:
        figure.add_trace(
            go.Scattermapbox(
                lat=geodataframe["latitude"],
                lon=geodataframe["longitude"],
                text=geodataframe["country"],
                customdata=geodataframe[["country_code", "ranking"]].to_numpy(),
                marker={
                    "size": 10,
                    "color": geodataframe["ranking"],
                    "colorscale": "RdYlGn",
                    "cmin": 0,
                    "cmax": 100,
                    "showscale": True,
                    "colorbar": {"title": "Ranking"},
                },
                hovertemplate=(
                    "<b>%{text}</b><br>"
                    "Código: %{customdata[0]}<br>"
                    "Ranking: %{customdata[1]:.2f}%<extra></extra>"
                ),
            )
        )
    figure.update_layout(
        mapbox={
            "style": "open-street-map",
            "center": {"lat": 53, "lon": 15},
            "zoom": 2.25,
        },
        margin={"l": 0, "r": 0, "t": 0, "b": 0},
        paper_bgcolor="#ffffff",
    )
    return figure


def _countries(document: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(document, dict):
        return []
    output = []
    for country in document.get("countries", []):
        if not isinstance(country, dict):
            continue
        ranking = country.get("ranking")
        if not isinstance(ranking, (int, float)):
            continue
        output.append(
            {
                "country": str(country.get("country") or "").strip(),
                "country_code": str(country.get("country_code") or "").strip(),
                "ranking": float(ranking),
            }
        )
    return [country for country in output if country["country"]]


def _aggregate_fra_answers(document: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(document, dict):
        return []
    grouped: dict[str, list[float]] = {}
    for answer in document.get("answers", []):
        if not isinstance(answer, dict):
            continue
        country = str(answer.get("country") or "").strip()
        percentage = answer.get("percentage")
        if country and isinstance(percentage, (int, float)):
            grouped.setdefault(country, []).append(float(percentage))
    return [
        {
            "country": country,
            "percentage": sum(values) / len(values),
            "observations": len(values),
        }
        for country, values in grouped.items()
    ]
