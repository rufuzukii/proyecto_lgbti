from __future__ import annotations

import logging
import re
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import plotly.graph_objects as go

from app.modules.reports.builder import ReportBuilder
from app.modules.reports.models import ReportConfiguration, ReportContent, ReportDataset
from app.modules.reports.pdf_exporter import PDFExporter
from app.modules.reports.static_charts import (
    ReportChartRenderer,
    ReportChartRenderError,
)
from app.modules.statistics.exports import build_export_filename
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
    timing_payloads = [dict(result.get("_statistics_timings") or {})]
    if configuration.source == "combined":
        timing_payloads.append(
            dict((result.get("combined_analysis") or {}).get("_statistics_timings") or {})
        )
    return ReportDataset(
        result=result,
        query_seconds=duration,
        normalization_seconds=sum(_timing_ms(item, "normalization_ms") for item in timing_payloads)
        / 1000,
        analysis_seconds=sum(_timing_ms(item, "analysis_ms") for item in timing_payloads) / 1000,
        cache_hit=bool(timing_payloads)
        and all(bool(item.get("cache_hit")) for item in timing_payloads),
    )


def build_report(configuration: ReportConfiguration) -> ReportContent:
    dataset = load_report_dataset(configuration)
    return ReportBuilder().build(configuration, dataset)


def build_report_preview(configuration: ReportConfiguration) -> ReportContent:
    try:
        dataset = load_report_dataset(configuration)
        content = ReportBuilder().build(configuration, dataset)
    except ReportGenerationError:
        raise
    except Exception as exc:
        logger.exception(
            "report_preview_failed source=%s year=%s",
            configuration.source,
            configuration.year,
        )
        raise ReportGenerationError("The report preview could not be generated.") from exc
    required_maps = {
        "fra": {"map_fra"},
        "ilga": {"map_ilga"},
        "combined": {"map_fra", "map_ilga"},
    }[configuration.source]
    rendered_keys = {chart.key for chart in content.charts if chart.figures}
    if not content.charts or not required_maps.issubset(rendered_keys):
        logger.error(
            "report_preview_incomplete source=%s charts_requested=%s chart_keys=%s",
            configuration.source,
            ",".join(configuration.charts),
            ",".join(sorted(rendered_keys)),
        )
        raise ReportGenerationError("The report preview could not be generated.")
    return content


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
    try:
        dataset = load_report_dataset(configuration)
        logger.info(
            "report_data_loaded source=%s report_query_ms=%.2f "
            "report_normalization_ms=%.2f report_analysis_ms=%.2f cache_hit=%s",
            configuration.source,
            dataset.query_seconds * 1000,
            dataset.normalization_seconds * 1000,
            dataset.analysis_seconds * 1000,
            dataset.cache_hit,
        )
        image_started = time.perf_counter()
        with tempfile.TemporaryDirectory(prefix="rainbowlens-datahub-report-") as temp_dir:
            root = Path(temp_dir).resolve()
            chart_paths: dict[str, list[Path]] = {}
            try:
                with ReportChartRenderer() as chart_renderer:

                    def export_figure(key: str, page: int, figure: go.Figure) -> None:
                        path = root / f"{key}-{page:02d}.png"
                        chart_renderer.write(key, figure, path)
                        chart_paths.setdefault(key, []).append(path)

                    content = ReportBuilder().build_for_pdf(
                        configuration,
                        dataset,
                        export_figure,
                    )
            except ReportChartRenderError as exc:
                logger.exception(
                    "report_generation_failed stage=chart_render",
                    extra={
                        "source": configuration.source,
                        "year": configuration.year,
                        "country_count": len(configuration.countries),
                    },
                )
                raise ReportGenerationError("The report could not be generated.") from exc
            image_seconds = time.perf_counter() - image_started
            image_count = sum(len(paths) for paths in chart_paths.values())
            apply_chart_narratives(content, chart_narratives or {})
            apply_section_narratives(content, section_narratives or {})
            logger.info(
                "report_figures_built count=%s preparation_ms=%.2f figure_ms=%.2f",
                image_count,
                content.timings["preparation_seconds"] * 1000,
                content.timings["figure_build_seconds"] * 1000,
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
            logger.info(
                "report_pdf_generated pages=%s bytes=%s total_ms=%.2f",
                page_count,
                len(pdf_bytes),
                pdf_seconds * 1000,
            )
        timings = {
            **content.timings,
            "queue_seconds": round(wait_seconds, 4),
            "chart_export_seconds": round(image_seconds, 4),
            "pdf_seconds": round(pdf_seconds, 4),
            "total_seconds": round(wait_seconds + time.perf_counter() - total_started, 4),
        }
        logger.info(
            "report_generation_completed source=%s charts=%s images=%s pages=%s total_ms=%.2f",
            configuration.source,
            len(content.charts),
            image_count,
            page_count,
            timings["total_seconds"] * 1000,
        )
        return GeneratedReport(
            content=content,
            pdf_bytes=pdf_bytes,
            filename=_report_filename(configuration, content),
            timings=timings,
            image_count=image_count,
            page_count=page_count,
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


def _timing_ms(payload: dict[str, object], key: str) -> float:
    value = payload.get(key)
    if not isinstance(value, int | float | str):
        return 0.0
    try:
        return max(0.0, float(value or 0.0))
    except TypeError, ValueError:
        return 0.0


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
