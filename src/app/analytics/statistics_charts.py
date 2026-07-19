from __future__ import annotations

import hashlib
import logging
from typing import Any

import pandas as pd
import plotly.graph_objects as go

from app.analytics.geography import EUROPE_CENTROIDS, to_iso3_country_code
from app.analytics.legal_criteria import (
    get_criterion_metadata,
    get_criterion_score_label,
    get_criterion_status,
)

logger = logging.getLogger(__name__)

CHART_COLORS = {
    "fra": "#3266a8",
    "fra_alt": "#a55233",
    "ilga": "#167d68",
    "partial": "#f2a03d",
    "missing": "#b8c0cc",
}
RESPONSE_COLOR_PALETTE = [
    "#3266a8",
    "#a55233",
    "#167d68",
    "#7c4dff",
    "#d14f7b",
    "#8a6f1d",
    "#2f8f9d",
    "#c46a1a",
    "#5f6c7b",
    "#b83280",
    "#4c7f2f",
    "#6d5a8d",
]
NON_GEOGRAPHIC_CODES = {"EU27"}
PLOTLY_TRANSPARENT = "rgba(0,0,0,0)"


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
            "bgcolor": PLOTLY_TRANSPARENT,
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
        return empty_figure("No hay distribución de respuestas para esta consulta.")
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


def build_fra_response_comparison_chart(
    data_rows: list[dict[str, Any]],
    *,
    selected_countries: list[str] | None = None,
) -> go.Figure:
    dataframe = _response_comparison_dataframe(data_rows)
    if dataframe.empty:
        return empty_figure("No hay respuestas comparables para esta pregunta y filtros.")

    mode = _response_comparison_mode(dataframe)
    selected_keys = _selected_country_keys(selected_countries)
    if mode == "stacked_percentage":
        figure = _build_stacked_response_chart(dataframe, selected_keys)
    elif mode == "categorical":
        figure = _build_categorical_response_chart(dataframe, selected_keys)
    else:
        figure = _build_numeric_response_chart(dataframe, selected_keys)
    _apply_comparison_height(figure, dataframe["country_key"].nunique())
    return figure


def summarize_response_comparison(data_rows: list[dict[str, Any]]) -> dict[str, Any]:
    dataframe = _response_comparison_dataframe(data_rows)
    if dataframe.empty:
        return {"countries": 0, "responses": 0, "distribution": [], "mode": "empty"}

    mode = _response_comparison_mode(dataframe)
    labels = _response_labels(dataframe)
    distribution: list[dict[str, Any]] = []
    if mode == "stacked_percentage":
        pivot = _response_percentage_pivot(dataframe)
        normalized = _normalize_percentage_pivot(pivot)
        means = normalized.mean(axis=0).dropna().sort_values(ascending=False)
        distribution = [
            {"label": labels.get(str(key), str(key)), "value": round(float(value), 1), "unit": "%"}
            for key, value in means.items()
        ]
    elif "response_key" in dataframe:
        country_answers = dataframe.drop_duplicates(["country_key", "response_key"])
        counts = country_answers.groupby("response_key")["country_key"].nunique().sort_values(ascending=False)
        distribution = [
            {"label": labels.get(str(key), str(key)), "value": int(value), "unit": "countries"}
            for key, value in counts.items()
        ]

    return {
        "countries": int(dataframe["country_key"].nunique()),
        "responses": int(dataframe["response_key"].nunique()) if "response_key" in dataframe else 0,
        "distribution": distribution,
        "mode": mode,
    }


def build_comparison_chart(ranking_rows: list[dict[str, Any]], *, source: str) -> go.Figure:
    dataframe = pd.DataFrame(ranking_rows)
    if dataframe.empty:
        return empty_figure("Selecciona entre 2 y 6 países para comparar.")
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


def _response_comparison_dataframe(data_rows: list[dict[str, Any]]) -> pd.DataFrame:
    dataframe = pd.DataFrame(data_rows)
    if dataframe.empty or "country" not in dataframe:
        return pd.DataFrame()
    dataframe = dataframe.copy()
    dataframe["country"] = dataframe["country"].astype(str).str.strip()
    if "iso" in dataframe:
        dataframe["iso"] = dataframe["iso"].fillna("").astype(str).str.strip().str.upper()
    else:
        dataframe["iso"] = ""
    dataframe = dataframe[
        dataframe["country"].ne("")
        & dataframe["iso"].ne("EU27")
        & dataframe["country"].str.upper().ne("EU27")
    ]
    if dataframe.empty:
        return pd.DataFrame()

    answer_source = "answer" if "answer" in dataframe else "response" if "response" in dataframe else None
    if answer_source:
        dataframe["response_raw"] = dataframe[answer_source].astype(str)
        dataframe["response_key"] = dataframe["response_raw"].apply(_response_key)
        dataframe = dataframe[dataframe["response_key"].ne("")]
        if dataframe.empty:
            return pd.DataFrame()
        label_by_key = _response_labels(dataframe)
        dataframe["response_label"] = dataframe["response_key"].map(label_by_key)
    else:
        dataframe["response_key"] = "value"
        dataframe["response_label"] = "Valor"

    numeric_source = "percentage" if "percentage" in dataframe else "value" if "value" in dataframe else None
    if numeric_source:
        dataframe["numeric_value"] = dataframe[numeric_source].apply(normalize_percentage)
    else:
        dataframe["numeric_value"] = None
    dataframe["country_key"] = dataframe.apply(
        lambda row: _country_key(row.get("iso"), row.get("country")),
        axis=1,
    )
    return dataframe[dataframe["country_key"].ne("")]


def _response_comparison_mode(dataframe: pd.DataFrame) -> str:
    has_numeric = dataframe["numeric_value"].notna().any()
    if not has_numeric:
        return "categorical"
    response_count = int(dataframe["response_key"].nunique())
    responses_per_country = dataframe.groupby("country_key")["response_key"].nunique()
    if response_count > 1 and int(responses_per_country.max()) > 1:
        return "stacked_percentage"
    return "numeric"


def _build_stacked_response_chart(dataframe: pd.DataFrame, selected_keys: set[str]) -> go.Figure:
    pivot = _response_percentage_pivot(dataframe)
    labels = _response_labels(dataframe)
    normalized = _normalize_percentage_pivot(pivot)

    order = _stacked_country_order(normalized)
    pivot = pivot.loc[order]
    normalized = normalized.loc[order]
    countries = [country for country, _iso in normalized.index]
    isos = [iso for _country, iso in normalized.index]
    selected = [_country_key(iso, country) in selected_keys for country, iso in zip(countries, isos)]

    figure = go.Figure()
    for response_key in sorted(normalized.columns, key=lambda key: labels.get(str(key), str(key)).casefold()):
        values = normalized[response_key].tolist()
        original_values = pivot[response_key].where(pivot[response_key].notna(), None).tolist()
        figure.add_trace(
            go.Bar(
                x=values,
                y=countries,
                name=labels.get(str(response_key), str(response_key)),
                orientation="h",
                marker={
                    "color": _response_color(str(response_key)),
                    "line": _selected_marker_line(selected),
                },
                customdata=[[iso, original] for iso, original in zip(isos, original_values)],
                hovertemplate=(
                    "<b>%{y}</b><br>"
                    "ISO: %{customdata[0]}<br>"
                    f"Respuesta: {labels.get(str(response_key), str(response_key))}<br>"
                    "Valor original: %{customdata[1]:.0f}%<br>"
                    "Porcentaje dentro del país: %{x:.2f}%<extra></extra>"
                ),
            )
        )
    _apply_base_layout(figure, margin={"l": 120, "r": 28, "t": 20, "b": 95})
    figure.update_layout(
        barmode="stack",
        xaxis={"title": "Distribución de respuestas", "range": [0, 100], "ticksuffix": "%"},
        yaxis={"title": "", "automargin": True},
        legend={"title": {"text": "Respuesta"}, "orientation": "h", "y": -0.18},
        showlegend=True,
    )
    _add_selected_country_annotations(figure, countries, isos, selected_keys)
    return figure


def _build_numeric_response_chart(dataframe: pd.DataFrame, selected_keys: set[str]) -> go.Figure:
    grouped = (
        dataframe[dataframe["numeric_value"].notna()]
        .groupby(["country", "iso", "country_key"], dropna=False)
        .agg(value=("numeric_value", "mean"), response_label=("response_label", "first"), response_key=("response_key", "first"))
        .reset_index()
        .sort_values("value", ascending=True)
    )
    if grouped.empty:
        return empty_figure("No hay valores numéricos comparables para esta consulta.")

    selected = grouped["country_key"].isin(selected_keys).tolist()
    colors = [
        _response_color(str(row.response_key)) if row.response_key else CHART_COLORS["fra"]
        for row in grouped.itertuples()
    ]
    figure = go.Figure(
        go.Bar(
            x=grouped["value"],
            y=grouped["country"],
            orientation="h",
            marker={"color": colors, "line": _selected_marker_line(selected)},
            customdata=grouped[["iso", "response_label"]].fillna("").to_numpy(),
            hovertemplate="<b>%{y}</b><br>ISO: %{customdata[0]}<br>%{customdata[1]}: %{x:.2f}%<extra></extra>",
            showlegend=False,
        )
    )
    figure.update_layout(xaxis={"title": "Valor", "range": [0, 100]}, yaxis={"title": "", "automargin": True})
    _apply_base_layout(figure, margin={"l": 120, "r": 28, "t": 20, "b": 55})
    _add_selected_country_annotations(figure, grouped["country"].tolist(), grouped["iso"].tolist(), selected_keys)
    return figure


def _build_categorical_response_chart(dataframe: pd.DataFrame, selected_keys: set[str]) -> go.Figure:
    labels = _response_labels(dataframe)
    country_answers = (
        dataframe.drop_duplicates(["country_key"])
        .sort_values(["response_label", "country"])
        [["country", "iso", "country_key", "response_key", "response_label"]]
    )
    figure = go.Figure()
    for response_key, rows in country_answers.groupby("response_key", sort=False):
        selected = rows["country_key"].isin(selected_keys).tolist()
        figure.add_trace(
            go.Bar(
                x=[1] * len(rows),
                y=rows["country"],
                name=labels.get(str(response_key), str(response_key)),
                orientation="h",
                marker={"color": _response_color(str(response_key)), "line": _selected_marker_line(selected)},
                customdata=rows[["iso", "response_label"]].fillna("").to_numpy(),
                hovertemplate="<b>%{y}</b><br>ISO: %{customdata[0]}<br>Respuesta: %{customdata[1]}<extra></extra>",
            )
        )
    _apply_base_layout(figure, margin={"l": 120, "r": 28, "t": 20, "b": 95})
    figure.update_layout(
        barmode="stack",
        xaxis={"title": "Respuesta categórica", "showticklabels": False, "range": [0, 1]},
        yaxis={"title": "", "automargin": True},
        legend={"title": {"text": "Respuesta"}, "orientation": "h", "y": -0.18},
        showlegend=True,
    )
    _add_selected_country_annotations(figure, country_answers["country"].tolist(), country_answers["iso"].tolist(), selected_keys)
    return figure


def _response_percentage_pivot(dataframe: pd.DataFrame) -> pd.DataFrame:
    grouped = (
        dataframe[dataframe["numeric_value"].notna()]
        .groupby(["country", "iso", "response_key"], dropna=False)["numeric_value"]
        .mean()
        .reset_index()
    )
    return grouped.pivot_table(
        index=["country", "iso"],
        columns="response_key",
        values="numeric_value",
        aggfunc="mean",
    )


def _normalize_percentage_pivot(pivot: pd.DataFrame) -> pd.DataFrame:
    if pivot.empty:
        return pivot
    clean = pivot.apply(pd.to_numeric, errors="coerce").fillna(0)
    clean = clean.clip(lower=0)
    totals = clean.sum(axis=1)
    normalized = clean.div(totals.where(totals > 0), axis=0) * 100
    normalized = normalized.fillna(0).clip(lower=0, upper=100)
    row_totals = normalized.sum(axis=1)
    return normalized.div(row_totals.where(row_totals > 0), axis=0).fillna(0) * 100


def _stacked_country_order(normalized: pd.DataFrame) -> list[tuple[str, str]]:
    order = pd.DataFrame(index=normalized.index)
    order["dominant_response"] = normalized.idxmax(axis=1)
    order["dominant_value"] = normalized.max(axis=1)
    order["country_name"] = [country for country, _iso in normalized.index]
    return order.sort_values(
        ["dominant_response", "dominant_value", "country_name"],
        ascending=[True, False, True],
    ).index.tolist()


def _response_labels(dataframe: pd.DataFrame) -> dict[str, str]:
    labels: dict[str, str] = {}
    for raw in dataframe.get("response_raw", dataframe.get("response_label", pd.Series(dtype=str))):
        label = " ".join(str(raw or "").strip().split())
        key = _response_key(label)
        if key and key not in labels:
            labels[key] = label
    if not labels and "response_key" in dataframe:
        labels = {str(key): str(key) for key in dataframe["response_key"].dropna().unique()}
    return labels


def _response_key(value: Any) -> str:
    return " ".join(str(value or "").strip().casefold().split())


def _country_key(iso: Any, country: Any) -> str:
    clean_iso = str(iso or "").strip().upper()
    if clean_iso:
        return clean_iso
    return " ".join(str(country or "").strip().casefold().split())


def _selected_country_keys(selected_countries: list[str] | None) -> set[str]:
    return {
        str(country or "").strip().upper() if len(str(country or "").strip()) <= 3 else _country_key("", country)
        for country in selected_countries or []
        if str(country or "").strip()
    }


def _response_color(response_key: str) -> str:
    digest = hashlib.sha256(response_key.encode("utf-8")).hexdigest()
    index = int(digest[:8], 16) % len(RESPONSE_COLOR_PALETTE)
    return RESPONSE_COLOR_PALETTE[index]


def _selected_marker_line(selected: list[bool]) -> dict[str, Any]:
    return {
        "color": ["#111827" if item else "rgba(255,255,255,0.72)" for item in selected],
        "width": [2.6 if item else 0.5 for item in selected],
    }


def _add_selected_country_annotations(
    figure: go.Figure,
    countries: list[str],
    isos: list[str],
    selected_keys: set[str],
) -> None:
    for country, iso in zip(countries, isos):
        if _country_key(iso, country) not in selected_keys:
            continue
        figure.add_annotation(
            x=1.01,
            y=country,
            xref="paper",
            yref="y",
            text="Seleccionado",
            showarrow=False,
            xanchor="left",
            font={"size": 11, "color": "#111827"},
            bgcolor="rgba(255,255,255,0.86)",
            bordercolor="#111827",
            borderwidth=1,
        )


def _apply_comparison_height(figure: go.Figure, country_count: int) -> None:
    figure.update_layout(height=min(980, max(420, country_count * 24 + 170)))


def build_ilga_criteria_heatmap(data_rows: list[dict[str, Any]], *, language: str = "es") -> go.Figure:
    dataframe = pd.DataFrame(data_rows)
    dataframe = dataframe[
        dataframe.get("criterion", pd.Series(dtype=str)).astype(str).ne("")
        & dataframe.get("criterion_value", pd.Series(dtype=float)).notna()
    ] if not dataframe.empty else dataframe
    if dataframe.empty:
        return empty_figure("No hay criterios jurídicos para esta selección.")
    countries = dataframe["country"].drop_duplicates().head(16).tolist()
    criteria = dataframe["criterion"].drop_duplicates().head(12).tolist()
    criteria_labels = [
        get_criterion_metadata(
            {
                "category": _first_criterion_category(dataframe, criterion),
                "indicator": criterion,
            },
            language,
        )["display_title"]
        for criterion in criteria
    ]
    matrix = []
    customdata = []
    for country in countries:
        row = []
        custom_row = []
        for criterion in criteria:
            matches = dataframe[(dataframe["country"] == country) & (dataframe["criterion"] == criterion)]
            if matches.empty:
                row.append(None)
                custom_row.append(_legal_hover_data({}, None, None, language=language))
                continue
            match = matches.iloc[0]
            value = normalize_percentage(match.get("criterion_value"))
            weight = normalize_percentage(match.get("criterion_weight"))
            row.append(_normalized_criterion_value(value, weight))
            custom_row.append(_legal_hover_data(match.to_dict(), value, weight, language=language))
        matrix.append(row)
        customdata.append(custom_row)
    figure = go.Figure(
        go.Heatmap(
            z=matrix,
            x=criteria_labels,
            y=countries,
            zmin=0,
            zmax=1,
            xgap=1,
            ygap=1,
            colorscale=[[0.0, "#f1f4f8"], [0.5, CHART_COLORS["partial"]], [1.0, CHART_COLORS["ilga"]]],
            colorbar={"title": "Cumplimiento"},
            customdata=customdata,
            hovertemplate=(
                "<b>%{y}</b><br>"
                "<b>%{customdata[0]}</b><br>"
                "%{customdata[1]}<br><br>"
                "%{customdata[2]} %{customdata[3]}<br>"
                "%{customdata[4]}"
                "<extra></extra>"
            ),
        )
    )
    figure.update_layout(xaxis={"title": "Criterio"}, yaxis={"title": ""}, hoverlabel={"align": "left"})
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
        return empty_figure("No hay países coincidentes para comparar FRA e ILGA-Europe.")
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
        xaxis={"title": "Puntuación jurídica ILGA-Europe (%)", "range": [0, 100]},
        yaxis={"title": "Indicador FRA (%)", "range": [0, 100]},
    )
    _apply_base_layout(figure)
    return figure


def _apply_base_layout(figure: go.Figure, margin: dict[str, int] | None = None) -> None:
    figure.update_layout(
        margin=margin or {"l": 45, "r": 20, "t": 20, "b": 55},
        paper_bgcolor=PLOTLY_TRANSPARENT,
        plot_bgcolor=PLOTLY_TRANSPARENT,
        font={"family": "Segoe UI, Arial, sans-serif", "color": "#252a31"},
        showlegend=False,
    )


def _first_criterion_category(dataframe: pd.DataFrame, criterion: str) -> str:
    matches = dataframe[dataframe["criterion"] == criterion]
    if matches.empty or "category" not in matches:
        return ""
    return str(matches.iloc[0].get("category") or "")


def _normalized_criterion_value(value: float | None, weight: float | None) -> float | None:
    if value is None:
        return None
    if weight is not None and weight > 0:
        return max(0.0, min(1.0, value / weight))
    return max(0.0, min(1.0, value))


def _legal_hover_data(
    criterion_row: dict[str, Any],
    value: float | None,
    weight: float | None,
    *,
    language: str = "es",
) -> list[str]:
    metadata = get_criterion_metadata(
        {
            "category": criterion_row.get("category"),
            "indicator": criterion_row.get("criterion"),
        },
        language,
    )
    status = get_criterion_status(value, weight, language)
    score = get_criterion_score_label(value, weight, language)
    unavailable_score = (
        "Score: information unavailable"
        if language == "en"
        else "Puntuación: información no disponible"
    )
    return [
        metadata["display_title"],
        _wrap_hover_text(metadata["summary"]),
        status["icon"],
        status["label"],
        score or unavailable_score,
    ]


def _wrap_hover_text(value: str, width: int = 84) -> str:
    words = str(value or "").split()
    if not words:
        return ""
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        if len(current) + 1 + len(word) > width:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}"
    lines.append(current)
    return "<br>".join(lines)
