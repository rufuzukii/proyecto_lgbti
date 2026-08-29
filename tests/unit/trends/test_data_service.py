from __future__ import annotations

from flask import Flask

import app.modules.trends.service as trend_service
import app.shared.data.repository as analytics_repository
from app.infrastructure.cache import init_cache
from app.modules.trends import historical_series
from app.modules.trends.models import HistoricalPoint, TrendFilters


def _point(year: int, value: float, code: str = "ES") -> HistoricalPoint:
    return HistoricalPoint(
        year=year,
        value=value,
        country_code=code,
        country_name={"ES": "Spain", "FR": "France"}.get(code, code),
    )


def test_loader_gets_all_global_scores_with_one_projected_history_call(monkeypatch) -> None:
    calls = []

    def history(category, criterion):
        calls.append((category, criterion))
        return [
            {"year": 2022, "country": "Spain", "iso": "ES", "value": 60},
            {"year": 2023, "country": "Spain", "iso": "ES", "value": 65},
        ]

    monkeypatch.setattr(historical_series, "get_ilga_history_rows", history)

    points = historical_series.load_ilga_global_history()

    assert calls == [("Ranking total", None)]
    assert [(point.year, point.value) for point in points] == [(2022, 60), (2023, 65)]


def test_loader_keeps_normalization_metadata_without_transforming_value(monkeypatch) -> None:
    monkeypatch.setattr(
        historical_series,
        "get_ilga_history_rows",
        lambda *_args: [
            {
                "year": 2011,
                "country": "Spain",
                "iso": "ES",
                "value": 50,
                "normalization_applied": True,
                "normalization_method": "linear_min_max",
                "original_scale_min": -7,
                "original_scale_max": 17,
                "target_scale_min": 0,
                "target_scale_max": 100,
            }
        ],
    )

    point = historical_series.load_ilga_global_history()[0]

    assert point.value == 50
    assert point.normalization_applied is True
    assert (point.original_scale_min, point.original_scale_max) == (-7, 17)


def test_catalog_is_derived_from_database_rows() -> None:
    scope = historical_series.build_trend_scope(
        (_point(2023, 60, "ES"), _point(2024, 65, "ES"), _point(2024, 70, "FR"))
    )

    assert set(scope.countries) == {("ES", "Spain"), ("FR", "France")}
    assert scope.years == (2023, 2024)


def test_country_series_filters_real_years_without_interpolation() -> None:
    points = (_point(2018, 50), _point(2020, 55), _point(2022, 60), _point(2024, 65))

    selected = historical_series.country_series(points, "ES", start_year=2019, end_year=2023)

    assert [point.year for point in selected] == [2020, 2022]


def test_dataset_and_country_series_are_cached_until_ilga_invalidation(monkeypatch) -> None:
    app = Flask("trend-cache-test")
    init_cache(app)
    calls = []

    def load():
        calls.append("load")
        return tuple(_point(2011 + index, 40 + index) for index in range(8))

    monkeypatch.setattr(trend_service, "load_ilga_global_history", load)
    with app.app_context():
        trend_service.invalidate_trend_cache()
        first = trend_service.get_historical_series("ES")
        second = trend_service.get_historical_series("ES")
        analytics_repository.invalidate_analytics_cache("ilga")
        third = trend_service.get_historical_series("ES")

    assert first == second == third
    assert calls == ["load", "load"]


def test_forecast_cache_reuses_model_when_only_horizon_changes(monkeypatch) -> None:
    app = Flask("trend-forecast-cache-test")
    init_cache(app)
    points = tuple(_point(2011 + index, 40 + index) for index in range(10))
    calls = []
    real_generate = trend_service.generate_forecast

    def generate(*args, **kwargs):
        calls.append("forecast")
        return real_generate(*args, **kwargs)

    monkeypatch.setattr(trend_service, "load_ilga_global_history", lambda: points)
    monkeypatch.setattr(trend_service, "generate_forecast", generate)
    with app.app_context():
        trend_service.invalidate_trend_cache()
        first = trend_service.generate_trend_analysis("ES", TrendFilters(), forecast_years=2)
        second = trend_service.generate_trend_analysis("ES", TrendFilters(), forecast_years=2)
        third = trend_service.generate_trend_analysis("ES", TrendFilters(), forecast_years=3)

    assert first == second
    assert third.forecast_horizon == 3
    assert first.forecast_horizon == 2
    assert calls == ["forecast"]


def test_country_coverage_reports_real_missing_years(monkeypatch) -> None:
    points = (_point(2018, 50), _point(2020, 55), _point(2021, 56))
    monkeypatch.setattr(trend_service, "_historical_dataset", lambda: points)

    coverage = trend_service.get_country_coverage()[0]

    assert coverage.observations == 3
    assert coverage.missing_years == (2019,)
