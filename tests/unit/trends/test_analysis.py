from __future__ import annotations

import pytest

from app.trends.analysis import analyze_historical_series
from app.trends.models import (
    HistoricalPoint,
    SeriesMetadata,
    TrendDirection,
    TrendSource,
)


def _metadata(**overrides) -> SeriesMetadata:
    values = {
        "source": TrendSource.ILGA,
        "indicator_id": "ranking_total",
        "indicator_label": "Ranking total",
        "category": "Ranking total",
        "country_code": "ES",
        "country_name": "España",
        "unit": "percentage_score",
        "scale_min": 0.0,
        "scale_max": 100.0,
        "methodology": "ilga_rainbow_map",
    }
    values.update(overrides)
    return SeriesMetadata(**values)


def _point(year, value, **overrides) -> HistoricalPoint:
    values = {
        "year": year,
        "value": value,
        "source": "ilga",
        "indicator_id": "ranking_total",
        "country_code": "ES",
        "country_name": "España",
        "unit": "percentage_score",
        "scale_min": 0.0,
        "scale_max": 100.0,
        "methodology": "ilga_rainbow_map",
    }
    values.update(overrides)
    return HistoricalPoint(**values)


@pytest.mark.parametrize("points", [[], [_point(2024, 70)]])
def test_zero_or_one_year_is_insufficient(points) -> None:
    result = analyze_historical_series(points, _metadata(), forecast_years=3)

    assert result.status == "insufficient"
    assert result.forecast == ()
    assert result.metrics is None


def test_two_year_series_is_exploratory_and_limits_forecast_to_one_year() -> None:
    result = analyze_historical_series(
        [_point(2023, 60), _point(2024, 70)],
        _metadata(),
        forecast_years=3,
    )

    assert result.status == "ok"
    assert result.exploratory is True
    assert result.forecast_horizon == 1
    assert result.forecast[0].year == 2025
    assert result.metrics is not None and result.metrics.r_squared is None


def test_three_year_series_sorts_years_and_calculates_metrics() -> None:
    result = analyze_historical_series(
        [_point(2024, 30), _point(2022, 10), _point(2023, 20)],
        _metadata(),
        forecast_years=3,
    )

    assert [point.year for point in result.points] == [2022, 2023, 2024]
    assert result.forecast_horizon == 2
    assert result.summary is not None
    assert result.summary.absolute_change == pytest.approx(20)
    assert result.summary.percentage_change == pytest.approx(200)
    assert result.metrics is not None
    assert result.metrics.mae == pytest.approx(0)
    assert result.metrics.rmse == pytest.approx(0)
    assert result.metrics.r_squared == pytest.approx(1)


def test_five_year_series_allows_three_year_forecast_and_ignores_nulls() -> None:
    points = [_point(2019 + index, 40 + index * 2) for index in range(1, 6)]
    points.extend([_point(None, 80), _point(2026, None)])

    result = analyze_historical_series(points, _metadata(), forecast_years=3)

    assert result.status == "ok"
    assert result.forecast_horizon == 3
    assert result.summary is not None and result.summary.observations == 5


def test_identical_duplicate_years_are_collapsed_but_conflicts_are_rejected() -> None:
    collapsed = analyze_historical_series(
        [_point(2022, 10), _point(2022, 10.005), _point(2023, 20)],
        _metadata(),
    )
    conflicting = analyze_historical_series(
        [_point(2022, 10), _point(2022, 12), _point(2023, 20)],
        _metadata(),
    )

    assert collapsed.status == "ok"
    assert len(collapsed.points) == 2
    assert conflicting.status == "incomparable"
    assert conflicting.reason == "conflicting_duplicate_year"


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        ([20, 30, 40], TrendDirection.UPWARD),
        ([40, 30, 20], TrendDirection.DOWNWARD),
        ([40, 40.1, 40.2], TrendDirection.STABLE),
    ],
)
def test_trend_direction_uses_stable_tolerance(values, expected) -> None:
    result = analyze_historical_series(
        [_point(2022 + index, value) for index, value in enumerate(values)],
        _metadata(stable_threshold=0.25),
    )

    assert result.summary is not None and result.summary.direction == expected


def test_forecasts_are_clamped_only_to_declared_scale() -> None:
    upper = analyze_historical_series(
        [_point(2023, 90), _point(2024, 100)], _metadata(), forecast_years=1
    )
    lower = analyze_historical_series(
        [_point(2023, 10), _point(2024, 0)], _metadata(), forecast_years=1
    )
    unbounded = analyze_historical_series(
        [
            _point(2023, 90, scale_min=None, scale_max=None, unit="count"),
            _point(2024, 100, scale_min=None, scale_max=None, unit="count"),
        ],
        _metadata(scale_min=None, scale_max=None, unit="count"),
        forecast_years=1,
    )

    assert upper.forecast[0].value == 100
    assert lower.forecast[0].value == 0
    assert unbounded.forecast[0].value == pytest.approx(110)


def test_metadata_mismatch_blocks_projection() -> None:
    result = analyze_historical_series(
        [_point(2023, 50), _point(2024, 60, methodology="changed_method")],
        _metadata(),
    )

    assert result.status == "incomparable"
    assert result.forecast == ()
    assert result.reason == "series_metadata_mismatch"
