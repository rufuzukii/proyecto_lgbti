from __future__ import annotations

import logging
from typing import Any

import plotly.graph_objects as go

from app.analytics.percentage_display import (
    MISSING_PERCENTAGE_COLOR,
    coerce_percentage,
    format_percentage,
    prepare_percentage_display_values,
)
from app.analytics.statistics_normalizers import normalize_country_code
from app.dash.i18n import ui_text

logger = logging.getLogger(__name__)

PLOTLY_TRANSPARENT = "rgba(0,0,0,0)"
ISO2_TO_ISO3 = {
    "AL": "ALB",
    "AD": "AND",
    "AM": "ARM",
    "AT": "AUT",
    "AZ": "AZE",
    "BA": "BIH",
    "BE": "BEL",
    "BG": "BGR",
    "BY": "BLR",
    "CH": "CHE",
    "CY": "CYP",
    "CZ": "CZE",
    "DE": "DEU",
    "DK": "DNK",
    "EE": "EST",
    "ES": "ESP",
    "FI": "FIN",
    "FR": "FRA",
    "GB": "GBR",
    "GE": "GEO",
    "GR": "GRC",
    "HR": "HRV",
    "HU": "HUN",
    "IE": "IRL",
    "IS": "ISL",
    "IT": "ITA",
    "LI": "LIE",
    "LT": "LTU",
    "LU": "LUX",
    "LV": "LVA",
    "MC": "MCO",
    "MD": "MDA",
    "ME": "MNE",
    "MK": "MKD",
    "MT": "MLT",
    "NL": "NLD",
    "NO": "NOR",
    "PL": "POL",
    "PT": "PRT",
    "RO": "ROU",
    "RS": "SRB",
    "RU": "RUS",
    "SE": "SWE",
    "SI": "SVN",
    "SK": "SVK",
    "SM": "SMR",
    "TR": "TUR",
    "UA": "UKR",
    "VA": "VAT",
    "XK": "XKX",
}


def build_ilga_choropleth(document: dict[str, Any] | None, *, language: str = "es") -> go.Figure:
    countries = _countries(document)
    countries = [country for country in countries if _iso3_location(country)]
    figure = go.Figure()
    if countries:
        for country in countries:
            country["ranking_text"] = format_percentage(country["ranking"]) or ""
            country["value_label"] = ui_text("chart_value", language)
        figure.add_trace(
            go.Choropleth(
                locations=[_iso3_location(country) for country in countries],
                locationmode="ISO-3",
                text=[country["country"] for country in countries],
                z=[country["ranking"] for country in countries],
                customdata=[
                    [country["country_code"], country["value_label"], country["ranking_text"]]
                    for country in countries
                ],
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
                    "title": ui_text("chart_percentage", language),
                    "ticksuffix": "%",
                    "thickness": 13,
                },
                hovertemplate=(
                    "<b>%{text}</b><br>%{customdata[1]}: %{customdata[2]}<extra></extra>"
                ),
            )
        )
    else:
        figure.add_annotation(
            text="No hay información legal disponible.",
            x=0.5,
            y=0.5,
            xref="paper",
            yref="paper",
            showarrow=False,
            font={"size": 18, "color": "#5f6672"},
        )

    figure.update_layout(
        margin={"l": 0, "r": 0, "t": 0, "b": 0},
        dragmode=False,
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
            "bgcolor": PLOTLY_TRANSPARENT,
        },
        paper_bgcolor=PLOTLY_TRANSPARENT,
        plot_bgcolor=PLOTLY_TRANSPARENT,
        font={"family": "Segoe UI, Arial, sans-serif", "color": "#252a31"},
        uirevision="ilga-europe",
    )
    return figure







def build_fra_choropleth(
    document: dict[str, Any] | None,
    answer: str | None = None,
    *,
    language: str = "es",
) -> go.Figure:
    selected_answer = answer or _default_fra_answer(document)
    answers = _fra_map_answers(document, answer=selected_answer)
    answers = [item for item in answers if _iso3_location(item)]
    display_values, _normalized = prepare_percentage_display_values(
        [item.get("percentage") for item in answers],
        normalize_when_total_is_not_100=False,
        logger=logger,
        context={"chart": "home_fra_choropleth"},
    )
    for item, display_value in zip(answers, display_values, strict=True):
        item["display_value"] = display_value
        item["display_value_text"] = format_percentage(display_value)
        item["value_label"] = ui_text("chart_value", language)
        item["missing_message"] = ui_text("chart_not_enough_information", language)
    drawable = [item for item in answers if item.get("display_value") is not None]
    unavailable = [item for item in answers if item.get("display_value") is None]
    figure = go.Figure()
    if drawable:
        figure.add_trace(
            go.Choropleth(
                locations=[_iso3_location(item) for item in drawable],
                locationmode="ISO-3",
                text=[item["country"] for item in drawable],
                z=[item["display_value"] for item in drawable],
                customdata=[
                    [item["country_code"], item["value_label"], item["display_value_text"]]
                    for item in drawable
                ],
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
                    "title": ui_text("chart_percentage", language),
                    "ticksuffix": "%",
                    "thickness": 13,
                },
                hovertemplate=(
                    "<b>%{text}</b><br>%{customdata[1]}: %{customdata[2]}<extra></extra>"
                ),
            )
        )
    if unavailable:
        figure.add_trace(
            go.Choropleth(
                locations=[_iso3_location(item) for item in unavailable],
                locationmode="ISO-3",
                text=[item["country"] for item in unavailable],
                z=[0] * len(unavailable),
                customdata=[
                    [item["country_code"], item["missing_message"]] for item in unavailable
                ],
                zmin=0,
                zmax=1,
                colorscale=[[0.0, MISSING_PERCENTAGE_COLOR], [1.0, MISSING_PERCENTAGE_COLOR]],
                marker={"line": {"color": "#ffffff", "width": 0.7}},
                showscale=False,
                hovertemplate="<b>%{text}</b><br>%{customdata[1]}<extra></extra>",
            )
        )
    if not drawable and not unavailable:
        figure.add_annotation(
            text="Selecciona un indicador FRA con valores por país.",
            x=0.5,
            y=0.5,
            xref="paper",
            yref="paper",
            showarrow=False,
            font={"size": 18, "color": "#5f6672"},
        )

    figure.update_layout(
        margin={"l": 0, "r": 0, "t": 0, "b": 0},
        dragmode=False,
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
            "bgcolor": PLOTLY_TRANSPARENT,
        },
        paper_bgcolor=PLOTLY_TRANSPARENT,
        plot_bgcolor=PLOTLY_TRANSPARENT,
        font={"family": "Segoe UI, Arial, sans-serif", "color": "#252a31"},
        uirevision="fra-europe",
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


def _iso3_location(row: dict[str, Any]) -> str:
    code = normalize_country_code(row.get("country_code"), row.get("country"))
    if len(code) == 3:
        return code
    return ISO2_TO_ISO3.get(code, "")


def _fra_map_answers(
    document: dict[str, Any] | None,
    answer: str | None = None,
) -> list[dict[str, Any]]:
    if not isinstance(document, dict):
        return []
    selected_answer = str(answer or "").strip()
    rows = [
        row
        for row in _fra_answer_rows(document, include_missing=True)
        if not selected_answer or row["answer"] == selected_answer
    ]
    all_filter_rows = [row for row in rows if _filters_are_all(row.get("filters"))]
    if all_filter_rows:
        rows = all_filter_rows

    rows_by_country: dict[str, dict[str, Any]] = {}
    for row in rows:
        country = row["country"]
        existing = rows_by_country.get(country)
        if existing is None:
            rows_by_country[country] = row
            continue
        if existing.get("percentage") is None and row.get("percentage") is not None:
            rows_by_country[country] = row
            continue
        if existing.get("percentage") is not None and row.get("percentage") is not None:
            logger.debug(
                "fra_map_duplicate_country_percentage_ignored",
                extra={"country": country, "answer": row.get("answer")},
            )
    return [
        {
            "country": row["country"],
            "country_code": row["country_code"],
            "percentage": row.get("percentage"),
        }
        for row in rows_by_country.values()
    ]



def _fra_answer_rows(
    document: dict[str, Any] | None,
    *,
    include_missing: bool = False,
) -> list[dict[str, Any]]:
    if not isinstance(document, dict):
        return []

    rows = []
    for answer in document.get("answers", []):
        if not isinstance(answer, dict):
            continue
        country = str(answer.get("country") or "").strip()
        answer_value = str(answer.get("answer") or "").strip()
        percentage = coerce_percentage(
            answer.get("percentage", answer.get("value")),
            logger=logger,
            context={
                "chart": "figures_fra_answer_rows",
                "country": country,
                "country_code": answer.get("country_code"),
                "answer": answer_value,
            },
        )
        if not country or not answer_value or (percentage is None and not include_missing):
            continue
        rows.append(
            {
                "country": country,
                "country_code": str(answer.get("country_code") or "").strip(),
                "answer": answer_value,
                "percentage": percentage,
                "filters": _clean_fra_filters(answer.get("filters")),
            }
        )
    return rows


def _clean_fra_filters(filters: Any) -> list[dict[str, str]]:
    if not isinstance(filters, list):
        return [{"type": "All", "value": "All"}]

    cleaned = []
    for item in filters:
        if not isinstance(item, dict):
            continue
        filter_type = str(item.get("type") or "").strip()
        filter_value = str(item.get("value") or "").strip()
        if filter_type and filter_value:
            cleaned.append({"type": filter_type, "value": filter_value})
    return cleaned or [{"type": "All", "value": "All"}]


def _filters_are_all(filters: Any) -> bool:
    if not isinstance(filters, list):
        return True
    return any(
        isinstance(item, dict)
        and str(item.get("type") or "").strip() == "All"
        and str(item.get("value") or "").strip() == "All"
        for item in filters
    )


def _default_fra_answer(document: dict[str, Any] | None) -> str | None:
    rows = _fra_answer_rows(document)
    if not rows:
        return None

    answers = [row["answer"] for row in rows]
    preferred = [
        "Yes",
        "Often",
        "Always",
        "Very often",
        "Never",
        "No",
    ]
    for value in preferred:
        if value in answers:
            return value

    counts: dict[str, int] = {}
    for answer in answers:
        counts[answer] = counts.get(answer, 0) + 1
    return max(counts.items(), key=lambda item: item[1])[0]
