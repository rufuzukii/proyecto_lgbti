from __future__ import annotations

import math


def mean_absolute_error(actual: list[float], predicted: list[float]) -> float:
    _validate_metric_inputs(actual, predicted)
    return sum(abs(observed - estimate) for observed, estimate in zip(actual, predicted, strict=True)) / len(actual)


def root_mean_squared_error(actual: list[float], predicted: list[float]) -> float:
    _validate_metric_inputs(actual, predicted)
    squared = [
        (observed - estimate) ** 2
        for observed, estimate in zip(actual, predicted, strict=True)
    ]
    return math.sqrt(sum(squared) / len(squared))


def r_squared(actual: list[float], predicted: list[float]) -> float | None:
    _validate_metric_inputs(actual, predicted)
    mean = sum(actual) / len(actual)
    total = sum((value - mean) ** 2 for value in actual)
    if math.isclose(total, 0.0):
        return None
    residual = sum(
        (observed - estimate) ** 2
        for observed, estimate in zip(actual, predicted, strict=True)
    )
    return 1.0 - residual / total


def _validate_metric_inputs(actual: list[float], predicted: list[float]) -> None:
    if not actual or len(actual) != len(predicted):
        raise ValueError("forecast_metric_length_mismatch")
    if not all(math.isfinite(value) for value in [*actual, *predicted]):
        raise ValueError("forecast_metric_non_finite")
