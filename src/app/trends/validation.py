from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import replace

from app.trends.models import (
    ComparabilityResult,
    HistoricalPoint,
    SeriesMetadata,
)

DUPLICATE_VALUE_TOLERANCE = 0.01


def validate_series_comparability(
    points: list[HistoricalPoint] | tuple[HistoricalPoint, ...],
    metadata: SeriesMetadata,
) -> ComparabilityResult:
    valid_points = [point for point in points if _has_numeric_observation(point)]
    if not valid_points:
        return ComparabilityResult(True)

    expected = (
        metadata.source.value,
        metadata.indicator_id,
        metadata.country_code.upper(),
        metadata.response,
        metadata.filters,
        metadata.unit,
        metadata.scale_min,
        metadata.scale_max,
        metadata.methodology,
    )
    for point in valid_points:
        observed = (
            point.source,
            point.indicator_id,
            point.country_code.upper(),
            point.response,
            point.filters,
            point.unit,
            point.scale_min,
            point.scale_max,
            point.methodology,
        )
        if observed != expected:
            return ComparabilityResult(False, "series_metadata_mismatch")

    values_by_year: dict[int, list[float]] = defaultdict(list)
    for point in valid_points:
        assert point.year is not None and point.value is not None
        values_by_year[int(point.year)].append(float(point.value))
    if any(
        max(values) - min(values) > DUPLICATE_VALUE_TOLERANCE
        for values in values_by_year.values()
        if len(values) > 1
    ):
        return ComparabilityResult(False, "conflicting_duplicate_year")
    return ComparabilityResult(True)


def normalize_historical_points(
    points: list[HistoricalPoint] | tuple[HistoricalPoint, ...],
) -> tuple[HistoricalPoint, ...]:
    by_year: dict[int, list[HistoricalPoint]] = defaultdict(list)
    for point in points:
        if _has_numeric_observation(point):
            assert point.year is not None
            by_year[int(point.year)].append(point)

    normalized: list[HistoricalPoint] = []
    for year, duplicates in by_year.items():
        numeric_values = [float(point.value) for point in duplicates if point.value is not None]
        value = sum(numeric_values) / len(numeric_values)
        normalized.append(replace(duplicates[0], year=year, value=value))
    return tuple(sorted(normalized, key=lambda point: int(point.year or 0)))


def max_forecast_horizon(observations: int) -> int:
    if observations < 2:
        return 0
    if observations == 2:
        return 1
    if observations <= 4:
        return 2
    return 3


def _has_numeric_observation(point: HistoricalPoint) -> bool:
    if point.year is None or isinstance(point.value, bool) or point.value is None:
        return False
    try:
        year = int(point.year)
        value = float(point.value)
    except TypeError, ValueError:
        return False
    return 1900 <= year <= 2200 and math.isfinite(value)
