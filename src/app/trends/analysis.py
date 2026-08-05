from __future__ import annotations

import logging
import math
from time import perf_counter

from app.trends.models import (
    ForecastPoint,
    HistoricalPoint,
    SeriesMetadata,
    TrendAnalysis,
    TrendDirection,
    TrendMetrics,
    TrendSummary,
)
from app.trends.validation import (
    max_forecast_horizon,
    normalize_historical_points,
    validate_series_comparability,
)

logger = logging.getLogger(__name__)


def analyze_historical_series(
    points: list[HistoricalPoint] | tuple[HistoricalPoint, ...],
    metadata: SeriesMetadata,
    *,
    forecast_years: int = 1,
) -> TrendAnalysis:
    started = perf_counter()
    comparability = validate_series_comparability(points, metadata)
    if not comparability.comparable:
        logger.info(
            "trend_analysis_skipped reason=%s observations=%d",
            comparability.reason,
            len(points),
            extra={"reason": comparability.reason, "observations": len(points)},
        )
        return TrendAnalysis(
            status="incomparable",
            comparability=comparability,
            reason=comparability.reason,
        )

    normalized = normalize_historical_points(points)
    if len(normalized) < 2:
        logger.info(
            "trend_analysis_skipped reason=insufficient_data observations=%d",
            len(normalized),
            extra={"reason": "insufficient_data", "observations": len(normalized)},
        )
        return TrendAnalysis(
            status="insufficient",
            points=normalized,
            comparability=comparability,
            reason="insufficient_data",
        )

    years = [float(point.year) for point in normalized if point.year is not None]
    values = [float(point.value) for point in normalized if point.value is not None]
    slope, intercept = _linear_regression(years, values)
    fitted = [slope * year + intercept for year in years]
    residuals = [actual - estimate for actual, estimate in zip(values, fitted, strict=True)]
    mae = sum(abs(value) for value in residuals) / len(residuals)
    rmse = math.sqrt(sum(value * value for value in residuals) / len(residuals))
    r_squared = _r_squared(values, fitted) if len(values) >= 3 else None

    allowed_horizon = max_forecast_horizon(len(normalized))
    horizon = min(max(int(forecast_years), 0), allowed_horizon)
    last_year = int(normalized[-1].year or 0)
    forecast = tuple(
        ForecastPoint(
            year=last_year + offset,
            value=_bounded_value(
                slope * (last_year + offset) + intercept,
                metadata.scale_min,
                metadata.scale_max,
            ),
        )
        for offset in range(1, horizon + 1)
    )
    absolute_change = values[-1] - values[0]
    percentage_change = None if math.isclose(values[0], 0.0) else 100 * absolute_change / values[0]
    direction = _trend_direction(slope, metadata.stable_threshold)
    summary = TrendSummary(
        observations=len(values),
        start_year=int(years[0]),
        end_year=int(years[-1]),
        initial_value=values[0],
        final_value=values[-1],
        absolute_change=absolute_change,
        percentage_change=percentage_change,
        minimum=min(values),
        maximum=max(values),
        mean=sum(values) / len(values),
        slope=slope,
        direction=direction,
    )
    metrics = TrendMetrics(
        observations=len(values),
        mae=mae,
        rmse=rmse,
        r_squared=r_squared,
        slope=slope,
        intercept=intercept,
    )
    logger.info(
        "trend_analysis_completed source=%s country=%s observations=%d forecast_years=%d",
        metadata.source.value,
        metadata.country_code,
        len(values),
        horizon,
        extra={
            "source": metadata.source.value,
            "indicator": metadata.indicator_id,
            "country": metadata.country_code,
            "observations": len(values),
            "forecast_years": horizon,
            "model": "ordinary_least_squares",
            "calculation_ms": round((perf_counter() - started) * 1000, 3),
        },
    )
    return TrendAnalysis(
        status="ok",
        points=normalized,
        forecast=forecast,
        summary=summary,
        metrics=metrics,
        comparability=comparability,
        exploratory=len(values) == 2,
        forecast_horizon=horizon,
    )


def _linear_regression(years: list[float], values: list[float]) -> tuple[float, float]:
    mean_year = sum(years) / len(years)
    mean_value = sum(values) / len(values)
    denominator = sum((year - mean_year) ** 2 for year in years)
    if math.isclose(denominator, 0.0):
        return 0.0, mean_value
    slope = (
        sum(
            (year - mean_year) * (value - mean_value)
            for year, value in zip(years, values, strict=True)
        )
        / denominator
    )
    return slope, mean_value - slope * mean_year


def _r_squared(values: list[float], fitted: list[float]) -> float | None:
    mean_value = sum(values) / len(values)
    total = sum((value - mean_value) ** 2 for value in values)
    if math.isclose(total, 0.0):
        return None
    residual = sum((value - estimate) ** 2 for value, estimate in zip(values, fitted, strict=True))
    return 1 - residual / total


def _bounded_value(value: float, minimum: float | None, maximum: float | None) -> float:
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def _trend_direction(slope: float, threshold: float) -> TrendDirection:
    if abs(slope) < max(0.0, threshold):
        return TrendDirection.STABLE
    return TrendDirection.UPWARD if slope > 0 else TrendDirection.DOWNWARD
