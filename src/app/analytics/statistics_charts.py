from __future__ import annotations

import colorsys
import hashlib
import logging
import time
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
    normalize_percentage_values,
    prepare_percentage_display_values,
)
from app.analytics.statistics_normalizers import (
    normalize_country_code,
    normalize_text_key,
)
from app.dash.i18n import country_labels, ui_text

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
    """Return a stable country colour shared by every application chart."""
    clean_iso = None if _is_missing_country_value(iso) else iso
    normalized_code = normalize_country_code(clean_iso, country)
    normalized_code = ISO3_TO_ISO2.get(normalized_code, normalized_code)
    if normalized_code in COUNTRY_COLORS:
        return COUNTRY_COLORS[normalized_code]

    for candidate in (country, clean_iso):
        mapped_code = COUNTRY_NAME_CODES.get(normalize_text_key(candidate), "")
        if mapped_code in COUNTRY_COLORS:
            return COUNTRY_COLORS[mapped_code]
    if normalized_code in ISO2_TO_ISO3:
        hue = int(hashlib.sha256(normalized_code.encode("ascii")).hexdigest()[:8], 16) / 0xFFFFFFFF
        red, green, blue = colorsys.hls_to_rgb(hue, 0.48, 0.68)
        return f"#{round(red * 255):02X}{round(green * 255):02X}{round(blue * 255):02X}"
    return DEFAULT_COUNTRY_COLOR


def _is_missing_country_value(value: Any) -> bool:
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except TypeError, ValueError:
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
        set(dataframe.loc[dataframe["iso3"].eq(""), "iso"].dropna()).difference(
            NON_GEOGRAPHIC_CODES
        )
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
                customdata=drawable[["iso", "value_label", "display_value_text"]]
                .fillna("")
                .to_numpy(),
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
                    "<b>%{text}</b><br>%{customdata[1]}: %{customdata[2]}<extra></extra>"
                ),
            )
        )
    if not unavailable.empty:
        unavailable = unavailable.assign(
            missing_message=ui_text("chart_not_enough_information", language)
        )
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
                customdata=[
                    [str(row.iso)]
                    for row in selected.itertuples()
                    if EUROPE_CENTROIDS.get(str(row.iso))
                ],
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
        dragmode=False,
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
    figure.update_layout(
        xaxis={"title": "Respuesta"}, yaxis={"title": "Porcentaje medio", "range": [0, 100]}
    )
    _apply_base_layout(figure)
    return figure


def build_fra_response_comparison_chart(
    data_rows: list[dict[str, Any]],
    *,
    available_countries: list[dict[str, Any]] | None = None,
    selected_countries: list[str] | None = None,
    selected_response: str | None = None,
    language: str = "es",
) -> go.Figure:
    dataframe = _response_comparison_dataframe(
        _append_missing_response_countries(
            data_rows,
            available_countries,
            language=language,
        ),
        language=language,
        localize_countries=True,
    )
    if dataframe.empty:
        return empty_figure("No hay respuestas comparables para esta pregunta y filtros.")

    mode = _response_comparison_mode(dataframe)
    selected_keys = _selected_country_keys(selected_countries)
    if mode == "stacked_percentage":
        figure = _build_stacked_response_chart(
            dataframe,
            selected_keys,
            selected_response=selected_response,
            language=language,
        )
    elif mode == "missing_numeric":
        figure = _build_missing_numeric_response_chart(dataframe, selected_keys, language=language)
    elif mode == "categorical":
        figure = _build_categorical_response_chart(dataframe, selected_keys, language=language)
    else:
        figure = _build_numeric_response_chart(dataframe, selected_keys, language=language)
    country_count = int(dataframe["country_key"].nunique())
    _apply_response_details_height(
        figure,
        country_count,
        response_count=int(dataframe["response_key"].nunique()),
    )
    countries_without_data = int(_incomplete_numeric_countries(dataframe).shape[0])
    countries_with_data = country_count - countries_without_data
    logger.info(
        "response_details_chart countries_loaded=%d countries_rendered=%d "
        "countries_without_data=%d",
        country_count,
        countries_with_data,
        countries_without_data,
        extra={
            "countries_loaded": country_count,
            "countries_rendered": countries_with_data,
            "countries_without_data": countries_without_data,
        },
    )
    return figure


def summarize_response_comparison(
    data_rows: list[dict[str, Any]],
    *,
    available_countries: list[dict[str, Any]] | None = None,
    language: str = "es",
) -> dict[str, Any]:
    dataframe = _response_comparison_dataframe(
        _append_missing_response_countries(
            data_rows,
            available_countries,
            language=language,
        ),
        language=language,
        localize_countries=True,
    )
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
        counts = (
            country_answers.groupby("response_key")["country_key"]
            .nunique()
            .sort_values(ascending=False)
        )
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


def _append_missing_response_countries(
    data_rows: list[dict[str, Any]],
    available_countries: list[dict[str, Any]] | None,
    *,
    language: str,
) -> list[dict[str, Any]]:
    if not available_countries:
        return data_rows
    complete_rows = [dict(row) for row in data_rows]
    represented = {
        _country_key(row.get("iso"), row.get("country"))
        for row in complete_rows
        if isinstance(row, dict)
    }
    missing_label = ui_text("chart_not_enough_information", language)
    for country in available_countries:
        if not isinstance(country, dict):
            continue
        country_key = _country_key(country.get("iso"), country.get("country"))
        if not country_key or country_key == "EU27" or country_key in represented:
            continue
        complete_rows.append(
            {
                "country": country.get("country"),
                "iso": country.get("iso"),
                "answer": missing_label,
                "percentage": None,
                "year": country.get("year"),
                "source": country.get("source") or "FRA",
            }
        )
        represented.add(country_key)
    return complete_rows


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
                "color": [country_color(row.iso, row.country) for row in dataframe.itertuples()]
            },
            customdata=dataframe[["iso", "value_label", "value_text"]].fillna("").to_numpy(),
            hovertemplate="<b>%{x}</b><br>%{customdata[1]}: %{customdata[2]}<extra></extra>",
        )
    )
    figure.update_layout(xaxis={"title": ""}, yaxis={"title": "Porcentaje", "range": [0, 100]})
    _apply_base_layout(figure)
    return figure


def _response_comparison_dataframe(
    data_rows: list[dict[str, Any]],
    *,
    language: str = "es",
    localize_countries: bool = False,
) -> pd.DataFrame:
    dataframe = pd.DataFrame(data_rows)
    if dataframe.empty:
        return pd.DataFrame()
    dataframe = dataframe.copy()
    if "country" not in dataframe and "country_name" in dataframe:
        dataframe["country"] = dataframe["country_name"]
    if "country" not in dataframe:
        return pd.DataFrame()
    dataframe["country"] = dataframe["country"].astype(str).str.strip()
    if "iso" not in dataframe and "country_code" in dataframe:
        dataframe["iso"] = dataframe["country_code"]
    if "iso" in dataframe:
        dataframe["iso"] = [
            normalize_country_code(iso, country)
            for iso, country in zip(dataframe["iso"], dataframe["country"], strict=True)
        ]
    else:
        dataframe["iso"] = ""
    dataframe = dataframe[
        dataframe["country"].ne("")
        & dataframe["iso"].ne("EU27")
        & dataframe["country"].str.upper().ne("EU27")
    ]
    if dataframe.empty:
        return pd.DataFrame()

    answer_source = (
        "response" if "response" in dataframe else "answer" if "answer" in dataframe else None
    )
    if answer_source:
        dataframe["response_raw"] = dataframe[answer_source].astype(str)
        dataframe["response_key"] = dataframe["response_raw"].apply(_response_key)
        dataframe = dataframe[dataframe["response_key"].ne("")]
        if dataframe.empty:
            return pd.DataFrame()
        label_by_key = _response_labels(dataframe)
        dataframe["response_label"] = dataframe["response_key"].map(label_by_key)
    else:
        dataframe["response_raw"] = "Valor"
        dataframe["response_key"] = "value"
        dataframe["response_label"] = "Valor"

    numeric_source = (
        "percentage" if "percentage" in dataframe else "value" if "value" in dataframe else None
    )
    if numeric_source:
        dataframe["numeric_value"] = normalize_percentage_values(
            dataframe[numeric_source].tolist(),
            logger=logger,
            context={
                "chart": "fra_response_comparison",
                "field": numeric_source,
                "countries": sorted(dataframe["iso"].dropna().unique().tolist()),
                "indicators": sorted(
                    dataframe.get("question_code", pd.Series(dtype=str))
                    .dropna()
                    .astype(str)
                    .unique()
                    .tolist()
                ),
                "years": sorted(
                    dataframe.get("year", pd.Series(dtype=object)).dropna().unique().tolist()
                ),
            },
        )
    else:
        dataframe["numeric_value"] = None
    dataframe["numeric_measure_present"] = numeric_source is not None
    dataframe["country_key"] = [
        _country_key(iso, country)
        for iso, country in zip(dataframe["iso"], dataframe["country"], strict=True)
    ]
    dataframe = dataframe[dataframe["country_key"].ne("")]
    consolidated = _consolidate_response_rows(dataframe)
    if localize_countries:
        label_by_key = {
            key: country_labels(iso, fallback)[1 if language == "en" else 0]
            for key, iso, fallback in consolidated[["country_key", "iso", "country"]]
            .drop_duplicates("country_key")
            .itertuples(index=False, name=None)
        }
        consolidated["country"] = consolidated["country_key"].map(label_by_key)
    return consolidated


def _consolidate_response_rows(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Collapse exact source duplicates without averaging conflicting percentages."""
    if dataframe.empty:
        return dataframe
    dataframe = dataframe.copy()
    if "question_code" not in dataframe and "indicator_id" in dataframe:
        dataframe["question_code"] = dataframe["indicator_id"]
    for column in ("year", "source", "question", "question_code", "filter_a", "filter_b"):
        if column not in dataframe:
            dataframe[column] = None

    grouped = (
        dataframe.groupby(["country_key", "response_key"], as_index=False, sort=False, dropna=False)
        .agg(
            country=("country", "first"),
            iso=("iso", "first"),
            response_raw=("response_raw", "first"),
            response_label=("response_label", "first"),
            numeric_value=("numeric_value", "first"),
            numeric_measure_present=("numeric_measure_present", "first"),
            valid_value_count=("numeric_value", "count"),
            distinct_value_count=("numeric_value", "nunique"),
            source_row_count=("country", "size"),
            year=("year", "first"),
            source=("source", "first"),
            question=("question", "first"),
            question_code=("question_code", "first"),
            filter_a=("filter_a", "first"),
            filter_b=("filter_b", "first"),
        )
        .reset_index(drop=True)
    )
    ambiguous = (grouped["distinct_value_count"] > 1) | (
        (grouped["source_row_count"] > 1)
        & (grouped["valid_value_count"] > 0)
        & (grouped["valid_value_count"] < grouped["source_row_count"])
    )
    if ambiguous.any():
        affected = grouped.loc[
            ambiguous, ["country", "iso", "response_label", "source_row_count"]
        ].to_dict("records")
        logger.warning(
            "conflicting_percentage_values groups=%d affected=%r",
            int(ambiguous.sum()),
            affected[:12],
            extra={
                "conflicting_percentage_group_count": int(ambiguous.sum()),
                "conflicting_percentage_groups": affected[:12],
            },
        )
        grouped.loc[ambiguous, "numeric_value"] = None
    return grouped.drop(columns=["valid_value_count", "distinct_value_count", "source_row_count"])


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
    selected_response: str | None = None,
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

    order = _stacked_country_order(normalized, selected_response=selected_response)
    pivot = pivot.loc[order]
    normalized = normalized.loc[order]
    countries = [country for country, _iso in normalized.index]
    isos = [iso for _country, iso in normalized.index]
    metadata = _response_country_metadata(dataframe)
    metadata_rows = [
        metadata.get(_country_key(iso, country), {"year": "", "source": ""})
        for country, iso in zip(countries, isos, strict=True)
    ]
    selected = [
        _country_key(iso, country) in selected_keys
        for country, iso in zip(countries, isos, strict=True)
    ]

    figure = go.Figure()
    indicator_label = _response_indicator_label(dataframe)
    response_keys = sorted(
        normalized.columns,
        key=lambda key: labels.get(str(key), str(key)).casefold(),
    )
    for response_index, response_key in enumerate(response_keys):
        values = normalized[response_key].tolist()
        formatted_values = [format_percentage(value) or "" for value in values]
        response_label = labels.get(str(response_key), str(response_key))
        figure.add_trace(
            go.Bar(
                x=values,
                y=countries,
                name=response_label,
                orientation="h",
                marker={
                    "color": _response_color(str(response_key), response_index),
                    "line": _selected_marker_line(selected),
                },
                customdata=[
                    [
                        iso,
                        response_label,
                        formatted,
                        str(metadata_row["year"] or ""),
                        str(metadata_row["source"] or ""),
                    ]
                    for iso, formatted, metadata_row in zip(
                        isos, formatted_values, metadata_rows, strict=True
                    )
                ],
                meta=indicator_label,
                hovertemplate=(
                    f"<b>%{{y}}</b><br>"
                    f"{_chart_text(language, 'Indicador', 'Indicator')}: %{{meta}}<br>"
                    f"{_chart_text(language, 'Respuesta', 'Answer')}: %{{customdata[1]}}<br>"
                    f"{_chart_text(language, 'Porcentaje', 'Percentage')}: "
                    "%{customdata[2]}<br>"
                    f"{_chart_text(language, 'Año', 'Year')}: %{{customdata[3]}}<br>"
                    f"{_chart_text(language, 'Fuente', 'Source')}: "
                    "%{customdata[4]}<extra></extra>"
                ),
            )
        )
    _add_missing_country_bars(
        figure,
        missing,
        selected_keys,
        language=language,
    )
    _apply_base_layout(
        figure,
        margin=_response_chart_margin(dataframe, response_count=len(response_keys)),
    )
    figure.update_layout(
        barmode="stack",
        xaxis={
            "title": _chart_text(language, "Distribución de respuestas", "Response distribution"),
            "range": [0, 100],
            "ticksuffix": "%",
            "automargin": True,
        },
        yaxis={
            "title": "",
            "automargin": True,
            "categoryorder": "array",
            "categoryarray": [*missing["country"].tolist(), *countries],
        },
        legend={
            "title": {"text": _chart_text(language, "Respuesta", "Answer")},
            "orientation": "h",
            "y": -0.12,
            "yanchor": "top",
        },
        showlegend=True,
    )
    _add_selected_country_annotations(
        figure,
        [*countries, *missing.get("country", pd.Series(dtype=str)).tolist()],
        [*isos, *missing.get("iso", pd.Series(dtype=str)).tolist()],
        selected_keys,
        language=language,
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
    grouped = dataframe.loc[
        dataframe["numeric_value"].notna() & ~dataframe["country_key"].isin(missing_keys),
        [
            "country",
            "iso",
            "country_key",
            "numeric_value",
            "response_label",
            "response_key",
            "year",
            "source",
        ],
    ].rename(columns={"numeric_value": "value"})
    grouped = grouped.sort_values(["value", "country"], ascending=[True, False])
    if grouped.empty and not missing.empty:
        return _build_missing_numeric_response_chart(dataframe, selected_keys, language=language)
    if grouped.empty:
        return empty_figure("No hay valores numéricos comparables para esta consulta.")

    selected = grouped["country_key"].isin(selected_keys).tolist()
    grouped["value_text"] = grouped["value"].apply(format_percentage)
    response_label = (
        str(grouped["response_label"].dropna().iloc[0])
        if not grouped["response_label"].dropna().empty
        else ui_text("chart_value", language)
    )
    response_key = (
        str(grouped["response_key"].dropna().iloc[0])
        if not grouped["response_key"].dropna().empty
        else ""
    )
    indicator_label = _response_indicator_label(dataframe)
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
            customdata=grouped[["iso", "response_label", "value_text", "year", "source"]]
            .fillna("")
            .to_numpy(),
            meta=indicator_label,
            hovertemplate=(
                f"<b>%{{y}}</b><br>"
                f"{_chart_text(language, 'Indicador', 'Indicator')}: %{{meta}}<br>"
                f"{_chart_text(language, 'Respuesta', 'Answer')}: %{{customdata[1]}}<br>"
                f"{_chart_text(language, 'Porcentaje', 'Percentage')}: %{{customdata[2]}}<br>"
                f"{_chart_text(language, 'Año', 'Year')}: %{{customdata[3]}}<br>"
                f"{_chart_text(language, 'Fuente', 'Source')}: "
                "%{customdata[4]}<extra></extra>"
            ),
            showlegend=True,
        )
    )
    _add_missing_country_bars(
        figure,
        missing,
        selected_keys,
        language=language,
    )
    _apply_base_layout(figure, margin=_response_chart_margin(dataframe, response_count=1))
    figure.update_layout(
        xaxis={
            "title": _chart_text(language, "Porcentaje", "Percentage"),
            "range": [0, 100],
            "ticksuffix": "%",
            "automargin": True,
        },
        yaxis={
            "title": "",
            "automargin": True,
            "categoryorder": "array",
            "categoryarray": [*missing["country"].tolist(), *grouped["country"].tolist()],
        },
        legend={
            "title": {"text": _chart_text(language, "Respuesta", "Answer")},
            "orientation": "h",
            "y": -0.1,
            "yanchor": "top",
        },
        showlegend=True,
    )
    _add_selected_country_annotations(
        figure,
        [*grouped["country"].tolist(), *missing.get("country", pd.Series(dtype=str)).tolist()],
        [*grouped["iso"].tolist(), *missing.get("iso", pd.Series(dtype=str)).tolist()],
        selected_keys,
        language=language,
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
    _apply_base_layout(figure, margin=_response_chart_margin(dataframe, response_count=1))
    figure.update_layout(
        xaxis={
            "title": _chart_text(language, "Valor", "Value"),
            "range": [0, 100],
            "automargin": True,
        },
        yaxis={"title": "", "automargin": True},
        legend={"title": {"text": _chart_text(language, "Respuesta", "Answer")}},
        showlegend=True,
    )
    _add_selected_country_annotations(
        figure,
        missing["country"].tolist(),
        missing["iso"].tolist(),
        selected_keys,
        language=language,
    )
    return figure


def _incomplete_numeric_countries(dataframe: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "country",
        "iso",
        "country_key",
        "year",
        "source",
        "question",
        "question_code",
    ]
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
    incomplete = (
        ~availability.all(axis=1) if expected_responses else pd.Series(True, index=all_country_keys)
    )
    explicitly_missing = set(
        dataframe.loc[
            response_keys.apply(_is_missing_response_label) | dataframe["numeric_value"].isna(),
            "country_key",
        ].tolist()
    )
    non_positive_distribution: set[str] = set()
    if len(expected_responses) > 1:
        country_totals = (
            dataframe[normal_response_mask].groupby("country_key")["numeric_value"].sum(min_count=1)
        )
        non_positive_distribution = set(
            country_totals[country_totals.notna() & country_totals.le(0)].index
        )
    missing_keys = (
        set(incomplete[incomplete].index).union(explicitly_missing).union(non_positive_distribution)
    )
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
    indicator_label = _response_indicator_label(missing)
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
            customdata=[
                [iso, message, str(year or ""), str(source or "")]
                for iso, year, source in zip(
                    missing["iso"], missing["year"], missing["source"], strict=True
                )
            ],
            meta=indicator_label,
            hovertemplate=(
                f"<b>%{{y}}</b><br>"
                f"{_chart_text(language, 'Indicador', 'Indicator')}: %{{meta}}<br>"
                "%{customdata[1]}<br>"
                f"{_chart_text(language, 'Año', 'Year')}: %{{customdata[2]}}<br>"
                f"{_chart_text(language, 'Fuente', 'Source')}: "
                "%{customdata[3]}<extra></extra>"
            ),
        )
    )


def _build_categorical_response_chart(
    dataframe: pd.DataFrame, selected_keys: set[str], *, language: str
) -> go.Figure:
    labels = _response_labels(dataframe)
    country_answers = dataframe.drop_duplicates(["country_key"]).sort_values(
        ["response_label", "country"]
    )[
        [
            "country",
            "iso",
            "country_key",
            "response_key",
            "response_label",
            "year",
            "source",
        ]
    ]
    figure = go.Figure()
    indicator_label = _response_indicator_label(dataframe)
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
                customdata=rows[["iso", "response_label", "year", "source"]].fillna("").to_numpy(),
                meta=indicator_label,
                hovertemplate=(
                    f"<b>%{{y}}</b><br>ISO: %{{customdata[0]}}<br>"
                    f"{_chart_text(language, 'Indicador', 'Indicator')}: %{{meta}}<br>"
                    f"{_chart_text(language, 'Respuesta', 'Answer')}: "
                    "%{customdata[1]}<br>"
                    f"{_chart_text(language, 'Año', 'Year')}: %{{customdata[2]}}<br>"
                    f"{_chart_text(language, 'Fuente', 'Source')}: "
                    "%{customdata[3]}<extra></extra>"
                ),
            )
        )
    _apply_base_layout(
        figure,
        margin=_response_chart_margin(dataframe, response_count=len(tuple(figure.data))),
    )
    figure.update_layout(
        barmode="stack",
        xaxis={
            "title": _chart_text(language, "Respuesta categórica", "Categorical answer"),
            "showticklabels": False,
            "range": [0, 1],
            "automargin": True,
        },
        yaxis={"title": "", "automargin": True},
        legend={
            "title": {"text": _chart_text(language, "Respuesta", "Answer")},
            "orientation": "h",
            "y": -0.12,
            "yanchor": "top",
        },
        showlegend=True,
    )
    _add_selected_country_annotations(
        figure,
        country_answers["country"].tolist(),
        country_answers["iso"].tolist(),
        selected_keys,
        language=language,
    )
    return figure


def _response_percentage_pivot(dataframe: pd.DataFrame) -> pd.DataFrame:
    grouped = dataframe.loc[
        dataframe["numeric_value"].notna(),
        ["country", "iso", "response_key", "numeric_value"],
    ]
    return grouped.pivot(
        index=["country", "iso"],
        columns="response_key",
        values="numeric_value",
    )


def _normalize_percentage_pivot(pivot: pd.DataFrame) -> pd.DataFrame:
    if pivot.empty:
        return pivot
    clean = pivot.apply(pd.to_numeric, errors="coerce")
    totals = clean.sum(axis=1, min_count=1)
    should_normalize = totals.notna() & totals.gt(0) & ~totals.sub(100.0).abs().le(1e-9)
    normalized = clean.copy()
    normalized.loc[should_normalize] = (
        clean.loc[should_normalize].div(totals.loc[should_normalize], axis=0).mul(100.0)
    )
    if should_normalize.any():
        logger.debug(
            "fra_response_comparison_percentages_normalized countries=%d",
            int(should_normalize.sum()),
            extra={"country_count": int(should_normalize.sum())},
        )
    return normalized


def _stacked_country_order(
    normalized: pd.DataFrame, *, selected_response: str | None
) -> list[tuple[str, str]]:
    order = pd.DataFrame(index=normalized.index)
    selected_key = _response_key(selected_response)
    matching_key = next(
        (column for column in normalized.columns if _response_key(column) == selected_key),
        None,
    )
    order["comparison_value"] = (
        normalized[matching_key] if matching_key is not None else normalized.max(axis=1)
    )
    order["country_name"] = [country for country, _iso in normalized.index]
    # Plotly's category array runs from bottom to top. Ascending values here
    # therefore render the highest percentage first at the top of the chart.
    return order.sort_values(
        ["comparison_value", "country_name"],
        ascending=[True, False],
    ).index.tolist()


def _response_country_metadata(dataframe: pd.DataFrame) -> dict[str, dict[str, Any]]:
    if dataframe.empty:
        return {}
    return cast(
        dict[str, dict[str, Any]],
        dataframe.groupby("country_key", sort=False, dropna=False)
        .agg(year=("year", "first"), source=("source", "first"))
        .to_dict("index"),
    )


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
        str(country or "").strip().upper()
        if len(str(country or "").strip()) <= 3
        else _country_key("", country)
        for country in selected_countries or []
        if str(country or "").strip()
    }


def _response_color(response_key: str, additional_index: int = 0) -> str:
    key = normalize_text_key(response_key)
    if key in {"yes", "si", "sí", "true", "verdadero", "afirmativo", "afirmativa"}:
        return YES_RESPONSE_COLOR
    if key in {"no", "false", "falso", "negativo", "negativa"}:
        return NO_RESPONSE_COLOR
    return ADDITIONAL_RESPONSE_COLORS[additional_index % len(ADDITIONAL_RESPONSE_COLORS)]


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


def _response_indicator_label(dataframe: pd.DataFrame) -> str:
    for column in ("question", "indicator_id", "question_code"):
        if column not in dataframe:
            continue
        values = dataframe[column].dropna().astype(str).str.strip()
        values = values[values.ne("")]
        if not values.empty:
            return str(values.iloc[0])
    return ""


def _response_chart_margin(dataframe: pd.DataFrame, *, response_count: int) -> dict[str, int]:
    longest_country = max(
        (len(str(country)) for country in dataframe.get("country", pd.Series(dtype=str))),
        default=0,
    )
    left = min(250, max(140, longest_country * 7 + 24))
    legend_rows = max(1, (max(1, response_count) + 3) // 4)
    return {"l": left, "r": 96, "t": 84, "b": 78 + legend_rows * 24}


def _add_selected_country_annotations(
    figure: go.Figure,
    countries: list[str],
    isos: list[str],
    selected_keys: set[str],
    *,
    language: str,
) -> None:
    for country, iso in zip(countries, isos, strict=True):
        if _country_key(iso, country) not in selected_keys:
            continue
        figure.add_annotation(
            x=1.01,
            y=country,
            xref="paper",
            yref="y",
            text=_chart_text(language, "Seleccionado", "Selected"),
            showarrow=False,
            xanchor="left",
            font={"size": 11, "color": "#111827"},
            bgcolor="rgba(255,255,255,0.86)",
            bordercolor="#111827",
            borderwidth=1,
        )


def _apply_comparison_height(figure: go.Figure, country_count: int) -> None:
    figure.update_layout(height=min(1280, max(500, country_count * 28 + 190)))


def _apply_response_details_height(
    figure: go.Figure, country_count: int, *, response_count: int = 1
) -> None:
    legend_rows = max(1, (max(1, response_count) + 3) // 4)
    figure.update_layout(
        autosize=True,
        height=max(520, country_count * 32 + 205 + (legend_rows - 1) * 24),
    )


def build_ilga_criteria_heatmap(
    data_rows: list[dict[str, Any]],
    *,
    available_countries: list[dict[str, Any]] | None = None,
    language: str = "es",
) -> go.Figure:
    dataframe = pd.DataFrame(data_rows)
    dataframe = (
        dataframe[dataframe.get("criterion", pd.Series(dtype=str)).astype(str).str.strip().ne("")]
        if not dataframe.empty
        else dataframe
    )
    if dataframe.empty:
        return empty_figure("No hay criterios jurídicos para esta selección.")
    dataframe = _consolidate_legal_criteria(dataframe)
    if dataframe.empty:
        return empty_figure("No hay criterios jurídicos para esta selección.")

    country_frame = _legal_country_universe(dataframe, available_countries)
    countries = country_frame["country"].tolist()
    country_keys = country_frame["country_key"].tolist()
    criteria = dataframe["criterion"].drop_duplicates().tolist()
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
    criterion_records = cast(list[dict[str, Any]], dataframe.to_dict("records"))
    lookup = {
        (str(row.get("country_key") or ""), str(row.get("criterion") or "")): row
        for row in criterion_records
    }
    matrix: list[list[float | None]] = []
    customdata: list[list[list[str]]] = []
    for _country, country_key in zip(countries, country_keys, strict=True):
        row: list[float | None] = []
        custom_row: list[list[str]] = []
        country_metadata = country_frame[country_frame["country_key"].eq(country_key)].iloc[0]
        for criterion in criteria:
            match = lookup.get((country_key, criterion))
            if match is None:
                row.append(None)
                custom_row.append(
                    _legal_hover_data(
                        {
                            "category": _first_criterion_category(dataframe, criterion),
                            "criterion": criterion,
                            "year": country_metadata.get("year"),
                            "source": country_metadata.get("source"),
                        },
                        None,
                        None,
                        language=language,
                    )
                )
                continue
            value = normalize_percentage(match.get("criterion_value"))
            weight = normalize_percentage(match.get("criterion_weight"))
            row.append(_normalized_criterion_value(value, weight))
            custom_row.append(_legal_hover_data(match, value, weight, language=language))
        matrix.append(row)
        customdata.append(custom_row)
    figure = go.Figure()
    for country_index, (country, values, hover_values) in enumerate(
        zip(countries, matrix, customdata, strict=True)
    ):
        iso = country_frame.iloc[country_index].get("iso")
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
                        format_percentage(value * 100) if value is not None else ""
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
                    "%{customdata[4]}<br>"
                    f"{_chart_text(language, 'Año', 'Year')}: %{{customdata[5]}}<br>"
                    f"{_chart_text(language, 'Fuente', 'Source')}: %{{customdata[6]}}"
                    "<extra></extra>"
                ),
            )
        )
    figure.update_layout(
        xaxis={
            "title": _chart_text(language, "Criterio", "Criterion"),
            "automargin": True,
            "tickangle": -25,
        },
        yaxis={
            "title": "",
            "automargin": True,
            "categoryorder": "array",
            "categoryarray": countries,
        },
        hoverlabel={"align": "left"},
    )
    _apply_base_layout(figure, margin={"l": 150, "r": 20, "t": 20, "b": 180})
    _apply_comparison_height(figure, len(countries))
    return figure


def _consolidate_legal_criteria(dataframe: pd.DataFrame) -> pd.DataFrame:
    dataframe = dataframe.copy()
    for column in ("country", "iso", "criterion"):
        if column not in dataframe:
            dataframe[column] = ""
    dataframe["country"] = dataframe["country"].fillna("").astype(str).str.strip()
    dataframe["iso"] = dataframe["iso"].fillna("").astype(str).str.strip().str.upper()
    dataframe["criterion"] = dataframe["criterion"].fillna("").astype(str).str.strip()
    dataframe["country_key"] = dataframe.apply(
        lambda row: _country_key(row.get("iso"), row.get("country")),
        axis=1,
    )
    for column in ("category", "year", "source", "criterion_value", "criterion_weight"):
        if column not in dataframe:
            dataframe[column] = None
    dataframe["criterion_value"] = normalize_percentage_values(
        dataframe["criterion_value"].tolist(),
        logger=logger,
        context={"chart": "ilga_criteria_heatmap", "field": "criterion_value"},
    )
    dataframe["criterion_weight"] = normalize_percentage_values(
        dataframe["criterion_weight"].tolist(),
        logger=logger,
        context={"chart": "ilga_criteria_heatmap", "field": "criterion_weight"},
    )
    grouped = (
        dataframe[dataframe["country_key"].ne("") & dataframe["criterion"].ne("")]
        .groupby(["country_key", "criterion"], as_index=False, sort=False, dropna=False)
        .agg(
            country=("country", "first"),
            iso=("iso", "first"),
            category=("category", "first"),
            criterion_value=("criterion_value", "first"),
            criterion_weight=("criterion_weight", "first"),
            value_variants=("criterion_value", "nunique"),
            weight_variants=("criterion_weight", "nunique"),
            year=("year", "first"),
            source=("source", "first"),
        )
    )
    conflicting = (grouped["value_variants"] > 1) | (grouped["weight_variants"] > 1)
    if conflicting.any():
        affected = grouped.loc[conflicting, ["country", "iso", "criterion"]].to_dict("records")
        logger.warning(
            "conflicting_legal_criterion_values groups=%d affected=%r",
            int(conflicting.sum()),
            affected[:12],
        )
        grouped.loc[conflicting, ["criterion_value", "criterion_weight"]] = None
    return grouped.drop(columns=["value_variants", "weight_variants"])


def _legal_country_universe(
    dataframe: pd.DataFrame,
    available_countries: list[dict[str, Any]] | None,
) -> pd.DataFrame:
    universe = pd.DataFrame(available_countries or [])
    for column in ("country", "iso", "year", "source", "ranking"):
        if column not in universe:
            universe[column] = None
    observed = dataframe[["country", "iso", "year", "source"]].drop_duplicates()
    combined = pd.concat(
        [universe[["country", "iso", "year", "source", "ranking"]], observed],
        ignore_index=True,
        sort=False,
    )
    combined["country"] = combined["country"].fillna("").astype(str).str.strip()
    combined["iso"] = combined["iso"].fillna("").astype(str).str.strip().str.upper()
    combined["country_key"] = combined.apply(
        lambda row: _country_key(row.get("iso"), row.get("country")),
        axis=1,
    )
    combined["ranking"] = pd.to_numeric(combined["ranking"], errors="coerce")
    scores = dataframe.assign(
        comparison_value=dataframe.apply(
            lambda row: _normalized_criterion_value(
                row.get("criterion_value"), row.get("criterion_weight")
            ),
            axis=1,
        )
    )
    scores = scores.groupby("country_key", as_index=False, dropna=False)["comparison_value"].mean()
    combined = combined.merge(scores, on="country_key", how="left")
    return (
        combined[combined["country_key"].ne("")]
        .sort_values(
            ["comparison_value", "ranking", "country"],
            ascending=[False, False, True],
            na_position="last",
        )
        .drop_duplicates("country_key")
        .reset_index(drop=True)
    )


def build_fra_ilga_scatter(
    fra_rows: list[dict[str, Any]], ilga_rows: list[dict[str, Any]]
) -> go.Figure:
    fra = pd.DataFrame(fra_rows)
    ilga = pd.DataFrame(ilga_rows)
    if fra.empty or ilga.empty:
        return empty_figure("No hay coincidencia suficiente entre FRA e ILGA-Europe.")
    fra_grouped = (
        fra.groupby(["country", "iso"], dropna=False)["percentage"]
        .mean()
        .reset_index(name="fra_value")
    )
    ilga_grouped = ilga[ilga["category"] == "Ranking total"][
        ["country", "iso", "ranking"]
    ].drop_duplicates()
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
                    for iso, country in zip(merged["iso"], countries, strict=True)
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
        return empty_figure(
            _chart_text(
                language,
                "No hay valores suficientes para analizar la distribución.",
                "There are not enough values to analyse the distribution.",
            )
        )
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
        go.Histogram(
            x=dataframe["value"],
            marker={"color": DEFAULT_COUNTRY_COLOR},
            nbinsx=12,
            name=_chart_text(language, "Países", "Countries"),
        ),
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
                "color": [country_color(row.iso, row.country) for row in dataframe.itertuples()],
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
                            country_color(row.iso, row.country) for row in highlighted.itertuples()
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
    figure.add_shape(
        type="line",
        x0=mean,
        x1=mean,
        y0=0,
        y1=1,
        xref="x",
        yref="paper",
        line={"dash": "dash", "color": DEFAULT_COUNTRY_COLOR},
    )
    figure.add_shape(
        type="line",
        x0=mean,
        x1=mean,
        y0=0,
        y1=1,
        xref="x2",
        yref="paper",
        line={"dash": "dash", "color": DEFAULT_COUNTRY_COLOR},
    )
    figure.update_xaxes(title_text=_chart_text(language, "Valor (%)", "Value (%)"))
    figure.update_yaxes(title_text=_chart_text(language, "Países", "Countries"), row=1, col=1)
    _apply_base_layout(figure, margin={"l": 55, "r": 25, "t": 55, "b": 55})
    figure.update_layout(showlegend=False)
    return figure


def build_comparative_ranking_chart(
    ranking_rows: list[dict[str, Any]],
    selected_countries: list[str] | None = None,
    language: str = "es",
    *,
    indicator: str | None = None,
    year: int | str | None = None,
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

    dataframe["position"] = dataframe["value"].rank(method="min", ascending=False)
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
    dataframe["position_text"] = dataframe["position"].map(
        lambda position: str(int(position)) if pd.notna(position) else missing_label
    )
    dataframe["year_text"] = str(year) if year not in (None, "") else missing_label
    dataframe["indicator_text"] = str(indicator or missing_label)
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
            customdata=dataframe[
                ["iso", "position_text", "value_text", "year_text", "indicator_text"]
            ].to_numpy(),
            hovertemplate=(
                "<b>%{y}</b><br>"
                + _chart_text(language, "Posici\u00f3n", "Position")
                + ": %{customdata[1]}<br>"
                + _chart_text(language, "Valor", "Value")
                + ": %{customdata[2]}<br>"
                + _chart_text(language, "A\u00f1o", "Year")
                + ": %{customdata[3]}<br>"
                + _chart_text(language, "Indicador", "Indicator")
                + ": %{customdata[4]}<extra></extra>"
            ),
        )
    )
    maximum = dataframe["value"].max()
    country_count = len(dataframe)
    chart_height = min(1500, max(500, country_count * 30 + 150))
    longest_country = max((len(str(country)) for country in dataframe["country"]), default=0)
    left_margin = min(260, max(125, longest_country * 7 + 28))
    figure.update_layout(
        xaxis={
            "title": _chart_text(language, "Valor (%)", "Value (%)"),
            "range": [0, max(105, float(maximum) + 12) if pd.notna(maximum) else 105],
            "automargin": True,
        },
        yaxis={"title": "", "automargin": True},
        height=chart_height,
        autosize=True,
    )
    _apply_base_layout(figure, margin={"l": left_margin, "r": 65, "t": 30, "b": 70})
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
    mean = float(stored_means.iloc[0]) if not stored_means.empty else float(numeric["value"].mean())
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
        focus["percentage_difference"] = focus["difference"] / mean * 100 if mean else float("nan")
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
            customdata=focus[["value_text", "absolute_text", "percentage_text"]].to_numpy(),
            hovertemplate=(
                f"<b>%{{y}}</b><br>{value_label}: %{{customdata[0]}}"
                f"<br>{mean_label}: {mean:.2f}%"
                f"<br>{absolute_label}: %{{customdata[1]}}"
                f"<br>{percentage_label}: %{{customdata[2]}}<extra></extra>"
            ),
        )
    )
    figure.add_vline(x=0, line_color="#6b7280", line_width=1.5)
    average_title = _chart_text(
        language, "Diferencia frente a la media europea", "Difference from the European average"
    )
    figure.update_layout(xaxis={"title": f"{average_title} ({mean:.2f}%)"}, yaxis={"title": ""})
    _apply_base_layout(figure, margin={"l": 110, "r": 25, "t": 20, "b": 60})
    return figure


def build_response_country_comparison_chart(
    detail_rows: list[dict[str, Any]],
    selected_countries: list[str] | None = None,
    language: str = "es",
    *,
    indicator: str | None = None,
    year: int | str | None = None,
) -> go.Figure:
    """Render dynamic responses on X and one vertical bar per country."""
    dataframe = _response_comparison_dataframe(
        detail_rows, language=language, localize_countries=True
    )
    selected_keys = _selected_country_keys(selected_countries)
    if selected_keys and not dataframe.empty:
        dataframe = dataframe[dataframe["country_key"].isin(selected_keys)]
    if dataframe.empty:
        return empty_figure(
            _chart_text(
                language,
                "No hay distribuciones de respuestas para esta selección.",
                "There are no response distributions for this selection.",
            )
        )

    response_order = dataframe["response_key"].drop_duplicates().tolist()
    labels = _response_labels(dataframe)
    x_labels = [labels.get(str(key), str(key)) for key in response_order]
    countries = (
        dataframe[["country_key", "country", "iso"]]
        .drop_duplicates("country_key")
        .sort_values("country", key=lambda values: values.str.casefold(), kind="stable")
    )
    missing_label = _chart_text(language, "Sin datos", "No data")
    figure = go.Figure()
    missing_values = 0
    for country_row in countries.itertuples(index=False):
        country_data = dataframe[dataframe["country_key"].eq(country_row.country_key)].set_index(
            "response_key"
        )
        values: list[float | None] = []
        hover_rows: list[list[str]] = []
        for response_key in response_order:
            response_row = (
                country_data.loc[response_key] if response_key in country_data.index else None
            )
            if isinstance(response_row, pd.DataFrame):
                response_row = response_row.iloc[0]
            raw_value = response_row.get("numeric_value") if response_row is not None else None
            value = float(raw_value) if pd.notna(raw_value) else None
            missing_values += int(value is None)
            values.append(value)
            hover_rows.append(
                [
                    str(country_row.country),
                    labels.get(str(response_key), str(response_key)),
                    format_percentage(value) or missing_label,
                    str(response_row.get("year") or year or missing_label)
                    if response_row is not None
                    else str(year or missing_label),
                    str(response_row.get("source") or "FRA") if response_row is not None else "FRA",
                    str(response_row.get("question") or indicator or missing_label)
                    if response_row is not None
                    else str(indicator or missing_label),
                    str(response_row.get("filter_a") or "All")
                    if response_row is not None
                    else "All",
                    str(response_row.get("filter_b") or "All")
                    if response_row is not None
                    else "All",
                ]
            )
        figure.add_trace(
            go.Bar(
                x=x_labels,
                y=values,
                name=str(country_row.country),
                marker={"color": country_color(country_row.iso, country_row.country)},
                customdata=hover_rows,
                hovertemplate=(
                    "<b>%{customdata[0]}</b><br>"
                    + _chart_text(language, "Respuesta", "Answer")
                    + ": %{customdata[1]}<br>"
                    + _chart_text(language, "Porcentaje", "Percentage")
                    + ": %{customdata[2]}<br>"
                    + _chart_text(language, "Año", "Year")
                    + ": %{customdata[3]}<br>"
                    + _chart_text(language, "Indicador", "Indicator")
                    + ": %{customdata[5]}<br>"
                    + _chart_text(language, "Fuente", "Source")
                    + ": %{customdata[4]}<br>"
                    + _chart_text(language, "Filtros", "Filters")
                    + ": %{customdata[6]} · %{customdata[7]}<extra></extra>"
                ),
            )
        )

    country_count = len(countries)
    minimum_width = max(760, 150 + len(response_order) * max(150, country_count * 24))
    _apply_base_layout(figure, margin={"l": 72, "r": 28, "t": 58, "b": 155})
    figure.update_layout(
        autosize=True,
        barmode="group",
        bargap=0.2,
        bargroupgap=0.06,
        height=610 if country_count > 12 else 560,
        meta={"minimum_width": minimum_width},
        xaxis={
            "title": _chart_text(language, "Respuesta", "Answer"),
            "categoryorder": "array",
            "categoryarray": x_labels,
            "automargin": True,
        },
        yaxis={
            "title": _chart_text(language, "Porcentaje", "Percentage"),
            "range": [0, 100],
            "ticksuffix": "%",
            "automargin": True,
        },
        legend={
            "title": {"text": _chart_text(language, "País", "Country")},
            "orientation": "h",
            "y": -0.2,
            "yanchor": "top",
        },
        showlegend=True,
    )
    if missing_values:
        figure.add_annotation(
            text=(
                f"{_chart_text(language, 'Valores ausentes', 'Missing values')}: {missing_values}"
            ),
            x=1,
            y=1.08,
            xref="paper",
            yref="paper",
            showarrow=False,
            xanchor="right",
        )
    logger.info(
        "response_country_comparison countries_rendered=%d responses=%d missing_values=%d",
        country_count,
        len(response_order),
        missing_values,
    )
    return figure


def build_ilga_response_details_chart(
    detail_rows: list[dict[str, Any]],
    selected_countries: list[str] | None = None,
    language: str = "es",
    *,
    indicator: str | None = None,
    year: int | str | None = None,
) -> go.Figure:
    """Render legal scores or semantic compliance states for every country."""
    started_at = time.perf_counter()
    dataframe = pd.DataFrame(detail_rows)
    required = {"country_code", "country_name", "value", "indicator_id", "response"}
    if dataframe.empty or not required.issubset(dataframe.columns):
        return empty_figure(
            _chart_text(
                language,
                "No hay detalles jurídicos para esta selección.",
                "There are no legal details for this selection.",
            )
        )
    dataframe = dataframe.copy()
    dataframe["country_code"] = [
        normalize_country_code(code, name)
        for code, name in zip(dataframe["country_code"], dataframe["country_name"], strict=True)
    ]
    dataframe = dataframe[dataframe["country_code"].ne("") & dataframe["country_code"].ne("EU27")]
    if dataframe.empty:
        return empty_figure("No hay países comparables para esta selección.")
    dataframe["country_label"] = [
        country_labels(code, str(name))[1 if language == "en" else 0]
        for code, name in zip(dataframe["country_code"], dataframe["country_name"], strict=True)
    ]
    dataframe["value"] = pd.to_numeric(dataframe["value"], errors="coerce")
    dataframe["response_order"] = pd.to_numeric(
        dataframe.get("response_order", pd.Series(index=dataframe.index, dtype=float)),
        errors="coerce",
    ).fillna(99)
    country_frame = (
        dataframe[["country_code", "country_label"]]
        .groupby("country_code", as_index=False, sort=False)
        .agg(country_label=("country_label", "first"))
        .sort_values("country_label", key=lambda values: values.str.casefold(), kind="stable")
    )
    countries = country_frame["country_label"].tolist()
    selected_keys = _selected_country_keys(selected_countries)
    indicator_count = int(dataframe["indicator_id"].astype(str).nunique())
    missing_count = int(dataframe["value"].isna().sum())
    response_order = (
        dataframe[["response", "response_order"]]
        .groupby("response", as_index=False, sort=False)
        .agg(response_order=("response_order", "min"))
        .sort_values(["response_order", "response"], kind="stable")["response"]
        .astype(str)
        .tolist()
    )
    visible_responses = [response for response in response_order if response != "not_available"]
    figure = go.Figure()
    if indicator_count <= 1:
        _add_legal_score_traces(
            figure,
            dataframe,
            visible_responses,
            selected_keys,
            language=language,
            indicator=indicator,
            year=year,
        )
        y_title = _chart_text(language, "Puntuación o valor legal", "Legal score or value")
        y_axis: dict[str, Any] = {
            "title": y_title,
            "range": [0, 100],
            "ticksuffix": "%",
            "automargin": True,
        }
        barmode = "group"
    else:
        _add_legal_status_count_traces(
            figure,
            dataframe,
            visible_responses,
            selected_keys,
            language=language,
            indicator=indicator,
            year=year,
        )
        y_axis = {
            "title": _chart_text(language, "Número de criterios", "Number of criteria"),
            "rangemode": "tozero",
            "dtick": 1,
            "automargin": True,
        }
        barmode = "stack"

    country_count = len(country_frame)
    response_count = max(1, len(visible_responses))
    chart_height = min(max(560, country_count * 8 + response_count * 32), 1000)
    # Keep country labels readable without making the Plotly canvas several
    # viewport widths larger than the section. Any remaining excess is handled
    # by the section's local horizontal scroller.
    minimum_width = min(2400, max(760, 190 + country_count * 44))
    _apply_base_layout(figure, margin={"l": 72, "r": 30, "t": 70, "b": 175})
    figure.update_layout(
        autosize=True,
        barmode=barmode,
        bargap=0.2,
        height=chart_height,
        meta={"minimum_width": minimum_width},
        xaxis={
            "title": _chart_text(language, "País", "Country"),
            "categoryorder": "array",
            "categoryarray": countries,
            "tickangle": -40,
            "automargin": True,
        },
        yaxis=y_axis,
        legend={
            "title": {"text": _chart_text(language, "Respuesta legal", "Legal response")},
            "orientation": "h",
            "y": -0.24,
            "yanchor": "top",
            "itemclick": "toggle",
            "itemdoubleclick": "toggleothers",
        },
        showlegend=True,
    )
    if missing_count:
        figure.add_annotation(
            text=f"{_chart_text(language, 'Sin datos', 'No data')}: {missing_count}",
            x=1,
            y=1.08,
            xref="paper",
            yref="paper",
            xanchor="right",
            showarrow=False,
        )
    logger.info(
        "legal_response_details_chart countries_loaded=%d responses_detected=%d rows_rendered=%d figure_ms=%.2f",
        country_count,
        len(response_order),
        int(dataframe["value"].notna().sum()),
        (time.perf_counter() - started_at) * 1000,
        extra={
            "countries_loaded": country_count,
            "responses_detected": response_order,
            "rows_rendered": int(dataframe["value"].notna().sum()),
            "figure_ms": round((time.perf_counter() - started_at) * 1000, 2),
        },
    )
    return figure


def _add_legal_score_traces(
    figure: go.Figure,
    dataframe: pd.DataFrame,
    responses: list[str],
    selected_keys: set[str],
    *,
    language: str,
    indicator: str | None,
    year: int | str | None,
) -> None:
    for response in responses:
        rows = dataframe[
            dataframe["response"].astype(str).eq(response) & dataframe["value"].notna()
        ]
        if rows.empty:
            continue
        selected = rows["country_code"].isin(selected_keys).tolist()
        values = rows["value"].astype(float).tolist()
        figure.add_trace(
            go.Bar(
                x=rows["country_label"],
                y=values,
                name=_legal_response_label(response, language),
                marker={
                    "color": _legal_response_color(response),
                    "opacity": [
                        1.0 if item else 0.72 if selected_keys else 0.9 for item in selected
                    ],
                    "line": _selected_marker_line(selected),
                },
                customdata=[
                    [
                        _legal_response_label(response, language),
                        format_percentage(value) or _chart_text(language, "Sin datos", "No data"),
                        str(row_year or year or ""),
                        str(row_indicator or indicator or ""),
                        str(source or "ILGA-Europe"),
                    ]
                    for value, row_year, row_indicator, source in zip(
                        values,
                        rows.get("year", pd.Series(index=rows.index, dtype=object)),
                        rows["indicator_id"],
                        rows.get("source", pd.Series(index=rows.index, dtype=object)),
                        strict=True,
                    )
                ],
                hovertemplate=(
                    "<b>%{x}</b><br>"
                    f"{_chart_text(language, 'Respuesta', 'Answer')}: %{{customdata[0]}}<br>"
                    f"{_chart_text(language, 'Valor', 'Value')}: %{{customdata[1]}}<br>"
                    f"{_chart_text(language, 'Año', 'Year')}: %{{customdata[2]}}<br>"
                    f"{_chart_text(language, 'Indicador', 'Indicator')}: %{{customdata[3]}}<br>"
                    f"{_chart_text(language, 'Fuente', 'Source')}: %{{customdata[4]}}"
                    "<extra></extra>"
                ),
            )
        )


def _add_legal_status_count_traces(
    figure: go.Figure,
    dataframe: pd.DataFrame,
    responses: list[str],
    selected_keys: set[str],
    *,
    language: str,
    indicator: str | None,
    year: int | str | None,
) -> None:
    valid = dataframe[dataframe["value"].notna()]
    grouped = valid.groupby(
        ["country_code", "country_label", "response"], as_index=False, sort=False
    ).agg(
        criterion_count=("indicator_id", "count"),
        row_year=("year", "first"),
        source=("source", "first"),
    )
    for response in responses:
        rows = grouped[grouped["response"].astype(str).eq(response)]
        if rows.empty:
            continue
        selected = rows["country_code"].isin(selected_keys).tolist()
        figure.add_trace(
            go.Bar(
                x=rows["country_label"],
                y=rows["criterion_count"],
                name=_legal_response_label(response, language),
                marker={
                    "color": _legal_response_color(response),
                    "opacity": [
                        1.0 if item else 0.72 if selected_keys else 0.9 for item in selected
                    ],
                    "line": _selected_marker_line(selected),
                },
                customdata=[
                    [
                        _legal_response_label(response, language),
                        int(count),
                        str(row_year or year or ""),
                        str(indicator or ""),
                        str(source or "ILGA-Europe"),
                    ]
                    for count, row_year, source in zip(
                        rows["criterion_count"], rows["row_year"], rows["source"], strict=True
                    )
                ],
                hovertemplate=(
                    "<b>%{x}</b><br>"
                    f"{_chart_text(language, 'Respuesta', 'Answer')}: %{{customdata[0]}}<br>"
                    f"{_chart_text(language, 'Criterios', 'Criteria')}: %{{customdata[1]}}<br>"
                    f"{_chart_text(language, 'Año', 'Year')}: %{{customdata[2]}}<br>"
                    f"{_chart_text(language, 'Indicador', 'Indicator')}: %{{customdata[3]}}<br>"
                    f"{_chart_text(language, 'Fuente', 'Source')}: %{{customdata[4]}}"
                    "<extra></extra>"
                ),
            )
        )


def _legal_response_label(response: str, language: str) -> str:
    samples: dict[str, float | None] = {
        "not_met": 0,
        "partially_met": 0.5,
        "fully_met": 1,
        "not_available": None,
    }
    if response == "overall_score":
        return _chart_text(language, "Puntuación legal", "Legal score")
    if response in samples:
        return get_criterion_status(samples[response], 1, language)["label"]
    return str(response).strip()


def _legal_response_color(response: str) -> str:
    return {
        "not_met": NO_RESPONSE_COLOR,
        "partially_met": "#E3B505",
        "fully_met": YES_RESPONSE_COLOR,
        "not_available": MISSING_PERCENTAGE_COLOR,
        "overall_score": DEFAULT_COUNTRY_COLOR,
    }.get(response, DEFAULT_COUNTRY_COLOR)


def build_temporal_evolution_chart(
    history_rows: list[dict[str, Any]],
    selected_countries: list[str] | None = None,
    language: str = "es",
    *,
    visible_countries: list[str] | None = None,
) -> go.Figure:
    started_at = time.perf_counter()
    dataframe = pd.DataFrame(history_rows)
    if dataframe.empty or not {"year", "country", "value"}.issubset(dataframe.columns):
        return empty_figure(
            _chart_text(
                language,
                "No hay datos históricos para este indicador.",
                "There is no historical data for this indicator.",
            )
        )
    dataframe = dataframe.copy()
    if "iso" not in dataframe and "country_code" in dataframe:
        dataframe["iso"] = dataframe["country_code"]
    if "iso" not in dataframe:
        dataframe["iso"] = ""
    dataframe["iso"] = [
        normalize_country_code(iso, country)
        for iso, country in zip(dataframe.get("iso", ""), dataframe["country"], strict=True)
    ]
    dataframe["year"] = pd.to_numeric(dataframe["year"], errors="coerce")
    dataframe["value"] = pd.to_numeric(dataframe["value"], errors="coerce")
    dataframe = dataframe[
        dataframe["iso"].ne("")
        & dataframe["iso"].ne("EU27")
        & dataframe["year"].notna()
        & dataframe["value"].notna()
        & dataframe["value"].between(0, 100)
    ]
    if visible_countries is not None:
        visible = _selected_country_keys(visible_countries)
        dataframe = dataframe[dataframe["iso"].isin(visible)]
    if dataframe.empty:
        return empty_figure(
            _chart_text(
                language,
                "No hay países activados en el selector de evolución temporal.",
                "No countries are enabled in the temporal evolution selector.",
            )
        )

    duplicate_groups = dataframe.groupby(["iso", "year"])["value"].nunique(dropna=True)
    conflicts = duplicate_groups[duplicate_groups.gt(1)]
    if not conflicts.empty:
        conflict_keys = set(conflicts.index.tolist())
        dataframe = dataframe[
            ~dataframe.apply(lambda row: (row["iso"], row["year"]) in conflict_keys, axis=1)
        ]
        logger.warning(
            "legal_temporal_conflicting_years groups=%d",
            len(conflict_keys),
            extra={"conflicting_year_group_count": len(conflict_keys)},
        )
    if dataframe.empty:
        return empty_figure(
            _chart_text(
                language,
                "Los datos históricos duplicados son contradictorios.",
                "The duplicate historical records conflict.",
            )
        )
    dataframe = dataframe.groupby(["iso", "year"], as_index=False, sort=False).agg(
        country=("country", "first"),
        value=("value", "first"),
        indicator_id=("indicator_id", "first")
        if "indicator_id" in dataframe
        else ("country", lambda _values: ""),
        source=("source", "first")
        if "source" in dataframe
        else ("country", lambda _values: "ILGA-Europe"),
    )
    highlighted = _selected_country_keys(selected_countries)
    all_years = sorted(int(year) for year in dataframe["year"].unique().tolist())
    year_count = len(all_years)
    figure = go.Figure()
    series = dataframe.sort_values(["country", "year"], kind="stable").groupby("iso", sort=False)
    for iso, rows in series:
        fallback_country = str(rows.iloc[0].get("country") or iso)
        country = country_labels(str(iso), fallback_country)[1 if language == "en" else 0]
        color = country_color(iso, fallback_country)
        values_by_year = {int(row.year): float(row.value) for row in rows.itertuples()}
        values = [values_by_year.get(year) for year in all_years]
        available_count = sum(value is not None for value in values)
        incomplete = available_count < year_count or available_count < 2
        completeness = (
            _chart_text(language, "Serie incompleta", "Incomplete series")
            if incomplete
            else _chart_text(language, "Serie completa", "Complete series")
        )
        is_highlighted = str(iso) in highlighted
        opacity = 1.0 if is_highlighted or not highlighted else 0.22
        figure.add_trace(
            go.Scatter(
                x=all_years,
                y=values,
                mode="markers" if available_count < 2 else "lines+markers",
                name=str(country),
                connectgaps=False,
                opacity=opacity,
                line={"color": color, "width": 3.2 if is_highlighted else 1.5},
                marker={"color": color, "size": 8 if is_highlighted else 5},
                customdata=[
                    [
                        str(
                            rows.loc[rows["year"].eq(year), "indicator_id"].iloc[0]
                            if year in values_by_year
                            else ""
                        ),
                        str(
                            rows.loc[rows["year"].eq(year), "source"].iloc[0]
                            if year in values_by_year
                            else "ILGA-Europe"
                        ),
                        completeness,
                        format_percentage(values_by_year.get(year)) or "",
                    ]
                    for year in all_years
                ],
                hovertemplate=(
                    "<b>%{fullData.name}</b><br>"
                    f"{_chart_text(language, 'Año', 'Year')}: %{{x}}<br>"
                    f"{_chart_text(language, 'Valor', 'Value')}: %{{customdata[3]}}<br>"
                    f"{_chart_text(language, 'Indicador', 'Indicator')}: %{{customdata[0]}}<br>"
                    f"{_chart_text(language, 'Fuente', 'Source')}: %{{customdata[1]}}<br>"
                    "%{customdata[2]}<extra></extra>"
                ),
            )
        )
    figure.update_layout(
        autosize=True,
        height=680,
        meta={"minimum_width": 860},
        xaxis={
            "title": _chart_text(language, "Año", "Year"),
            "dtick": 1,
            "automargin": True,
        },
        yaxis={
            "title": _chart_text(language, "Puntuación ILGA (%)", "ILGA score (%)"),
            "range": [0, 100],
            "automargin": True,
        },
    )
    _apply_base_layout(figure, margin={"l": 68, "r": 230, "t": 28, "b": 70})
    figure.update_layout(
        showlegend=True,
        legend={
            "orientation": "v",
            "x": 1.01,
            "xanchor": "left",
            "y": 1,
            "yanchor": "top",
            "maxheight": 0.98,
            "itemclick": "toggle",
            "itemdoubleclick": "toggleothers",
        },
    )
    logger.info(
        "legal_temporal_figure countries_loaded=%d years_loaded=%d series_rendered=%d figure_ms=%.2f",
        int(dataframe["iso"].nunique()),
        year_count,
        len(figure.data),
        (time.perf_counter() - started_at) * 1000,
        extra={
            "countries_loaded": int(dataframe["iso"].nunique()),
            "years_loaded": year_count,
            "series_rendered": len(figure.data),
            "figure_ms": round((time.perf_counter() - started_at) * 1000, 2),
        },
    )
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
        dataframe = dataframe.assign(
            gap=(dataframe["ilga_value"] - dataframe["fra_value"]).abs()
        ).nlargest(10, "gap")
    figure = go.Figure()
    colors = [country_color(row.iso, row.country) for row in dataframe.itertuples()]
    figure.add_trace(
        go.Bar(
            y=dataframe["country"],
            x=dataframe["ilga_value"],
            orientation="h",
            name=_chart_text(language, "Protección legal", "Legal protection"),
            marker={"color": colors, "opacity": 1.0},
        )
    )
    figure.add_trace(
        go.Bar(
            y=dataframe["country"],
            x=dataframe["fra_value"],
            orientation="h",
            name=_chart_text(language, "Experiencia real", "Lived experience"),
            marker={"color": colors, "opacity": 0.5},
        )
    )
    figure.update_layout(
        barmode="group",
        xaxis={"title": _chart_text(language, "Valor (%)", "Value (%)"), "range": [0, 100]},
        yaxis={"title": ""},
    )
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
        return empty_figure(
            _chart_text(
                language,
                "No hay coincidencias suficientes para estimar la relación.",
                "There are not enough matches to estimate the relationship.",
            )
        )
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
                "color": [country_color(row.iso, row.country) for row in dataframe.itertuples()],
            },
            hovertemplate="<b>%{text}</b><br>ILGA: %{x:.2f}%<br>FRA: %{y:.2f}%<extra></extra>",
        )
    )
    figure.update_layout(
        xaxis={
            "title": _chart_text(language, "Puntuación ILGA (%)", "ILGA score (%)"),
            "range": [0, 100],
        },
        yaxis={
            "title": _chart_text(language, "Indicador FRA (%)", "FRA indicator (%)"),
            "range": [0, 100],
        },
        annotations=[
            {
                "text": (
                    f"{_chart_text(language, 'Correlación', 'Correlation')}: {correlation:.2f}"
                    if pd.notna(correlation)
                    else _chart_text(
                        language, "Correlación no disponible", "Correlation unavailable"
                    )
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
            text=[[format_percentage(value) or "" for value in row] for row in values],
            texttemplate="%{text}",
            hovertemplate="<b>%{y}</b><br>%{x}: %{z:.2f}%<extra></extra>",
        )
    )
    _apply_base_layout(figure, margin={"l": 110, "r": 25, "t": 20, "b": 70})
    return figure


def build_experience_legal_radar(
    payload: dict[str, Any],
    country_iso: str | None,
    language: str = "es",
) -> tuple[go.Figure, bool, str, str]:
    """Compare explicitly mapped lived-experience and legal-protection dimensions."""
    rows = pd.DataFrame(payload.get("rows") or [])
    empty_message = _chart_text(
        language,
        "No hay suficientes datos comparables para generar este radar.",
        "There is not enough comparable data to generate this radar.",
    )
    if rows.empty or not country_iso:
        return empty_figure(empty_message), False, "", empty_message

    iso = normalize_country_code(country_iso) or str(country_iso).strip().upper()
    focus = rows[rows["iso"].astype(str).str.upper().eq(iso)].copy()
    focus["experience_score"] = pd.to_numeric(focus["experience_score"], errors="coerce")
    focus["legal_score"] = pd.to_numeric(focus["legal_score"], errors="coerce")
    focus = focus.dropna(subset=["experience_score", "legal_score"])
    if focus["dimension"].nunique() < 3:
        return empty_figure(empty_message), False, "", empty_message

    dimension_metadata = payload.get("dimensions") or []
    dimension_order = [
        str(item.get("key"))
        for item in dimension_metadata
        if isinstance(item, dict) and item.get("key") in set(focus["dimension"])
    ]
    label_by_key = {
        str(item.get("key")): str(
            item.get("label_en") if language == "en" else item.get("label_es")
        )
        for item in dimension_metadata
        if isinstance(item, dict)
    }
    focus = focus.set_index("dimension").reindex(dimension_order)
    labels = [label_by_key.get(key, key) for key in dimension_order]
    all_rows = rows[rows["dimension"].isin(dimension_order)].copy()
    all_rows["experience_score"] = pd.to_numeric(all_rows["experience_score"], errors="coerce")
    all_rows["legal_score"] = pd.to_numeric(all_rows["legal_score"], errors="coerce")
    means = (
        all_rows.groupby("dimension", dropna=False)[["experience_score", "legal_score"]]
        .mean()
        .reindex(dimension_order)
    )

    fallback_name = (
        str(focus["country"].dropna().iloc[0]) if focus["country"].notna().any() else iso
    )
    country_name = country_labels(iso, fallback_name)[1 if language == "en" else 0]
    experience_label = _chart_text(language, "Experiencia real", "Real-life experience")
    legal_label = _chart_text(language, "Protección legal", "Legal protection")
    eu_label = _chart_text(language, "Media europea", "European average")
    figure = go.Figure()
    series = (
        (
            f"{experience_label} · {country_name}",
            focus["experience_score"].tolist(),
            "#C62828",
            "solid",
            0.2,
        ),
        (f"{legal_label} · {country_name}", focus["legal_score"].tolist(), "#2F6BDE", "solid", 0.2),
        (
            f"{eu_label} · {experience_label}",
            means["experience_score"].tolist(),
            "#C62828",
            "dot",
            0.0,
        ),
        (f"{eu_label} · {legal_label}", means["legal_score"].tolist(), "#2F6BDE", "dot", 0.0),
    )
    for name, values, color, dash, opacity in series:
        numeric_values = [float(value) if pd.notna(value) else None for value in values]
        figure.add_trace(
            go.Scatterpolar(
                r=[*numeric_values, numeric_values[0]],
                theta=[*labels, labels[0]],
                name=name,
                mode="lines+markers",
                fill="toself" if opacity else "none",
                fillcolor=f"rgba({','.join(str(int(color[index : index + 2], 16)) for index in (1, 3, 5))},{opacity})"
                if opacity
                else None,
                line={"color": color, "width": 2.4, "dash": dash},
                marker={"color": color, "size": 7},
                hovertemplate="<b>%{fullData.name}</b><br>%{theta}: %{r:.1f}%<extra></extra>",
            )
        )
    _apply_base_layout(figure, margin={"l": 70, "r": 70, "t": 55, "b": 115})
    figure.update_layout(
        autosize=True,
        height=650,
        polar={
            "radialaxis": {"visible": True, "range": [0, 100], "ticksuffix": "%"},
        },
        legend={"orientation": "h", "y": -0.12, "yanchor": "top", "x": 0.5, "xanchor": "center"},
        showlegend=True,
    )
    fra_year = payload.get("fra_year") or _chart_text(language, "sin año", "year unavailable")
    ilga_year = payload.get("ilga_year") or _chart_text(language, "sin año", "year unavailable")
    metadata = _chart_text(
        language,
        f"Experiencia real: FRA {fra_year} · Protección legal: ILGA-Europe {ilga_year}",
        f"Real-life experience: FRA {fra_year} · Legal protection: ILGA-Europe {ilga_year}",
    )
    differences = focus["legal_score"] - focus["experience_score"]
    largest_key = str(differences.abs().idxmax())
    largest_label = label_by_key.get(largest_key, largest_key)
    average_gap = float(differences.mean())
    if average_gap >= 4:
        interpretation = _chart_text(
            language,
            f"La protección legal se sitúa descriptivamente por encima de la experiencia real, con la mayor diferencia en {largest_label}. Las fuentes no permiten inferir causalidad.",
            f"Legal protection is descriptively above real-life experience, with the largest gap in {largest_label}. These sources do not support causal inference.",
        )
    elif average_gap <= -4:
        interpretation = _chart_text(
            language,
            f"La experiencia real se sitúa descriptivamente por encima de la protección legal, con la mayor diferencia en {largest_label}. Las fuentes no permiten inferir causalidad.",
            f"Real-life experience is descriptively above legal protection, with the largest gap in {largest_label}. These sources do not support causal inference.",
        )
    else:
        interpretation = _chart_text(
            language,
            f"Las dos series presentan un nivel medio similar; la mayor diferencia descriptiva aparece en {largest_label}. Las fuentes no permiten inferir causalidad.",
            f"The two series have a similar average level; the largest descriptive gap is in {largest_label}. These sources do not support causal inference.",
        )
    return figure, True, metadata, interpretation


def _numeric_ranking_dataframe(ranking_rows: list[dict[str, Any]]) -> pd.DataFrame:
    return (
        _ranking_dataframe_with_missing(ranking_rows)
        .dropna(subset=["value"])
        .sort_values("value", ascending=False)
    )


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
    except TypeError, ValueError:
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
    status = get_criterion_status(value, 1, language)
    score = get_criterion_score_label(value, 1, language)
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
        str(criterion_row.get("year") or ""),
        str(criterion_row.get("source") or "ILGA-Europe"),
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
