from typing import cast

import fitz
import pytest

from app.modules.reports.models import ReportConfiguration, ReportContent, ReportMetric
from app.modules.reports.pdf_exporter import PDFExporter


@pytest.mark.parametrize("language,heading", [("en", "Key metrics"), ("es", "Métricas principales")])
@pytest.mark.parametrize("paragraph_count", [1, 30])
def test_pdf_keeps_metrics_heading_with_first_card(
    language: str, heading: str, paragraph_count: int
) -> None:
    # Thirty short paragraphs leave room for the heading, but not the first metric row.
    content = ReportContent(
        configuration=ReportConfiguration(language=language, sections=("executive", "metrics")),
        source_name="FRA",
        indicator="Workplace discrimination",
        country_names=["Spain", "France"],
        metrics=[
            ReportMetric(str(index), f"Metric {index}", f"{18 + index} %") for index in range(6)
        ],
        executive_summary=["A paragraph of edited report context."] * paragraph_count,
        methodology=[],
        workplace_analysis=[],
        demographic_analysis=[],
        conclusions=[],
        recommendations=[],
        limitations=[],
        sources=[],
        charts=[],
        table_rows=[],
    )

    pdf_bytes = PDFExporter().export(content, {})

    with fitz.open(stream=pdf_bytes, filetype="pdf") as document:
        pages = [cast(str, page.get_text()) for page in document]
    heading_pages = [text for text in pages if heading in text]
    assert len(heading_pages) == 1
    assert "Metric 0" in heading_pages[0]
    assert all(f"Metric {index}" in "\n".join(pages) for index in range(6))
