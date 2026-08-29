from __future__ import annotations

import math
import statistics
from collections import defaultdict
from dataclasses import replace

from app.modules.trends.forecast_models import fit_forecast_model
from app.modules.trends.forecast_validation import (
    evaluate_candidate_models,
    select_best_forecasting_model,
)
from app.modules.trends.models import (
    ForecastPoint,
    ForecastResult,
    HistoricalPoint,
    TrendDirection,
    TrendSummary,
)

DUPLICATE_VALUE_TOLERANCE = 0.01
STABLE_TREND_THRESHOLD = 0.25
STABLE_RANGE_THRESHOLD = 2.0
IRREGULAR_COUNTER_MOVEMENT_SHARE = 0.35


def generate_forecast(
    points: list[HistoricalPoint] | tuple[HistoricalPoint, ...],
    *,
    country_code: str,
    country_name: str,
    horizon: int = 1,
) -> ForecastResult:
    requested_horizon = max(1, min(3, int(horizon)))
    normalized, validation_error = normalize_historical_series(points)
    summary = summarize_historical_series(normalized) if normalized else None
    if validation_error:
        return ForecastResult(
            status="invalid",
            country_code=country_code,
            country_name=country_name,
            historical=normalized,
            summary=summary,
            requested_horizon=requested_horizon,
            reason=validation_error,
        )
    if len(normalized) < 3:
        return ForecastResult(
            status="insufficient",
            country_code=country_code,
            country_name=country_name,
            historical=normalized,
            summary=summary,
            requested_horizon=requested_horizon,
            reason="insufficient_observations",
        )

    validation = evaluate_candidate_models(normalized)
    if not validation:
        return ForecastResult(
            status="invalid",
            country_code=country_code,
            country_name=country_name,
            historical=normalized,
            summary=summary,
            requested_horizon=requested_horizon,
            reason="model_validation_failed",
        )
    selected_model, selection_reason = select_best_forecasting_model(validation)
    fitted = fit_forecast_model(selected_model, normalized)
    allowed_horizon = min(requested_horizon, forecast_horizon_limit(len(normalized)))
    selected_validation = next(item for item in validation if item.model == selected_model)
    uncertainty_available = len(selected_validation.folds) >= 2
    last_year = int(normalized[-1].year or 0)
    forecast: list[ForecastPoint] = []
    for step in range(1, allowed_horizon + 1):
        year = last_year + step
        raw_value = fitted.predict(year)
        value = bounded_score(raw_value)
        radius = selected_validation.rmse * math.sqrt(step) if uncertainty_available else None
        forecast.append(
            ForecastPoint(
                year=year,
                value=value,
                raw_value=raw_value,
                lower=bounded_score(raw_value - radius) if radius is not None else None,
                upper=bounded_score(raw_value + radius) if radius is not None else None,
            )
        )
    return ForecastResult(
        status="ok",
        country_code=country_code,
        country_name=country_name,
        historical=normalized,
        forecast=tuple(forecast),
        summary=summary,
        selected_model=selected_model,
        validation=validation,
        selection_reason=selection_reason,
        uncertainty_method=(
            "walk_forward_rmse_scaled_by_horizon" if uncertainty_available else ""
        ),
        exploratory=len(normalized) <= 5,
        requested_horizon=requested_horizon,
        forecast_horizon=allowed_horizon,
    )


def normalize_historical_series(
    points: list[HistoricalPoint] | tuple[HistoricalPoint, ...],
) -> tuple[tuple[HistoricalPoint, ...], str]:
    by_year: dict[int, list[HistoricalPoint]] = defaultdict(list)
    for point in points:
        if point.year is None or point.value is None or isinstance(point.value, bool):
            continue
        try:
            year = int(point.year)
            value = float(point.value)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(value) or not 1900 <= year <= 2200:
            continue
        if not 0.0 <= value <= 100.0:
            return (), "historical_value_out_of_range"
        by_year[year].append(replace(point, year=year, value=value))

    normalized: list[HistoricalPoint] = []
    for year, duplicates in by_year.items():
        values = [float(point.value) for point in duplicates if point.value is not None]
        if max(values) - min(values) > DUPLICATE_VALUE_TOLERANCE:
            return (), "conflicting_duplicate_year"
        normalized.append(replace(duplicates[0], year=year, value=sum(values) / len(values)))
    return tuple(sorted(normalized, key=lambda point: int(point.year or 0))), ""


def summarize_historical_series(points: tuple[HistoricalPoint, ...]) -> TrendSummary:
    years = [int(point.year) for point in points if point.year is not None]
    values = [float(point.value) for point in points if point.value is not None]
    if not years or len(years) != len(values):
        raise ValueError("empty_historical_summary")
    robust_slope = theil_sen_slope(years, values)
    direction = classify_historical_trend(years, values, robust_slope=robust_slope)
    missing_years = tuple(year for year in range(years[0], years[-1] + 1) if year not in years)
    return TrendSummary(
        observations=len(values),
        start_year=years[0],
        end_year=years[-1],
        initial_value=values[0],
        final_value=values[-1],
        absolute_change=values[-1] - values[0],
        minimum=min(values),
        maximum=max(values),
        mean=sum(values) / len(values),
        robust_slope=robust_slope,
        direction=direction,
        missing_years=missing_years,
    )


def theil_sen_slope(years: list[int], values: list[float]) -> float:
    slopes = [
        (values[right] - values[left]) / (years[right] - years[left])
        for left in range(len(years))
        for right in range(left + 1, len(years))
        if years[right] != years[left]
    ]
    return float(statistics.median(slopes)) if slopes else 0.0


def classify_historical_trend(
    years: list[int],
    values: list[float],
    *,
    robust_slope: float | None = None,
) -> TrendDirection:
    """Classify the whole observed period without relying on the final year alone."""
    if len(years) < 2 or len(years) != len(values):
        return TrendDirection.STABLE
    slope = theil_sen_slope(years, values) if robust_slope is None else robust_slope
    observed_range = max(values) - min(values)
    if abs(slope) < STABLE_TREND_THRESHOLD and observed_range <= STABLE_RANGE_THRESHOLD:
        return TrendDirection.STABLE

    annualized_changes = [
        (values[index] - values[index - 1]) / (years[index] - years[index - 1])
        for index in range(1, len(values))
        if years[index] != years[index - 1]
    ]
    movement = sum(abs(change) for change in annualized_changes)
    if movement:
        expected_sign = 1 if slope >= 0 else -1
        counter_movement = sum(
            abs(change)
            for change in annualized_changes
            if change * expected_sign < -STABLE_TREND_THRESHOLD
        )
        meaningful_signs = [
            1 if change > 0 else -1
            for change in annualized_changes
            if abs(change) >= STABLE_TREND_THRESHOLD
        ]
        reversals = sum(
            meaningful_signs[index] != meaningful_signs[index - 1]
            for index in range(1, len(meaningful_signs))
        )
        if (
            counter_movement / movement >= IRREGULAR_COUNTER_MOVEMENT_SHARE
            and reversals >= 2
        ):
            return TrendDirection.IRREGULAR
    if abs(slope) < STABLE_TREND_THRESHOLD:
        return TrendDirection.IRREGULAR if observed_range > STABLE_RANGE_THRESHOLD else TrendDirection.STABLE
    return TrendDirection.UPWARD if slope > 0 else TrendDirection.DOWNWARD


def forecast_horizon_limit(observations: int) -> int:
    if observations < 3:
        return 0
    if observations <= 5:
        return 1
    return 3


def bounded_score(value: float) -> float:
    if not math.isfinite(value):
        raise ValueError("non_finite_forecast")
    return max(0.0, min(100.0, float(value)))
