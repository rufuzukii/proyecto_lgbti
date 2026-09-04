from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import fitz
import plotly.graph_objects as go
import pytest
from PIL import Image

from app.modules.reports import service as report_service
from app.modules.reports.models import ReportConfiguration, ReportDataset
from app.modules.reports.static_charts import ReportChartRenderer

pytestmark = pytest.mark.production_like


def test_report_renderer_exports_png_without_a_browser(tmp_path: Path) -> None:
    figure = go.Figure(go.Bar(x=["A", "B"], y=[1, 2]))
    target = tmp_path / "chart.png"

    with ReportChartRenderer(width=640, height=360) as renderer:
        rendered = renderer.write("ranking", figure, target)

    assert rendered == target
    assert target.stat().st_size > 0
    with Image.open(target) as image:
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
            5.0,
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
            7,
            10.0,
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
            5.0,
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
            9,
            10.0,
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
    with fitz.open(stream=generated.pdf_bytes, filetype="pdf") as document:
        assert document.page_count == generated.page_count
        assert sum(len(page.get_images(full=True)) for page in document) >= expected_images
        document_text = "\n".join(str(page.get_text("text")) for page in document)
        assert "Ranking comparativo" in document_text
        expected_map_title = (
            "Mapa europeo FRA" if configuration.source == "fra" else "Mapa legal ILGA-Europe"
        )
        assert expected_map_title in document_text


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
