from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from app.trends.models import ForecastModelName, HistoricalPoint


@dataclass(frozen=True)
class FittedForecastModel:
    name: ForecastModelName
    reference_year: float
    coefficients: tuple[float, ...] = ()
    last_year: int | None = None
    level: float | None = None
    trend: float | None = None
    alpha: float | None = None
    beta: float | None = None

    def predict(self, year: float) -> float:
        if self.name is ForecastModelName.LINEAR:
            intercept, slope = self.coefficients
            return intercept + slope * (float(year) - self.reference_year)
        if self.name is ForecastModelName.QUADRATIC:
            intercept, linear, quadratic = self.coefficients
            centered = float(year) - self.reference_year
            return intercept + linear * centered + quadratic * centered**2
        if self.name is ForecastModelName.HOLT:
            if self.last_year is None or self.level is None or self.trend is None:
                raise ValueError("invalid_holt_fit")
            return self.level + self.trend * (float(year) - self.last_year)
        raise ValueError("unsupported_forecast_model")


def fit_forecast_model(
    model: ForecastModelName,
    points: list[HistoricalPoint] | tuple[HistoricalPoint, ...],
) -> FittedForecastModel:
    observations = _observations(points)
    if model is ForecastModelName.LINEAR:
        return _fit_linear(observations)
    if model is ForecastModelName.HOLT:
        return _fit_holt(observations)
    if model is ForecastModelName.QUADRATIC:
        return _fit_quadratic(observations)
    raise ValueError("unsupported_forecast_model")


def minimum_observations(model: ForecastModelName) -> int:
    return {
        ForecastModelName.LINEAR: 2,
        ForecastModelName.HOLT: 3,
        ForecastModelName.QUADRATIC: 4,
    }[model]


def _fit_linear(observations: list[tuple[int, float]]) -> FittedForecastModel:
    if len(observations) < minimum_observations(ForecastModelName.LINEAR):
        raise ValueError("insufficient_linear_observations")
    years = [float(year) for year, _value in observations]
    values = [value for _year, value in observations]
    reference = sum(years) / len(years)
    centered = [year - reference for year in years]
    denominator = sum(value * value for value in centered)
    slope = (
        sum(x * y for x, y in zip(centered, values, strict=True)) / denominator
        if not math.isclose(denominator, 0.0)
        else 0.0
    )
    intercept = sum(values) / len(values)
    return FittedForecastModel(
        name=ForecastModelName.LINEAR,
        reference_year=reference,
        coefficients=(intercept, slope),
    )


def _fit_quadratic(observations: list[tuple[int, float]]) -> FittedForecastModel:
    if len(observations) < minimum_observations(ForecastModelName.QUADRATIC):
        raise ValueError("insufficient_quadratic_observations")
    years = np.asarray([year for year, _value in observations], dtype=float)
    values = np.asarray([value for _year, value in observations], dtype=float)
    reference = float(years.mean())
    centered = years - reference
    design = np.column_stack((np.ones(len(years)), centered, centered**2))
    coefficients, _residuals, rank, _singular = np.linalg.lstsq(design, values, rcond=None)
    if rank < 3 or not np.isfinite(coefficients).all():
        raise ValueError("unstable_quadratic_fit")
    return FittedForecastModel(
        name=ForecastModelName.QUADRATIC,
        reference_year=reference,
        coefficients=tuple(float(value) for value in coefficients),
    )


def _fit_holt(observations: list[tuple[int, float]]) -> FittedForecastModel:
    if len(observations) < minimum_observations(ForecastModelName.HOLT):
        raise ValueError("insufficient_holt_observations")
    best: tuple[float, float, float, float, float] | None = None
    for alpha_index in range(1, 10):
        for beta_index in range(1, 10):
            alpha = alpha_index / 10
            beta = beta_index / 10
            level, trend, squared_error = _holt_state(observations, alpha, beta)
            candidate = (squared_error, alpha, beta, level, trend)
            if best is None or candidate[:3] < best[:3]:
                best = candidate
    if best is None:
        raise ValueError("holt_fit_failed")
    _error, alpha, beta, level, trend = best
    return FittedForecastModel(
        name=ForecastModelName.HOLT,
        reference_year=float(observations[-1][0]),
        last_year=observations[-1][0],
        level=level,
        trend=trend,
        alpha=alpha,
        beta=beta,
    )


def _holt_state(
    observations: list[tuple[int, float]],
    alpha: float,
    beta: float,
) -> tuple[float, float, float]:
    first_year, first_value = observations[0]
    second_year, second_value = observations[1]
    initial_gap = max(1, second_year - first_year)
    level = first_value
    trend = (second_value - first_value) / initial_gap
    previous_year = first_year
    squared_error = 0.0
    for year, actual in observations[1:]:
        gap = max(1, year - previous_year)
        predicted = level + trend * gap
        squared_error += (actual - predicted) ** 2
        updated_level = alpha * actual + (1.0 - alpha) * predicted
        updated_trend = beta * ((updated_level - level) / gap) + (1.0 - beta) * trend
        level = updated_level
        trend = updated_trend
        previous_year = year
    return level, trend, squared_error


def _observations(
    points: list[HistoricalPoint] | tuple[HistoricalPoint, ...],
) -> list[tuple[int, float]]:
    observations = [
        (int(point.year), float(point.value))
        for point in points
        if point.year is not None and point.value is not None
    ]
    if not observations or not all(math.isfinite(value) for _year, value in observations):
        raise ValueError("invalid_forecast_observations")
    return observations
