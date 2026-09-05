from __future__ import annotations

import math
from typing import Any, cast

from dash import html
from dash.development.base_component import Component

from app.shared.data.legal_criteria import get_criterion_metadata
from app.web.i18n import country_labels, text_attrs


def countries_with_ilga_criteria(document: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(document, dict) or not isinstance(document.get("countries"), list):
        return []
    return [
        country
        for country in document["countries"]
        if isinstance(country, dict) and isinstance(country.get("criteria"), list)
    ]


def find_ilga_country(
    document: dict[str, Any] | None,
    country_key: str | None,
) -> dict[str, Any] | None:
    clean_key = str(country_key or "").strip().casefold()
    if not clean_key:
        return None
    for country in countries_with_ilga_criteria(document):
        keys = {
            str(country.get("country_code") or "").strip().casefold(),
            str(country.get("country") or "").strip().casefold(),
        }
        if clean_key in keys:
            return country
    return None


def build_ilga_country_criteria_panel(country: dict[str, Any]) -> Component:
    ranking = country.get("ranking")
    ranking_text = f"{float(ranking):.2f}%" if isinstance(ranking, (int, float)) else "-"
    country_code = str(country.get("country_code") or "").strip().upper()
    country_fallback = str(country.get("country") or country_code or "País")
    country_es, country_en = country_labels(country_code, country_fallback)
    criteria = (
        cast(list[dict[str, Any]], country.get("criteria"))
        if isinstance(country.get("criteria"), list)
        else []
    )
    return html.Div(
        [
            html.Div(
                [
                    html.H3(country_es, **text_attrs(country_es, country_en)),
                    html.Span(country_code),
                    html.Strong(ranking_text),
                ],
                className="home-ilga-country-summary",
            ),
            html.Div(
                [_criterion_row(criterion) for criterion in criteria],
                className="home-ilga-criteria-list",
            ),
        ]
    )


def _criterion_row(criterion: dict[str, Any]) -> Component:
    weight = criterion.get("weight")
    value = criterion.get("value")
    metadata_es = get_criterion_metadata(criterion, "es")
    metadata_en = get_criterion_metadata(criterion, "en")
    compliance_es, compliance_en = _criterion_compliance_labels(value)
    contribution_es, contribution_en = _criterion_contribution_labels(value, weight)
    return html.Div(
        [
            html.Div(
                [
                    html.Span(
                        metadata_es["category_label"],
                        className="ilga-indicator-card__category",
                        **text_attrs(metadata_es["category_label"], metadata_en["category_label"]),
                    ),
                    html.Strong(
                        metadata_es["display_title"],
                        className="ilga-indicator-card__title",
                        **text_attrs(metadata_es["display_title"], metadata_en["display_title"]),
                    ),
                    html.P(
                        metadata_es["summary"],
                        className="ilga-indicator-card__description",
                        **text_attrs(metadata_es["summary"], metadata_en["summary"]),
                    ),
                ],
                className="ilga-indicator-card__content",
            ),
            html.Table(
                [
                    html.Caption(
                        "Cumplimiento y aporte al ranking",
                        **text_attrs(
                            "Cumplimiento y aporte al ranking",
                            "Compliance and ranking contribution",
                        ),
                    ),
                    html.Thead(
                        html.Tr(
                            [
                                html.Th(
                                    "Cumplimiento",
                                    scope="col",
                                    **text_attrs("Cumplimiento", "Compliance"),
                                ),
                                html.Th(
                                    "Aporte al ranking",
                                    scope="col",
                                    **text_attrs("Aporte al ranking", "Ranking contribution"),
                                ),
                            ]
                        )
                    ),
                    html.Tbody(
                        html.Tr(
                            [
                                html.Td(compliance_es, **text_attrs(compliance_es, compliance_en)),
                                html.Td(
                                    contribution_es,
                                    **text_attrs(contribution_es, contribution_en),
                                ),
                            ]
                        )
                    ),
                ],
                className="ilga-indicator-card__metadata",
            ),
        ],
        className="ilga-indicator-card",
    )


def _criterion_compliance_labels(value: Any) -> tuple[str, str]:
    numeric_value = _criterion_number(value)
    if numeric_value is None or not 0 <= numeric_value <= 1:
        return "Información no disponible", "Information unavailable"
    percentage = _format_number(numeric_value * 100)
    return f"{percentage} %", f"{percentage}%"


def _criterion_contribution_labels(value: Any, weight: Any) -> tuple[str, str]:
    numeric_value = _criterion_number(value)
    numeric_weight = _criterion_number(weight)
    if (
        numeric_value is None
        or numeric_weight is None
        or not 0 <= numeric_value <= 1
        or numeric_weight <= 0
    ):
        return "Información no disponible", "Information unavailable"
    contribution = _format_number(numeric_value * numeric_weight)
    return f"{contribution} puntos", f"{contribution} points"


def _criterion_number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str):
        value = value.strip().replace("%", "").replace(",", ".")
        if not value:
            return None
    try:
        numeric_value = float(value)
    except TypeError, ValueError:
        return None
    return numeric_value if math.isfinite(numeric_value) else None


def _format_number(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")
