from __future__ import annotations

import logging
import re
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from app.modules.reports.builder import ReportBuilder
from app.modules.reports.models import ReportConfiguration, ReportContent, ReportDataset
from app.modules.reports.pdf_exporter import PDFExporter
from app.modules.reports.resource_usage import ReportMemorySampler
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
report_generation_lock = threading.Lock()


class ReportGenerationError(RuntimeError):
    """Safe report-generation failure for presentation layers."""


@dataclass(frozen=True)
class GeneratedReport:
    content: ReportContent
    pdf_bytes: bytes
    filename: str
    timings: dict[str, float]
    image_count: int
    page_count: int
    memory_peak_mb: float | None


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


def build_report_preview(configuration: ReportConfiguration) -> ReportContent:
    dataset = load_report_dataset(configuration)
    return ReportBuilder().build(configuration, dataset, include_figures=False)


def generate_report_pdf(
    configuration: ReportConfiguration,
    *,
    chart_narratives: dict[str, dict[str, str]] | None = None,
    section_narratives: dict[str, str] | None = None,
) -> GeneratedReport:
    """Build all report artifacts and guarantee temporary-file cleanup."""
    wait_started = time.perf_counter()
    logger.info(
        "report_generation_started source=%s year=%s country_count=%s",
        configuration.source,
        configuration.year,
        len(configuration.countries),
    )
    with report_generation_lock:
        wait_seconds = time.perf_counter() - wait_started
        return _generate_report_pdf(
            configuration,
            chart_narratives=chart_narratives,
            section_narratives=section_narratives,
            wait_seconds=wait_seconds,
        )


def _generate_report_pdf(
    configuration: ReportConfiguration,
    *,
    chart_narratives: dict[str, dict[str, str]] | None,
    section_narratives: dict[str, str] | None,
    wait_seconds: float,
) -> GeneratedReport:
    total_started = time.perf_counter()
    memory_sampler = ReportMemorySampler()
    memory_sampler.start()
    try:
        dataset = load_report_dataset(configuration)
        data_memory = memory_sampler.sample()
        logger.info(
            "report_data_loaded source=%s query_ms=%.2f memory_mb=%s python_mb=%s "
            "memory_limit_mb=%s memory_source=%s",
            configuration.source,
            dataset.query_seconds * 1000,
            _memory_value(data_memory.total_mb),
            _memory_value(data_memory.python_mb),
            _memory_value(data_memory.limit_mb),
            data_memory.source,
        )
        content = ReportBuilder().build(configuration, dataset)
        apply_chart_narratives(content, chart_narratives or {})
        apply_section_narratives(content, section_narratives or {})
        image_count = sum(len(chart.figures) for chart in content.charts)
        figure_memory = memory_sampler.sample()
        logger.info(
            "report_figures_built count=%s preparation_ms=%.2f figure_ms=%.2f "
            "memory_mb=%s python_mb=%s",
            image_count,
            content.timings["preparation_seconds"] * 1000,
            content.timings["figure_build_seconds"] * 1000,
            _memory_value(figure_memory.total_mb),
            _memory_value(figure_memory.python_mb),
        )
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
            paths = [path for chart in content.charts for path in chart_paths[chart.key]]
            try:
                export_figures_for_report(
                    _release_report_figures(content),
                    paths,
                )
            except ChartExportError as exc:
                logger.error(
                    "chart_export_failed",
                    extra={
                        "source": configuration.source,
                        "year": configuration.year,
                        "country_count": len(configuration.countries),
                        "image_count": image_count,
                    },
                )
                raise ReportGenerationError("The report could not be generated.") from exc
            image_seconds = time.perf_counter() - image_started
            export_memory = memory_sampler.sample()
            logger.info(
                "report_chart_export_completed count=%s total_ms=%.2f "
                "memory_mb=%s peak_memory_mb=%s",
                image_count,
                image_seconds * 1000,
                _memory_value(export_memory.total_mb),
                _memory_value(memory_sampler.peak_mb),
            )
            pdf_started = time.perf_counter()
            try:
                pdf_exporter = PDFExporter()
                pdf_bytes = pdf_exporter.export(content, chart_paths)
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
            page_count = pdf_exporter.page_count
            pdf_memory = memory_sampler.sample()
            logger.info(
                "report_pdf_generated pages=%s bytes=%s total_ms=%.2f memory_mb=%s",
                page_count,
                len(pdf_bytes),
                pdf_seconds * 1000,
                _memory_value(pdf_memory.total_mb),
            )
        memory_sampler.stop()
        memory_peak_mb = memory_sampler.peak_mb
        timings = {
            **content.timings,
            "queue_seconds": round(wait_seconds, 4),
            "chart_export_seconds": round(image_seconds, 4),
            "pdf_seconds": round(pdf_seconds, 4),
            "total_seconds": round(wait_seconds + time.perf_counter() - total_started, 4),
        }
        logger.info(
            "report_generation_completed source=%s charts=%s images=%s pages=%s "
            "total_ms=%.2f peak_memory_mb=%s",
            configuration.source,
            len(content.charts),
            image_count,
            page_count,
            timings["total_seconds"] * 1000,
            _memory_value(memory_peak_mb),
        )
        return GeneratedReport(
            content=content,
            pdf_bytes=pdf_bytes,
            filename=_report_filename(configuration, content),
            timings=timings,
            image_count=image_count,
            page_count=page_count,
            memory_peak_mb=memory_peak_mb,
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
    finally:
        memory_sampler.stop()


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
            f"{content.configuration.year or 'el periodo disponible'} como contexto "
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


def _memory_value(value: float | None) -> str:
    return f"{value:.1f}" if value is not None else "unavailable"


def _release_report_figures(content: ReportContent):
    for chart in content.charts:
        figure = chart.figure
        chart.figure = None
        if figure is not None:
            yield figure
        while chart.additional_figures:
            yield chart.additional_figures.pop(0)


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
