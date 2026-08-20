from __future__ import annotations

import logging
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from app.analytics.statistics_exports import (
    build_export_filename,
    export_figures_for_report,
)
from app.analytics.statistics_models import FraStatisticsQuery, IlgaStatisticsQuery
from app.analytics.statistics_service import (
    get_combined_statistics_analysis,
    get_fra_statistics,
    get_ilga_statistics,
)
from app.reports.builder import ReportBuilder
from app.reports.models import ReportConfiguration, ReportContent, ReportDataset
from app.reports.pdf_exporter import PDFExporter

logger = logging.getLogger(__name__)


class ReportGenerationError(RuntimeError):
    """Safe report-generation failure for presentation layers."""


@dataclass(frozen=True)
class GeneratedReport:
    content: ReportContent
    pdf_bytes: bytes
    filename: str
    timings: dict[str, float]


def load_report_dataset(configuration: ReportConfiguration) -> ReportDataset:
    """Use one optimized statistics query for the complete report dataset."""
    started = time.perf_counter()
    if configuration.source in {"fra", "combined"}:
        query = FraStatisticsQuery(
            year=configuration.year,
            category=configuration.category or None,
            question_code=configuration.indicator_id or None,
            answer=configuration.answer or None,
            filter_a_name=configuration.filter_a_name or "All",
            filter_a_value=configuration.filter_a_value or "All",
            filter_b_name=configuration.filter_b_name or "All",
            filter_b_value=configuration.filter_b_value or "All",
        )
        fra_result = get_fra_statistics(query)
        if fra_result.get("status") != "ok":
            result = fra_result
        elif configuration.source == "combined":
            combined = get_combined_statistics_analysis(query, fra_result=fra_result)
            result = (
                {
                    **fra_result,
                    "source": "FRA + ILGA-Europe",
                    "combined_analysis": combined,
                    "fra_median_comparison": combined.get("fra_median_comparison"),
                    "availability": combined.get("availability"),
                }
                if combined.get("status") == "ok"
                else combined
            )
        else:
            result = fra_result
    else:
        result = get_ilga_statistics(
            IlgaStatisticsQuery(
                year=configuration.year,
                category=configuration.category or "Ranking total",
                criterion=configuration.criterion or None,
            )
        )
    duration = time.perf_counter() - started
    if result.get("status") != "ok":
        raise ReportGenerationError(
            str(result.get("message") or "No data is available for this report.")
        )
    return ReportDataset(result=result, query_seconds=duration)


def build_report(configuration: ReportConfiguration) -> ReportContent:
    dataset = load_report_dataset(configuration)
    return ReportBuilder().build(configuration, dataset)


def generate_report_pdf(configuration: ReportConfiguration) -> GeneratedReport:
    """Build all report artifacts and guarantee temporary-file cleanup."""
    total_started = time.perf_counter()
    try:
        content = build_report(configuration)
        image_started = time.perf_counter()
        with tempfile.TemporaryDirectory(prefix="rainbowlens-datahub-report-") as temp_dir:
            root = Path(temp_dir).resolve()
            chart_paths = {
                chart.key: root / f"{index:02d}-{chart.key}.png"
                for index, chart in enumerate(content.charts, start=1)
            }
            export_figures_for_report(
                [chart.figure for chart in content.charts],
                [chart_paths[chart.key] for chart in content.charts],
            )
            image_seconds = time.perf_counter() - image_started
            pdf_started = time.perf_counter()
            pdf_bytes = PDFExporter().export(content, chart_paths)
            pdf_seconds = time.perf_counter() - pdf_started
        timings = {
            **content.timings,
            "chart_export_seconds": round(image_seconds, 4),
            "pdf_seconds": round(pdf_seconds, 4),
            "total_seconds": round(time.perf_counter() - total_started, 4),
        }
        logger.info(
            "report_generated",
            extra={
                "source": configuration.source,
                "year": configuration.year,
                "country_count": len(configuration.countries),
                "chart_count": len(content.charts),
                **timings,
            },
        )
        return GeneratedReport(
            content=content,
            pdf_bytes=pdf_bytes,
            filename=_report_filename(configuration, content),
            timings=timings,
        )
    except ReportGenerationError:
        raise
    except Exception as exc:
        logger.exception(
            "report_generation_failed",
            extra={
                "source": configuration.source,
                "year": configuration.year,
                "country_count": len(configuration.countries),
            },
        )
        raise ReportGenerationError("The report could not be generated.") from exc


def _report_filename(
    configuration: ReportConfiguration,
    content: ReportContent,
) -> str:
    png_name = build_export_filename(
        f"rainbowlens-{configuration.profile_key}",
        content.indicator or configuration.objective or "informe",
        content.country_names,
        configuration.year,
    )
    return f"{png_name.removesuffix('.png')}.pdf"
