from __future__ import annotations

import hashlib
import logging
from typing import Any

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from app.analytics.geography import EUROPE_CENTROIDS, to_iso3_country_code
from app.analytics.legal_criteria import (
    get_criterion_metadata,
    get_criterion_score_label,
    get_criterion_status,
)
from app.analytics.percentage_display import (
    MISSING_PERCENTAGE_COLOR,
    coerce_percentage,
    format_percentage,
    prepare_percentage_display_values,
)
from app.dash.i18n import ui_text

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
    "#d73027",
    "#167d68",
    "#7c4dff",
    "#d14f7b",
    "#8a6f1d",
    "#2f8f9d",
    "#c62828",
    "#2e7d32",
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
    selected_isos: list[str] | None = None,
    language: str = "es",
) -> go.Figure:
    dataframe = pd.DataFrame(ranking_rows)
    required_columns = {"country", "iso"}
    if dataframe.empty or not required_columns.issubset(dataframe.columns):
        return empty_figure("No hay datos cartografiables para los filtros seleccionados.")
    if "value" not in dataframe.columns:
        dataframe["value"] = None

    dataframe = dataframe.copy()
    dataframe["value"] = dataframe["value"].apply(
        lambda value: coerce_percentage(
            value,
            logger=logger,
            context={"chart": "europe_choropleth", "source": source},
        )
    )
    dataframe["iso"] = dataframe["iso"].astype(str).str.strip().str.upper()
    dataframe["iso3"] = dataframe["iso"].apply(to_iso3_country_code)
    display_values, normalized = prepare_percentage_display_values(
        dataframe["value"].tolist(),
        normalize_when_total_is_not_100=False,
        logger=logger,
        context={"chart": "europe_choropleth", "source": source},
    )
    dataframe["display_value"] = display_values
    dataframe["display_value_text"] = dataframe["display_value"].apply(format_percentage)
    valid_values = dataframe["display_value"].dropna()
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
            "value_dtype": str(dataframe["display_value"].dtype),
            "value_min": float(valid_values.min()) if not valid_values.empty else None,
            "value_max": float(valid_values.max()) if not valid_values.empty else None,
            "value_nulls": int(dataframe["display_value"].isna().sum()),
            "iso_codes": sorted(dataframe["iso"].dropna().unique().tolist()),
            "normalized": normalized,
        },
    )

    drawable = dataframe[dataframe["iso3"].ne("") & dataframe["display_value"].notna()]
    unavailable = dataframe[dataframe["iso3"].ne("") & dataframe["display_value"].isna()]
    if drawable.empty and unavailable.empty:
        return empty_figure("No hay países con correspondencia geográfica para esta consulta.")

    minimum = float(valid_values.min()) if not valid_values.empty else 0
    maximum = float(valid_values.max()) if not valid_values.empty else 100
    if not valid_values.empty and minimum == maximum:
        minimum = max(0, minimum - 1)
        maximum = min(100, maximum + 1)

    color_scale = (
        [[0.0, "#d9ecff"], [0.35, "#73b3df"], [0.7, "#2171b5"], [1.0, "#08306b"]]
        if source == "FRA"
        else [[0.0, "#d73027"], [0.35, "#fdae61"], [0.65, "#fee08b"], [0.82, "#66c2a5"], [1.0, "#177245"]]
    )
    figure = go.Figure()
    if not drawable.empty:
        drawable = drawable.assign(value_label=ui_text("chart_value", language))
        figure.add_trace(
            go.Choropleth(
                locations=drawable["iso3"],
                locationmode="ISO-3",
                z=drawable["display_value"],
                text=drawable["country"],
                customdata=drawable[["iso", "value_label", "display_value_text"]].fillna("").to_numpy(),
                zmin=minimum,
                zmax=maximum,
                colorscale=color_scale,
                marker={"line": {"color": "#ffffff", "width": 0.75}},
                colorbar={"title": ui_text("chart_percentage", language), "ticksuffix": "%", "thickness": 13},
                hovertemplate=(
                    "<b>%{text}</b><br>"
                    "%{customdata[1]}: %{customdata[2]}<extra></extra>"
                ),
            )
        )
    if not unavailable.empty:
        unavailable = unavailable.assign(missing_message=ui_text("chart_not_enough_information", language))
        figure.add_trace(
            go.Choropleth(
                locations=unavailable["iso3"],
                locationmode="ISO-3",
                z=[0] * len(unavailable),
                text=unavailable["country"],
                customdata=unavailable[["iso", "missing_message"]].fillna("").to_numpy(),
                zmin=0,
                zmax=1,
                colorscale=[[0.0, MISSING_PERCENTAGE_COLOR], [1.0, MISSING_PERCENTAGE_COLOR]],
                marker={"line": {"color": "#ffffff", "width": 0.75}},
                showscale=False,
                hovertemplate="<b>%{text}</b><br>%{customdata[1]}<extra></extra>",
            )
        )
    selected_codes = {
        str(value or "").strip().upper()
        for value in [*(selected_isos or []), selected_iso]
        if str(value or "").strip()
    }
    selected = dataframe[dataframe["iso"].isin(selected_codes) & dataframe["iso3"].ne("")]
    latitudes: list[float] = []
    longitudes: list[float] = []
    labels: list[str] = []
    for row in selected.itertuples():
        centroid = EUROPE_CENTROIDS.get(str(row.iso))
        if centroid:
            latitude, longitude = centroid
            latitudes.append(latitude)
            longitudes.append(longitude)
            labels.append(str(row.country))
    if latitudes:
        figure.add_trace(
            go.Scattergeo(
                lat=latitudes,
                lon=longitudes,
                text=labels,
                customdata=[[str(row.iso)] for row in selected.itertuples() if EUROPE_CENTROIDS.get(str(row.iso))],
                mode="markers",
                marker={"size": 13, "color": "#111827", "line": {"color": "#ffffff", "width": 2.5}},
                hovertemplate="<b>%{text}</b><br>Seleccionado<extra></extra>",
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
    if not unavailable.empty:
        figure.add_annotation(
            text=ui_text("chart_no_data_grey", language),
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
    return coerce_percentage(value)


def build_ranking_chart(
    ranking_rows: list[dict[str, Any]],
    *,
    source: str,
    limit: int = 60,
    selected_countries: list[str] | None = None,
    language: str = "es",
) -> go.Figure:
    dataframe = pd.DataFrame(ranking_rows)
    if dataframe.empty:
        return empty_figure("No hay ranking para mostrar.")
    if "answer" in dataframe.columns and dataframe["answer"].notna().any():
        return _build_response_ranking_chart(
            dataframe,
            selected_countries=selected_countries,
            limit=limit,
            language=language,
        )
    dataframe = dataframe.sort_values("value", ascending=False).head(limit)
    selected = _selected_country_keys(selected_countries)
    dataframe["value_text"] = dataframe["value"].apply(format_percentage)
    dataframe["value_label"] = ui_text("chart_value", language)
    figure = go.Figure(
        go.Bar(
            x=dataframe["value"].iloc[::-1],
            y=dataframe["country"].iloc[::-1],
            orientation="h",
            marker={
                "color": [
                    "#111827" if _country_key(row.iso, row.country) in selected
                    else CHART_COLORS["fra" if source == "FRA" else "ilga"]
                    for row in dataframe.iloc[::-1].itertuples()
                ]
            },
            customdata=dataframe[["iso", "value_label", "value_text"]].iloc[::-1].fillna("").to_numpy(),
            hovertemplate="<b>%{y}</b><br>%{customdata[1]}: %{customdata[2]}<extra></extra>",
        )
    )
    figure.update_layout(xaxis={"title": "Porcentaje", "range": [0, 100]}, yaxis={"title": ""})
    _apply_base_layout(figure)
    return figure


def _build_response_ranking_chart(
    dataframe: pd.DataFrame,
    *,
    selected_countries: list[str] | None,
    limit: int,
    language: str,
) -> go.Figure:
    dataframe = dataframe.copy()
    dataframe["value"] = pd.to_numeric(dataframe["value"], errors="coerce")
    dataframe = dataframe.dropna(subset=["value", "country", "answer"])
    if dataframe.empty:
        return empty_figure("No hay ranking para mostrar.")
    country_order = (
        dataframe.groupby("country", as_index=False)
        .agg(value=("value", "max"))
        .sort_values("value", ascending=False)
        .head(limit)["country"]
        .tolist()
    )
    country_order = list(reversed(country_order))
    dataframe = dataframe[dataframe["country"].isin(country_order)]
    selected = _selected_country_keys(selected_countries)
    figure = go.Figure()
    for answer, rows in dataframe.groupby("answer", sort=True):
        rows = rows.set_index("country").reindex(country_order).reset_index()
        selected_rows = [
            _country_key(row.iso, row.country) in selected
            for row in rows.itertuples()
        ]
        figure.add_trace(
            go.Bar(
                x=rows["value"],
                y=rows["country"],
                orientation="h",
                name=str(answer),
                marker={
                    "color": _response_color(_response_key(answer)),
                    "line": {
                        "color": ["#111827" if is_selected else "rgba(0,0,0,0)" for is_selected in selected_rows],
                        "width": [2 if is_selected else 0 for is_selected in selected_rows],
                    },
                },
                hovertemplate=f"<b>%{{y}}</b><br>{answer}: %{{x:.2f}}%<extra></extra>",
            )
        )
    figure.update_layout(
        barmode="group",
        xaxis={"title": _chart_text(language, "Porcentaje", "Percentage"), "range": [0, 100]},
        yaxis={"title": "", "categoryorder": "array", "categoryarray": country_order},
        height=max(520, len(country_order) * 23),
    )
    _apply_base_layout(figure, margin={"l": 115, "r": 25, "t": 20, "b": 60})
    figure.update_layout(showlegend=True, legend={"orientation": "h", "y": -0.08})
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
    language: str = "es",
) -> go.Figure:
    dataframe = _response_comparison_dataframe(data_rows)
    if dataframe.empty:
        return empty_figure("No hay respuestas comparables para esta pregunta y filtros.")

    mode = _response_comparison_mode(dataframe)
    selected_keys = _selected_country_keys(selected_countries)
    if mode == "stacked_percentage":
        figure = _build_stacked_response_chart(dataframe, selected_keys, language=language)
    elif mode == "categorical":
        figure = _build_categorical_response_chart(dataframe, selected_keys)
    else:
        figure = _build_numeric_response_chart(dataframe, selected_keys, language=language)
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


def build_comparison_chart(
    ranking_rows: list[dict[str, Any]],
    *,
    source: str,
    language: str = "es",
) -> go.Figure:
    dataframe = pd.DataFrame(ranking_rows)
    if dataframe.empty:
        return empty_figure("Selecciona entre 2 y 6 países para comparar.")
    dataframe = dataframe.sort_values("value", ascending=False)
    dataframe["value_text"] = dataframe["value"].apply(format_percentage)
    dataframe["value_label"] = ui_text("chart_value", language)
    figure = go.Figure(
        go.Bar(
            x=dataframe["country"],
            y=dataframe["value"],
            marker={"color": CHART_COLORS["fra_alt" if source == "FRA" else "ilga"]},
            customdata=dataframe[["iso", "value_label", "value_text"]].fillna("").to_numpy(),
            hovertemplate="<b>%{x}</b><br>%{customdata[1]}: %{customdata[2]}<extra></extra>",
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
        dataframe["numeric_value"] = dataframe[numeric_source].apply(
            lambda value: coerce_percentage(
                value,
                logger=logger,
                context={"chart": "fra_response_comparison", "field": numeric_source},
            )
        )
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


def _build_stacked_response_chart(
    dataframe: pd.DataFrame,
    selected_keys: set[str],
    *,
    language: str = "es",
) -> go.Figure:
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
        formatted_values = [format_percentage(value) or "" for value in values]
        value_label = ui_text("chart_value", language)
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
                customdata=[[iso, value_label, formatted] for iso, formatted in zip(isos, formatted_values)],
                hovertemplate="<b>%{y}</b><br>%{customdata[1]}: %{customdata[2]}<extra></extra>",
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


def _build_numeric_response_chart(
    dataframe: pd.DataFrame,
    selected_keys: set[str],
    *,
    language: str = "es",
) -> go.Figure:
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
    grouped["value_text"] = grouped["value"].apply(format_percentage)
    grouped["value_label"] = ui_text("chart_value", language)
    colors = [
        _response_color(str(row.response_key)) if row.response_key else CHART_COLORS["fra"]
        for row in grouped.itertuples()
    ]
    response_label = str(grouped["response_label"].dropna().iloc[0]) if not grouped["response_label"].dropna().empty else ui_text("chart_value", language)
    figure = go.Figure(
        go.Bar(
            x=grouped["value"],
            y=grouped["country"],
            name=response_label,
            orientation="h",
            marker={"color": colors, "line": _selected_marker_line(selected)},
            customdata=grouped[["iso", "value_label", "value_text"]].fillna("").to_numpy(),
            hovertemplate="<b>%{y}</b><br>%{customdata[1]}: %{customdata[2]}<extra></extra>",
            showlegend=True,
        )
    )
    _apply_base_layout(figure, margin={"l": 120, "r": 28, "t": 20, "b": 55})
    figure.update_layout(
        xaxis={"title": "Valor", "range": [0, 100]},
        yaxis={"title": "", "automargin": True},
        legend={"title": {"text": "Respuesta"}, "orientation": "h", "y": -0.12},
        showlegend=True,
    )
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
    clean = pivot.apply(pd.to_numeric, errors="coerce")
    normalized = pd.DataFrame(index=clean.index, columns=clean.columns, dtype=float)
    for index, row in clean.iterrows():
        display_values, was_normalized = prepare_percentage_display_values(
            row.tolist(),
            normalize_when_total_is_not_100=True,
            logger=logger,
            context={"chart": "fra_response_comparison", "country": index[0] if isinstance(index, tuple) else index},
        )
        normalized.loc[index] = [
            0 if value is None else value
            for value in display_values
        ]
        if was_normalized:
            logger.debug(
                "fra_response_comparison_percentages_normalized",
                extra={"country": index[0] if isinstance(index, tuple) else index},
            )
    return normalized


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


def build_europe_distribution_chart(
    ranking_rows: list[dict[str, Any]],
    selected_countries: list[str] | None = None,
    language: str = "es",
) -> go.Figure:
    dataframe = _numeric_ranking_dataframe(ranking_rows)
    if dataframe.empty:
        return empty_figure(_chart_text(language, "No hay valores suficientes para analizar la distribución.", "There are not enough values to analyse the distribution."))
    selected = _selected_country_keys(selected_countries)
    figure = make_subplots(
        rows=1,
        cols=2,
        subplot_titles=(
            _chart_text(language, "Histograma", "Histogram"),
            _chart_text(language, "Boxplot", "Box plot"),
        ),
    )
    figure.add_trace(
        go.Histogram(x=dataframe["value"], marker={"color": CHART_COLORS["fra"]}, nbinsx=12, name=_chart_text(language, "Países", "Countries")),
        row=1,
        col=1,
    )
    figure.add_trace(
        go.Box(
            x=dataframe["value"],
            y=["Europa"] * len(dataframe),
            text=dataframe["country"],
            marker={"color": CHART_COLORS["fra"]},
            boxpoints="all",
            jitter=0.35,
            pointpos=0,
            name="Europa",
            hovertemplate="<b>%{text}</b><br>%{x:.2f}%<extra></extra>",
        ),
        row=1,
        col=2,
    )
    if selected:
        highlighted = dataframe[
            dataframe.apply(
                lambda row: _country_key(row.get("iso"), row.get("country")) in selected,
                axis=1,
            )
        ]
        if not highlighted.empty:
            figure.add_trace(
                go.Scatter(
                    x=highlighted["value"],
                    y=["Europa"] * len(highlighted),
                    text=highlighted["country"],
                    mode="markers",
                    marker={"color": "#111827", "size": 11, "line": {"color": "white", "width": 2}},
                    hovertemplate="<b>%{text}</b><br>%{x:.2f}%<extra></extra>",
                    name=_chart_text(language, "Selección", "Selection"),
                ),
                row=1,
                col=2,
            )
    mean = float(dataframe["value"].mean())
    figure.add_shape(type="line", x0=mean, x1=mean, y0=0, y1=1, xref="x", yref="paper", line={"dash": "dash", "color": CHART_COLORS["ilga"]})
    figure.add_shape(type="line", x0=mean, x1=mean, y0=0, y1=1, xref="x2", yref="paper", line={"dash": "dash", "color": CHART_COLORS["ilga"]})
    figure.update_xaxes(title_text=_chart_text(language, "Valor (%)", "Value (%)"))
    figure.update_yaxes(title_text=_chart_text(language, "Países", "Countries"), row=1, col=1)
    _apply_base_layout(figure, margin={"l": 55, "r": 25, "t": 55, "b": 55})
    figure.update_layout(showlegend=False)
    return figure


def build_eu_average_comparison_chart(
    ranking_rows: list[dict[str, Any]],
    selected_countries: list[str] | None = None,
    language: str = "es",
) -> go.Figure:
    dataframe = _numeric_ranking_dataframe(ranking_rows)
    if dataframe.empty:
        return empty_figure("No hay datos para comparar con la media europea.")
    mean = float(dataframe["value"].mean())
    selected = _selected_country_keys(selected_countries)
    focus = dataframe[
        dataframe.apply(lambda row: _country_key(row.get("iso"), row.get("country")) in selected, axis=1)
    ]
    if focus.empty:
        focus = dataframe.head(5)
    focus = focus.assign(difference=focus["value"] - mean).sort_values("difference")
    colors = [CHART_COLORS["ilga"] if value >= 0 else CHART_COLORS["fra_alt"] for value in focus["difference"]]
    figure = go.Figure(
        go.Bar(
            x=focus["difference"],
            y=focus["country"],
            orientation="h",
            marker={"color": colors},
            customdata=focus[["value"]].to_numpy(),
            hovertemplate="<b>%{y}</b><br>Valor: %{customdata[0]:.2f}%<br>Diferencia: %{x:+.2f} pp<extra></extra>",
        )
    )
    figure.add_vline(x=0, line_color="#6b7280", line_width=1.5)
    average_title = _chart_text(language, "Diferencia frente a la media europea", "Difference from the European average")
    figure.update_layout(xaxis={"title": f"{average_title} ({mean:.2f}%)"}, yaxis={"title": ""})
    _apply_base_layout(figure, margin={"l": 110, "r": 25, "t": 20, "b": 60})
    return figure


def build_country_comparison_chart(
    ranking_rows: list[dict[str, Any]],
    selected_countries: list[str] | None = None,
    language: str = "es",
) -> go.Figure:
    dataframe = _numeric_ranking_dataframe(ranking_rows)
    if dataframe.empty:
        return empty_figure(_chart_text(language, "No hay países comparables.", "There are no comparable countries."))
    selected = _selected_country_keys(selected_countries)
    if selected:
        dataframe = dataframe[
            dataframe.apply(lambda row: _country_key(row.get("iso"), row.get("country")) in selected, axis=1)
        ]
    else:
        dataframe = dataframe.head(10)
    dataframe = dataframe.sort_values("value")
    figure = go.Figure(
        go.Bar(
            x=dataframe["value"],
            y=dataframe["country"],
            orientation="h",
            marker={"color": CHART_COLORS["fra"]},
            text=dataframe["value"].map(lambda value: f"{value:.1f}%"),
            textposition="outside",
            hovertemplate="<b>%{y}</b><br>%{x:.2f}%<extra></extra>",
        )
    )
    figure.update_layout(xaxis={"title": _chart_text(language, "Valor (%)", "Value (%)"), "range": [0, 105]}, yaxis={"title": ""})
    _apply_base_layout(figure, margin={"l": 110, "r": 45, "t": 20, "b": 55})
    return figure


def build_filter_analysis_chart(
    data_rows: list[dict[str, Any]],
    selected_countries: list[str] | None = None,
    language: str = "es",
) -> go.Figure:
    dataframe = pd.DataFrame(data_rows)
    if dataframe.empty or "percentage" not in dataframe:
        return empty_figure("No hay segmentaciones comparables para esta consulta.")
    selected = _selected_country_keys(selected_countries)
    if selected:
        dataframe = dataframe[
            dataframe.apply(lambda row: _country_key(row.get("iso"), row.get("country")) in selected, axis=1)
        ]
    if "segment" not in dataframe:
        dataframe["segment"] = dataframe.apply(
            lambda row: next(
                (str(value) for value in (row.get("filter_a"), row.get("filter_b")) if str(value or "") not in {"", "All"}),
                "Todos",
            ),
            axis=1,
        )
    dataframe["percentage"] = pd.to_numeric(dataframe["percentage"], errors="coerce")
    grouped = dataframe.dropna(subset=["percentage"]).groupby(["segment", "answer"], as_index=False)["percentage"].mean()
    if grouped.empty:
        return empty_figure("No hay segmentaciones comparables para esta consulta.")
    figure = go.Figure()
    for answer, rows in grouped.groupby("answer"):
        figure.add_trace(
            go.Bar(
                x=rows["segment"],
                y=rows["percentage"],
                name=str(answer),
                marker={"color": _response_color(_response_key(answer))},
                hovertemplate="<b>%{x}</b><br>%{y:.2f}%<extra></extra>",
            )
        )
    figure.update_layout(
        barmode="group",
        xaxis={"title": _chart_text(language, "Segmento", "Segment")},
        yaxis={"title": _chart_text(language, "Valor (%)", "Value (%)"), "range": [0, 100]},
        showlegend=True,
    )
    _apply_base_layout(figure, margin={"l": 50, "r": 20, "t": 20, "b": 90})
    figure.update_layout(showlegend=True, legend={"orientation": "h", "y": -0.25})
    return figure


def build_temporal_evolution_chart(
    history_rows: list[dict[str, Any]],
    selected_countries: list[str] | None = None,
    language: str = "es",
) -> go.Figure:
    dataframe = pd.DataFrame(history_rows)
    if dataframe.empty or not {"year", "country", "value"}.issubset(dataframe.columns):
        return empty_figure(_chart_text(language, "No hay datos históricos para este indicador.", "There is no historical data for this indicator."))
    selected = _selected_country_keys(selected_countries)
    if selected:
        dataframe = dataframe[
            dataframe.apply(lambda row: _country_key(row.get("iso"), row.get("country")) in selected, axis=1)
        ]
    else:
        latest = dataframe.sort_values("year").groupby("country", as_index=False).tail(1).nlargest(6, "value")
        dataframe = dataframe[dataframe["country"].isin(latest["country"])]
    figure = go.Figure()
    for country, rows in dataframe.sort_values("year").groupby("country"):
        figure.add_trace(go.Scatter(x=rows["year"], y=rows["value"], mode="lines+markers", name=str(country)))
    figure.update_layout(
        xaxis={"title": _chart_text(language, "Año", "Year"), "dtick": 1},
        yaxis={"title": _chart_text(language, "Puntuación ILGA (%)", "ILGA score (%)"), "range": [0, 100]},
    )
    _apply_base_layout(figure, margin={"l": 55, "r": 25, "t": 20, "b": 55})
    figure.update_layout(showlegend=True, legend={"orientation": "h", "y": -0.2})
    return figure


def build_legal_reality_gap_chart(
    combined_rows: list[dict[str, Any]],
    selected_countries: list[str] | None = None,
    language: str = "es",
) -> go.Figure:
    dataframe = pd.DataFrame(combined_rows)
    if dataframe.empty:
        return empty_figure("No hay coincidencias FRA/ILGA para esta consulta.")
    selected = _selected_country_keys(selected_countries)
    if selected:
        dataframe = dataframe[dataframe["iso"].astype(str).str.upper().isin(selected)]
    else:
        dataframe = dataframe.assign(gap=(dataframe["ilga_value"] - dataframe["fra_value"]).abs()).nlargest(10, "gap")
    figure = go.Figure()
    figure.add_trace(go.Bar(y=dataframe["country"], x=dataframe["ilga_value"], orientation="h", name=_chart_text(language, "Protección legal", "Legal protection"), marker={"color": CHART_COLORS["ilga"]}))
    figure.add_trace(go.Bar(y=dataframe["country"], x=dataframe["fra_value"], orientation="h", name=_chart_text(language, "Experiencia real", "Lived experience"), marker={"color": CHART_COLORS["fra"]}))
    figure.update_layout(barmode="group", xaxis={"title": _chart_text(language, "Valor (%)", "Value (%)"), "range": [0, 100]}, yaxis={"title": ""})
    _apply_base_layout(figure, margin={"l": 110, "r": 20, "t": 20, "b": 60})
    figure.update_layout(showlegend=True, legend={"orientation": "h", "y": -0.18})
    return figure


def build_combined_scatter(combined_rows: list[dict[str, Any]], language: str = "es") -> go.Figure:
    dataframe = pd.DataFrame(combined_rows)
    if dataframe.empty:
        return empty_figure(_chart_text(language, "No hay coincidencias suficientes para estimar la relación.", "There are not enough matches to estimate the relationship."))
    correlation = dataframe["ilga_value"].corr(dataframe["fra_value"])
    figure = go.Figure(
        go.Scatter(
            x=dataframe["ilga_value"],
            y=dataframe["fra_value"],
            mode="markers+text",
            text=dataframe["country"],
            textposition="top center",
            marker={"size": 10, "color": CHART_COLORS["fra"]},
            hovertemplate="<b>%{text}</b><br>ILGA: %{x:.2f}%<br>FRA: %{y:.2f}%<extra></extra>",
        )
    )
    figure.update_layout(
        xaxis={"title": _chart_text(language, "Puntuación ILGA (%)", "ILGA score (%)"), "range": [0, 100]},
        yaxis={"title": _chart_text(language, "Indicador FRA (%)", "FRA indicator (%)"), "range": [0, 100]},
        annotations=[
            {
                "text": (
                    f"{_chart_text(language, 'Correlación', 'Correlation')}: {correlation:.2f}"
                    if pd.notna(correlation)
                    else _chart_text(language, "Correlación no disponible", "Correlation unavailable")
                ),
                "x": 0.01,
                "y": 0.99,
                "xref": "paper",
                "yref": "paper",
                "showarrow": False,
                "xanchor": "left",
            }
        ],
    )
    _apply_base_layout(figure)
    return figure


def build_combined_heatmap(combined_rows: list[dict[str, Any]], language: str = "es") -> go.Figure:
    dataframe = pd.DataFrame(combined_rows)
    if dataframe.empty:
        return empty_figure("No hay coincidencias para construir el mapa de calor.")
    dataframe = dataframe.sort_values("country")
    figure = go.Figure(
        go.Heatmap(
            z=dataframe[["ilga_value", "fra_value"]].to_numpy(),
            x=[
                _chart_text(language, "Protección legal", "Legal protection"),
                _chart_text(language, "Experiencia real", "Lived experience"),
            ],
            y=dataframe["country"],
            zmin=0,
            zmax=100,
            colorscale="RdYlGn",
            colorbar={"title": "%"},
            hovertemplate="<b>%{y}</b><br>%{x}: %{z:.2f}%<extra></extra>",
        )
    )
    _apply_base_layout(figure, margin={"l": 110, "r": 25, "t": 20, "b": 70})
    return figure


def build_combined_radar(
    combined_rows: list[dict[str, Any]],
    selected_countries: list[str] | None = None,
    language: str = "es",
) -> go.Figure:
    dataframe = pd.DataFrame(combined_rows)
    if dataframe.empty:
        return empty_figure(_chart_text(language, "No hay países para comparar en radar.", "There are no countries to compare in the radar chart."))
    selected = _selected_country_keys(selected_countries)
    if selected:
        dataframe = dataframe[dataframe["iso"].astype(str).str.upper().isin(selected)]
    else:
        dataframe = dataframe.head(4)
    figure = go.Figure()
    dimensions = [
        _chart_text(language, "Protección legal", "Legal protection"),
        _chart_text(language, "Experiencia real", "Lived experience"),
        _chart_text(language, "Equilibrio", "Balance"),
    ]
    for row in dataframe.head(6).itertuples():
        ilga_value = float(str(row.ilga_value))
        fra_value = float(str(row.fra_value))
        balance = max(0.0, 100 - abs(ilga_value - fra_value))
        values = [ilga_value, fra_value, balance]
        figure.add_trace(go.Scatterpolar(r=[*values, values[0]], theta=[*dimensions, dimensions[0]], fill="toself", name=str(row.country)))
    figure.update_layout(polar={"radialaxis": {"visible": True, "range": [0, 100]}}, showlegend=True)
    _apply_base_layout(figure, margin={"l": 45, "r": 45, "t": 35, "b": 45})
    figure.update_layout(showlegend=True)
    return figure


def _numeric_ranking_dataframe(ranking_rows: list[dict[str, Any]]) -> pd.DataFrame:
    dataframe = pd.DataFrame(ranking_rows)
    if dataframe.empty or not {"country", "value"}.issubset(dataframe.columns):
        return pd.DataFrame(columns=["country", "iso", "value"])
    if "iso" not in dataframe:
        dataframe["iso"] = ""
    dataframe["value"] = pd.to_numeric(dataframe["value"], errors="coerce")
    return dataframe.dropna(subset=["value"]).sort_values("value", ascending=False)


def _chart_text(language: str, spanish: str, english: str) -> str:
    return english if language == "en" else spanish


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
