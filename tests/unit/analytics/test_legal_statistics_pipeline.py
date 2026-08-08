from __future__ import annotations

from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock

import pandas as pd
import pytest

import app.analytics.repository as analytics_repository
from app.analytics import statistics_service
from app.analytics.statistics_charts import (
    build_ilga_response_details_chart,
    build_temporal_evolution_chart,
)
from app.analytics.statistics_exports import EXPORT_WIDTH, prepare_figure_for_export
from app.analytics.statistics_models import IlgaStatisticsQuery
from app.analytics.statistics_service import (
    get_ilga_statistics,
    ilga_analysis_rows_to_dataframe,
)


def _projected_country(
    code: str,
    name: str,
    year: int,
    ranking: float,
    *,
    criteria: list[dict[str, Any]] | None = None,
    document_id: str | None = None,
    normalization: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "document_id": document_id or str(year),
        "year": year,
        "country_index": 0,
        "country_code": code,
        "country_name": name,
        "ranking": ranking,
        "criteria": criteria or [],
        "normalization": normalization or {"applied": False},
    }


def test_ilga_repository_uses_one_projected_aggregate_without_limit(monkeypatch) -> None:
    collection = MagicMock()
    collection.aggregate.return_value = []
    monkeypatch.setattr(analytics_repository, "_mongo_collection", lambda _name: collection)

    analytics_repository.get_ilga_analysis_rows("Family", "Marriage equality")

    collection.aggregate.assert_called_once()
    pipeline = collection.aggregate.call_args.args[0]
    assert pipeline[0] == {"$match": {"dataset": "ilga_rainbow_map"}}
    assert not any("$limit" in stage for stage in pipeline)
    projected_country = pipeline[1]["$project"]["countries"]["$map"]["in"]
    assert set(projected_country) == {"country_code", "country_name", "ranking", "criteria"}
    assert pipeline[-1] == {
        "$sort": {"year": 1, "country_code": 1, "document_id": -1, "country_index": 1}
    }


def test_legal_statistics_cache_key_tracks_database_year_catalog(monkeypatch) -> None:
    query = IlgaStatisticsQuery(year=2026, category="Ranking total")
    monkeypatch.setattr(statistics_service, "get_ilga_years", lambda: [2026])
    before = statistics_service._ilga_statistics_cache_key(query, include_history=True)
    monkeypatch.setattr(statistics_service, "get_ilga_years", lambda: [2026, 2025])
    after = statistics_service._ilga_statistics_cache_key(query, include_history=True)

    assert before != after


def test_ilga_normalization_resolves_duplicates_and_preserves_missing_values() -> None:
    criterion = {
        "category": "Family",
        "indicator": "Marriage equality",
        "weight": 1,
        "value": 0.5,
    }
    rows = [
        _projected_country("BA", "Bosnia & Herzegovina", 2025, 40, document_id="1"),
        _projected_country(
            "BA",
            "Bosnia and Herzegovina",
            2026,
            42,
            criteria=[criterion, dict(criterion)],
            document_id="2",
        ),
        _projected_country(
            "ES",
            "Spain",
            2026,
            75,
            criteria=[
                {**criterion, "value": 0},
                {**criterion, "value": 1},
            ],
            document_id="2",
        ),
    ]

    dataframe = ilga_analysis_rows_to_dataframe(rows)
    family = dataframe[dataframe["category"].eq("Family")]
    bosnia = family[family["country_code"].eq("BA")].iloc[0]
    spain = family[family["country_code"].eq("ES")].iloc[0]

    assert bosnia["country_name"] == "Bosnia and Herzegovina"
    assert bosnia["value"] == 50
    assert bosnia["response"] == "partially_met"
    assert pd.isna(spain["value"])
    assert spain["response"] == "not_available"
    assert list(dataframe.columns) == [
        "document_id",
        "country_index",
        "criterion_index",
        "source",
        "year",
        "country",
        "country_name",
        "iso",
        "country_code",
        "ranking",
        "category",
        "criterion",
        "indicator_id",
        "criterion_value",
        "criterion_weight",
        "value",
        "response",
        "response_order",
        "normalization_applied",
        "normalization_method",
        "original_scale_min",
        "original_scale_max",
        "target_scale_min",
        "target_scale_max",
    ]


def test_legal_statistics_reuses_one_query_for_all_countries_and_years(monkeypatch) -> None:
    calls = 0
    rows: list[dict[str, Any]] = []
    normalized_scales = {
        2011: {
            "applied": True,
            "method": "linear_min_max",
            "original_min": -7,
            "original_max": 17,
            "target_min": 0,
            "target_max": 100,
        },
        2012: {
            "applied": True,
            "method": "linear_min_max",
            "original_min": -12,
            "original_max": 30,
            "target_min": 0,
            "target_max": 100,
        },
    }
    for year in range(2011, 2027):
        for index in range(49):
            rows.append(
                _projected_country(
                    f"X{index:02d}",
                    f"Country {index:02d}",
                    year,
                    20 + index,
                    normalization=normalized_scales.get(year),
                )
            )

    def load(_category: str | None, _criterion: str | None) -> list[dict[str, Any]]:
        nonlocal calls
        calls += 1
        return rows

    monkeypatch.setattr("app.analytics.statistics_service.get_ilga_analysis_rows", load)
    monkeypatch.setattr("app.analytics.statistics_service._server_cache_get", lambda _key: None)
    monkeypatch.setattr("app.analytics.statistics_service._server_cache_set", lambda *_args: None)

    result = get_ilga_statistics(IlgaStatisticsQuery(year=2026, category="Ranking total"))

    assert calls == 1
    assert result["status"] == "ok"
    assert len(result["ranking"]) == 49
    assert len(result["history"]) == 49 * 16
    assert {row["year"] for row in result["history"]} == set(range(2011, 2027))
    assert {row["country_code"] for row in result["history"]} == {
        f"X{index:02d}" for index in range(49)
    }
    assert {
        "country_code",
        "country_name",
        "year",
        "value",
        "indicator_id",
        "source",
    }.issubset(result["history"][0])
    normalized_history = {
        row["year"] for row in result["history"] if row["normalization_applied"]
    }
    assert normalized_history == {2011, 2012}


def test_legal_details_detect_responses_and_keep_country_without_criterion(monkeypatch) -> None:
    values = (("ES", "Spain", 0), ("FR", "France", 0.5), ("DE", "Germany", 1))
    rows = [
        _projected_country(
            code,
            name,
            2026,
            50,
            criteria=[
                {
                    "category": "Family",
                    "indicator": "Marriage equality",
                    "weight": 1.5,
                    "value": value,
                }
            ],
        )
        for code, name, value in values
    ]
    rows.append(_projected_country("PT", "Portugal", 2026, 45))
    monkeypatch.setattr(
        "app.analytics.statistics_service.get_ilga_analysis_rows",
        lambda _category, _criterion: rows,
    )
    monkeypatch.setattr("app.analytics.statistics_service._server_cache_get", lambda _key: None)
    monkeypatch.setattr("app.analytics.statistics_service._server_cache_set", lambda *_args: None)

    result = get_ilga_statistics(
        IlgaStatisticsQuery(year=2026, category="Family", criterion="Marriage equality")
    )
    details = {row["country_code"]: row for row in result["detail_data"]}

    assert {code: details[code]["value"] for code in ("ES", "FR", "DE", "PT")} == {
        "ES": 0,
        "FR": 50,
        "DE": 100,
        "PT": None,
    }
    assert result["legal_response_details_diagnostics"]["responses_detected"] == [
        "not_met",
        "partially_met",
        "fully_met",
        "not_available",
    ]


def test_temporal_chart_renders_every_country_and_does_not_filter_map_selection() -> None:
    rows: list[dict[str, Any]] = []
    for index in range(49):
        years = (2025,) if index == 48 else (2025, 2026)
        for year in years:
            rows.append(
                {
                    "country_code": f"X{index:02d}",
                    "country_name": f"Country {index:02d}",
                    "country": f"Country {index:02d}",
                    "iso": f"X{index:02d}",
                    "year": year,
                    "value": index + year - 2025,
                    "indicator_id": "Ranking total",
                    "source": "ILGA-Europe",
                }
            )

    figure = build_temporal_evolution_chart(rows, ["X00"])
    traces = cast(Any, figure).data

    assert len(traces) == 49
    assert traces[0].opacity == 1
    assert all(trace.opacity == pytest.approx(0.22) for trace in traces[1:])
    incomplete = next(trace for trace in traces if trace.name == "Country 48")
    assert list(incomplete.y) == [48.0, None]
    assert incomplete.connectgaps is False
    assert incomplete.mode == "markers"

    one_country = build_temporal_evolution_chart(rows, visible_countries=["X03"])
    one_country_traces = cast(Any, one_country).data
    assert len(one_country_traces) == 1
    assert one_country_traces[0].name == "Country 03"


def test_legal_response_chart_handles_more_than_40_countries_and_nulls() -> None:
    responses = ("not_met", "partially_met", "fully_met")
    rows = [
        {
            "country_code": f"X{index:02d}",
            "country_name": f"Country with a long name {index:02d}",
            "country": f"Country with a long name {index:02d}",
            "iso": f"X{index:02d}",
            "year": 2026,
            "value": None if index == 44 else (index % 3) * 50,
            "indicator_id": "Marriage equality",
            "source": "ILGA-Europe",
            "response": "not_available" if index == 44 else responses[index % 3],
            "response_order": 3 if index == 44 else index % 3,
        }
        for index in range(45)
    ]

    figure = build_ilga_response_details_chart(rows, ["X00"])
    traces = cast(Any, figure).data

    assert [trace.name for trace in traces] == [
        "No reconocido",
        "Cumplimiento parcial",
        "Cumplimiento completo",
    ]
    assert sum(len(trace.x) for trace in traces) == 44
    assert 760 < cast(Any, figure).layout.meta["minimum_width"] <= 2400
    assert cast(Any, figure).layout.height >= 560
    assert cast(Any, figure).layout.xaxis.automargin is True
    assert cast(Any, figure).layout.yaxis.automargin is True


def test_legal_response_chart_uses_semantic_stacked_counts_for_multiple_criteria() -> None:
    rows = [
        {
            "country_code": country,
            "country_name": name,
            "value": value * 100,
            "indicator_id": indicator,
            "response": response,
            "response_order": order,
            "year": 2026,
            "source": "ILGA-Europe",
        }
        for country, name in (("ES", "Spain"), ("FR", "France"))
        for indicator, value, response, order in (
            ("Criterion A", 0, "not_met", 0),
            ("Criterion B", 0.5, "partially_met", 1),
            ("Criterion C", 1, "fully_met", 2),
        )
    ]

    figure = build_ilga_response_details_chart(rows, indicator="Family")
    traces = cast(Any, figure).data

    assert cast(Any, figure).layout.barmode == "stack"
    assert cast(Any, figure).layout.yaxis.title.text == "Número de criterios"
    assert all(list(trace.y) == [1, 1] for trace in traces)


def test_legal_sections_css_keeps_full_width_and_only_local_horizontal_scroll() -> None:
    css = Path("src/app/dash/assets/statistics.css").read_text(encoding="utf-8")

    assert ".stats-temporal-wrapper" in css
    assert ".stats-response-panel" in css
    assert "grid-column: 1 / -1" in css
    assert ".stats-response-detail-scroll" in css
    assert ".stats-temporal-chart-scroll" in css
    assert "overflow-x: auto" in css
    assert "contain: inline-size" in css
    assert "overflow-x: clip" in css
    assert "scrollbar-gutter: stable" in css
    assert ".stats-temporal-country-list" in css
    assert "grid-template-columns: minmax(0, 1fr)" in css


def test_wide_legal_chart_keeps_dynamic_export_dimensions() -> None:
    figure = build_ilga_response_details_chart(
        [
            {
                "country_code": f"X{index:02d}",
                "country_name": f"Country {index:02d}",
                "value": 50,
                "indicator_id": "Criterion",
                "response": "partially_met",
                "response_order": 1,
                "year": 2026,
                "source": "ILGA-Europe",
            }
            for index in range(49)
        ]
    )

    prepare_figure_for_export(
        figure,
        chart_type="responses",
        chart_title="Detalle de respuestas",
        indicator="Criterion",
        countries=[],
        year=2026,
        source="ILGA-Europe",
    )

    assert cast(Any, figure).layout.meta["export_width"] > EXPORT_WIDTH
