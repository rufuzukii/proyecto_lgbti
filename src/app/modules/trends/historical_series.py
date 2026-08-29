from __future__ import annotations

import math
from collections import defaultdict
from typing import Any

from app.modules.statistics.service import get_ilga_history_rows
from app.modules.trends.models import CountryCoverage, HistoricalPoint, TrendScope
from app.shared.data.normalization import repair_text_encoding

GLOBAL_RANKING_CATEGORY = "Ranking total"


def load_ilga_global_history() -> tuple[HistoricalPoint, ...]:
    """Load every overall Rainbow Map score with one projected MongoDB aggregation."""
    rows = get_ilga_history_rows(GLOBAL_RANKING_CATEGORY, None)
    points: list[HistoricalPoint] = []
    for row in rows:
        year = _safe_year(row.get("year"))
        value = _safe_float(row.get("value"))
        country_code = str(row.get("country_code") or row.get("iso") or "").strip().upper()
        country_name = repair_text_encoding(
            row.get("country_name") or row.get("country")
        ).strip()
        if year is None or not country_code:
            continue
        points.append(
            HistoricalPoint(
                year=year,
                value=value,
                country_code=country_code,
                country_name=country_name or country_code,
                source=str(row.get("source") or "ILGA-Europe").strip(),
                normalization_applied=bool(row.get("normalization_applied")),
                normalization_method=str(row.get("normalization_method") or "").strip(),
                original_scale_min=_safe_float(row.get("original_scale_min")),
                original_scale_max=_safe_float(row.get("original_scale_max")),
                target_scale_min=_safe_float(row.get("target_scale_min")),
                target_scale_max=_safe_float(row.get("target_scale_max")),
            )
        )
    return tuple(
        sorted(
            points,
            key=lambda point: (point.country_code, int(point.year or 0)),
        )
    )


def build_trend_scope(points: tuple[HistoricalPoint, ...]) -> TrendScope:
    countries = tuple(
        sorted(
            {
                (point.country_code, point.country_name or point.country_code)
                for point in points
                if point.country_code
            },
            key=lambda item: item[1].casefold(),
        )
    )
    years = tuple(
        sorted(
            {
                int(point.year)
                for point in points
                if point.year is not None and point.value is not None
            }
        )
    )
    return TrendScope(countries=countries, years=years)


def country_series(
    points: tuple[HistoricalPoint, ...],
    country_code: str,
    *,
    start_year: int | None = None,
    end_year: int | None = None,
) -> tuple[HistoricalPoint, ...]:
    clean_code = str(country_code or "").strip().upper()
    return tuple(
        point
        for point in points
        if point.country_code == clean_code
        and (start_year is None or (point.year is not None and point.year >= start_year))
        and (end_year is None or (point.year is not None and point.year <= end_year))
    )


def audit_country_coverage(
    points: tuple[HistoricalPoint, ...],
) -> tuple[CountryCoverage, ...]:
    grouped: dict[str, list[HistoricalPoint]] = defaultdict(list)
    for point in points:
        if point.year is not None and point.value is not None and point.country_code:
            grouped[point.country_code].append(point)
    rows: list[CountryCoverage] = []
    for country_code, country_points in grouped.items():
        years = sorted({int(point.year) for point in country_points if point.year is not None})
        rows.append(
            CountryCoverage(
                country_code=country_code,
                country_name=country_points[0].country_name or country_code,
                start_year=years[0],
                end_year=years[-1],
                observations=len(years),
                missing_years=tuple(
                    year for year in range(years[0], years[-1] + 1) if year not in years
                ),
            )
        )
    return tuple(sorted(rows, key=lambda row: row.country_code))


def _safe_year(value: Any) -> int | None:
    try:
        year = int(value)
    except (TypeError, ValueError):
        return None
    return year if 1900 <= year <= 2200 else None


def _safe_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None
