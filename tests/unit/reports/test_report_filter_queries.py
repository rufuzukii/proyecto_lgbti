from dataclasses import replace
from typing import Any, cast

import fitz
import pytest
from flask import Flask

from app.infrastructure.cache import LocalTTLCache
from app.modules.reports import service as report_service
from app.modules.reports.models import ReportConfiguration
from app.modules.statistics import service as statistics_service


@pytest.fixture
def report_data(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str, int]]:
    answers = []
    for filter_type, filter_value, percentages in (
        ("All", "All", (70, 80, 90)),
        ("Age", "25-39", (19, 18, 20)),
        ("Age", "40-54", (10, 20, 30)),
        ("Sexual Orientation", "Lesbian", (13, 18, 29)),
        ("Sexual Orientation", "Gay", (61, 62, 63)),
    ):
        for (country, code), percentage in zip(
            (("Spain", "ES"), ("France", "FR"), ("Germany", "DE")), percentages, strict=True
        ):
            for response, value in (("Yes", percentage), ("No", 100 - percentage)):
                answers.append(
                    {
                        "country": country,
                        "country_code": code,
                        "answer": response,
                        "percentage": value,
                        "date": "2023",
                        "filters": [{"type": filter_type, "value": filter_value}],
                    }
                )
    document = {
        "code": "REPORT_FILTERS",
        "category": "Discrimination",
        "specific_category": "Work",
        "question": "Felt discriminated in the past 12 months at work",
        "answers": answers,
    }
    queries = []

    def load_document(code: str, category: str, year: int) -> dict[str, Any]:
        queries.append((code, category, year))
        return document

    local_cache = LocalTTLCache()
    local_cache.init_app(Flask("report-filter-query-test"))
    monkeypatch.setattr(statistics_service, "cache", local_cache)
    monkeypatch.setattr(statistics_service, "get_fra_indicator_answers", load_document)
    return queries


def _configuration(**filters: str) -> ReportConfiguration:
    return ReportConfiguration.from_mapping(
        {
            "source": "fra",
            "year": 2023,
            "category": "Discrimination",
            "indicator_id": "REPORT_FILTERS",
            "answer": "Yes",
            "countries": ["ES", "FR"],
            "primary_country": "ES",
            "language": "en",
            "sections": ["executive", "metrics", "comparison", "demographics", "sources"],
            **filters,
        }
    )


@pytest.mark.parametrize(
    ("filters", "expected_values", "scope"),
    [
        (
            {"filter_a_name": "Age", "filter_a_value": "25-39"},
            {"ES": 19.0, "FR": 18.0, "DE": 20.0},
            "Age: 25-39",
        ),
        (
            {"filter_b_name": "Sexual Orientation", "filter_b_value": "Lesbian"},
            {"ES": 13.0, "FR": 18.0, "DE": 29.0},
            "Sexual Orientation: Lesbian",
        ),
    ],
)
def test_report_filter_reaches_statistics_preview_and_real_pdf_without_global_data(
    report_data: list[tuple[str, str, int]],
    filters: dict[str, str],
    expected_values: dict[str, float],
    scope: str,
) -> None:
    global_configuration = _configuration()
    global_data = report_service.load_report_dataset(global_configuration)
    assert {row["iso"]: row["value"] for row in global_data.result["ranking"]} == {
        "ES": 70.0,
        "FR": 80.0,
        "DE": 90.0,
    }
    configuration = _configuration(**filters)

    dataset = report_service.load_report_dataset(configuration)
    assert {row["iso"]: row["value"] for row in dataset.result["ranking"]} == expected_values
    assert {
        (row["iso"], row["answer"]): row["percentage"] for row in dataset.result["detail_data"]
    } == {
        (code, answer): value
        for code, percentage in expected_values.items()
        for answer, value in (("Yes", percentage), ("No", 100 - percentage))
    }
    preview = report_service.build_report_preview(configuration)
    metrics = {metric.key: metric for metric in preview.metrics}
    assert metrics["country_value"].numeric_value == expected_values["ES"]
    assert metrics["eu_average"].numeric_value == sum(expected_values.values()) / 3
    assert {row["country"]: row["value"] for row in preview.table_rows} == {
        "Spain": expected_values["ES"],
        "France": expected_values["FR"],
    }
    assert {chart.key for chart in preview.charts} == {"map_fra", "ranking", "responses"}
    ranking = next(chart.figure for chart in preview.charts if chart.key == "ranking")
    assert ranking is not None
    plotted_values = [value for trace in cast(Any, ranking).data for value in trace.x]
    assert sorted(plotted_values) == sorted([expected_values["ES"], expected_values["FR"]])

    generated = report_service.generate_report_pdf(
        configuration,
        section_narratives={"executive": "Filtered report reviewed by the user."},
        chart_narratives={"map_fra": {"what_shows": "Reviewed filtered country percentages."}},
    )
    assert generated.content.metrics == preview.metrics
    assert generated.image_count == 3
    with fitz.open(stream=generated.pdf_bytes, filetype="pdf") as document:
        text = "\n".join(cast(str, page.get_text()) for page in document)
        assert scope in text
        assert metrics["country_value"].display_value in text
        assert metrics["eu_average"].display_value in text
        assert "Filtered report reviewed by the user." in text
        assert sum(len(page.get_images()) for page in document) == 3
        widgets = {
            cast(Any, widget).field_name: cast(Any, widget).field_value
            for page in document
            for widget in page.widgets() or []
        }
        assert widgets["chart_map_fra_what_shows"] == "Reviewed filtered country percentages."

    # Reusing the cached indicator and returning to All must not reuse the filtered result.
    restored = report_service.load_report_dataset(global_configuration)
    assert restored.result["ranking"] == global_data.result["ranking"]
    assert report_data == [("REPORT_FILTERS", "Discrimination", 2023)]


@pytest.mark.parametrize(
    "filters",
    [
        {"filter_b_name": "Age", "filter_b_value": "25-39"},
        {"filter_a_name": "Sexual Orientation", "filter_a_value": "Lesbian"},
        {
            "filter_a_name": "Age",
            "filter_a_value": "25-39",
            "filter_b_name": "Sexual Orientation",
            "filter_b_value": "Lesbian",
        },
    ],
)
def test_report_rejects_wrong_filter_groups_and_simultaneous_filters_before_loading_data(
    monkeypatch: pytest.MonkeyPatch, filters: dict[str, str]
) -> None:
    def unexpected_query(*_args: Any, **_kwargs: Any) -> None:
        pytest.fail("Invalid report filters must be rejected before reading FRA data")

    monkeypatch.setattr(statistics_service, "get_fra_indicator_answers", unexpected_query)
    configuration = replace(_configuration(), **filters)
    with pytest.raises(report_service.ReportGenerationError):
        report_service.build_report_preview(configuration)
    with pytest.raises(report_service.ReportGenerationError):
        report_service.generate_report_pdf(configuration)
