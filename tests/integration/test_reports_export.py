from __future__ import annotations

from app.analytics.statistics_exports import export_summary_table
from app.reports.builder import HRReportBuilder
from app.reports.models import ReportConfiguration, ReportDataset


def test_report_metrics_flow_into_the_exported_summary_table() -> None:
    # Arrange
    configuration = ReportConfiguration.from_mapping(
        {
            "source": "fra",
            "category": "Employment",
            "indicator_id": "EMP_1",
            "answer": "Yes",
            "year": 2024,
            "countries": ["ES", "FR"],
            "primary_country": "ES",
        }
    )
    result = {
        "status": "ok",
        "source": "FRA",
        "year": 2024,
        "indicator": "Workplace discrimination",
        "ranking": [
            {"country": "España", "iso": "ES", "value": 64.0},
            {"country": "France", "iso": "FR", "value": 48.0},
        ],
        "detail_data": [],
        "data": [],
        "methodology": "FRA survey data.",
    }

    # Act
    report = HRReportBuilder().build(configuration, ReportDataset(result, query_seconds=0.01))
    exported = export_summary_table(
        report.table_rows,
        [
            {"field": "country", "headerName": "País"},
            {"field": "value", "headerName": "Valor"},
            {"field": "ranking", "headerName": "Posición"},
        ],
        language="es",
        metadata={"indicator": report.indicator, "countries": ["ES", "FR"], "year": 2024},
    )

    # Assert
    metrics = {metric.key: metric.numeric_value for metric in report.metrics}
    assert metrics["eu_average"] == 56.0
    assert metrics["country_value"] == 64.0
    assert "España;64.0;" in exported.content
    assert exported.filename.endswith("_2024.csv")
