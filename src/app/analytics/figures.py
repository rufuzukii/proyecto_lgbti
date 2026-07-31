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
        paper_bgcolor=PLOTLY_TRANSPARENT,
        plot_bgcolor=PLOTLY_TRANSPARENT,
        showlegend=False,
    )
    return figure


def build_fra_country_bar(document: dict[str, Any] | None) -> go.Figure:
    answers = _aggregate_fra_answers(document, answer=_default_fra_answer(document))
    answers = sorted(answers, key=lambda item: item["percentage"], reverse=True)
    figure = go.Figure(
        go.Bar(
            x=[item["country"] for item in answers],
            y=[item["percentage"] for item in answers],
            marker={"color": "#a55233"},
            customdata=[item["observations"] for item in answers],
            hovertemplate=(
                "<b>%{x}</b><br>Media: %{y:.2f}%<br>Observaciones: %{customdata}<extra></extra>"
            ),
        )
    )
    figure.update_layout(
        margin={"l": 45, "r": 20, "t": 20, "b": 100},
        xaxis={"tickangle": -45, "title": ""},
        yaxis={"title": "Porcentaje medio", "range": [0, 100]},
        paper_bgcolor=PLOTLY_TRANSPARENT,
        plot_bgcolor=PLOTLY_TRANSPARENT,
        showlegend=False,
    )
    return figure


def build_fra_answer_distribution(document: dict[str, Any] | None) -> go.Figure:
    grouped: dict[str, list[float]] = {}
    for row in _fra_answer_rows(document):
        grouped.setdefault(row["answer"], []).append(row["percentage"])

    answers = [
        {
            "answer": answer,
            "percentage": sum(values) / len(values),
            "observations": len(values),
        }
        for answer, values in grouped.items()
    ]
    answers = sorted(answers, key=lambda item: item["percentage"], reverse=True)

    figure = go.Figure(
        go.Bar(
            x=[item["answer"] for item in answers],
            y=[item["percentage"] for item in answers],
            customdata=[item["observations"] for item in answers],
            marker={"color": "#3266a8"},
            hovertemplate=(
                "<b>%{x}</b><br>Media: %{y:.2f}%<br>Observaciones: %{customdata}<extra></extra>"
            ),
        )
    )
    if not answers:
        _add_empty_annotation(figure, "Selecciona un indicador FRA con respuestas.")
    figure.update_layout(
        margin={"l": 45, "r": 20, "t": 20, "b": 65},
        xaxis={"title": "Respuesta"},
        yaxis={"title": "Porcentaje medio", "range": [0, 100]},
        paper_bgcolor=PLOTLY_TRANSPARENT,
        plot_bgcolor=PLOTLY_TRANSPARENT,
        showlegend=False,
    )
    return figure


def build_fra_country_answer_bar(
    document: dict[str, Any] | None,
    answer: str | None = None,
    limit: int = 18,
) -> go.Figure:
    selected_answer = answer or _default_fra_answer(document)
    answers = _aggregate_fra_answers(document, answer=selected_answer)
    answers = [
        item
        for item in answers
        if item["country_code"] != "EU27" and item["country"].upper() != "EU27"
    ]
    answers = sorted(answers, key=lambda item: item["percentage"], reverse=True)[:limit]

    figure = go.Figure(
        go.Bar(
            x=[item["percentage"] for item in reversed(answers)],
            y=[item["country"] for item in reversed(answers)],
            orientation="h",
            marker={"color": "#a55233"},
            customdata=[item["observations"] for item in reversed(answers)],
            hovertemplate=(
                "<b>%{y}</b><br>%{x:.2f}%<br>Observaciones: %{customdata}<extra></extra>"
            ),
        )
    )
    if not answers:
        _add_empty_annotation(figure, "No hay datos por país para esta respuesta.")
    figure.update_layout(
        margin={"l": 10, "r": 20, "t": 20, "b": 35},
        xaxis={"title": f"% {selected_answer or 'respuesta'}", "range": [0, 100]},
        yaxis={"title": ""},
        paper_bgcolor=PLOTLY_TRANSPARENT,
        plot_bgcolor=PLOTLY_TRANSPARENT,
        showlegend=False,
    )
    return figure


def build_fra_filter_heatmap(document: dict[str, Any] | None) -> go.Figure:
    rows = _fra_answer_rows(document)
    filter_type = _representative_filter_type(rows)
    figure = go.Figure()
    if not rows or not filter_type:
        _add_empty_annotation(figure, "No hay filtros demográficos suficientes.")
    else:
        answers = sorted({row["answer"] for row in rows})
        filter_values = sorted(
            {
                filter_item["value"]
                for row in rows
                for filter_item in row["filters"]
                if filter_item["type"] == filter_type and filter_item["value"] != "All"
            }
        )
        matrix = []
        for filter_value in filter_values:
            line = []
            for answer in answers:
                values = [
                    row["percentage"]
                    for row in rows
                    if row["answer"] == answer
                    and any(
                        item["type"] == filter_type and item["value"] == filter_value
                        for item in row["filters"]
                    )
                ]
                line.append(sum(values) / len(values) if values else None)
            matrix.append(line)

        figure.add_trace(
            go.Heatmap(
                z=matrix,
                x=answers,
                y=filter_values,
                zmin=0,
                zmax=100,
                colorscale="YlGnBu",
                colorbar={"title": "%"},
                hovertemplate=(
                    f"{filter_type}: %{{y}}<br>"
                    "Respuesta: %{x}<br>Media: %{z:.2f}%<extra></extra>"
                ),
            )
        )
    figure.update_layout(
        margin={"l": 120, "r": 20, "t": 20, "b": 75},
        xaxis={"title": "Respuesta"},
        yaxis={"title": filter_type or ""},
        paper_bgcolor=PLOTLY_TRANSPARENT,
        plot_bgcolor=PLOTLY_TRANSPARENT,
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


def build_ilga_category_score_bar(
    document: dict[str, Any] | None,
    category: str | None,
    limit: int = 15,
) -> go.Figure:
    scores = _ilga_category_scores(document, category)
    scores = sorted(scores, key=lambda item: item["score"], reverse=True)[:limit]
    figure = go.Figure(
        go.Bar(
            x=[item["score"] for item in reversed(scores)],
            y=[item["country"] for item in reversed(scores)],
            orientation="h",
            customdata=[item["matched_weight"] for item in reversed(scores)],
            marker={"color": "#167d68"},
            hovertemplate=(
                "<b>%{y}</b><br>Puntuación: %{x:.2f}%"
                "<br>Peso analizado: %{customdata:.2f}<extra></extra>"
            ),
        )
    )
    if not scores:
        _add_empty_annotation(figure, "No hay criterios ILGA para esta categoría.")
    figure.update_layout(
        margin={"l": 10, "r": 20, "t": 20, "b": 35},
        xaxis={"title": "Cumplimiento ponderado (%)", "range": [0, 100]},
        yaxis={"title": ""},
        paper_bgcolor=PLOTLY_TRANSPARENT,
        plot_bgcolor=PLOTLY_TRANSPARENT,
        showlegend=False,
    )
    return figure


def build_ilga_category_map(
    document: dict[str, Any] | None,
    category: str | None,
) -> go.Figure:
    scores = _ilga_category_scores(document, category)
    scores = [item for item in scores if _iso3_location(item)]
    figure = go.Figure()
    if scores:
        figure.add_trace(
            go.Choropleth(
                locations=[_iso3_location(item) for item in scores],
                locationmode="ISO-3",
                text=[item["country"] for item in scores],
                z=[item["score"] for item in scores],
                customdata=[item["country_code"] for item in scores],
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
                colorbar={"title": "%", "thickness": 13},
                hovertemplate=(
                    "<b>%{text}</b><br>Codigo: %{customdata}<br>"
                    "Cumplimiento: %{z:.2f}%<extra></extra>"
                ),
            )
        )
    else:
        _add_empty_annotation(figure, "No hay datos ILGA cartografiables.")

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
            "bgcolor": PLOTLY_TRANSPARENT,
        },
        paper_bgcolor=PLOTLY_TRANSPARENT,
        plot_bgcolor=PLOTLY_TRANSPARENT,
        font={"family": "Segoe UI, Arial, sans-serif", "color": "#252a31"},
        uirevision=f"ilga-category-{category or 'all'}",
    )
    return figure


def build_ilga_indicator_coverage_bar(
    document: dict[str, Any] | None,
    category: str | None,
    limit: int = 14,
) -> go.Figure:
    grouped: dict[str, list[float]] = {}
    for criterion in _ilga_category_criteria(document, category):
        indicator = str(criterion.get("indicator") or "").strip()
        value = criterion.get("value")
        if not indicator or not isinstance(value, (int, float)):
            continue
        grouped.setdefault(indicator, []).append(1.0 if float(value) > 0 else 0.0)

    coverage = [
        {
            "indicator": indicator,
            "percentage": 100 * sum(values) / len(values),
            "countries": len(values),
        }
        for indicator, values in grouped.items()
        if values
    ]
    coverage = sorted(coverage, key=lambda item: item["percentage"], reverse=True)[:limit]
    figure = go.Figure(
        go.Bar(
            x=[item["percentage"] for item in reversed(coverage)],
            y=[item["indicator"] for item in reversed(coverage)],
            orientation="h",
            customdata=[item["countries"] for item in reversed(coverage)],
            marker={"color": "#705aa8"},
            hovertemplate=(
                "<b>%{y}</b><br>Paises que cumplen: %{x:.1f}%"
                "<br>Paises evaluados: %{customdata}<extra></extra>"
            ),
        )
    )
    if not coverage:
        _add_empty_annotation(figure, "No hay indicadores ILGA para esta categoría.")
    figure.update_layout(
        margin={"l": 180, "r": 20, "t": 20, "b": 35},
        xaxis={"title": "Paises que cumplen (%)", "range": [0, 100]},
        yaxis={"title": ""},
        paper_bgcolor=PLOTLY_TRANSPARENT,
        plot_bgcolor=PLOTLY_TRANSPARENT,
        showlegend=False,
    )
    return figure


def build_ilga_category_heatmap(
    document: dict[str, Any] | None,
    category: str | None,
    country_limit: int = 16,
    indicator_limit: int = 12,
) -> go.Figure:
    scores = sorted(
        _ilga_category_scores(document, category),
        key=lambda item: item["score"],
        reverse=True,
    )[:country_limit]
    countries = [item["country"] for item in scores]
    criteria = _ilga_category_criteria(document, category)
    indicators = []
    for criterion in criteria:
        indicator = str(criterion.get("indicator") or "").strip()
        if indicator and indicator not in indicators:
            indicators.append(indicator)
        if len(indicators) >= indicator_limit:
            break

    values_by_country: dict[str, dict[str, float | None]] = {}
    if isinstance(document, dict):
        for country in document.get("countries", []):
            if not isinstance(country, dict):
                continue
            country_name = str(country.get("country") or "").strip()
            if country_name not in countries:
                continue
            values_by_country[country_name] = {}
            for criterion in _country_matching_criteria(country, category):
                indicator = str(criterion.get("indicator") or "").strip()
                value = criterion.get("value")
                if indicator in indicators and isinstance(value, (int, float)):
                    values_by_country[country_name][indicator] = float(value)

    matrix = [
        [values_by_country.get(country, {}).get(indicator) for indicator in indicators]
        for country in countries
    ]
    figure = go.Figure()
    if countries and indicators:
        figure.add_trace(
            go.Heatmap(
                z=matrix,
                x=indicators,
                y=countries,
                zmin=0,
                zmax=1,
                colorscale=[
                    [0.0, "#f1f4f8"],
                    [0.5, "#fdae61"],
                    [1.0, "#167d68"],
                ],
                colorbar={"title": "Valor"},
                hovertemplate=("<b>%{y}</b><br>%{x}<br>Valor: %{z}<extra></extra>"),
            )
        )
    else:
        _add_empty_annotation(figure, "No hay matriz ILGA para esta categoría.")
    figure.update_layout(
        margin={"l": 120, "r": 20, "t": 20, "b": 150},
        xaxis={"title": "Indicador"},
        yaxis={"title": ""},
        paper_bgcolor=PLOTLY_TRANSPARENT,
        plot_bgcolor=PLOTLY_TRANSPARENT,
    )
    return figure


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
        paper_bgcolor=PLOTLY_TRANSPARENT,
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


def _aggregate_fra_answers(
    document: dict[str, Any] | None,
    answer: str | None = None,
) -> list[dict[str, Any]]:
    if not isinstance(document, dict):
        return []
    grouped: dict[str, list[float]] = {}
    country_codes: dict[str, str] = {}
    selected_answer = str(answer or "").strip()
    for row in _fra_answer_rows(document):
        if selected_answer and row["answer"] != selected_answer:
            continue
        country = row["country"]
        grouped.setdefault(country, []).append(row["percentage"])
        country_codes[country] = row["country_code"]
    return [
        {
            "country": country,
            "country_code": country_codes.get(country, ""),
            "percentage": sum(values) / len(values),
            "observations": len(values),
        }
        for country, values in grouped.items()
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


def _representative_filter_type(rows: list[dict[str, Any]]) -> str | None:
    candidates: dict[str, set[str]] = {}
    for row in rows:
        for item in row["filters"]:
            filter_type = item["type"]
            filter_value = item["value"]
            if filter_type == "All" or filter_value == "All":
                continue
            candidates.setdefault(filter_type, set()).add(filter_value)

    scored = [
        (filter_type, len(values))
        for filter_type, values in candidates.items()
        if 2 <= len(values) <= 12
    ]
    if not scored:
        return None
    return max(scored, key=lambda item: item[1])[0]


def _add_empty_annotation(figure: go.Figure, text: str) -> None:
    figure.add_annotation(
        text=text,
        x=0.5,
        y=0.5,
        xref="paper",
        yref="paper",
        showarrow=False,
        font={"size": 16, "color": "#5f6672"},
    )


def _ilga_category_scores(
    document: dict[str, Any] | None,
    category: str | None,
) -> list[dict[str, Any]]:
    if not isinstance(document, dict):
        return []

    scores = []
    for country in document.get("countries", []):
        if not isinstance(country, dict):
            continue
        criteria = _country_matching_criteria(country, category)
        if criteria:
            total_weight = 0.0
            achieved = 0.0
            for criterion in criteria:
                value = criterion.get("value")
                weight = criterion.get("weight")
                if not isinstance(value, (int, float)) or not isinstance(weight, (int, float)):
                    continue
                total_weight += float(weight)
                achieved += float(value) * float(weight)
            if total_weight <= 0:
                continue
            score = 100 * achieved / total_weight
        else:
            ranking = country.get("ranking")
            if not isinstance(ranking, (int, float)):
                continue
            total_weight = 100.0
            score = float(ranking)

        country_name = str(country.get("country") or "").strip()
        if not country_name:
            continue
        scores.append(
            {
                "country": country_name,
                "country_code": str(country.get("country_code") or "").strip(),
                "score": max(0.0, min(100.0, score)),
                "matched_weight": total_weight,
            }
        )
    return scores


def _ilga_category_criteria(
    document: dict[str, Any] | None,
    category: str | None,
) -> list[dict[str, Any]]:
    if not isinstance(document, dict):
        return []

    criteria = []
    for country in document.get("countries", []):
        if isinstance(country, dict):
            criteria.extend(_country_matching_criteria(country, category))
    return criteria


def _country_matching_criteria(
    country: dict[str, Any],
    category: str | None,
) -> list[dict[str, Any]]:
    criteria = country.get("criteria")
    if not isinstance(criteria, list):
        return []

    selected = _normalize_category_key(category)
    output = []
    for criterion in criteria:
        if not isinstance(criterion, dict):
            continue
        criterion_category = str(criterion.get("category") or "").strip()
        if selected and _normalize_category_key(criterion_category) != selected:
            continue
        output.append(criterion)
    return output


def _normalize_category_key(value: str | None) -> str:
    aliases = {
        "civilsocietyspace": "civilsocietyspace",
        "equalityandnondiscrimination": "equalitynondiscrimination",
        "equalitynondiscrimination": "equalitynondiscrimination",
        "hatecrimeandhatespeech": "hatecrimehatespeech",
        "hatecrimehatespeech": "hatecrimehatespeech",
        "intersexrights": "intersexbodilyintegrity",
        "intersexbodilyintegrity": "intersexbodilyintegrity",
        "legal": "",
        "legalgenderrecognition": "legalgenderrecognition",
    }
    raw = "".join(ch for ch in str(value or "").lower() if ch.isalnum())
    return aliases.get(raw, raw)
