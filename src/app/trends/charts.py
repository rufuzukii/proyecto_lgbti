from __future__ import annotations

from typing import Any

import plotly.graph_objects as go

from app.analytics.statistics.common_layout import apply_base_layout
from app.dash.i18n import country_labels, ui_text
from app.trends.models import ForecastResult

HISTORICAL_COLOR = "#2F6BDE"
FORECAST_COLOR = "#C62878"
UNCERTAINTY_COLOR = "rgba(198, 40, 120, 0.16)"


def build_trend_figure(result: ForecastResult, *, language: str = "es") -> go.Figure:
    if not result.historical:
        raise ValueError("trend_analysis_not_renderable")
    country = country_labels(result.country_code, result.country_name)[
        1 if language == "en" else 0
    ]
    actual_by_year = {
        int(point.year): float(point.value)
        for point in result.historical
        if point.year is not None and point.value is not None
    }
    first_year = min(actual_by_year)
    last_year = max(actual_by_year)
    dense_years = list(range(first_year, last_year + 1))
    dense_values = [actual_by_year.get(year) for year in dense_years]
    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=dense_years,
            y=dense_values,
            mode="lines+markers",
            name=ui_text("trends_historical_data", language),
            connectgaps=False,
            line={"color": HISTORICAL_COLOR, "width": 3},
            marker={"color": HISTORICAL_COLOR, "size": 8},
            customdata=[
                [
                    country,
                    ui_text("trends_historical_observation", language),
                    ui_text("trends_historical_source", language),
                ]
                for _year in dense_years
            ],
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>"
                + ui_text("trends_year", language)
                + ": %{x}<br>"
                + ui_text("trends_legal_score", language)
                + ": %{y:.1f}<br>%{customdata[1]}<br>%{customdata[2]}<extra></extra>"
            ),
        )
    )

    bounded_forecasts = [
        point for point in result.forecast if point.lower is not None and point.upper is not None
    ]
    if bounded_forecasts:
        years = [point.year for point in bounded_forecasts]
        figure.add_trace(
            go.Scatter(
                x=[*years, *reversed(years)],
                y=[
                    *[point.upper for point in bounded_forecasts],
                    *[point.lower for point in reversed(bounded_forecasts)],
                ],
                fill="toself",
                fillcolor=UNCERTAINTY_COLOR,
                line={"color": "rgba(0,0,0,0)", "width": 0},
                name=ui_text("trends_uncertainty", language),
                hoverinfo="skip",
                showlegend=True,
            )
        )

    if result.forecast:
        bridge_years = [last_year, *[point.year for point in result.forecast]]
        bridge_values = [actual_by_year[last_year], *[point.value for point in result.forecast]]
        hover_text = [
            _historical_hover(country, last_year, actual_by_year[last_year], language),
            *[_forecast_hover(country, point, language) for point in result.forecast],
        ]
        figure.add_trace(
            go.Scatter(
                x=bridge_years,
                y=bridge_values,
                mode="lines+markers",
                name=ui_text("trends_forecast", language),
                line={"color": FORECAST_COLOR, "width": 3, "dash": "dash"},
                marker={"color": FORECAST_COLOR, "size": 8, "symbol": "diamond"},
                hovertext=hover_text,
                hovertemplate="%{hovertext}<extra></extra>",
            )
        )
        figure.add_vline(
            x=last_year + 0.5,
            line={"color": "#64748B", "dash": "dot", "width": 1.5},
            annotation_text=ui_text("trends_forecast_starts", language),
            annotation_position="top",
        )

    apply_base_layout(figure, margin={"l": 62, "r": 28, "t": 48, "b": 62})
    figure.update_layout(
        autosize=True,
        height=540,
        hovermode="x unified",
        legend={"orientation": "h", "x": 0, "y": 1.12},
        xaxis={
            "title": ui_text("trends_year", language),
            "dtick": 1,
            "tickmode": "linear",
            "automargin": True,
        },
        yaxis={
            "title": ui_text("trends_legal_score", language),
            "range": [0, 100],
            "ticksuffix": "%",
            "automargin": True,
        },
        uirevision=f"trends-{result.country_code}",
    )
    return figure


def _historical_hover(country: str, year: int, value: float, language: str) -> str:
    return (
        f"<b>{country}</b><br>{year}<br>"
        f"{ui_text('trends_legal_score', language)}: {value:.1f}<br>"
        f"{ui_text('trends_historical_observation', language)}"
    )


def _forecast_hover(country: str, point: Any, language: str) -> str:
    lines = [
        f"<b>{country}</b>",
        str(point.year),
        f"{ui_text('trends_estimated_value', language)}: {point.value:.1f}",
        ui_text("trends_projection_observation", language),
    ]
    if point.lower is not None and point.upper is not None:
        lines.append(
            f"{ui_text('trends_estimated_interval', language)}: "
            f"{point.lower:.1f} - {point.upper:.1f}"
        )
    lines.append(ui_text("trends_projection_source", language))
    return "<br>".join(lines)
