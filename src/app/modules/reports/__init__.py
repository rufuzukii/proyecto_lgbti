"""Generación de informes de diversidad a partir de los servicios estadísticos compartidos."""

from app.modules.reports.models import (
    ReportChart,
    ReportConfiguration,
    ReportContent,
    ReportDataset,
    ReportMetric,
    ReportRecommendation,
)
from app.modules.reports.service import (
    build_report,
    build_report_preview,
    generate_report_pdf,
    load_report_dataset,
)

__all__ = [
    "ReportChart",
    "ReportConfiguration",
    "ReportContent",
    "ReportDataset",
    "ReportMetric",
    "ReportRecommendation",
    "build_report",
    "build_report_preview",
    "generate_report_pdf",
    "load_report_dataset",
]
