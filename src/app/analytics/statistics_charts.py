from __future__ import annotations

import logging
from typing import Any

import pandas as pd
import plotly.graph_objects as go

from app.analytics.geography import EUROPE_CENTROIDS, to_iso3_country_code

logger = logging.getLogger(__name__)

CHART_COLORS = {
    "fra": "#3266a8",
    "fra_alt": "#a55233",
    "ilga": "#167d68",
    "partial": "#f2a03d",
    "missing": "#b8c0cc",
}
NON_GEOGRAPHIC_CODES = {"EU27"}


def empty_figure(message: str) -> go.Figure:
    figure = go.Figure()
    figure.add_annotation(
        text=message,
        x=0.5,
        y=0.5,
        xref="paper",
        yref="paper",
        showarrow=False,
        font={"size": 16, "color": "#5f6672"},
    )
    _apply_base_layout(figure)
    return figure


def build_europe_choropleth(
    ranking_rows: list[dict[str, Any]],
    *,
    source: str,
    selected_iso: str | None = None,
) -> go.Figure:
    dataframe = pd.DataFrame(ranking_rows)
    required_columns = {"country", "iso", "value"}
    if dataframe.empty or not required_columns.issubset(dataframe.columns):
        return empty_figure("No hay datos cartografiables para los filtros seleccionados.")

    dataframe = dataframe.copy()
    dataframe["value"] = dataframe["value"].apply(normalize_percentage)
    dataframe["iso"] = dataframe["iso"].astype(str).str.strip().str.upper()
    dataframe["iso3"] = dataframe["iso"].apply(to_iso3_country_code)
    valid_values = dataframe["value"].dropna()
    if valid_values.empty:
        return empty_figure("No hay datos disponibles para esta combinación de filtros.")

    if float(valid_values.max()) <= 1 and float(valid_values.min()) >= 0:
        dataframe.loc[dataframe["value"].notna(), "value"] = dataframe.loc[dataframe["value"].notna(), "value"] * 100
        valid_values = dataframe["value"].dropna()

    missing_codes = sorted(
        set(dataframe.loc[dataframe["iso3"].eq(""), "iso"].dropna()).difference(NON_GEOGRAPHIC_CODES)
    )
    if missing_codes:
        logger.warning(
            "statistics_map_missing_iso3_codes",
            extra={"missing_codes": missing_codes, "source": source},
        )
    logger.debug(
        "statistics_map_dataframe",
        extra={
            "columns": dataframe.columns.tolist(),
            "value_dtype": str(dataframe["value"].dtype),
            "value_min": float(valid_values.min()),
            "value_max": float(valid_values.max()),
            "value_nulls": int(dataframe["value"].isna().sum()),
            "iso_codes": sorted(dataframe["iso"].dropna().unique().tolist()),
        },
    )

    drawable = dataframe[dataframe["iso3"].ne("") & dataframe["value"].notna()]
    if drawable.empty:
        return empty_figure("No hay países con correspondencia geográfica para esta consulta.")

    minimum = float(valid_values.min())
    maximum = float(valid_values.max())
    if minimum == maximum:
        minimum = max(0, minimum - 1)
        maximum = min(100, maximum + 1)

    color_scale = (
        [[0.0, "#d9ecff"], [0.35, "#73b3df"], [0.7, "#2171b5"], [1.0, "#08306b"]]
        if source == "FRA"
        else [[0.0, "#d73027"], [0.35, "#fdae61"], [0.65, "#fee08b"], [0.82, "#66c2a5"], [1.0, "#177245"]]
    )
    figure = go.Figure(
        go.Choropleth(
            locations=drawable["iso3"],
            locationmode="ISO-3",
            z=drawable["value"],
            text=drawable["country"],
            customdata=drawable[["iso"]].fillna("").to_numpy(),
            zmin=minimum,
            zmax=maximum,
            colorscale=color_scale,
            marker={"line": {"color": "#ffffff", "width": 0.75}},
            colorbar={"title": "Porcentaje", "ticksuffix": "%", "thickness": 13},
            hovertemplate=(
                "<b>%{text}</b><br>"
                "ISO: %{customdata[0]}<br>"
                f"{source}: %{{z:.2f}}%<extra></extra>"
            ),
        )
    )
    if selected_iso:
        selected = drawable[drawable["iso"] == selected_iso]
        if not selected.empty:
            centroid = EUROPE_CENTROIDS.get(selected_iso)
            if centroid:
                latitude, longitude = centroid
                figure.add_trace(
                    go.Scattergeo(
                        lat=[latitude],
                        lon=[longitude],
                        text=[selected.iloc[0]["country"]],
                        mode="markers",
                        marker={"size": 12, "color": "#111827", "line": {"color": "#ffffff", "width": 2}},
                        hoverinfo="skip",
                        showlegend=False,
                    )
                )
    figure.update_layout(
        geo={
            "scope": "europe",
            "projection_type": "natural earth",
            "showframe": False,
            "showcoastlines": True,
            "coastlinecolor": "#b9c0ca",
            "showland": True,
            "landcolor": "#d1d5db",
            "showocean": True,
            "oceancolor": "#dcebf2",
            "bgcolor": "#ffffff",
        },
        uirevision=f"statistics-{source}",
    )
    _apply_base_layout(figure, margin={"l": 0, "r": 0, "t": 12, "b": 0})
    figure.add_annotation(
        text="Sin datos: gris",
        x=0,
        y=0,
        xref="paper",
        yref="paper",
        showarrow=False,
        xanchor="left",
        yanchor="bottom",
        font={"size": 11, "color": "#5f6672"},
        bgcolor="rgba(255,255,255,0.75)",
        bordercolor="#d1d5db",
        borderwidth=1,
    )
    return figure


def normalize_percentage(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip().replace("%", "").replace(",", ".")
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def build_ranking_chart(ranking_rows: list[dict[str, Any]], *, source: str, limit: int = 20) -> go.Figure:
    dataframe = pd.DataFrame(ranking_rows)
    if dataframe.empty:
        return empty_figure("No hay ranking para mostrar.")
    dataframe = dataframe.sort_values("value", ascending=False).head(limit)
    figure = go.Figure(
        go.Bar(
            x=dataframe["value"].iloc[::-1],
            y=dataframe["country"].iloc[::-1],
            orientation="h",
            marker={"color": CHART_COLORS["fra" if source == "FRA" else "ilga"]},
            customdata=dataframe[["iso"]].iloc[::-1].fillna("").to_numpy(),
            hovertemplate="<b>%{y}</b><br>ISO: %{customdata[0]}<br>%{x:.2f}%<extra></extra>",
        )
    )
    figure.update_layout(xaxis={"title": "Porcentaje", "range": [0, 100]}, yaxis={"title": ""})
    _apply_base_layout(figure)
    return figure


def build_fra_distribution_chart(data_rows: list[dict[str, Any]]) -> go.Figure:
    dataframe = pd.DataFrame(data_rows)
    if dataframe.empty or "answer" not in dataframe:
        return empty_figure("No hay distribucion de respuestas para esta consulta.")
    grouped = dataframe.groupby("answer", dropna=False)["percentage"].mean().reset_index()
    grouped = grouped.sort_values("percentage", ascending=False)
    figure = go.Figure(
        go.Bar(
            x=grouped["answer"],
            y=grouped["percentage"],
            marker={"color": CHART_COLORS["fra"]},
            hovertemplate="<b>%{x}</b><br>Media: %{y:.2f}%<extra></extra>",
        )
    )
    figure.update_layout(xaxis={"title": "Respuesta"}, yaxis={"title": "Porcentaje medio", "range": [0, 100]})
    _apply_base_layout(figure)
    return figure


def build_comparison_chart(ranking_rows: list[dict[str, Any]], *, source: str) -> go.Figure:
    dataframe = pd.DataFrame(ranking_rows)
    if dataframe.empty:
        return empty_figure("Selecciona entre 2 y 6 paises para comparar.")
    dataframe = dataframe.sort_values("value", ascending=False)
    figure = go.Figure(
        go.Bar(
            x=dataframe["country"],
            y=dataframe["value"],
            marker={"color": CHART_COLORS["fra_alt" if source == "FRA" else "ilga"]},
            customdata=dataframe[["iso"]].fillna("").to_numpy(),
            hovertemplate="<b>%{x}</b><br>ISO: %{customdata[0]}<br>%{y:.2f}%<extra></extra>",
        )
    )
    figure.update_layout(xaxis={"title": ""}, yaxis={"title": "Porcentaje", "range": [0, 100]})
    _apply_base_layout(figure)
    return figure


def build_ilga_criteria_heatmap(data_rows: list[dict[str, Any]]) -> go.Figure:
    dataframe = pd.DataFrame(data_rows)
    dataframe = dataframe[
        dataframe.get("criterion", pd.Series(dtype=str)).astype(str).ne("")
        & dataframe.get("criterion_value", pd.Series(dtype=float)).notna()
    ] if not dataframe.empty else dataframe
    if dataframe.empty:
        return empty_figure("No hay criterios juridicos para esta seleccion.")
    countries = dataframe["country"].drop_duplicates().head(16).tolist()
    criteria = dataframe["criterion"].drop_duplicates().head(12).tolist()
    matrix = []
    for country in countries:
        row = []
        for criterion in criteria:
            values = dataframe[(dataframe["country"] == country) & (dataframe["criterion"] == criterion)]["criterion_value"]
            row.append(float(values.iloc[0]) if not values.empty else None)
        matrix.append(row)
    figure = go.Figure(
        go.Heatmap(
            z=matrix,
            x=criteria,
            y=countries,
            zmin=0,
            zmax=1,
            xgap=1,
            ygap=1,
            colorscale=[[0.0, "#f1f4f8"], [0.5, CHART_COLORS["partial"]], [1.0, CHART_COLORS["ilga"]]],
            colorbar={"title": "Valor"},
            hovertemplate="<b>%{y}</b><br>%{x}<br>Valor: %{z}<extra></extra>",
        )
    )
    figure.update_layout(xaxis={"title": "Criterio"}, yaxis={"title": ""})
    _apply_base_layout(figure, margin={"l": 120, "r": 20, "t": 20, "b": 150})
    figure.update_layout(plot_bgcolor="#000000")
    return figure


def build_fra_ilga_scatter(fra_rows: list[dict[str, Any]], ilga_rows: list[dict[str, Any]]) -> go.Figure:
    fra = pd.DataFrame(fra_rows)
    ilga = pd.DataFrame(ilga_rows)
    if fra.empty or ilga.empty:
        return empty_figure("No hay coincidencia suficiente entre FRA e ILGA-Europe.")
    fra_grouped = fra.groupby(["country", "iso"], dropna=False)["percentage"].mean().reset_index(name="fra_value")
    ilga_grouped = ilga[ilga["category"] == "Ranking total"][["country", "iso", "ranking"]].drop_duplicates()
    merged = fra_grouped.merge(ilga_grouped, on="iso", how="inner", suffixes=("_fra", "_ilga"))
    if merged.empty:
        return empty_figure("No hay paises coincidentes para comparar FRA e ILGA-Europe.")
    figure = go.Figure(
        go.Scatter(
            x=merged["ranking"],
            y=merged["fra_value"],
            mode="markers+text",
            text=merged["country_fra"].fillna(merged["country_ilga"]),
            textposition="top center",
            marker={"size": 10, "color": CHART_COLORS["fra"]},
            hovertemplate="<b>%{text}</b><br>ILGA: %{x:.2f}%<br>FRA: %{y:.2f}%<extra></extra>",
        )
    )
    figure.update_layout(
        xaxis={"title": "Puntuacion juridica ILGA-Europe (%)", "range": [0, 100]},
        yaxis={"title": "Indicador FRA (%)", "range": [0, 100]},
    )
    _apply_base_layout(figure)
    return figure


def _apply_base_layout(figure: go.Figure, margin: dict[str, int] | None = None) -> None:
    figure.update_layout(
        margin=margin or {"l": 45, "r": 20, "t": 20, "b": 55},
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        font={"family": "Segoe UI, Arial, sans-serif", "color": "#252a31"},
        showlegend=False,
    )
