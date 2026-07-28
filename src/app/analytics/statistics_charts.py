from __future__ import annotations

import logging
from typing import Any, cast

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from app.analytics.geography import (
    EUROPE_CENTROIDS,
    ISO2_TO_ISO3,
    to_iso3_country_code,
)
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
from app.analytics.statistics_normalizers import (
    normalize_country_code,
    normalize_text_key,
)
from app.dash.i18n import ui_text

logger = logging.getLogger(__name__)

COUNTRY_COLORS = {
    "FR": "#2F6BDE",
    "DE": "#2B2B2B",
    "BE": "#E3B505",
    "NL": "#E85D5D",
    "LU": "#5AA9E6",
    "IT": "#2E8B57",
    "DK": "#B22234",
    "ES": "#C62828",
    "PT": "#2F855A",
    "IE": "#F28C28",
    "GR": "#3A86D1",
    "SE": "#4A90E2",
    "FI": "#6FA8DC",
    "AT": "#8E2430",
    "EE": "#2C7DA0",
    "LV": "#7A1F2B",
    "LT": "#6B8E23",
    "PL": "#D45A7A",
    "CZ": "#1E5AA8",
    "SK": "#4361EE",
    "SI": "#3D5AFE",
    "HU": "#009B77",
    "RO": "#F4B400",
    "BG": "#5A8F29",
    "MT": "#D7265E",
    "CY": "#52B788",
    "HR": "#277DA1",
}
DEFAULT_COUNTRY_COLOR = "#2F6BDE"
EUROPE_PERCENTAGE_COLORSCALE = [
    [0.0, "#E8F1FC"],
    [0.5, "#8AAEE5"],
    [1.0, "#2F6BDE"],
]
YES_RESPONSE_COLOR = "#2E8B57"
NO_RESPONSE_COLOR = "#C62828"
ADDITIONAL_RESPONSE_COLORS = (
    "#2F6BDE",
    "#E3B505",
    "#F28C28",
    "#7A1F7A",
    "#2C7DA0",
    "#D45A7A",
)
COUNTRY_NAME_CODES = {
    "france": "FR",
    "francia": "FR",
    "germany": "DE",
    "alemania": "DE",
    "belgium": "BE",
    "belgica": "BE",
    "bélgica": "BE",
    "netherlands": "NL",
    "the netherlands": "NL",
    "paises bajos": "NL",
    "países bajos": "NL",
    "luxembourg": "LU",
    "luxemburgo": "LU",
    "italy": "IT",
    "italia": "IT",
    "denmark": "DK",
    "dinamarca": "DK",
    "spain": "ES",
    "espana": "ES",
    "españa": "ES",
    "portugal": "PT",
    "ireland": "IE",
    "irlanda": "IE",
    "greece": "GR",
    "grecia": "GR",
    "sweden": "SE",
    "suecia": "SE",
    "finland": "FI",
    "finlandia": "FI",
    "austria": "AT",
    "estonia": "EE",
    "latvia": "LV",
    "letonia": "LV",
    "lithuania": "LT",
    "lituania": "LT",
    "poland": "PL",
    "polonia": "PL",
    "czech republic": "CZ",
    "czechia": "CZ",
    "republica checa": "CZ",
    "república checa": "CZ",
    "slovakia": "SK",
    "eslovaquia": "SK",
    "slovenia": "SI",
    "eslovenia": "SI",
    "hungary": "HU",
    "hungria": "HU",
    "hungría": "HU",
    "romania": "RO",
    "rumania": "RO",
    "bulgaria": "BG",
    "malta": "MT",
    "cyprus": "CY",
    "chipre": "CY",
    "croatia": "HR",
    "croacia": "HR",
}
ISO3_TO_ISO2 = {iso3: iso2 for iso2, iso3 in ISO2_TO_ISO3.items()}
NON_GEOGRAPHIC_CODES = {"EU27"}
PLOTLY_TRANSPARENT = "rgba(0,0,0,0)"


def country_color(iso: Any = None, country: Any = None) -> str:
    """Return the approved country colour or the default blue."""
    clean_iso = None if _is_missing_country_value(iso) else iso
    code = normalize_country_code(clean_iso, country)
    code = ISO3_TO_ISO2.get(code, code)
    if code in COUNTRY_COLORS:
        return COUNTRY_COLORS[code]

    for candidate in (country, clean_iso):
        code = COUNTRY_NAME_CODES.get(normalize_text_key(candidate), "")
        if code in COUNTRY_COLORS:
            return COUNTRY_COLORS[code]
    return DEFAULT_COUNTRY_COLOR


def _is_missing_country_value(value: Any) -> bool:
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


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
                zmin=0,
                zmax=100,
                colorscale=EUROPE_PERCENTAGE_COLORSCALE,
                marker={"line": {"color": "#ffffff", "width": 0.75}},
                colorbar={
                    "title": ui_text("chart_percentage", language),
                    "ticksuffix": "%",
                    "thickness": 13,
                },
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
                marker={
                    "size": 13,
                    "color": "#111827",
                    "line": {"color": "#ffffff", "width": 2.5},
                },
                hovertemplate=(
                    f"<b>%{{text}}</b><br>"
                    f"{_chart_text(language, 'Seleccionado', 'Selected')}<extra></extra>"
                ),
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
            marker={"color": DEFAULT_COUNTRY_COLOR},
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
    elif mode == "missing_numeric":
        figure = _build_missing_numeric_response_chart(dataframe, selected_keys, language=language)
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
        incomplete = _incomplete_numeric_countries(dataframe)
        incomplete_keys = set(incomplete.get("country_key", pd.Series(dtype=str)).tolist())
        pivot = _response_percentage_pivot(
            dataframe[~dataframe["country_key"].isin(incomplete_keys)]
        )
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
            marker={
                "color": [
                    country_color(row.iso, row.country)
                    for row in dataframe.itertuples()
                ]
            },
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
    dataframe["numeric_measure_present"] = numeric_source is not None
    dataframe["country_key"] = dataframe.apply(
        lambda row: _country_key(row.get("iso"), row.get("country")),
        axis=1,
    )
    return dataframe[dataframe["country_key"].ne("")]


def _response_comparison_mode(dataframe: pd.DataFrame) -> str:
    has_numeric = dataframe["numeric_value"].notna().any()
    if not has_numeric:
        if dataframe.get("numeric_measure_present", pd.Series(dtype=bool)).any():
            return "missing_numeric"
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
    missing = _incomplete_numeric_countries(dataframe)
    missing_keys = set(missing.get("country_key", pd.Series(dtype=str)).tolist())
    complete_dataframe = dataframe[~dataframe["country_key"].isin(missing_keys)]
    pivot = _response_percentage_pivot(complete_dataframe)
    if pivot.empty:
        return _build_missing_numeric_response_chart(dataframe, selected_keys, language=language)
    labels = _response_labels(dataframe)
    normalized = _normalize_percentage_pivot(pivot)

    order = _stacked_country_order(normalized)
    pivot = pivot.loc[order]
    normalized = normalized.loc[order]
    countries = [country for country, _iso in normalized.index]
    isos = [iso for _country, iso in normalized.index]
    selected = [_country_key(iso, country) in selected_keys for country, iso in zip(countries, isos)]

    figure = go.Figure()
    response_keys = sorted(
        normalized.columns,
        key=lambda key: labels.get(str(key), str(key)).casefold(),
    )
    for response_index, response_key in enumerate(response_keys):
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
                    "color": _response_color(str(response_key), response_index),
                    "line": _selected_marker_line(selected),
                },
                customdata=[[iso, value_label, formatted] for iso, formatted in zip(isos, formatted_values)],
                hovertemplate="<b>%{y}</b><br>%{customdata[1]}: %{customdata[2]}<extra></extra>",
            )
        )
    _add_missing_country_bars(
        figure,
        missing,
        selected_keys,
        language=language,
    )
    _apply_base_layout(figure, margin={"l": 120, "r": 28, "t": 20, "b": 95})
    figure.update_layout(
        barmode="stack",
        xaxis={"title": "Distribución de respuestas", "range": [0, 100], "ticksuffix": "%"},
        yaxis={
            "title": "",
            "automargin": True,
            "categoryorder": "array",
            "categoryarray": [*missing["country"].tolist(), *countries],
        },
        legend={"title": {"text": "Respuesta"}, "orientation": "h", "y": -0.18},
        showlegend=True,
    )
    _add_selected_country_annotations(
        figure,
        [*countries, *missing.get("country", pd.Series(dtype=str)).tolist()],
        [*isos, *missing.get("iso", pd.Series(dtype=str)).tolist()],
        selected_keys,
    )
    return figure


def _build_numeric_response_chart(
    dataframe: pd.DataFrame,
    selected_keys: set[str],
    *,
    language: str = "es",
) -> go.Figure:
    missing = _incomplete_numeric_countries(dataframe)
    missing_keys = set(missing.get("country_key", pd.Series(dtype=str)).tolist())
    grouped = (
        dataframe[
            dataframe["numeric_value"].notna()
            & ~dataframe["country_key"].isin(missing_keys)
        ]
        .groupby(["country", "iso", "country_key"], dropna=False)
        .agg(value=("numeric_value", "mean"), response_label=("response_label", "first"), response_key=("response_key", "first"))
        .reset_index()
        .sort_values("value", ascending=True)
    )
    if grouped.empty and not missing.empty:
        return _build_missing_numeric_response_chart(dataframe, selected_keys, language=language)
    if grouped.empty:
        return empty_figure("No hay valores numéricos comparables para esta consulta.")

    selected = grouped["country_key"].isin(selected_keys).tolist()
    grouped["value_text"] = grouped["value"].apply(format_percentage)
    grouped["value_label"] = ui_text("chart_value", language)
    response_label = str(grouped["response_label"].dropna().iloc[0]) if not grouped["response_label"].dropna().empty else ui_text("chart_value", language)
    response_key = str(grouped["response_key"].dropna().iloc[0]) if not grouped["response_key"].dropna().empty else ""
    figure = go.Figure(
        go.Bar(
            x=grouped["value"],
            y=grouped["country"],
            name=response_label,
            orientation="h",
            marker={
                "color": _response_color(response_key),
                "line": _selected_marker_line(selected),
            },
            customdata=grouped[["iso", "value_label", "value_text"]].fillna("").to_numpy(),
            hovertemplate="<b>%{y}</b><br>%{customdata[1]}: %{customdata[2]}<extra></extra>",
            showlegend=True,
        )
    )
    _add_missing_country_bars(
        figure,
        missing,
        selected_keys,
        language=language,
    )
    _apply_base_layout(figure, margin={"l": 120, "r": 28, "t": 20, "b": 55})
    figure.update_layout(
        xaxis={"title": "Valor", "range": [0, 100]},
        yaxis={
            "title": "",
            "automargin": True,
            "categoryorder": "array",
            "categoryarray": [*missing["country"].tolist(), *grouped["country"].tolist()],
        },
        legend={"title": {"text": "Respuesta"}, "orientation": "h", "y": -0.12},
        showlegend=True,
    )
    _add_selected_country_annotations(
        figure,
        [*grouped["country"].tolist(), *missing.get("country", pd.Series(dtype=str)).tolist()],
        [*grouped["iso"].tolist(), *missing.get("iso", pd.Series(dtype=str)).tolist()],
        selected_keys,
    )
    return figure


def _build_missing_numeric_response_chart(
    dataframe: pd.DataFrame,
    selected_keys: set[str],
    *,
    language: str,
) -> go.Figure:
    missing = _incomplete_numeric_countries(dataframe)
    if missing.empty:
        return empty_figure("No hay valores numéricos comparables para esta consulta.")
    figure = go.Figure()
    _add_missing_country_bars(
        figure,
        missing,
        selected_keys,
        language=language,
    )
    _apply_base_layout(figure, margin={"l": 120, "r": 28, "t": 20, "b": 55})
    figure.update_layout(
        xaxis={"title": _chart_text(language, "Valor", "Value"), "range": [0, 100]},
        yaxis={"title": "", "automargin": True},
        legend={"title": {"text": _chart_text(language, "Respuesta", "Answer")}},
        showlegend=True,
    )
    _add_selected_country_annotations(
        figure,
        missing["country"].tolist(),
        missing["iso"].tolist(),
        selected_keys,
    )
    return figure


def _incomplete_numeric_countries(dataframe: pd.DataFrame) -> pd.DataFrame:
    columns = ["country", "iso", "country_key"]
    if (
        dataframe.empty
        or "numeric_value" not in dataframe
        or not dataframe.get("numeric_measure_present", pd.Series(dtype=bool)).any()
    ):
        return pd.DataFrame(columns=columns)
    response_keys = dataframe["response_key"].astype(str)
    normal_response_mask = ~response_keys.apply(_is_missing_response_label)
    expected_responses = sorted(response_keys[normal_response_mask].dropna().unique().tolist())
    availability = (
        dataframe[normal_response_mask]
        .groupby(["country_key", "response_key"])["numeric_value"]
        .apply(lambda values: values.notna().any())
        .unstack(fill_value=False)
        .reindex(columns=expected_responses, fill_value=False)
    )
    all_country_keys = pd.Index(dataframe["country_key"].dropna().unique())
    availability = availability.reindex(all_country_keys, fill_value=False)
    incomplete = ~availability.all(axis=1) if expected_responses else pd.Series(True, index=all_country_keys)
    explicitly_missing = set(
        dataframe.loc[
            response_keys.apply(_is_missing_response_label) | dataframe["numeric_value"].isna(),
            "country_key",
        ].tolist()
    )
    missing_keys = set(incomplete[incomplete].index).union(explicitly_missing)
    return (
        dataframe[dataframe["country_key"].isin(missing_keys)]
        .drop_duplicates("country_key")[columns]
        .sort_values("country")
        .reset_index(drop=True)
    )


def _add_missing_country_bars(
    figure: go.Figure,
    missing: pd.DataFrame,
    selected_keys: set[str],
    *,
    language: str,
) -> None:
    if missing.empty:
        return
    message = ui_text("chart_not_enough_information", language)
    selected = missing["country_key"].isin(selected_keys).tolist()
    figure.add_trace(
        go.Bar(
            x=[100] * len(missing),
            y=missing["country"],
            name=message,
            orientation="h",
            marker={
                "color": MISSING_PERCENTAGE_COLOR,
                "line": _selected_marker_line(selected),
            },
            customdata=[[iso, message] for iso in missing["iso"]],
            hovertemplate="<b>%{y}</b><br>%{customdata[1]}<extra></extra>",
        )
    )


def _build_categorical_response_chart(dataframe: pd.DataFrame, selected_keys: set[str]) -> go.Figure:
    labels = _response_labels(dataframe)
    country_answers = (
        dataframe.drop_duplicates(["country_key"])
        .sort_values(["response_label", "country"])
        [["country", "iso", "country_key", "response_key", "response_label"]]
    )
    figure = go.Figure()
    for response_index, (response_key, rows) in enumerate(
        country_answers.groupby("response_key", sort=False)
    ):
        selected = rows["country_key"].isin(selected_keys).tolist()
        response_label = labels.get(str(response_key), str(response_key))
        is_missing = _is_missing_response_label(response_label)
        figure.add_trace(
            go.Bar(
                x=[1] * len(rows),
                y=rows["country"],
                name=labels.get(str(response_key), str(response_key)),
                orientation="h",
                marker={
                    "color": (
                        MISSING_PERCENTAGE_COLOR
                        if is_missing
                        else _response_color(str(response_key), response_index)
                    ),
                    "line": _selected_marker_line(selected),
                },
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


def _response_color(response_key: str, additional_index: int = 0) -> str:
    key = normalize_text_key(response_key)
    if key in {"yes", "si", "sí", "true", "verdadero", "afirmativo", "afirmativa"}:
        return YES_RESPONSE_COLOR
    if key in {"no", "false", "falso", "negativo", "negativa"}:
        return NO_RESPONSE_COLOR
    return ADDITIONAL_RESPONSE_COLORS[
        additional_index % len(ADDITIONAL_RESPONSE_COLORS)
    ]


def _is_missing_response_label(value: Any) -> bool:
    key = " ".join(str(value or "").strip().casefold().split())
    return key in {
        "no hay suficiente información",
        "there is not enough information",
        "not enough information",
        "insufficient information",
        "datos insuficientes",
    }


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
    figure = go.Figure()
    for country, values, hover_values in zip(countries, matrix, customdata):
        country_rows = dataframe[dataframe["country"] == country]
        iso = (
            country_rows["iso"].dropna().iloc[0]
            if "iso" in country_rows and not country_rows["iso"].dropna().empty
            else None
        )
        color = country_color(iso, country)
        figure.add_trace(
            go.Heatmap(
                z=[values],
                x=criteria_labels,
                y=[country],
                zmin=0,
                zmax=1,
                xgap=1,
                ygap=1,
                colorscale=[[0.0, color], [1.0, color]],
                showscale=False,
                text=[
                    [
                        format_percentage(value * 100)
                        if value is not None
                        else ""
                        for value in values
                    ]
                ],
                texttemplate="%{text}",
                customdata=[hover_values],
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
    countries = merged["country_fra"].fillna(merged["country_ilga"])
    figure = go.Figure(
        go.Scatter(
            x=merged["ranking"],
            y=merged["fra_value"],
            mode="markers+text",
            text=countries,
            textposition="top center",
            marker={
                "size": 10,
                "color": [
                    country_color(iso, country)
                    for iso, country in zip(merged["iso"], countries)
                ],
            },
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
        go.Histogram(x=dataframe["value"], marker={"color": DEFAULT_COUNTRY_COLOR}, nbinsx=12, name=_chart_text(language, "Países", "Countries")),
        row=1,
        col=1,
    )
    figure.add_trace(
        go.Box(
            x=dataframe["value"],
            y=["Europa"] * len(dataframe),
            text=dataframe["country"],
            marker={"color": DEFAULT_COUNTRY_COLOR},
            boxpoints=False,
            name="Europa",
            hovertemplate="<b>%{text}</b><br>%{x:.2f}%<extra></extra>",
        ),
        row=1,
        col=2,
    )
    figure.add_trace(
        go.Scatter(
            x=dataframe["value"],
            y=["Europa"] * len(dataframe),
            text=dataframe["country"],
            mode="markers",
            marker={
                "color": [
                    country_color(row.iso, row.country)
                    for row in dataframe.itertuples()
                ],
                "size": 8,
                "opacity": 0.82,
                "line": {"color": "white", "width": 0.8},
            },
            hovertemplate="<b>%{text}</b><br>%{x:.2f}%<extra></extra>",
            name=_chart_text(language, "Países", "Countries"),
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
                    marker={
                        "color": [
                            country_color(row.iso, row.country)
                            for row in highlighted.itertuples()
                        ],
                        "size": 13,
                        "line": {"color": "#111827", "width": 2.5},
                    },
                    hovertemplate="<b>%{text}</b><br>%{x:.2f}%<extra></extra>",
                    name=_chart_text(language, "Selección", "Selection"),
                ),
                row=1,
                col=2,
            )
    mean = float(dataframe["value"].mean())
    figure.add_shape(type="line", x0=mean, x1=mean, y0=0, y1=1, xref="x", yref="paper", line={"dash": "dash", "color": DEFAULT_COUNTRY_COLOR})
    figure.add_shape(type="line", x0=mean, x1=mean, y0=0, y1=1, xref="x2", yref="paper", line={"dash": "dash", "color": DEFAULT_COUNTRY_COLOR})
    figure.update_xaxes(title_text=_chart_text(language, "Valor (%)", "Value (%)"))
    figure.update_yaxes(title_text=_chart_text(language, "Países", "Countries"), row=1, col=1)
    _apply_base_layout(figure, margin={"l": 55, "r": 25, "t": 55, "b": 55})
    figure.update_layout(showlegend=False)
    return figure


def build_comparative_ranking_chart(
    ranking_rows: list[dict[str, Any]],
    selected_countries: list[str] | None = None,
    language: str = "es",
) -> go.Figure:
    dataframe = _ranking_dataframe_with_missing(ranking_rows)
    if dataframe.empty:
        return empty_figure(
            _chart_text(
                language,
                "No hay países disponibles para el ranking.",
                "There are no countries available for the ranking.",
            )
        )

    selected = _selected_country_keys(selected_countries)
    if selected:
        dataframe = dataframe[
            dataframe.apply(
                lambda row: _country_key(row.get("iso"), row.get("country")) in selected,
                axis=1,
            )
        ]
    if dataframe.empty:
        return empty_figure(
            _chart_text(
                language,
                "Los países seleccionados no están disponibles para esta consulta.",
                "The selected countries are not available for this query.",
            )
        )

    dataframe = dataframe.sort_values(
        ["value", "country"],
        ascending=[True, False],
        na_position="first",
    )
    missing_label = _chart_text(language, "Sin datos", "No data")
    dataframe["plot_value"] = dataframe["value"].fillna(0.0)
    dataframe["value_text"] = dataframe["value"].map(
        lambda value: f"{value:.2f}%" if pd.notna(value) else missing_label
    )
    colors = [
        country_color(row.iso, row.country) if pd.notna(row.value) else MISSING_PERCENTAGE_COLOR
        for row in dataframe.itertuples()
    ]
    figure = go.Figure(
        go.Bar(
            x=dataframe["plot_value"],
            y=dataframe["country"],
            orientation="h",
            marker={"color": colors},
            text=dataframe["value_text"],
            textposition="outside",
            customdata=dataframe[["iso", "value_text"]].to_numpy(),
            hovertemplate="<b>%{y}</b><br>%{customdata[1]}<extra></extra>",
        )
    )
    maximum = dataframe["value"].max()
    figure.update_layout(
        xaxis={
            "title": _chart_text(language, "Valor (%)", "Value (%)"),
            "range": [0, max(105, float(maximum) + 12) if pd.notna(maximum) else 105],
        },
        yaxis={"title": ""},
        height=max(360, min(1150, 34 * len(dataframe) + 110)),
    )
    _apply_base_layout(figure, margin={"l": 125, "r": 65, "t": 20, "b": 55})
    return figure


def build_eu_average_comparison_chart(
    ranking_rows: list[dict[str, Any]],
    selected_countries: list[str] | None = None,
    language: str = "es",
) -> go.Figure:
    all_countries = _ranking_dataframe_with_missing(ranking_rows)
    numeric = all_countries.dropna(subset=["value"])
    if numeric.empty:
        return empty_figure(
            _chart_text(
                language,
                "No hay datos para comparar con la media europea.",
                "There are no data to compare with the European average.",
            )
        )
    stored_means = (
        pd.to_numeric(all_countries["european_mean"], errors="coerce").dropna()
        if "european_mean" in all_countries
        else pd.Series(dtype=float)
    )
    mean = (
        float(stored_means.iloc[0])
        if not stored_means.empty
        else float(numeric["value"].mean())
    )
    selected = _selected_country_keys(selected_countries)
    focus = all_countries[
        all_countries.apply(
            lambda row: _country_key(row.get("iso"), row.get("country")) in selected,
            axis=1,
        )
    ]
    if focus.empty:
        focus = numeric.head(5)
    focus = focus.copy()
    if "difference" not in focus:
        focus["difference"] = focus["value"] - mean
    else:
        focus["difference"] = pd.to_numeric(focus["difference"], errors="coerce")
    if "absolute_difference" not in focus:
        focus["absolute_difference"] = focus["difference"].abs()
    else:
        focus["absolute_difference"] = pd.to_numeric(
            focus["absolute_difference"],
            errors="coerce",
        )
    if "percentage_difference" not in focus:
        focus["percentage_difference"] = (
            focus["difference"] / mean * 100 if mean else float("nan")
        )
    else:
        focus["percentage_difference"] = pd.to_numeric(
            focus["percentage_difference"],
            errors="coerce",
        )
    focus = focus.sort_values(["difference", "country"], na_position="first")
    missing_label = _chart_text(language, "Sin datos", "No data")
    focus["plot_difference"] = focus["difference"].fillna(0.0)
    focus["value_text"] = focus["value"].map(
        lambda value: f"{value:.2f}%" if pd.notna(value) else missing_label
    )
    focus["absolute_text"] = focus["absolute_difference"].map(
        lambda value: f"{value:.2f} pp" if pd.notna(value) else missing_label
    )
    focus["percentage_text"] = focus["percentage_difference"].map(
        lambda value: f"{value:+.2f}%" if pd.notna(value) else missing_label
    )
    colors = [
        country_color(row.iso, row.country) if pd.notna(row.value) else MISSING_PERCENTAGE_COLOR
        for row in focus.itertuples()
    ]
    value_label = _chart_text(language, "Valor del país", "Country value")
    mean_label = _chart_text(language, "Media europea", "European average")
    absolute_label = _chart_text(language, "Diferencia absoluta", "Absolute difference")
    percentage_label = _chart_text(language, "Diferencia porcentual", "Percentage difference")
    figure = go.Figure(
        go.Bar(
            x=focus["plot_difference"],
            y=focus["country"],
            orientation="h",
            marker={"color": colors},
            customdata=focus[
                ["value_text", "absolute_text", "percentage_text"]
            ].to_numpy(),
            hovertemplate=(
                f"<b>%{{y}}</b><br>{value_label}: %{{customdata[0]}}"
                f"<br>{mean_label}: {mean:.2f}%"
                f"<br>{absolute_label}: %{{customdata[1]}}"
                f"<br>{percentage_label}: %{{customdata[2]}}<extra></extra>"
            ),
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
    *,
    detail_rows: list[dict[str, Any]] | None = None,
    source: str | None = None,
) -> go.Figure:
    if source == "FRA" and detail_rows:
        return _build_fra_grouped_country_chart(
            ranking_rows,
            detail_rows,
            selected_countries,
            language,
        )

    dataframe = _ranking_dataframe_with_missing(ranking_rows)
    if dataframe.empty:
        return empty_figure(_chart_text(language, "No hay países comparables.", "There are no comparable countries."))
    selected = _selected_country_keys(selected_countries)
    if selected:
        dataframe = dataframe[
            dataframe.apply(lambda row: _country_key(row.get("iso"), row.get("country")) in selected, axis=1)
        ]
    else:
        dataframe = dataframe.dropna(subset=["value"]).head(10)
    dataframe = dataframe.sort_values("value", na_position="first")
    if dataframe.empty:
        return empty_figure(
            _chart_text(
                language,
                "Los países seleccionados no tienen datos para este indicador.",
                "The selected countries have no data for this indicator.",
            )
        )
    missing_label = _chart_text(language, "Sin datos", "No data")
    dataframe["plot_value"] = dataframe["value"].fillna(0.0)
    dataframe["value_text"] = dataframe["value"].map(
        lambda value: f"{value:.2f}%" if pd.notna(value) else missing_label
    )
    figure = go.Figure(
        go.Bar(
            x=dataframe["plot_value"],
            y=dataframe["country"],
            orientation="h",
            marker={
                "color": [
                    country_color(row.iso, row.country)
                    if pd.notna(row.value)
                    else MISSING_PERCENTAGE_COLOR
                    for row in dataframe.itertuples()
                ]
            },
            text=dataframe["value_text"],
            textposition="outside",
            customdata=dataframe[["value_text"]].to_numpy(),
            hovertemplate="<b>%{y}</b><br>%{customdata[0]}<extra></extra>",
        )
    )
    figure.update_layout(xaxis={"title": _chart_text(language, "Valor (%)", "Value (%)"), "range": [0, 105]}, yaxis={"title": ""})
    _apply_base_layout(figure, margin={"l": 110, "r": 45, "t": 20, "b": 55})
    return figure


def _build_fra_grouped_country_chart(
    ranking_rows: list[dict[str, Any]],
    detail_rows: list[dict[str, Any]],
    selected_countries: list[str] | None,
    language: str,
) -> go.Figure:
    dataframe = _response_comparison_dataframe(detail_rows)
    if dataframe.empty or "percentage" not in dataframe:
        return empty_figure(
            _chart_text(
                language,
                "No hay respuestas comparables para los países seleccionados.",
                "There are no comparable answers for the selected countries.",
            )
        )
    selected = _selected_country_keys(selected_countries)
    missing_selected_names: list[str] = []
    if selected:
        available_detail_keys = set(dataframe["country_key"].astype(str))
        ranking = _ranking_dataframe_with_missing(ranking_rows)
        missing_selected_names = [
            str(row.country)
            for row in ranking.itertuples()
            if _country_key(row.iso, row.country) in selected
            and (
                pd.isna(row.value)
                or _country_key(row.iso, row.country) not in available_detail_keys
            )
        ]
        dataframe = dataframe[dataframe["country_key"].isin(selected)]
    else:
        leading = _numeric_ranking_dataframe(ranking_rows).head(8)
        leading_keys = {
            _country_key(row.iso, row.country) for row in leading.itertuples()
        }
        dataframe = dataframe[dataframe["country_key"].isin(leading_keys)]
    if dataframe.empty:
        return empty_figure(
            _chart_text(
                language,
                "Los países seleccionados no tienen respuestas para esta consulta.",
                "The selected countries have no responses for this query.",
            )
        )

    dataframe = dataframe.copy()
    dataframe["percentage"] = pd.to_numeric(dataframe["percentage"], errors="coerce")
    labels = _response_labels(dataframe)
    answer_order = list(dict.fromkeys(dataframe["response_key"].astype(str).tolist()))
    figure = go.Figure()
    for (_country_key_value, country, iso), rows in dataframe.groupby(
        ["country_key", "country", "iso"],
        sort=True,
        dropna=False,
    ):
        values_by_answer = (
            rows.groupby("response_key", dropna=False)["percentage"].mean().to_dict()
        )
        values = [values_by_answer.get(answer) for answer in answer_order]
        figure.add_trace(
            go.Bar(
                name=str(country),
                x=[labels.get(answer, answer) for answer in answer_order],
                y=values,
                marker={"color": country_color(iso, country)},
                customdata=[
                    [
                        str(iso),
                        (
                            f"{value:.2f}%"
                            if pd.notna(value)
                            else _chart_text(language, "Sin datos", "No data")
                        ),
                    ]
                    for value in values
                ],
                hovertemplate="<b>%{fullData.name}</b><br>%{x}: %{customdata[1]}<extra></extra>",
            )
        )
    figure.update_layout(
        barmode="group",
        xaxis={"title": _chart_text(language, "Respuesta", "Answer")},
        yaxis={"title": _chart_text(language, "Valor (%)", "Value (%)"), "range": [0, 105]},
        showlegend=True,
        legend={"orientation": "h", "y": -0.24},
        height=max(380, min(700, 340 + 24 * len(tuple(figure.data)))),
    )
    _apply_base_layout(figure, margin={"l": 55, "r": 25, "t": 20, "b": 95})
    figure.update_layout(showlegend=True)
    if missing_selected_names:
        figure.add_annotation(
            text=(
                f"{_chart_text(language, 'Sin datos', 'No data')}: "
                f"{', '.join(missing_selected_names)}"
            ),
            x=0,
            y=1.08,
            xref="paper",
            yref="paper",
            showarrow=False,
            xanchor="left",
            font={"color": MISSING_PERCENTAGE_COLOR, "size": 12},
        )
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
        iso = rows.iloc[0].get("iso")
        color = country_color(iso, country)
        figure.add_trace(
            go.Scatter(
                x=rows["year"],
                y=rows["value"],
                mode="lines+markers",
                name=str(country),
                line={"color": color},
                marker={"color": color},
            )
        )
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
    colors = [
        country_color(row.iso, row.country) for row in dataframe.itertuples()
    ]
    figure.add_trace(go.Bar(y=dataframe["country"], x=dataframe["ilga_value"], orientation="h", name=_chart_text(language, "Protección legal", "Legal protection"), marker={"color": colors, "opacity": 1.0}))
    figure.add_trace(go.Bar(y=dataframe["country"], x=dataframe["fra_value"], orientation="h", name=_chart_text(language, "Experiencia real", "Lived experience"), marker={"color": colors, "opacity": 0.5}))
    figure.update_layout(barmode="group", xaxis={"title": _chart_text(language, "Valor (%)", "Value (%)"), "range": [0, 100]}, yaxis={"title": ""})
    _apply_base_layout(figure, margin={"l": 110, "r": 20, "t": 20, "b": 60})
    figure.update_layout(showlegend=True, legend={"orientation": "h", "y": -0.18})
    return figure


def build_combined_scatter(
    combined_rows: list[dict[str, Any]],
    language: str = "es",
    selected_countries: list[str] | None = None,
) -> go.Figure:
    dataframe = pd.DataFrame(combined_rows)
    if dataframe.empty:
        return empty_figure(_chart_text(language, "No hay coincidencias suficientes para estimar la relación.", "There are not enough matches to estimate the relationship."))
    selected = _selected_country_keys(selected_countries)
    if selected:
        dataframe = dataframe[dataframe["iso"].astype(str).str.upper().isin(selected)]
    if dataframe.empty:
        return empty_figure(
            _chart_text(
                language,
                "Los países seleccionados no tienen datos FRA e ILGA comparables.",
                "The selected countries have no comparable FRA and ILGA data.",
            )
        )
    correlation = dataframe["ilga_value"].corr(dataframe["fra_value"])
    figure = go.Figure(
        go.Scatter(
            x=dataframe["ilga_value"],
            y=dataframe["fra_value"],
            mode="markers+text",
            text=dataframe["country"],
            textposition="top center",
            marker={
                "size": 10,
                "color": [
                    country_color(row.iso, row.country)
                    for row in dataframe.itertuples()
                ],
            },
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


def build_combined_heatmap(
    combined_rows: list[dict[str, Any]],
    language: str = "es",
    selected_countries: list[str] | None = None,
) -> go.Figure:
    dataframe = pd.DataFrame(combined_rows)
    if dataframe.empty:
        return empty_figure("No hay coincidencias para construir el mapa de calor.")
    selected = _selected_country_keys(selected_countries)
    if selected:
        dataframe = dataframe[dataframe["iso"].astype(str).str.upper().isin(selected)]
    if dataframe.empty:
        return empty_figure(
            _chart_text(
                language,
                "Los países seleccionados no tienen datos para el mapa de calor.",
                "The selected countries have no data for the heatmap.",
            )
        )
    dataframe = dataframe.sort_values("country")
    dimensions = [
        _chart_text(language, "Protección legal", "Legal protection"),
        _chart_text(language, "Experiencia real", "Lived experience"),
    ]
    values = dataframe[["ilga_value", "fra_value"]].to_numpy()
    figure = go.Figure(
        go.Heatmap(
            z=values,
            x=dimensions,
            y=dataframe["country"],
            zmin=0,
            zmax=100,
            colorscale=EUROPE_PERCENTAGE_COLORSCALE,
            colorbar={"title": "%", "ticksuffix": "%", "thickness": 13},
            text=[
                [format_percentage(value) or "" for value in row]
                for row in values
            ],
            texttemplate="%{text}",
            hovertemplate="<b>%{y}</b><br>%{x}: %{z:.2f}%<extra></extra>",
        )
    )
    _apply_base_layout(figure, margin={"l": 110, "r": 25, "t": 20, "b": 70})
    return figure


def build_indicator_radar(
    data_rows: list[dict[str, Any]],
    *,
    source: str,
    selected_countries: list[str] | None = None,
    language: str = "es",
) -> tuple[go.Figure, bool]:
    dataframe = pd.DataFrame(data_rows)
    incompatible_message = _chart_text(
        language,
        "Este indicador no dispone de tres dimensiones comparables.",
        "This indicator does not provide three comparable dimensions.",
    )
    if dataframe.empty:
        return empty_figure(incompatible_message), False

    radar_data: pd.DataFrame
    if source == "FRA":
        response_data = _response_comparison_dataframe(data_rows)
        if response_data.empty or "percentage" not in response_data:
            return empty_figure(incompatible_message), False
        response_data["percentage"] = pd.to_numeric(
            response_data["percentage"], errors="coerce"
        )
        response_data["dimension"] = response_data["answer"].astype(str)
        radar_data = response_data[
            ["country", "iso", "country_key", "dimension", "percentage"]
        ].rename(columns={"percentage": "radar_value"})
    else:
        legal = dataframe.copy()
        required = {
            "country",
            "iso",
            "category",
            "criterion",
            "criterion_value",
            "criterion_weight",
        }
        if not required.issubset(legal.columns):
            return empty_figure(incompatible_message), False
        legal = legal[
            legal["category"].astype(str).ne("Ranking total")
            & legal["criterion"].astype(str).str.strip().ne("")
        ]
        if legal.empty:
            return empty_figure(incompatible_message), False
        legal["normalized_value"] = [
            _normalized_criterion_value(
                _safe_chart_float(value),
                _safe_chart_float(weight),
            )
            for value, weight in zip(
                legal["criterion_value"],
                legal["criterion_weight"],
            )
        ]
        legal["radar_value"] = pd.to_numeric(
            legal["normalized_value"], errors="coerce"
        ) * 100
        category_count = legal["category"].dropna().astype(str).nunique()
        if category_count >= 3:
            legal["dimension"] = legal["category"].astype(str)
            radar_data = (
                legal.groupby(
                    ["country", "iso", "dimension"],
                    dropna=False,
                    as_index=False,
                )
                .agg(radar_value=("radar_value", "mean"))
            )
        else:
            legal["dimension"] = [
                get_criterion_metadata(
                    {
                        "category": row.category,
                        "indicator": row.criterion,
                    },
                    language,
                )["display_title"]
                for row in legal.itertuples()
            ]
            radar_data = legal[
                ["country", "iso", "dimension", "radar_value"]
            ]
        radar_data["country_key"] = [
            _country_key(iso, country)
            for iso, country in zip(radar_data["iso"], radar_data["country"])
        ]

    coverage = (
        radar_data.dropna(subset=["radar_value"])
        .groupby("dimension")["country_key"]
        .nunique()
        .sort_values(ascending=False)
    )
    dimensions = coverage.index.astype(str).tolist()[:10]
    if len(dimensions) < 3:
        return empty_figure(incompatible_message), False
    radar_data = radar_data[radar_data["dimension"].astype(str).isin(dimensions)]

    selected = _selected_country_keys(selected_countries)
    if selected:
        radar_data = radar_data[radar_data["country_key"].isin(selected)]
    else:
        leading = (
            radar_data.groupby(
                ["country_key", "country", "iso"],
                as_index=False,
            )
            .agg(radar_value=("radar_value", "mean"))
            .nlargest(4, columns="radar_value")
        )
        radar_data = radar_data[radar_data["country_key"].isin(leading["country_key"])]
    if radar_data.empty:
        return (
            empty_figure(
                _chart_text(
                    language,
                    "Los países seleccionados no tienen dimensiones para este radar.",
                    "The selected countries have no dimensions for this radar chart.",
                )
            ),
            True,
        )

    pivot = radar_data.pivot_table(
        index=["country_key", "country", "iso"],
        columns="dimension",
        values="radar_value",
        aggfunc="mean",
    ).reindex(columns=dimensions)
    figure = go.Figure()
    for raw_index, values in pivot.iterrows():
        _key, country, iso = cast(tuple[Any, Any, Any], raw_index)
        numeric_values = [
            float(value) if pd.notna(value) else None for value in values.tolist()
        ]
        color = country_color(iso, country)
        figure.add_trace(
            go.Scatterpolar(
                r=[*numeric_values, numeric_values[0]],
                theta=[*dimensions, dimensions[0]],
                fill="toself",
                name=str(country),
                line={"color": color, "width": 2},
                marker={"color": color},
                opacity=0.72,
                hovertemplate="<b>%{fullData.name}</b><br>%{theta}: %{r:.2f}%<extra></extra>",
            )
        )
    figure.update_layout(
        polar={"radialaxis": {"visible": True, "range": [0, 100], "ticksuffix": "%"}},
        showlegend=True,
        legend={"orientation": "h", "y": -0.18},
    )
    _apply_base_layout(figure, margin={"l": 55, "r": 55, "t": 45, "b": 80})
    figure.update_layout(showlegend=True)
    return figure, True


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
        color = country_color(getattr(row, "iso", None), row.country)
        figure.add_trace(
            go.Scatterpolar(
                r=[*values, values[0]],
                theta=[*dimensions, dimensions[0]],
                fill="toself",
                name=str(row.country),
                line={"color": color},
                marker={"color": color},
            )
        )
    figure.update_layout(polar={"radialaxis": {"visible": True, "range": [0, 100]}}, showlegend=True)
    _apply_base_layout(figure, margin={"l": 45, "r": 45, "t": 35, "b": 45})
    figure.update_layout(showlegend=True)
    return figure


def _numeric_ranking_dataframe(ranking_rows: list[dict[str, Any]]) -> pd.DataFrame:
    return _ranking_dataframe_with_missing(ranking_rows).dropna(
        subset=["value"]
    ).sort_values("value", ascending=False)


def _ranking_dataframe_with_missing(
    ranking_rows: list[dict[str, Any]],
) -> pd.DataFrame:
    dataframe = pd.DataFrame(ranking_rows)
    if dataframe.empty or not {"country", "value"}.issubset(dataframe.columns):
        return pd.DataFrame(columns=["country", "iso", "value"])
    dataframe = dataframe.copy()
    if "iso" not in dataframe:
        dataframe["iso"] = ""
    dataframe["value"] = pd.to_numeric(dataframe["value"], errors="coerce")
    dataframe["country"] = dataframe["country"].fillna("").astype(str)
    dataframe["iso"] = dataframe["iso"].fillna("").astype(str).str.upper()
    return dataframe.sort_values("value", ascending=False, na_position="last")


def _safe_chart_float(value: Any) -> float | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if pd.notna(numeric) else None


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
