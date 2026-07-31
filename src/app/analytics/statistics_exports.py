from __future__ import annotations

import html
import logging
import re
import unicodedata
from collections.abc import Iterable
from pathlib import Path
from typing import Any, cast

import plotly.graph_objects as go
import plotly.io as pio

EXPORT_FORMAT = "png"
EXPORT_WIDTH = 1600
EXPORT_HEIGHT = 900
EXPORT_SCALE = 2
EXPORT_FILENAME_MAX_LENGTH = 160
REPORT_EXPORT_WIDTH = 1400
REPORT_EXPORT_HEIGHT = 780
REPORT_EXPORT_SCALE = 1.25

logger = logging.getLogger(__name__)


class ChartExportError(RuntimeError):
    """Raised when Plotly cannot render a report chart."""


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
) -> str:
    """Build a safe, descriptive PNG filename with a bounded length."""
    country_values = [str(country).strip() for country in countries or [] if str(country).strip()]
    parts = [
        "rainbow-lens",
        _slug(chart_type, fallback="grafico", limit=32),
        _slug(indicator, fallback="estadisticas", limit=64),
        _slug("-".join(country_values), fallback="europa", limit=40),
    ]
    if year is not None and str(year).strip():
        parts.append(_slug(str(year), fallback="periodo", limit=12))
    stem = "_".join(parts)
    suffix = f".{EXPORT_FORMAT}"
    return f"{stem[: EXPORT_FILENAME_MAX_LENGTH - len(suffix)].rstrip('_-')}{suffix}"


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
    source_label = _source_label(source, language)
    details = [
        str(indicator or "").strip(),
        scope,
        str(year).strip() if year is not None else "",
        source_label,
        *[str(value).strip() for value in filters or [] if str(value).strip()],
    ]
    subtitle = " · ".join(value for value in details if value)
    if len(subtitle) > 180:
        subtitle = f"{subtitle[:177].rstrip()}…"
    title_text = (
        f"<b>{html.escape(str(chart_title or chart_type))}</b>"
        f"<br><sup>{html.escape(subtitle)}</sup>"
    )

    margin = cast(Any, figure).layout.margin
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
            "t": max(margin.t or 0, 82),
            "b": margin.b if margin.b is not None else 55,
        },
        meta={
            "export_filename": build_export_filename(
                chart_type,
                indicator,
                country_values,
                year,
            ),
            "export_format": EXPORT_FORMAT,
            "export_width": EXPORT_WIDTH,
            "export_height": EXPORT_HEIGHT,
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
    prepared = _prepare_report_figure(figure)
    try:
        return pio.to_image(
            prepared,
            format=EXPORT_FORMAT,
            width=width,
            height=height,
            scale=scale,
            validate=True,
        )
    except Exception as exc:
        logger.exception("report_chart_export_failed")
        raise ChartExportError("The report chart could not be generated.") from exc


def export_figures_for_report(
    figures: Iterable[go.Figure],
    paths: Iterable[str | Path],
    *,
    width: int = REPORT_EXPORT_WIDTH,
    height: int = REPORT_EXPORT_HEIGHT,
    scale: float = REPORT_EXPORT_SCALE,
) -> list[Path]:
    """Batch-render report figures so one Chrome session serves all charts."""
    prepared = [_prepare_report_figure(figure) for figure in figures]
    targets: list[str | Path] = [Path(path) for path in paths]
    if len(prepared) != len(targets):
        raise ValueError("Each report figure requires exactly one output path.")
    if not prepared:
        return []
    for target_value in targets:
        Path(target_value).parent.mkdir(parents=True, exist_ok=True)
    try:
        pio.write_images(
            prepared,
            targets,
            format=EXPORT_FORMAT,
            width=width,
            height=height,
            scale=scale,
            validate=True,
        )
    except Exception as exc:
        logger.exception(
            "report_chart_batch_export_failed",
            extra={"chart_count": len(prepared)},
        )
        raise ChartExportError("The report charts could not be generated.") from exc
    return [Path(target) for target in targets]


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


def _source_label(source: str, language: str) -> str:
    if source == "FRA":
        return (
            "Source: FRA EU LGBTIQ Survey III"
            if language == "en"
            else "Fuente: FRA EU LGBTIQ Survey III"
        )
    if source == "ILGA-Europe":
        return (
            "Source: ILGA-Europe Rainbow Map"
            if language == "en"
            else "Fuente: ILGA-Europe Rainbow Map"
        )
    return (
        "Source: FRA EU LGBTIQ Survey III + ILGA-Europe Rainbow Map"
        if language == "en"
        else "Fuente: FRA EU LGBTIQ Survey III + ILGA-Europe Rainbow Map"
    )


def _slug(value: str, *, fallback: str, limit: int) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii").lower()
    clean = re.sub(r"[^a-z0-9]+", "-", ascii_value).strip("-")
    return (clean or fallback)[:limit].rstrip("-")
