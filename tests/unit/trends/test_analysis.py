from __future__ import annotations

import pytest

from app.modules.trends.forecast_metrics import mean_absolute_error, root_mean_squared_error
from app.modules.trends.forecast_models import fit_forecast_model
from app.modules.trends.forecast_validation import (
    candidate_models,
    evaluate_candidate_models,
    select_best_forecasting_model,
    walk_forward_validation,
)
from app.modules.trends.forecasting_service import bounded_score, generate_forecast
from app.modules.trends.models import ForecastModelName, HistoricalPoint, TrendDirection


def _point(year: int | None, value: float | None, **overrides) -> HistoricalPoint:
    values = {
        "year": year,
        "value": value,
        "country_code": "ES",
        "country_name": "Spain",
    }
    values.update(overrides)
    return HistoricalPoint(**values)


def _series(values: list[float], *, start: int = 2011) -> list[HistoricalPoint]:
    return [_point(start + index, value) for index, value in enumerate(values)]


def test_mae_and_rmse_use_out_of_sample_errors() -> None:
    actual = [10.0, 20.0, 30.0]
    predicted = [12.0, 18.0, 35.0]

    assert mean_absolute_error(actual, predicted) == pytest.approx(3.0)
    assert root_mean_squared_error(actual, predicted) == pytest.approx(3.31662479)


@pytest.mark.parametrize(
    ("model", "minimum"),
    [
        (ForecastModelName.LINEAR, 2),
        (ForecastModelName.HOLT, 3),
        (ForecastModelName.QUADRATIC, 4),
    ],
)
def test_candidate_models_fit_deterministically(model, minimum) -> None:
    points = _series([40, 42, 45, 49, 52, 56])[:minimum]
    first = fit_forecast_model(model, points).predict(2020)
    second = fit_forecast_model(model, points).predict(2020)

    assert first == pytest.approx(second)


def test_walk_forward_validation_uses_only_prior_years() -> None:
    points = tuple(_series([30, 33, 36, 39, 42, 45, 48, 51]))

    validation = walk_forward_validation(points, ForecastModelName.LINEAR)

    assert validation.folds
    assert all(fold.train_end_year < fold.target_year for fold in validation.folds)
    assert validation.mae == pytest.approx(0.0)
    assert validation.rmse == pytest.approx(0.0)


def test_thirteen_observations_evaluate_all_simple_models() -> None:
    points = tuple(_series([30 + index * 2 for index in range(13)]))

    validations = evaluate_candidate_models(points)

    assert candidate_models(len(points)) == (
        ForecastModelName.LINEAR,
        ForecastModelName.HOLT,
        ForecastModelName.QUADRATIC,
    )
    assert {item.model for item in validations} == set(ForecastModelName)
    assert all(item.folds for item in validations)


def test_similar_accuracy_prefers_simpler_model() -> None:
    validations = evaluate_candidate_models(tuple(_series([20 + index * 2 for index in range(10)])))

    selected, reason = select_best_forecasting_model(validations)

    assert selected is ForecastModelName.LINEAR
    assert reason in {"lowest_validation_error", "simpler_model_with_similar_error"}


def test_polynomial_is_not_selected_for_training_fit_when_validation_is_worse() -> None:
    # Un cambio tardío permite ajustar el histórico con una parábola, pero hace
    # menos estable su extrapolación con ventana creciente que la del modelo base.
    points = tuple(_series([20, 24, 28, 32, 36, 40, 44, 48, 43, 47, 51, 55, 59]))
    validations = evaluate_candidate_models(points)
    selected, _reason = select_best_forecasting_model(validations)
    by_model = {item.model: item for item in validations}

    assert by_model[ForecastModelName.QUADRATIC].mae > by_model[ForecastModelName.LINEAR].mae
    assert selected is not ForecastModelName.QUADRATIC


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        ([20, 24, 28, 32, 36, 40], TrendDirection.UPWARD),
        ([60, 55, 50, 45, 40, 35], TrendDirection.DOWNWARD),
        ([40, 40.1, 39.9, 40.0, 40.1, 40.0], TrendDirection.STABLE),
        ([40, 60, 42, 61, 43, 62], TrendDirection.IRREGULAR),
    ],
)
def test_robust_historical_direction(values, expected) -> None:
    result = generate_forecast(_series(values), country_code="ES", country_name="Spain")

    assert result.summary is not None
    assert result.summary.direction is expected


def test_missing_years_and_nulls_are_not_invented() -> None:
    points = [
        _point(2018, 40),
        _point(2019, None),
        _point(2020, 44),
        _point(2022, 48),
        _point(None, 50),
        _point(2023, 50),
        _point(2024, 52),
        _point(2025, 54),
    ]

    result = generate_forecast(points, country_code="ES", country_name="Spain")

    assert [point.year for point in result.historical] == [2018, 2020, 2022, 2023, 2024, 2025]
    assert result.summary is not None
    assert result.summary.missing_years == (2019, 2021)


@pytest.mark.parametrize("observations", [0, 1, 2])
def test_fewer_than_three_observations_never_generate_forecast(observations) -> None:
    result = generate_forecast(
        _series([40 + index for index in range(observations)]),
        country_code="ES",
        country_name="Spain",
        horizon=3,
    )

    assert result.status == "insufficient"
    assert result.forecast == ()


def test_insufficient_sample_still_has_a_deterministic_historical_summary() -> None:
    result = generate_forecast(
        _series([40, 46]), country_code="ES", country_name="Spain", horizon=3
    )

    assert result.status == "insufficient"
    assert result.summary is not None
    assert result.summary.absolute_change == 6
    assert result.summary.direction is TrendDirection.UPWARD


def test_three_to_five_observations_are_exploratory_and_limited_to_one_year() -> None:
    result = generate_forecast(
        _series([40, 42, 44, 46, 48]),
        country_code="ES",
        country_name="Spain",
        horizon=3,
    )

    assert result.status == "ok"
    assert result.exploratory is True
    assert result.forecast_horizon == 1
    assert result.selected_model is ForecastModelName.LINEAR


@pytest.mark.parametrize("horizon", [1, 2, 3])
def test_supported_horizons(horizon) -> None:
    result = generate_forecast(
        _series([30 + index for index in range(10)]),
        country_code="ES",
        country_name="Spain",
        horizon=horizon,
    )

    assert result.forecast_horizon == horizon
    assert len(result.forecast) == horizon


def test_forecasts_are_clipped_to_zero_and_one_hundred_but_raw_value_is_kept() -> None:
    upper = generate_forecast(
        _series([80, 85, 90, 95, 100, 100]),
        country_code="ES",
        country_name="Spain",
        horizon=3,
    )
    lower = generate_forecast(
        _series([20, 15, 10, 5, 0, 0]),
        country_code="ES",
        country_name="Spain",
        horizon=3,
    )

    assert all(0 <= point.value <= 100 for point in (*upper.forecast, *lower.forecast))
    assert bounded_score(120) == 100
    assert bounded_score(-20) == 0
    assert any(point.raw_value != point.value for point in (*upper.forecast, *lower.forecast))


def test_uncertainty_uses_validation_rmse_and_is_not_labelled_confidence_interval() -> None:
    result = generate_forecast(
        _series([30, 31, 35, 34, 39, 41, 42, 47]),
        country_code="ES",
        country_name="Spain",
        horizon=2,
    )

    assert result.uncertainty_method == "walk_forward_rmse_scaled_by_horizon"
    assert all(point.lower is not None and point.upper is not None for point in result.forecast)


def test_2011_and_2012_values_are_preserved_without_second_normalization() -> None:
    points = _series([50, 60, 62, 64, 66, 68])
    points[0] = _point(
        2011,
        50,
        normalization_applied=True,
        original_scale_min=-7,
        original_scale_max=17,
        target_scale_min=0,
        target_scale_max=100,
    )
    points[1] = _point(
        2012,
        60,
        normalization_applied=True,
        original_scale_min=-12,
        original_scale_max=30,
        target_scale_min=0,
        target_scale_max=100,
    )

    result = generate_forecast(points, country_code="ES", country_name="Spain")

    assert [point.value for point in result.historical[:2]] == [50, 60]
    assert result.normalization_years == (2011, 2012)
