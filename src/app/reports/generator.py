from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.reports.models import ReportConfiguration
from app.reports.service import GeneratedReport, generate_report_pdf


def generate_report(
    configuration: ReportConfiguration | Mapping[str, Any],
) -> GeneratedReport:
    """Compatibility entry point for the completed report service."""
    resolved = (
        configuration
        if isinstance(configuration, ReportConfiguration)
        else ReportConfiguration.from_mapping(configuration)
    )
    return generate_report_pdf(resolved)

