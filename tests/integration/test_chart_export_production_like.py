from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

import fitz
import plotly.graph_objects as go
import pytest
from PIL import Image

from app.modules.reports import service as report_service
from app.modules.reports.models import ReportConfiguration, ReportDataset
from app.modules.statistics.exports import (
    export_figure_for_report,
    export_figures_for_report,
)

pytestmark = [
    pytest.mark.browser,
    pytest.mark.production_like,
    pytest.mark.skipif(
        os.getenv("RUN_BROWSER_INTEGRATION") != "1",
        reason="set RUN_BROWSER_INTEGRATION=1 in an environment with Chrome/Kaleido",
    ),
]


def test_plotly_kaleido_exports_one_png_and_a_rainbowlens_batch(tmp_path: Path) -> None:
    figure = go.Figure(go.Bar(x=["A", "B"], y=[1, 2]))

    single = tmp_path / "single.png"
    single.write_bytes(export_figure_for_report(figure, width=640, height=360, scale=1))
    batch = [tmp_path / f"batch-{index}.png" for index in range(1, 6)]
    rendered = export_figures_for_report(
        [figure for _path in batch],
        batch,
        width=640,
        height=360,
        scale=1,
    )

    assert rendered == batch
    for path in [single, *batch]:
        assert path.stat().st_size > 0
        with Image.open(path) as image:
            assert image.format == "PNG"
            assert image.size == (640, 360)


@pytest.mark.parametrize(
    ("case", "configuration", "result_factory", "expected_images", "maximum_seconds"),
    (
        (
            "social_selected",
            ReportConfiguration.from_mapping(
                {
                    "source": "fra",
                    "category": "Employment",
                    "indicator_id": "EMP_1",
                    "answer": "Yes",
                    "year": 2024,
                    "countries": ["ES"],
                    "primary_country": "ES",
                }
            ),
            lambda: _social_result(),
            3,
            30.0,
        ),
        (
            "social_all_countries",
            ReportConfiguration.from_mapping(
                {
                    "source": "fra",
                    "category": "Employment",
                    "indicator_id": "EMP_1",
                    "answer": "Yes",
                    "year": 2024,
                    "countries": [],
                }
            ),
            lambda: _social_result(all_countries=True),
            3,
            60.0,
        ),
        (
            "legal_selected",
            ReportConfiguration.from_mapping(
                {
                    "source": "ilga",
                    "category": "Ranking total",
                    "year": 2026,
                    "countries": ["ES"],
                    "primary_country": "ES",
                }
            ),
            lambda: _legal_result(),
            3,
            30.0,
        ),
        (
            "legal_all_countries",
            ReportConfiguration.from_mapping(
                {
                    "source": "ilga",
                    "category": "Ranking total",
                    "year": 2026,
                    "countries": [],
                }
            ),
            lambda: _legal_result(all_countries=True),
            5,
            60.0,
        ),
    ),
    ids=("social-selected", "social-all", "legal-selected", "legal-all"),
)
def test_generate_report_pdf_production_like(
    case: str,
    configuration: ReportConfiguration,
    result_factory: Callable[[], dict[str, object]],
    expected_images: int,
    maximum_seconds: float,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        report_service,
        "load_report_dataset",
        lambda _configuration: ReportDataset(result_factory(), query_seconds=0.01),
    )

    generated = report_service.generate_report_pdf(configuration)

    assert case
    assert generated.pdf_bytes.startswith(b"%PDF")
    assert generated.filename.endswith(".pdf")
    assert generated.image_count == expected_images
    assert generated.timings["chart_export_seconds"] > 0
    assert generated.timings["total_seconds"] < maximum_seconds
    memory_budget = os.getenv("REPORT_MEMORY_BUDGET_MB")
    if memory_budget and generated.memory_peak_mb is not None:
        assert generated.memory_peak_mb < float(memory_budget)
    with fitz.open(stream=generated.pdf_bytes, filetype="pdf") as document:
        assert document.page_count == generated.page_count
        assert sum(len(page.get_images(full=True)) for page in document) >= expected_images


def _social_result(*, all_countries: bool = False) -> dict[str, object]:
    countries = _countries(30 if all_countries else 3)
    detail = [
        {"country": country, "iso": iso, "answer": answer, "percentage": value}
        for index, (iso, country) in enumerate(countries)
        for answer, value in (
            ("Yes", float(70 - index)),
            ("No", float(30 + index)),
        )
    ]
    return {
        "status": "ok",
        "source": "FRA",
        "year": 2024,
        "category": "Employment",
        "indicator": "Workplace discrimination",
        "indicator_code": "EMP_1",
        "answer": "Yes",
        "ranking": [
            {"country": country, "iso": iso, "value": float(70 - index)}
            for index, (iso, country) in enumerate(countries)
        ],
        "detail_data": detail,
        "data": [row for row in detail if row["answer"] == "Yes"],
        "methodology": "Aggregated FRA survey data.",
    }


def _legal_result(*, all_countries: bool = False) -> dict[str, object]:
    countries = _countries(40 if all_countries else 3)
    return {
        "status": "ok",
        "source": "ILGA-Europe",
        "year": 2026,
        "category": "Ranking total",
        "indicator": "Ranking total",
        "ranking": [
            {"iso": code, "country": country, "value": float(90 - index)}
            for index, (code, country) in enumerate(countries)
        ],
        "data": [],
        "history": [
            {"country": country, "iso": code, "year": year, "value": value}
            for code, country in countries
            for year, value in ((2024, 70.0), (2025, 72.0), (2026, 74.0))
        ],
    }


def _countries(count: int) -> tuple[tuple[str, str], ...]:
    codes = (
        "ES",
        "FR",
        "DE",
        "NL",
        "GB",
        "CZ",
        "PT",
        "IT",
        "BE",
        "AT",
        "SE",
        "FI",
        "AL",
        "AD",
        "AM",
        "AZ",
        "BA",
        "BG",
        "HR",
        "CY",
        "DK",
        "EE",
        "GE",
        "GR",
        "HU",
        "IS",
        "IE",
        "LV",
        "LI",
        "LT",
        "LU",
        "MT",
        "MD",
        "MC",
        "ME",
        "MK",
        "NO",
        "PL",
        "RO",
        "SM",
        "RS",
        "SK",
        "SI",
        "CH",
        "TR",
        "UA",
    )
    return tuple((code, code) for code in codes[:count])
