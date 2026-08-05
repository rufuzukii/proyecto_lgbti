from __future__ import annotations

import math
import re
from typing import Any

from app.analytics.repository import (
    get_fra_categories,
    get_fra_historical_documents,
    get_fra_mongo_indicators_by_category,
    get_ilga_criteria_by_year,
    get_ilga_criteria_categories_by_year,
    get_ilga_years,
)
from app.analytics.statistics_normalizers import normalize_country_code, repair_text_encoding
from app.analytics.statistics_service import get_ilga_history_rows
from app.trends.models import (
    HistoricalPoint,
    SeriesVariant,
    TrendIndicator,
    TrendSource,
    filters_from_answer,
)

RANKING_CATEGORY = "Ranking total"
RANKING_INDICATOR = "ranking_total"


def list_categories(source: TrendSource) -> list[str]:
    if source == TrendSource.FRA:
        return get_fra_categories()
    years = get_ilga_years()
    latest_year = years[0] if years else None
    categories = get_ilga_criteria_categories_by_year(latest_year)
    return [RANKING_CATEGORY, *[item for item in categories if item != RANKING_CATEGORY]]


def list_indicators(source: TrendSource, category: str) -> list[TrendIndicator]:
    clean_category = str(category or "").strip()
    if not clean_category:
        return []
    if source == TrendSource.FRA:
        indicators: dict[tuple[str, str, str], TrendIndicator] = {}
        for indicator in get_fra_mongo_indicators_by_category(clean_category):
            key = (indicator.code, indicator.specific_category, indicator.question)
            indicators.setdefault(
                key,
                TrendIndicator(
                    source=source,
                    category=indicator.category,
                    indicator_id=indicator.code,
                    label=_fra_indicator_label(
                        indicator.code,
                        indicator.specific_category,
                        indicator.question,
                    ),
                    specific_category=indicator.specific_category,
                    question=indicator.question,
                ),
            )
        return sorted(indicators.values(), key=lambda item: item.label.casefold())
    if clean_category == RANKING_CATEGORY:
        return [
            TrendIndicator(
                source=source,
                category=RANKING_CATEGORY,
                indicator_id=RANKING_INDICATOR,
                label=RANKING_CATEGORY,
            )
        ]
    years = get_ilga_years()
    latest_year = years[0] if years else None
    return [
        TrendIndicator(
            source=source,
            category=clean_category,
            indicator_id=str(item.get("indicator") or "").strip(),
            label=str(item.get("indicator") or "").strip(),
            criterion=str(item.get("indicator") or "").strip(),
        )
        for item in get_ilga_criteria_by_year(latest_year, clean_category)
        if str(item.get("indicator") or "").strip()
    ]


def load_historical_points(indicator: TrendIndicator) -> list[HistoricalPoint]:
    if indicator.source == TrendSource.ILGA:
        criterion = indicator.criterion or None
        return [
            HistoricalPoint(
                year=_safe_year(row.get("year")),
                value=_safe_float(row.get("value")),
                source=TrendSource.ILGA.value,
                indicator_id=indicator.indicator_id,
                country_code=str(row.get("iso") or "").strip().upper(),
                country_name=repair_text_encoding(row.get("country")).strip(),
                unit="percentage_score",
                scale_min=0.0,
                scale_max=100.0,
                methodology="ilga_rainbow_map",
            )
            for row in get_ilga_history_rows(indicator.category, criterion)
        ]

    documents = get_fra_historical_documents(
        indicator.indicator_id,
        indicator.category,
        indicator.specific_category,
        indicator.question,
    )
    points: list[HistoricalPoint] = []
    for document in documents:
        raw_metadata = document.get("metadata")
        metadata: dict[str, Any] = raw_metadata if isinstance(raw_metadata, dict) else {}
        fallback_year = _metadata_year(metadata)
        methodology = str(
            metadata.get("methodology_version")
            or metadata.get("methodology")
            or "fra_lgbtiq_survey"
        ).strip()
        for answer in document.get("answers") or []:
            if not isinstance(answer, dict):
                continue
            country_name = repair_text_encoding(answer.get("country")).strip()
            country_code = normalize_country_code(answer.get("country_code"), country_name)
            points.append(
                HistoricalPoint(
                    year=_safe_year(answer.get("date")) or fallback_year,
                    value=_safe_float(answer.get("percentage")),
                    source=TrendSource.FRA.value,
                    indicator_id=indicator.indicator_id,
                    country_code=country_code,
                    country_name=country_name,
                    response=repair_text_encoding(answer.get("answer")).strip(),
                    filters=filters_from_answer(answer.get("filters")),
                    unit="percentage",
                    scale_min=0.0,
                    scale_max=100.0,
                    methodology=methodology,
                )
            )
    return points


def list_variants(points: list[HistoricalPoint]) -> list[SeriesVariant]:
    return sorted(
        {SeriesVariant(response=point.response, filters=point.filters) for point in points},
        key=lambda item: (item.response.casefold(), item.filters),
    )


def _fra_indicator_label(code: str, specific_category: str, question: str) -> str:
    description = " — ".join(
        item
        for item in (repair_text_encoding(specific_category), repair_text_encoding(question))
        if item
    )
    return f"{description} [{code}]" if description else code


def _metadata_year(metadata: dict[str, Any]) -> int | None:
    for key in ("year", "survey_year", "date", "downloaded_at"):
        if year := _safe_year(metadata.get(key)):
            return year
    return None


def _safe_year(value: Any) -> int | None:
    match = re.search(r"(?<!\d)(?:19|20|21)\d{2}(?!\d)", str(value or ""))
    return int(match.group(0)) if match else None


def _safe_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except TypeError, ValueError:
        return None
    return number if math.isfinite(number) else None
