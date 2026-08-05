from __future__ import annotations

import plotly.graph_objects as go

from app.dash.i18n import ui_text
from app.trends.models import SeriesMetadata, TrendAnalysis

OBSERVED_COLOR = "#19705f"
FORECAST_COLOR = "#b84d77"


def build_trend_figure(
    analysis: TrendAnalysis,
    metadata: SeriesMetadata,
    *,
    language: str = "es",
) -> go.Figure:
    if analysis.status != "ok" or analysis.summary is None:
        raise ValueError("trend_analysis_not_renderable")

    observed_years = [int(point.year) for point in analysis.points if point.year is not None]
    observed_values = [float(point.value) for point in analysis.points if point.value is not None]
    source_label = "ILGA-Europe" if metadata.source.value == "ilga" else "FRA"
    observed_type = ui_text("trends_real_data", language)
    estimated_type = ui_text("trends_estimated_data", language)
    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=observed_years,
            y=observed_values,
            mode="lines+markers",
            name=ui_text("trends_historical_data", language),
            line={"color": OBSERVED_COLOR, "width": 3},
            marker={"color": OBSERVED_COLOR, "size": 9},
            customdata=[[observed_type, source_label] for _ in observed_years],
            hovertemplate=_hover_template(language),
        )
    )
    if analysis.forecast:
        projected_years = [analysis.summary.end_year, *[point.year for point in analysis.forecast]]
        projected_values = [
            analysis.summary.final_value,
            *[point.value for point in analysis.forecast],
        ]
        figure.add_trace(
            go.Scatter(
                x=projected_years,
                y=projected_values,
                mode="lines+markers",
                name=ui_text("trends_forecast", language),
                line={"color": FORECAST_COLOR, "dash": "dash", "width": 3},
                marker={"color": FORECAST_COLOR, "symbol": "diamond", "size": 8},
                customdata=[[estimated_type, source_label] for _ in projected_years],
                hovertemplate=_hover_template(language),
            )
        )
        figure.add_vline(
            x=analysis.summary.end_year,
            line={"color": FORECAST_COLOR, "dash": "dot", "width": 1.5},
            annotation_text=ui_text("trends_forecast", language),
            annotation_position="top right",
        )

    figure.update_layout(
        title={
            "text": f"{metadata.indicator_label} · {metadata.country_name}",
            "x": 0.01,
            "xanchor": "left",
        },
        xaxis={
            "title": ui_text("trends_year", language),
            "dtick": 1,
            "fixedrange": False,
            "showgrid": True,
        },
        yaxis={
            "title": ui_text("trends_value", language),
            "fixedrange": False,
            "showgrid": True,
        },
        hovermode="closest",
        legend={"orientation": "h", "y": -0.23, "x": 0, "xanchor": "left"},
        margin={"l": 56, "r": 24, "t": 80, "b": 95},
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        font={"color": "#30242a"},
        transition={"duration": 180},
    )
    if metadata.bounded:
        figure.update_yaxes(range=[metadata.scale_min, metadata.scale_max])
    return figure


def _hover_template(language: str) -> str:
    year = ui_text("trends_year", language)
    value = ui_text("trends_value", language)
    data_type = ui_text("trends_type", language)
    source = ui_text("trends_source_short", language)
    return (
        f"<b>{year}:</b> %{{x}}<br>"
        f"<b>{value}:</b> %{{y:.2f}}<br>"
        f"<b>{data_type}:</b> %{{customdata[0]}}<br>"
        f"<b>{source}:</b> %{{customdata[1]}}<extra></extra>"
    )
