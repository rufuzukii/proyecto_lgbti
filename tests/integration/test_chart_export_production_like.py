from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

import fitz
import plotly.graph_objects as go
import pytest
from PIL import Image

from app.modules.reports import service as report_service
from app.modules.reports.builder import HRReportBuilder
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
    single.write_bytes(
        export_figure_for_report(figure, width=640, height=360, scale=1)
    )
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
    ("case", "configuration", "result_factory"),
    (
        (
            "social",
            ReportConfiguration.from_mapping(
                {
                    "source": "fra",
                    "category": "Employment",
                    "indicator_id": "EMP_1",
                    "answer": "Yes",
                    "year": 2024,
                    "countries": ["ES", "FR"],
                    "primary_country": "ES",
                }
            ),
            lambda: _social_result(),
        ),
        (
            "legal",
            ReportConfiguration.from_mapping(
                {
                    "source": "ilga",
                    "category": "Ranking total",
                    "year": 2026,
                    "countries": ["ES", "FR"],
                    "primary_country": "ES",
                }
            ),
            lambda: _legal_result(),
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
            lambda: _legal_result(),
        ),
    ),
    ids=("social", "legal", "legal-all-countries"),
)
def test_generate_report_pdf_production_like(
    case: str,
    configuration: ReportConfiguration,
    result_factory: Callable[[], dict[str, object]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    content = HRReportBuilder().build(
        configuration,
        ReportDataset(result_factory(), query_seconds=0.01),
    )
    monkeypatch.setattr(report_service, "build_report", lambda _configuration: content)

    generated = report_service.generate_report_pdf(configuration)

    assert case
    assert generated.pdf_bytes.startswith(b"%PDF")
    assert generated.filename.endswith(".pdf")
    assert generated.timings["chart_export_seconds"] > 0
    with fitz.open(stream=generated.pdf_bytes, filetype="pdf") as document:
        assert document.page_count > 0
        assert any(page.get_images(full=True) for page in document)


def _social_result() -> dict[str, object]:
    detail = [
        {"country": country, "iso": iso, "answer": answer, "percentage": value}
        for country, iso, yes, no in (
            ("España", "ES", 64.0, 36.0),
            ("Francia", "FR", 55.0, 45.0),
            ("Alemania", "DE", 49.0, 51.0),
        )
        for answer, value in (("Yes", yes), ("No", no))
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
            {"country": "España", "iso": "ES", "value": 64.0},
            {"country": "Francia", "iso": "FR", "value": 55.0},
            {"country": "Alemania", "iso": "DE", "value": 49.0},
        ],
        "detail_data": detail,
        "data": [row for row in detail if row["answer"] == "Yes"],
        "methodology": "Aggregated FRA survey data.",
    }


def _legal_result() -> dict[str, object]:
    countries = (
        ("ES", "España"),
        ("FR", "Francia"),
        ("DE", "Alemania"),
        ("NL", "Países Bajos"),
        ("GB", "Reino Unido"),
        ("CZ", "Chequia"),
        ("PT", "Portugal"),
        ("IT", "Italia"),
        ("BE", "Bélgica"),
        ("AT", "Austria"),
        ("SE", "Suecia"),
        ("FI", "Finlandia"),
    )
    return {
        "status": "ok",
        "source": "ILGA-Europe",
        "year": 2026,
        "category": "Ranking total",
        "indicator": "Ranking total",
        "ranking": [
            {"iso": code, "country": country, "value": float(90 - index * 3)}
            for index, (code, country) in enumerate(countries)
        ],
        "data": [],
        "history": [
            {"country": country, "iso": code, "year": year, "value": value}
            for code, country in countries[:3]
            for year, value in ((2024, 70.0), (2025, 72.0), (2026, 74.0))
        ],
    }
