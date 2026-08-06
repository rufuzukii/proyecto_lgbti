from __future__ import annotations

from unittest.mock import MagicMock

from flask import Flask

import app.analytics.repository as analytics_repository
import app.trends.data as trend_data
import app.trends.service as trend_service
from app.cache import init_cache
from app.trends.models import (
    HistoricalPoint,
    SeriesVariant,
    TrendFilters,
    TrendIndicator,
    TrendSource,
)


def _indicator(source=TrendSource.ILGA) -> TrendIndicator:
    return TrendIndicator(
        source=source,
        category="Ranking total" if source == TrendSource.ILGA else "Discrimination",
        indicator_id="ranking_total" if source == TrendSource.ILGA else "D1_1",
        label="Ranking total" if source == TrendSource.ILGA else "Discrimination [D1_1]",
        specific_category="" if source == TrendSource.ILGA else "Experiences",
        question="" if source == TrendSource.ILGA else "Felt discriminated",
    )


def _point(year=2024, value=70.0) -> HistoricalPoint:
    return HistoricalPoint(
        year=year,
        value=value,
        source="ilga",
        indicator_id="ranking_total",
        country_code="ES",
        country_name="Spain",
        unit="percentage_score",
        scale_min=0,
        scale_max=100,
        methodology="ilga_rainbow_map",
    )


def test_ilga_loader_reuses_history_service_in_one_call(monkeypatch) -> None:
    calls = []

    def history(category, criterion):
        calls.append((category, criterion))
        return [
            {"year": 2022, "country": "Spain", "iso": "ES", "value": 60},
            {"year": 2023, "country": "Spain", "iso": "ES", "value": 65},
        ]

    monkeypatch.setattr(trend_data, "get_ilga_history_rows", history)

    points = trend_data.load_historical_points(_indicator())

    assert calls == [("Ranking total", None)]
    assert [(point.year, point.value) for point in points] == [(2022, 60), (2023, 65)]


def test_fra_loader_preserves_exact_response_filters_and_year(monkeypatch) -> None:
    monkeypatch.setattr(
        trend_data,
        "get_fra_historical_documents",
        lambda *_args: [
            {
                "survey_year": 2023,
                "metadata": {"methodology_version": "survey-v3", "survey_year": 2023},
                "answers": [
                    {
                        "country": "Spain",
                        "country_code": "ES",
                        "answer": "Yes",
                        "percentage": 42,
                        "survey_year": 2024,
                        "filters": [{"type": "Age", "value": "25-39"}],
                    },
                    {
                        "country": "Spain",
                        "country_code": "ES",
                        "answer": "No",
                        "percentage": None,
                        "filters": [{"type": "All", "value": "All"}],
                    },
                ],
            }
        ],
    )

    points = trend_data.load_historical_points(_indicator(TrendSource.FRA))

    assert points[0].year == 2024
    assert points[0].response == "Yes"
    assert points[0].filters == (("Age", "25-39"),)
    assert points[0].methodology == "survey-v3"
    assert points[1].year == 2023
    assert points[1].value is None


def test_fra_repository_queries_exact_question_once_with_projection(monkeypatch) -> None:
    collection = MagicMock()
    collection.find.return_value = [{"code": "D1_1", "answers": []}]
    monkeypatch.setattr(analytics_repository, "_mongo_collection", lambda _name: collection)

    rows = analytics_repository.get_fra_historical_documents.uncached(
        "D1_1", "Discrimination", "Experiences", "Felt discriminated"
    )

    assert rows == [{"code": "D1_1", "answers": []}]
    collection.find.assert_called_once()
    query, projection = collection.find.call_args.args
    assert query["code"] == "D1_1"
    assert query["specific_category"] == "Experiences"
    assert query["question"] == "Felt discriminated"
    assert projection["answers"] == 1
    assert projection["metadata"] == 1


def test_series_cache_is_reused_and_shared_invalidation_clears_it(monkeypatch) -> None:
    app = Flask("trend-cache-test")
    init_cache(app)
    calls = []

    def load(_indicator):
        calls.append("load")
        return [_point(2023, 60), _point(2024, 70)]

    monkeypatch.setattr(trend_service, "load_historical_points", load)
    token = _indicator().to_token()
    filters = TrendFilters(series_key="default")
    with app.app_context():
        first = trend_service.get_historical_series("ilga", token, "ES", filters)
        second = trend_service.get_historical_series("ilga", token, "ES", filters)
        analytics_repository.invalidate_analytics_cache()
        third = trend_service.get_historical_series("ilga", token, "ES", filters)

    assert first == second == third
    assert calls == ["load", "load"]


def test_empty_series_is_not_cached(monkeypatch) -> None:
    app = Flask("trend-empty-cache-test")
    init_cache(app)
    calls = []

    def load(_indicator):
        calls.append("load")
        return []

    monkeypatch.setattr(trend_service, "load_historical_points", load)
    token = _indicator().to_token()
    with app.app_context():
        trend_service.invalidate_trend_cache()
        trend_service.get_historical_series("ilga", token, "ES", TrendFilters(series_key="default"))
        trend_service.get_historical_series("ilga", token, "ES", TrendFilters(series_key="default"))

    assert calls == ["load", "load"]


def test_scope_keeps_variants_separate(monkeypatch) -> None:
    yes = HistoricalPoint(
        year=2023,
        value=50,
        source="fra",
        indicator_id="D1_1",
        country_code="ES",
        country_name="Spain",
        response="Yes",
        filters=(("All", "All"),),
        unit="percentage",
        scale_min=0,
        scale_max=100,
        methodology="fra_lgbtiq_survey",
    )
    no = HistoricalPoint(**{**yes.__dict__, "response": "No", "country_code": "PT"})
    monkeypatch.setattr(trend_service, "load_historical_points", lambda _indicator: [yes, no])
    indicator = _indicator(TrendSource.FRA)
    variant = SeriesVariant(response="Yes", filters=(("All", "All"),))

    scope = trend_service.get_trend_scope(indicator.to_token(), variant.to_token())

    assert scope.countries == (("ES", "Spain"),)
    assert scope.years == (2023,)
