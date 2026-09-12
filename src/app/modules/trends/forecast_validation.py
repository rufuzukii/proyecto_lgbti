from __future__ import annotations

import math

import numpy as np

from app.modules.trends.forecast_metrics import (
    mean_absolute_error,
    r_squared,
    root_mean_squared_error,
)
from app.modules.trends.forecast_models import fit_forecast_model, minimum_observations
from app.modules.trends.models import (
    ForecastModelName,
    HistoricalPoint,
    ModelValidation,
    ValidationFold,
)

MODEL_COMPLEXITY = {
    ForecastModelName.LINEAR: 0,
    ForecastModelName.HOLT: 1,
    ForecastModelName.QUADRATIC: 2,
}


def candidate_models(observations: int) -> tuple[ForecastModelName, ...]:
    if observations < 3:
        return ()
    if observations <= 5:
        return (ForecastModelName.LINEAR,)
    return (
        ForecastModelName.LINEAR,
        ForecastModelName.HOLT,
        ForecastModelName.QUADRATIC,
    )


def walk_forward_validation(
    points: tuple[HistoricalPoint, ...],
    model: ForecastModelName,
    *,
    minimum_training_size: int | None = None,
) -> ModelValidation:
    """Valida con ventanas crecientes: cada predicción utiliza solo observaciones anteriores.

    Las métricas usan el mismo recorte a [0, 100] que la previsión publicada.
    La predicción original se conserva en cada partición para poder auditar ese recorte.
    """
    if len(points) <= minimum_observations(model):
        raise ValueError("insufficient_walk_forward_observations")
    default_training_size = 2 if len(points) <= 5 else max(4, len(points) // 2)
    start = max(
        minimum_observations(model),
        minimum_training_size or default_training_size,
    )
    if start >= len(points):
        raise ValueError("insufficient_walk_forward_folds")

    folds: list[ValidationFold] = []
    for target_index in range(start, len(points)):
        training = points[:target_index]
        target = points[target_index]
        if target.year is None or target.value is None:
            continue
        fitted = fit_forecast_model(model, training)
        raw_predicted = fitted.predict(int(target.year))
        predicted = _bounded_score(raw_predicted)
        folds.append(
            ValidationFold(
                train_end_year=int(points[target_index - 1].year or 0),
                target_year=int(target.year),
                actual=float(target.value),
                predicted=predicted,
                raw_predicted=raw_predicted,
            )
        )
    if not folds:
        raise ValueError("empty_walk_forward_validation")

    actual = [fold.actual for fold in folds]
    predicted = [fold.predicted for fold in folds]
    final_fit = fit_forecast_model(model, points)
    fitted_historical = [
        _bounded_score(final_fit.predict(int(point.year)))
        for point in points
        if point.year is not None
    ]
    historical_values = [float(point.value) for point in points if point.value is not None]
    return ModelValidation(
        model=model,
        mae=mean_absolute_error(actual, predicted),
        rmse=root_mean_squared_error(actual, predicted),
        folds=tuple(folds),
        r_squared=r_squared(historical_values, fitted_historical),
    )


def evaluate_candidate_models(
    points: tuple[HistoricalPoint, ...],
) -> tuple[ModelValidation, ...]:
    results: list[ModelValidation] = []
    models = candidate_models(len(points))
    common_training_size = 2 if len(points) <= 5 else max(4, len(points) // 2)
    # Todos los candidatos se evalúan sobre los mismos años para comparar errores equivalentes.
    for model in models:
        try:
            results.append(
                walk_forward_validation(
                    points,
                    model,
                    minimum_training_size=common_training_size,
                )
            )
        except ValueError, np.linalg.LinAlgError:
            continue
    return tuple(results)


def select_best_forecasting_model(
    validation: tuple[ModelValidation, ...],
) -> tuple[ForecastModelName, str]:
    if not validation:
        raise ValueError("no_valid_forecasting_models")
    ranked = sorted(
        validation,
        key=lambda item: (item.mae, item.rmse, MODEL_COMPLEXITY[item.model]),
    )
    raw_best = ranked[0]
    # Se prefiere el modelo más sencillo si su MAE está a 0,25 puntos o al 5 % del mejor.
    tolerance = max(0.25, raw_best.mae * 0.05)
    competitive = [item for item in ranked if item.mae <= raw_best.mae + tolerance]
    selected = min(
        competitive,
        key=lambda item: (MODEL_COMPLEXITY[item.model], item.mae, item.rmse),
    )
    reason = "lowest_validation_error"
    if selected.model != raw_best.model:
        reason = "simpler_model_with_similar_error"
    return selected.model, reason


def _bounded_score(value: float) -> float:
    if not math.isfinite(value):
        raise ValueError("non_finite_forecast")
    return max(0.0, min(100.0, float(value)))
