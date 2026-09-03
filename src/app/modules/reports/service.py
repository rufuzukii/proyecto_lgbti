from __future__ import annotations

import logging
import re
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from app.modules.reports.builder import ReportBuilder
from app.modules.reports.models import ReportConfiguration, ReportContent, ReportDataset
from app.modules.reports.pdf_exporter import PDFExporter
from app.modules.statistics.exports import (
    ChartExportError,
    build_export_filename,
    export_figures_for_report,
)
from app.modules.statistics.models import FraStatisticsQuery, IlgaStatisticsQuery
from app.modules.statistics.service import (
    get_combined_statistics_analysis,
    get_fra_statistics,
    get_ilga_statistics,
)

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
                    "ranking_gap": combined.get("ranking_gap"),
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


def generate_report_pdf(
    configuration: ReportConfiguration,
    *,
    chart_narratives: dict[str, dict[str, str]] | None = None,
    section_narratives: dict[str, str] | None = None,
) -> GeneratedReport:
    """Build all report artifacts and guarantee temporary-file cleanup."""
    total_started = time.perf_counter()
    try:
        content = build_report(configuration)
        apply_chart_narratives(content, chart_narratives or {})
        apply_section_narratives(content, section_narratives or {})
        image_started = time.perf_counter()
        with tempfile.TemporaryDirectory(prefix="rainbowlens-datahub-report-") as temp_dir:
            root = Path(temp_dir).resolve()
            chart_paths = {
                chart.key: [
                    root / f"{index:02d}-{chart.key}-{page:02d}.png"
                    for page, _figure in enumerate(chart.figures, start=1)
                ]
                for index, chart in enumerate(content.charts, start=1)
            }
            figures = [
                figure for chart in content.charts for figure in chart.figures
            ]
            paths = [
                path for chart in content.charts for path in chart_paths[chart.key]
            ]
            try:
                export_figures_for_report(
                    figures,
                    paths,
                )
            except ChartExportError as exc:
                logger.error(
                    "chart_export_failed",
                    extra={
                        "source": configuration.source,
                        "year": configuration.year,
                        "country_count": len(configuration.countries),
                        "image_count": len(figures),
                    },
                )
                raise ReportGenerationError("The report could not be generated.") from exc
            image_seconds = time.perf_counter() - image_started
            pdf_started = time.perf_counter()
            try:
                pdf_bytes = PDFExporter().export(content, chart_paths)
            except Exception as exc:
                logger.exception(
                    "pdf_generation_failed",
                    extra={
                        "source": configuration.source,
                        "year": configuration.year,
                        "country_count": len(configuration.countries),
                    },
                )
                raise ReportGenerationError("The report could not be generated.") from exc
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
                "image_count": len(figures),
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


def apply_chart_narratives(
    content: ReportContent,
    narratives: dict[str, dict[str, str]],
) -> ReportContent:
    """Apply the user's preview edits without changing report calculations."""
    for chart in content.charts:
        edits = narratives.get(chart.key)
        if edits is None:
            continue
        for field in ("what_shows", "how_to_read", "observation"):
            if field in edits:
                setattr(chart, field, sanitize_report_narrative(edits[field]))
    return content


def apply_section_narratives(
    content: ReportContent,
    narratives: dict[str, str],
) -> ReportContent:
    """Apply editable prose sections while preserving untouched generated content."""
    for section in ("executive", "context", "recommendations"):
        if section not in narratives:
            continue
        edited = sanitize_report_narrative(narratives[section], max_length=8_000)
        if edited != default_section_narrative(content, section):
            content.section_narratives[section] = edited
    return content


def default_section_narrative(content: ReportContent, section: str) -> str:
    """Return the generated text used to initialise an editable report section."""
    language = content.configuration.language
    if section == "executive":
        return "\n\n".join(content.executive_summary)
    if section == "context":
        if language == "en":
            return (
                f'The report analyses "{content.indicator}" for '
                f"{content.configuration.year or 'the available period'} as external "
                "context supporting diversity and inclusion policies."
            )
        return (
            f'Se analiza "{content.indicator}" para '
            f'{content.configuration.year or "el periodo disponible"} como contexto '
            "externo para apoyar políticas de diversidad e inclusión."
        )
    if section == "recommendations":
        return "\n".join(item.text for item in content.recommendations)
    return ""


def sanitize_report_narrative(value: object, *, max_length: int = 2_000) -> str:
    """Keep multiline prose while removing unsafe control characters."""
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    return text[:max_length]


def _report_filename(
    configuration: ReportConfiguration,
    content: ReportContent,
) -> str:
    png_name = build_export_filename(
        "rainbowlens-rrhh-inclusion",
        content.indicator or configuration.objective or "informe",
        content.country_names,
        configuration.year,
    )
    return f"{png_name.removesuffix('.png')}.pdf"
