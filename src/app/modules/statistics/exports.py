from __future__ import annotations

import csv
import html
import io
import logging
import re
import textwrap
import time
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Self, cast

import kaleido
import plotly.graph_objects as go
import plotly.io as pio

from app.modules.statistics.chart_export_runtime import (
    ChartExportBrowser,
    configure_chart_export_browser,
)
from app.shared.data.source_attribution import attribution_for_sources, source_metadata

EXPORT_FORMAT = "png"
EXPORT_WIDTH = 1600
EXPORT_HEIGHT = 900
EXPORT_SCALE = 2
EXPORT_FILENAME_MAX_LENGTH = 160
EXPORT_SUBTITLE_LINE_LENGTH = 110
REPORT_EXPORT_WIDTH = 1000
REPORT_EXPORT_HEIGHT = 650
REPORT_EXPORT_SCALE = 1
REPORT_EXPORT_TIMEOUT_SECONDS = 60
SUMMARY_TABLE_EXPORT_FIELDS = (
    "country",
    "country_code",
    "response",
    "value",
    "ranking",
    "difference",
    "difference_percentage",
    "year",
    "source",
    "indicator",
    "status",
    "fra_value",
    "ilga_score",
    "legal_rank",
    "social_rank",
    "ranking_position_difference",
)

logger = logging.getLogger(__name__)


class ChartExportError(RuntimeError):
    """Raised when Plotly cannot render a report chart."""


@dataclass(frozen=True)
class SummaryTableExport:
    content: str
    filename: str
    mime_type: str


class ReportFigureExporter:
    """Export one report figure per bounded Kaleido browser lifecycle."""

    def __init__(
        self,
        *,
        width: int = REPORT_EXPORT_WIDTH,
        height: int = REPORT_EXPORT_HEIGHT,
        scale: float = REPORT_EXPORT_SCALE,
    ) -> None:
        self.width = width
        self.height = height
        self.scale = scale
        self.image_count = 0
        self.elapsed_seconds = 0.0
        self._started_at = 0.0
        self._open = False

    def __enter__(self) -> Self:
        _require_chart_export_browser()
        self._started_at = time.perf_counter()
        logger.info(
            "report_chart_export_started batch_size=1 width=%s height=%s scale=%s",
            self.width,
            self.height,
            self.scale,
        )
        self._open = True
        return self

    def write(self, figure: go.Figure, path: str | Path) -> Path:
        if not self._open:
            raise RuntimeError("report_figure_exporter_not_open")
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = _prepare_report_payload(figure)
        try:
            errors = kaleido.write_fig_sync(
                payload,
                path=target,
                opts={
                    "format": EXPORT_FORMAT,
                    "width": self.width,
                    "height": self.height,
                    "scale": self.scale,
                },
                cancel_on_error=True,
                kopts={"n": 1, "timeout": REPORT_EXPORT_TIMEOUT_SECONDS},
            )
            if errors:
                raise errors[0]
        except Exception as exc:
            logger.exception(_chart_export_error_event(exc))
            raise ChartExportError("The report chart could not be generated.") from exc
        finally:
            payload.clear()
        if not _is_png_file(target):
            logger.error("chart_export_failed reason=invalid_or_missing_png")
            raise ChartExportError("The report chart could not be generated.")
        self.image_count += 1
        return target

    def __exit__(self, *_exc_info: object) -> None:
        if self._open:
            self._open = False
            self.elapsed_seconds = time.perf_counter() - self._started_at
            logger.info(
                "report_chart_export_completed count=%s total_ms=%.2f",
                self.image_count,
                self.elapsed_seconds * 1000,
            )


def chart_graph_config() -> Any:
    """Return the shared interactive configuration for exportable charts."""
    return {
        "displaylogo": False,
        "responsive": True,
        "modeBarButtonsToRemove": ["toImage"],
    }


def build_export_filename(
    chart_type: str,
    indicator: str,
    countries: Iterable[str] | None,
    year: int | str | None,
    *,
    file_format: str = EXPORT_FORMAT,
) -> str:
    """Build a safe, descriptive export filename with a bounded length."""
    country_values = [str(country).strip() for country in countries or [] if str(country).strip()]
    parts = [
        "rainbowlens-datahub",
        _slug(chart_type, fallback="grafico", limit=32),
        _slug(indicator, fallback="estadisticas", limit=64),
        _slug("-".join(country_values), fallback="europa", limit=40),
    ]
    if year is not None and str(year).strip():
        parts.append(_slug(str(year), fallback="periodo", limit=12))
    stem = "_".join(parts)
    clean_format = re.sub(r"[^a-z0-9]", "", str(file_format).lower()) or EXPORT_FORMAT
    suffix = f".{clean_format}"
    return f"{stem[: EXPORT_FILENAME_MAX_LENGTH - len(suffix)].rstrip('_-')}{suffix}"


def export_summary_table(
    rows: list[dict[str, Any]],
    columns: list[dict[str, Any]],
    *,
    language: str,
    metadata: dict[str, Any],
) -> SummaryTableExport:
    """Serialize the current AG Grid rows without exposing internal fields."""
    if not rows:
        raise ValueError("Summary table rows are required for export.")

    allowed_fields = set(SUMMARY_TABLE_EXPORT_FIELDS)
    visible_columns = [
        (str(column.get("field") or ""), str(column.get("headerName") or ""))
        for column in columns
        if str(column.get("field") or "") in allowed_fields
    ]
    if not visible_columns:
        raise ValueError("Summary table columns are required for export.")

    output = io.StringIO(newline="")
    output.write("\ufeff")
    writer = csv.writer(output, delimiter=";", lineterminator="\r\n")
    writer.writerow([header or field for field, header in visible_columns])
    writer.writerows(
        [_csv_safe_value(row.get(field)) for field, _header in visible_columns] for row in rows
    )
    source = str(metadata.get("source") or "").strip()
    if source:
        attribution = _source_label(source, language, metadata.get("year"))
        source_url = _primary_source_url(source, metadata.get("year"))
        writer.writerow([])
        writer.writerow(
            [
                "Source and attribution" if language == "en" else "Fuente y atribución",
                attribution,
            ]
        )
        writer.writerow(
            [
                "Original source" if language == "en" else "Fuente original",
                source_url,
            ]
        )

    countries = metadata.get("countries")
    country_values = countries if isinstance(countries, list) else []
    table_label = "summary-table" if language == "en" else "tabla-resumida"
    filename = build_export_filename(
        table_label,
        str(metadata.get("indicator") or ""),
        country_values,
        metadata.get("year"),
        file_format="csv",
    )
    return SummaryTableExport(
        content=output.getvalue(),
        filename=filename,
        mime_type="text/csv;charset=utf-8",
    )


def _csv_safe_value(value: Any) -> Any:
    if value is None:
        return ""
    if not isinstance(value, str):
        return value
    if value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")):
        return f"'{value}"
    return value


def prepare_figure_for_export(
    figure: go.Figure,
    *,
    chart_type: str,
    chart_title: str,
    indicator: str,
    countries: Iterable[str] | None,
    year: int | str | None,
    source: str,
    filters: Iterable[str] | None = None,
    language: str = "es",
) -> go.Figure:
    """Attach visible context and client-export metadata to an existing figure."""
    country_values = [str(country).strip() for country in countries or [] if str(country).strip()]
    scope = (
        ", ".join(country_values)
        if country_values
        else ("Europe" if language == "en" else "Europa")
    )
    source_label = _source_label(source, language, year)
    details = [
        str(indicator or "").strip(),
        scope,
        str(year).strip() if year is not None else "",
        source_label,
        *[str(value).strip() for value in filters or [] if str(value).strip()],
    ]
    subtitle = " · ".join(value for value in details if value)
    subtitle_lines = textwrap.wrap(
        subtitle,
        width=EXPORT_SUBTITLE_LINE_LENGTH,
        break_long_words=False,
        break_on_hyphens=False,
    ) or [""]
    subtitle_html = "<br>".join(html.escape(line) for line in subtitle_lines)
    title_text = (
        f"<b>{html.escape(str(chart_title or chart_type))}</b><br><sup>{subtitle_html}</sup>"
    )

    margin = cast(Any, figure).layout.margin
    existing_meta = cast(Any, figure).layout.meta
    preserved_meta = dict(existing_meta) if isinstance(existing_meta, dict) else {}
    minimum_width = preserved_meta.get("minimum_width")
    export_width = EXPORT_WIDTH
    if isinstance(minimum_width, (int, float)):
        export_width = max(EXPORT_WIDTH, min(4800, int(minimum_width)))
    layout_height = cast(Any, figure).layout.height
    export_height = EXPORT_HEIGHT
    if isinstance(layout_height, (int, float)):
        export_height = max(EXPORT_HEIGHT, min(2000, int(layout_height)))
    figure.update_layout(
        title={
            "text": title_text,
            "x": 0.02,
            "xanchor": "left",
            "font": {"size": 18},
        },
        margin={
            "l": margin.l if margin.l is not None else 45,
            "r": margin.r if margin.r is not None else 20,
            "t": max(margin.t or 0, 82 + 18 * (len(subtitle_lines) - 1)),
            "b": margin.b if margin.b is not None else 55,
        },
        meta={
            **preserved_meta,
            "export_filename": build_export_filename(
                chart_type,
                indicator,
                country_values,
                year,
            ),
            "export_format": EXPORT_FORMAT,
            "export_width": export_width,
            "export_height": export_height,
            "export_scale": EXPORT_SCALE,
            "export_source": source_label,
        },
    )
    return figure


def export_figure_for_report(
    figure: go.Figure,
    *,
    width: int = REPORT_EXPORT_WIDTH,
    height: int = REPORT_EXPORT_HEIGHT,
    scale: float = REPORT_EXPORT_SCALE,
) -> bytes:
    """Render one existing Plotly figure as a document-ready white PNG."""
    _require_chart_export_browser()
    prepared = _prepare_report_figure(figure)
    try:
        image_bytes = pio.to_image(
            prepared,
            format=EXPORT_FORMAT,
            width=width,
            height=height,
            scale=scale,
            validate=True,
        )
    except Exception as exc:
        logger.exception(_chart_export_error_event(exc))
        raise ChartExportError("The report chart could not be generated.") from exc
    if not _is_png(image_bytes):
        logger.error("chart_export_failed reason=invalid_png")
        raise ChartExportError("The report chart could not be generated.")
    return image_bytes


def export_figures_for_report(
    figures: Iterable[go.Figure],
    paths: Iterable[str | Path],
    *,
    width: int = REPORT_EXPORT_WIDTH,
    height: int = REPORT_EXPORT_HEIGHT,
    scale: float = REPORT_EXPORT_SCALE,
) -> list[Path]:
    """Render figures one at a time in one bounded, explicitly closed browser."""
    source_figures = iter(figures)
    targets = [Path(path) for path in paths]
    if not targets:
        if next(source_figures, None) is not None:
            raise ValueError("Each report figure requires exactly one output path.")
        return []
    rendered: list[Path] = []
    with ReportFigureExporter(width=width, height=height, scale=scale) as exporter:
        for target in targets:
            try:
                figure = next(source_figures)
            except StopIteration as exc:
                raise ValueError("Each report figure requires exactly one output path.") from exc
            rendered.append(exporter.write(figure, target))
            del figure
    if next(source_figures, None) is not None:
        raise ValueError("Each report figure requires exactly one output path.")
    return rendered


def _configure_kaleido_browser(prefix: str | Path | None = None) -> str | None:
    """Compatibility wrapper around the shared runtime browser detector."""
    browser = configure_chart_export_browser(prefix)
    return str(browser.path) if browser.ready and browser.path is not None else None


def _require_chart_export_browser() -> ChartExportBrowser:
    browser = configure_chart_export_browser()
    if not browser.found:
        logger.error("browser_not_found")
        raise ChartExportError("The report charts could not be generated.")
    if not browser.executable:
        logger.error("browser_not_executable browser_path=%s", browser.path)
        raise ChartExportError("The report charts could not be generated.")
    return browser


def _chart_export_error_event(exc: BaseException) -> str:
    exceptions: list[BaseException] = []
    current: BaseException | None = exc
    while current is not None and current not in exceptions:
        exceptions.append(current)
        current = current.__cause__ or current.__context__
    names = {type(item).__name__ for item in exceptions}
    messages = " ".join(str(item).casefold() for item in exceptions)
    if "ChromeNotFoundError" in names or ("chrome" in messages and "not" in messages):
        return "browser_not_found"
    if names & {"BrowserFailedError", "BrowserClosedError"}:
        return "kaleido_initialization_failed"
    return "chart_export_failed"


def _is_png(value: bytes) -> bool:
    return len(value) > 8 and value.startswith(b"\x89PNG\r\n\x1a\n")


def _is_png_file(path: Path) -> bool:
    try:
        with path.open("rb") as image_file:
            return _is_png(image_file.read(16))
    except OSError:
        return False


def _prepare_report_figure(figure: go.Figure) -> go.Figure:
    prepared = go.Figure(figure)
    margin = cast(Any, prepared).layout.margin
    annotations = [
        annotation
        for annotation in list(cast(Any, prepared).layout.annotations or [])
        if str(getattr(annotation, "text", "") or "").strip().casefold()
        not in {"seleccionado", "selected"}
    ]
    prepared.update_layout(
        paper_bgcolor="#FFFFFF",
        plot_bgcolor="#FFFFFF",
        font={"family": "Arial, sans-serif", "color": "#172033", "size": 15},
        title_font={"color": "#172033", "size": 21},
        legend={
            "bgcolor": "rgba(255,255,255,0.9)",
            "font": {"color": "#172033", "size": 13},
        },
        margin={
            "l": max(margin.l or 0, 70),
            "r": max(margin.r or 0, 100),
            "t": max(margin.t or 0, 105),
            "b": max(margin.b or 0, 75),
        },
    )
    cast(Any, prepared).layout.annotations = annotations
    prepared.update_xaxes(
        color="#172033",
        gridcolor="#E5EAF2",
        zerolinecolor="#B9C2D0",
        automargin=True,
    )
    prepared.update_yaxes(
        color="#172033",
        gridcolor="#E5EAF2",
        zerolinecolor="#B9C2D0",
        automargin=True,
    )
    title_text = getattr(cast(Any, prepared).layout.title, "text", None)
    if isinstance(title_text, str):
        prepared.update_layout(
            title_text=title_text.replace("·", " - ").replace("–", "-").replace("—", "-")
        )
    return prepared


def _prepare_report_payload(figure: go.Figure) -> dict[str, Any]:
    prepared = _prepare_report_figure(figure)
    payload = prepared.to_dict()
    payload.get("layout", {}).pop("meta", None)
    for trace in payload.get("data", []):
        trace.pop("customdata", None)
        trace.pop("hovertemplate", None)
        trace.pop("hoverlabel", None)
        trace.pop("meta", None)
        trace["hoverinfo"] = "skip"
    return payload


def _source_label(source: str, language: str, year: int | str | None = None) -> str:
    sources = _source_keys(source)
    clean_year = _safe_year(year)
    return " | ".join(
        attribution_for_sources(
            sources,
            language=language,
            year=clean_year,
            compact=True,
        )
    )


def _primary_source_url(source: str, year: int | str | None = None) -> str:
    sources = _source_keys(source)
    return " | ".join(source_metadata(item, year=_safe_year(year)).source_url for item in sources)


def _source_keys(source: str) -> list[str]:
    value = str(source or "").casefold()
    keys: list[str] = []
    if "fra" in value:
        keys.append("fra")
    if "ilga" in value or "rainbow map" in value:
        keys.append("ilga")
    if "felgtbi" in value or "felgtb" in value:
        keys.append("felgtbi")
    return keys or ["fra", "ilga"]


def _safe_year(value: int | str | None) -> int | None:
    try:
        return int(value) if value is not None else None
    except TypeError, ValueError:
        return None


def _slug(value: str, *, fallback: str, limit: int) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii").lower()
    clean = re.sub(r"[^a-z0-9]+", "-", ascii_value).strip("-")
    return (clean or fallback)[:limit].rstrip("-")
