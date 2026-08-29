"""Diversity report generation built on the shared statistics services."""

from app.modules.reports.models import (
    ReportChart,
    ReportConfiguration,
    ReportContent,
    ReportDataset,
    ReportMetric,
    ReportRecommendation,
)
from app.modules.reports.service import build_report, generate_report_pdf, load_report_dataset

__all__ = [
    "ReportChart",
    "ReportConfiguration",
    "ReportContent",
    "ReportDataset",
    "ReportMetric",
    "ReportRecommendation",
    "build_report",
    "generate_report_pdf",
    "load_report_dataset",
]
