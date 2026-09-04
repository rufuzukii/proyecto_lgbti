from __future__ import annotations

import html
import logging
import math
import re
import textwrap
import time
from collections.abc import Iterable, Sequence
from functools import lru_cache
from pathlib import Path
from typing import Any, Self

import plotly.graph_objects as go
from PIL import Image, ImageColor, ImageDraw, ImageFont

from app.shared.data.geography import ISO2_TO_ISO3
from app.shared.data.geography_service import europe_geojson

REPORT_CHART_WIDTH = 1000
REPORT_CHART_HEIGHT = 650

_WHITE = "#FFFFFF"
_INK = "#172033"
_MUTED = "#5F6B7A"
_GRID = "#DDE3EC"
_BLUE = "#2F6BDE"
_NO_DATA = "#CBD5E1"

logger = logging.getLogger(__name__)


class ReportChartRenderError(RuntimeError):
    """Raised when a report chart cannot be drawn without a browser."""


class ReportChartRenderer:
    """Draw report-only PNGs with Pillow, without Chrome or Kaleido."""

    def __init__(self, *, width: int = REPORT_CHART_WIDTH, height: int = REPORT_CHART_HEIGHT) -> None:
        self.width = width
        self.height = height
        self.image_count = 0
        self.elapsed_seconds = 0.0
        self._started_at = 0.0

    def __enter__(self) -> Self:
        self._started_at = time.perf_counter()
        logger.info(
            "report_chart_render_started engine=pillow width=%s height=%s",
            self.width,
            self.height,
        )
        return self

    def write(self, chart_key: str, figure: go.Figure, path: str | Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            image = _render_figure(figure, self.width, self.height)
            try:
                image.save(target, format="PNG", compress_level=6)
            finally:
                image.close()
        except Exception as exc:
            raise ReportChartRenderError(
                f"The report chart {chart_key!r} could not be generated."
            ) from exc
        if not _is_png(target):
            raise ReportChartRenderError("The report chart could not be generated.")
        self.image_count += 1
        return target

    def __exit__(self, *_exc_info: object) -> None:
        self.elapsed_seconds = time.perf_counter() - self._started_at
        logger.info(
            "report_chart_render_completed engine=pillow count=%s total_ms=%.2f",
            self.image_count,
            self.elapsed_seconds * 1000,
        )


def _render_figure(figure: go.Figure, width: int, height: int) -> Image.Image:
    image = Image.new("RGB", (width, height), _WHITE)
    draw = ImageDraw.Draw(image)
    plot_top = _draw_title(draw, figure, width)
    traces = [trace for trace in figure.data if getattr(trace, "visible", True) is not False]
    trace_types = {str(getattr(trace, "type", "")) for trace in traces}
    if "choropleth" in trace_types:
        _draw_map(draw, traces, (35, plot_top, width - 35, height - 38))
    elif "scatterpolar" in trace_types:
        _draw_radar(draw, traces, (55, plot_top, width - 55, height - 45))
    elif "bar" in trace_types:
        bars = [trace for trace in traces if getattr(trace, "type", "") == "bar"]
        if any(str(getattr(trace, "orientation", "") or "") == "h" for trace in bars):
            _draw_horizontal_bars(draw, figure, bars, (30, plot_top, width - 35, height - 45))
        else:
            _draw_vertical_bars(draw, figure, bars, (55, plot_top, width - 35, height - 55))
    elif trace_types & {"scatter", "scattergl"}:
        points = [
            trace for trace in traces if getattr(trace, "type", "") in {"scatter", "scattergl"}
        ]
        if _has_categorical_y(points):
            _draw_categorical_y_scatter(
                draw,
                figure,
                points,
                (30, plot_top, width - 35, height - 55),
            )
        else:
            _draw_scatter(draw, figure, points, (65, plot_top, width - 45, height - 55))
    else:
        raise ValueError(f"Unsupported report chart types: {sorted(trace_types)}")
    return image


def _draw_title(draw: ImageDraw.ImageDraw, figure: go.Figure, width: int) -> int:
    raw_title = str(getattr(getattr(figure.layout, "title", None), "text", "") or "")
    lines = _plain_title_lines(raw_title)
    title = lines[0] if lines else "RainbowLens DataHub"
    subtitle = " · ".join(line for line in lines[1:] if line)
    draw.text((36, 22), title, fill=_INK, font=_font(24, bold=True))
    if subtitle:
        wrapped = textwrap.wrap(subtitle, width=max(70, width // 11))[:2]
        for index, line in enumerate(wrapped):
            draw.text((36, 56 + index * 18), line, fill=_MUTED, font=_font(13))
        return 104 if len(wrapped) > 1 else 88
    return 70


def _plain_title_lines(value: str) -> list[str]:
    normalized = re.sub(r"(?i)<br\s*/?>", "\n", value)
    normalized = re.sub(r"<[^>]+>", "", normalized)
    return [html.unescape(line).strip() for line in normalized.splitlines() if line.strip()]


def _draw_horizontal_bars(
    draw: ImageDraw.ImageDraw,
    figure: go.Figure,
    traces: list[Any],
    bounds: tuple[int, int, int, int],
) -> None:
    first = next((trace for trace in traces if _values(trace.y)), traces[0])
    categories = [str(value) for value in _values(first.y)]
    categories.reverse()
    if not categories:
        raise ValueError("Horizontal bar chart has no categories")
    left, top, right, bottom = bounds
    label_width = min(285, max(145, max(map(len, categories)) * 7 + 18))
    plot_left = left + label_width
    legend_height = 35 if len(traces) > 1 else 0
    plot_bottom = bottom - legend_height
    plot_width = max(1, right - plot_left - 45)
    row_height = (plot_bottom - top) / len(categories)
    values_by_trace = [_category_values(trace, "y", "x") for trace in traces]
    totals = [sum(max(0.0, values.get(category, 0.0)) for values in values_by_trace) for category in categories]
    maximum = max(totals, default=1.0)
    axis_title = _axis_title(figure, "xaxis")
    scale_max = 100.0 if maximum <= 100 and (len(traces) > 1 or "%" in axis_title) else maximum * 1.12
    scale_max = max(scale_max, 1.0)
    _draw_horizontal_grid(draw, plot_left, top, plot_width, plot_bottom, scale_max)
    for row_index, category in enumerate(categories):
        center_y = top + (row_index + 0.5) * row_height
        label = _ellipsize(category, max(18, label_width // 7))
        label_box = draw.textbbox((0, 0), label, font=_font(13))
        draw.text(
            (plot_left - 10 - (label_box[2] - label_box[0]), center_y - 7),
            label,
            fill=_INK,
            font=_font(13),
        )
        cursor = float(plot_left)
        bar_height = max(5.0, min(row_height * 0.62, 28.0))
        total = 0.0
        for trace_index, (trace, values) in enumerate(zip(traces, values_by_trace, strict=True)):
            value = max(0.0, values.get(category, 0.0))
            width = plot_width * value / scale_max
            trace_categories = [str(item) for item in _values(getattr(trace, "y", None))]
            try:
                item_index = trace_categories.index(category)
            except ValueError:
                item_index = None
            draw.rectangle(
                (cursor, center_y - bar_height / 2, cursor + width, center_y + bar_height / 2),
                fill=_trace_color(trace, trace_index, item_index),
            )
            cursor += width
            total += value
        if len(traces) == 1:
            label_text = _trace_text_for_category(first, category) or _format_number(total)
            draw.text((min(cursor + 6, right - 55), center_y - 7), label_text, fill=_INK, font=_font(12))
    if len(traces) > 1:
        _draw_legend(draw, traces, plot_left, bottom - 22, right)


def _draw_horizontal_grid(
    draw: ImageDraw.ImageDraw,
    left: int,
    top: int,
    width: int,
    bottom: int,
    maximum: float,
) -> None:
    for step in range(5):
        value = maximum * step / 4
        x = left + width * step / 4
        draw.line((x, top, x, bottom), fill=_GRID, width=1)
        label = _format_number(value)
        draw.text((x - 10, bottom + 5), label, fill=_MUTED, font=_font(11))


def _draw_vertical_bars(
    draw: ImageDraw.ImageDraw,
    figure: go.Figure,
    traces: list[Any],
    bounds: tuple[int, int, int, int],
) -> None:
    first = traces[0]
    categories = [str(value) for value in _values(first.x)]
    if not categories:
        raise ValueError("Vertical bar chart has no categories")
    left, top, right, bottom = bounds
    plot_bottom = bottom - 38
    values = [_numeric_sequence(trace.y) for trace in traces]
    maximum = max((value for series in values for value in series), default=1.0)
    axis_title = _axis_title(figure, "yaxis")
    scale_max = 100.0 if maximum <= 100 and "%" in axis_title else max(1.0, maximum * 1.12)
    for step in range(5):
        y = plot_bottom - (plot_bottom - top) * step / 4
        draw.line((left, y, right, y), fill=_GRID, width=1)
        draw.text((8, y - 7), _format_number(scale_max * step / 4), fill=_MUTED, font=_font(11))
    group_width = (right - left) / len(categories)
    bar_width = max(3.0, group_width * 0.72 / max(1, len(traces)))
    for category_index, category in enumerate(categories):
        group_left = left + category_index * group_width + group_width * 0.14
        for trace_index, trace in enumerate(traces):
            series = values[trace_index]
            value = series[category_index] if category_index < len(series) else 0.0
            height = (plot_bottom - top) * value / scale_max
            x0 = group_left + trace_index * bar_width
            draw.rectangle(
                (x0, plot_bottom - height, x0 + bar_width - 1, plot_bottom),
                fill=_trace_color(trace, trace_index, category_index),
            )
        label = _ellipsize(category, max(5, int(group_width / 7)))
        box = draw.textbbox((0, 0), label, font=_font(10))
        draw.text(
            (left + (category_index + 0.5) * group_width - (box[2] - box[0]) / 2, bottom - 30),
            label,
            fill=_INK,
            font=_font(10),
        )
    if len(traces) > 1:
        _draw_legend(draw, traces, left, bottom - 6, right)


def _draw_scatter(
    draw: ImageDraw.ImageDraw,
    figure: go.Figure,
    traces: list[Any],
    bounds: tuple[int, int, int, int],
) -> None:
    series = [_xy_values(trace) for trace in traces]
    all_x = [point[0] for points in series for point in points]
    all_y = [point[1] for points in series for point in points]
    if not all_x or not all_y:
        raise ValueError("Scatter chart has no numeric points")
    left, top, right, bottom = bounds
    legend_width = 175 if len(traces) > 1 else 0
    plot_right = right - legend_width
    x_min, x_max = _axis_range(all_x)
    y_min, y_max = _axis_range(all_y, percentage=max(all_y) <= 100 and min(all_y) >= 0)
    for step in range(5):
        x = left + (plot_right - left) * step / 4
        y = bottom - (bottom - top) * step / 4
        draw.line((x, top, x, bottom), fill=_GRID, width=1)
        draw.line((left, y, plot_right, y), fill=_GRID, width=1)
        draw.text((x - 12, bottom + 6), _format_number(x_min + (x_max - x_min) * step / 4), fill=_MUTED, font=_font(10))
        draw.text((8, y - 7), _format_number(y_min + (y_max - y_min) * step / 4), fill=_MUTED, font=_font(10))
    for trace_index, (trace, points) in enumerate(zip(traces, series, strict=True)):
        color = _trace_color(trace, trace_index)
        pixels = [
            (
                left + (plot_right - left) * (x - x_min) / (x_max - x_min),
                bottom - (bottom - top) * (y - y_min) / (y_max - y_min),
            )
            for x, y in points
        ]
        mode = str(getattr(trace, "mode", "") or "")
        if "lines" in mode and len(pixels) > 1:
            draw.line(pixels, fill=color, width=3)
        for x, y in pixels:
            draw.ellipse((x - 4, y - 4, x + 4, y + 4), fill=color, outline=_WHITE, width=1)
        text_values = [str(value) for value in _values(getattr(trace, "text", None))]
        if len(traces) == 1 and len(text_values) == len(pixels) and len(pixels) <= 40:
            for (x, y), label in zip(pixels, text_values, strict=True):
                draw.text((x + 6, y - 7), _ellipsize(label, 18), fill=_INK, font=_font(10))
    if len(traces) > 1:
        _draw_vertical_legend(draw, traces, plot_right + 18, top, right)
    _draw_axis_titles(draw, figure, left, top, plot_right, bottom)


def _has_categorical_y(traces: list[Any]) -> bool:
    values = [value for trace in traces for value in _values(getattr(trace, "y", None))]
    return bool(values) and any(value is not None and _number(value) is None for value in values)


def _draw_categorical_y_scatter(
    draw: ImageDraw.ImageDraw,
    figure: go.Figure,
    traces: list[Any],
    bounds: tuple[int, int, int, int],
) -> None:
    categories = list(
        dict.fromkeys(
            str(value)
            for trace in traces
            for value in _values(getattr(trace, "y", None))
            if value is not None
        )
    )
    numeric_x = [
        number
        for trace in traces
        for value in _values(getattr(trace, "x", None))
        if (number := _number(value)) is not None
    ]
    if not categories or not numeric_x:
        raise ValueError("Categorical scatter chart has no points")
    left, top, right, bottom = bounds
    label_width = min(285, max(145, max(map(len, categories)) * 7 + 18))
    plot_left = left + label_width
    legend_height = 35 if sum(bool(getattr(trace, "showlegend", True)) for trace in traces) > 1 else 0
    plot_bottom = bottom - legend_height
    plot_width = max(1, right - plot_left)
    row_height = (plot_bottom - top) / len(categories)
    x_min, x_max = _axis_range(numeric_x)
    axis_range = _layout_range(figure, "xaxis")
    if axis_range is not None:
        x_min, x_max = axis_range

    def point(value: float, category: str) -> tuple[float, float]:
        row = categories.index(category)
        return (
            plot_left + plot_width * (value - x_min) / (x_max - x_min),
            top + (row + 0.5) * row_height,
        )

    for step in range(5):
        value = x_min + (x_max - x_min) * step / 4
        x = plot_left + plot_width * step / 4
        draw.line((x, top, x, plot_bottom), fill=_GRID, width=1)
        draw.text((x - 10, plot_bottom + 5), _format_number(value), fill=_MUTED, font=_font(10))
    for category in categories:
        _, y = point(x_min, category)
        label = _ellipsize(category, max(18, label_width // 7))
        box = draw.textbbox((0, 0), label, font=_font(12))
        draw.text((plot_left - 10 - box[2], y - 7), label, fill=_INK, font=_font(12))
    for trace_index, trace in enumerate(traces):
        color = _trace_color(trace, trace_index)
        mode = str(getattr(trace, "mode", "") or "")
        x_values = _values(getattr(trace, "x", None))
        y_values = _values(getattr(trace, "y", None))
        previous: tuple[float, float] | None = None
        for item_index, (raw_x, raw_y) in enumerate(zip(x_values, y_values, strict=False)):
            value = _number(raw_x)
            if value is None or raw_y is None or str(raw_y) not in categories:
                previous = None
                continue
            pixel = point(value, str(raw_y))
            if "lines" in mode and previous is not None:
                draw.line((*previous, *pixel), fill=color, width=3)
            if "markers" in mode:
                marker_color = _trace_color(trace, trace_index, item_index)
                x, y = pixel
                draw.ellipse((x - 5, y - 5, x + 5, y + 5), fill=marker_color, outline=_WHITE)
            previous = pixel
    legend_traces = [trace for trace in traces if bool(getattr(trace, "showlegend", True))]
    if legend_traces:
        _draw_legend(draw, legend_traces, plot_left, bottom - 18, right)
    _draw_axis_titles(draw, figure, plot_left, top, right, plot_bottom)


def _draw_radar(
    draw: ImageDraw.ImageDraw,
    traces: list[Any],
    bounds: tuple[int, int, int, int],
) -> None:
    first = traces[0]
    labels = [str(value) for value in _values(getattr(first, "theta", None))]
    if len(labels) < 3:
        raise ValueError("Radar chart has fewer than three dimensions")
    left, top, right, bottom = bounds
    center_x = (left + right) / 2
    center_y = (top + bottom) / 2
    radius = min(right - left, bottom - top) * 0.36
    for ring in range(1, 6):
        points = [
            _polar_point(center_x, center_y, radius * ring / 5, index, len(labels))
            for index in range(len(labels))
        ]
        draw.polygon(points, outline=_GRID)
    for index, label in enumerate(labels):
        x, y = _polar_point(center_x, center_y, radius, index, len(labels))
        draw.line((center_x, center_y, x, y), fill=_GRID, width=1)
        label_x, label_y = _polar_point(center_x, center_y, radius + 26, index, len(labels))
        draw.text((label_x - 35, label_y - 7), _ellipsize(label, 12), fill=_INK, font=_font(11))
    for trace_index, trace in enumerate(traces):
        values = _numeric_sequence(getattr(trace, "r", None))[: len(labels)]
        if not values:
            continue
        maximum = max(100.0, max(values))
        points = [
            _polar_point(center_x, center_y, radius * value / maximum, index, len(labels))
            for index, value in enumerate(values)
        ]
        color = _trace_color(trace, trace_index)
        draw.line([*points, points[0]], fill=color, width=3)
        for x, y in points:
            draw.ellipse((x - 4, y - 4, x + 4, y + 4), fill=color)


def _draw_map(
    draw: ImageDraw.ImageDraw,
    traces: list[Any],
    bounds: tuple[int, int, int, int],
) -> None:
    choropleth = next(trace for trace in traces if getattr(trace, "type", "") == "choropleth")
    geojson = getattr(choropleth, "geojson", None)
    if geojson is None:
        geojson = europe_geojson()
    if not isinstance(geojson, dict):
        raise TypeError("Map chart has invalid GeoJSON")
    locations = [str(value) for value in _values(choropleth.locations)]
    values = _values(choropleth.z)
    iso3_to_iso2 = {iso3: iso2 for iso2, iso3 in ISO2_TO_ISO3.items()}
    values_by_location = {
        iso3_to_iso2.get(location, location): _number(value)
        for location, value in zip(locations, values, strict=False)
    }
    features = [feature for feature in geojson.get("features", []) if isinstance(feature, dict)]
    coordinates = list(_all_feature_points(features))
    if not coordinates:
        raise ValueError("Map GeoJSON has no coordinates")
    left, top, right, bottom = bounds
    legend_width = 92
    map_right = right - legend_width
    lon_values = [point[0] for point in coordinates]
    lat_values = [point[1] for point in coordinates]
    mean_latitude = sum(lat_values) / len(lat_values)
    cosine = max(0.2, math.cos(math.radians(mean_latitude)))
    projected_x = [value * cosine for value in lon_values]
    minimum_x, maximum_x = min(projected_x), max(projected_x)
    minimum_y, maximum_y = min(lat_values), max(lat_values)
    scale = min(
        (map_right - left) / max(1e-6, maximum_x - minimum_x),
        (bottom - top) / max(1e-6, maximum_y - minimum_y),
    )
    x_offset = left + ((map_right - left) - (maximum_x - minimum_x) * scale) / 2
    y_offset = top + ((bottom - top) - (maximum_y - minimum_y) * scale) / 2

    def project(point: Sequence[float]) -> tuple[float, float]:
        return (
            x_offset + (float(point[0]) * cosine - minimum_x) * scale,
            y_offset + (maximum_y - float(point[1])) * scale,
        )

    draw.rectangle((left, top, map_right, bottom), fill="#EEF6FA")
    for feature in features:
        properties = feature.get("properties") or {}
        location = str(properties.get("country_code") or properties.get("iso3") or "")
        value = values_by_location.get(location)
        fill = _choropleth_color(choropleth, value)
        for polygon in _feature_polygons(feature):
            if not polygon:
                continue
            draw.polygon([project(point) for point in polygon[0]], fill=fill, outline="#64748B")
            for hole in polygon[1:]:
                draw.polygon([project(point) for point in hole], fill="#EEF6FA", outline="#64748B")
    for trace in traces:
        if getattr(trace, "type", "") != "scattergeo":
            continue
        for latitude, longitude in zip(
            _values(getattr(trace, "lat", None)),
            _values(getattr(trace, "lon", None)),
            strict=False,
        ):
            if _number(latitude) is None or _number(longitude) is None:
                continue
            x, y = project((float(longitude), float(latitude)))
            draw.ellipse((x - 6, y - 6, x + 6, y + 6), fill=_INK, outline=_WHITE, width=2)
    _draw_color_scale(draw, choropleth, map_right + 25, top + 40, bottom - 65)


def _draw_color_scale(draw: ImageDraw.ImageDraw, trace: Any, x: int, top: int, bottom: int) -> None:
    z_min = float(_number(getattr(trace, "zmin", None)) or 0.0)
    z_max = float(_number(getattr(trace, "zmax", None)) or 100.0)
    for y in range(top, bottom):
        ratio = 1 - (y - top) / max(1, bottom - top)
        value = z_min + (z_max - z_min) * ratio
        draw.line((x, y, x + 14, y), fill=_choropleth_color(trace, value))
    draw.rectangle((x, top, x + 14, bottom), outline=_MUTED)
    draw.text((x + 20, top - 6), _format_number(z_max), fill=_MUTED, font=_font(10))
    draw.text((x + 20, bottom - 8), _format_number(max(0.0, z_min)), fill=_MUTED, font=_font(10))
    draw.rectangle((x, bottom + 20, x + 12, bottom + 32), fill=_NO_DATA, outline=_MUTED)
    draw.text((x + 18, bottom + 18), "Sin datos", fill=_MUTED, font=_font(9))


def _draw_legend(
    draw: ImageDraw.ImageDraw,
    traces: list[Any],
    left: int,
    y: int,
    right: int,
) -> None:
    x = left
    for index, trace in enumerate(traces):
        label = str(getattr(trace, "name", "") or f"Serie {index + 1}")
        color = _trace_color(trace, index)
        draw.rectangle((x, y, x + 12, y + 12), fill=color)
        draw.text((x + 18, y - 2), _ellipsize(label, 22), fill=_INK, font=_font(11))
        x += min(180, max(95, len(label) * 7 + 35))
        if x > right - 100:
            break


def _draw_vertical_legend(
    draw: ImageDraw.ImageDraw,
    traces: list[Any],
    left: int,
    top: int,
    right: int,
) -> None:
    for index, trace in enumerate(traces[:16]):
        y = top + index * 24
        color = _trace_color(trace, index)
        label = str(getattr(trace, "name", "") or f"Serie {index + 1}")
        draw.line((left, y + 6, left + 18, y + 6), fill=color, width=3)
        draw.text((left + 24, y), _ellipsize(label, max(8, (right - left - 24) // 7)), fill=_INK, font=_font(10))


def _draw_axis_titles(
    draw: ImageDraw.ImageDraw,
    figure: go.Figure,
    left: int,
    top: int,
    right: int,
    bottom: int,
) -> None:
    x_title = _axis_title(figure, "xaxis")
    y_title = _axis_title(figure, "yaxis")
    if x_title:
        box = draw.textbbox((0, 0), x_title, font=_font(11))
        draw.text(((left + right - (box[2] - box[0])) / 2, bottom + 28), x_title, fill=_MUTED, font=_font(11))
    if y_title:
        draw.text((left, max(2, top - 18)), y_title, fill=_MUTED, font=_font(11))


def _axis_title(figure: go.Figure, name: str) -> str:
    axis = getattr(figure.layout, name, None)
    title = getattr(axis, "title", None)
    return str(getattr(title, "text", "") or "")


def _layout_range(figure: go.Figure, name: str) -> tuple[float, float] | None:
    values = _values(getattr(getattr(figure.layout, name, None), "range", None))
    if len(values) != 2:
        return None
    minimum, maximum = _number(values[0]), _number(values[1])
    if minimum is None or maximum is None or minimum == maximum:
        return None
    return minimum, maximum


def _xy_values(trace: Any) -> list[tuple[float, float]]:
    x_values = _values(getattr(trace, "x", None))
    y_values = _values(getattr(trace, "y", None))
    numeric_x = [_number(value) for value in x_values]
    if not all(value is not None for value in numeric_x):
        categories = {str(value): float(index) for index, value in enumerate(dict.fromkeys(x_values))}
        numeric_x = [categories[str(value)] for value in x_values]
    return [
        (float(x), float(y))
        for x, y in zip(numeric_x, (_number(value) for value in y_values), strict=False)
        if x is not None and y is not None
    ]


def _axis_range(values: list[float], *, percentage: bool = False) -> tuple[float, float]:
    if percentage:
        return 0.0, 100.0
    minimum, maximum = min(values), max(values)
    padding = (
        max(1.0, abs(minimum) * 0.1)
        if minimum == maximum
        else (maximum - minimum) * 0.08
    )
    return minimum - padding, maximum + padding


def _category_values(trace: Any, category_axis: str, value_axis: str) -> dict[str, float]:
    categories = _values(getattr(trace, category_axis, None))
    values = _values(getattr(trace, value_axis, None))
    return {
        str(category): float(number)
        for category, value in zip(categories, values, strict=False)
        if (number := _number(value)) is not None
    }


def _trace_text_for_category(trace: Any, category: str) -> str:
    categories = [str(value) for value in _values(getattr(trace, "y", None))]
    texts = [str(value) for value in _values(getattr(trace, "text", None))]
    try:
        index = categories.index(category)
    except ValueError:
        return ""
    return texts[index] if index < len(texts) else ""


def _trace_color(trace: Any, trace_index: int, item_index: int | None = None) -> str:
    marker = getattr(trace, "marker", None)
    line = getattr(trace, "line", None)
    raw = getattr(marker, "color", None)
    if raw is None or (isinstance(raw, str) and not raw):
        raw = getattr(line, "color", None)
    if not isinstance(raw, str) and raw is not None:
        colors = _values(raw)
        if item_index is not None:
            raw = colors[item_index] if item_index < len(colors) else None
        else:
            raw = colors[0] if colors else None
    palette = ("#2F6BDE", "#E3B505", "#F28C28", "#7A1F7A", "#2C7DA0", "#D45A7A")
    return _safe_color(raw, palette[trace_index % len(palette)])


def _choropleth_color(trace: Any, value: float | None) -> str:
    if value is None:
        return _NO_DATA
    z_min = float(_number(getattr(trace, "zmin", None)) or 0.0)
    z_max = float(_number(getattr(trace, "zmax", None)) or 100.0)
    ratio = min(1.0, max(0.0, (value - z_min) / max(1e-9, z_max - z_min)))
    raw_scale = _values(getattr(trace, "colorscale", None))
    scale: list[tuple[float, str]] = []
    for item in raw_scale:
        if isinstance(item, Sequence) and len(item) >= 2 and _number(item[0]) is not None:
            scale.append((float(item[0]), _safe_color(item[1], _BLUE)))
    if not scale:
        scale = [(0.0, "#A9C8F0"), (1.0, "#12376F")]
    scale.sort(key=lambda item: item[0])
    lower = scale[0]
    upper = scale[-1]
    for candidate in scale[1:]:
        if ratio <= candidate[0]:
            upper = candidate
            break
        lower = candidate
    width = max(1e-9, upper[0] - lower[0])
    local_ratio = min(1.0, max(0.0, (ratio - lower[0]) / width))
    return _mix_colors(lower[1], upper[1], local_ratio)


def _mix_colors(first: str, second: str, ratio: float) -> str:
    rgb_first = ImageColor.getrgb(first)
    rgb_second = ImageColor.getrgb(second)
    rgb = tuple(round(a + (b - a) * ratio) for a, b in zip(rgb_first, rgb_second, strict=True))
    return "#" + "".join(f"{channel:02X}" for channel in rgb)


def _safe_color(value: object, fallback: str) -> str:
    candidate = str(value or "").strip()
    if candidate.startswith("rgb("):
        parts = re.findall(r"[\d.]+", candidate)
        if len(parts) >= 3:
            return "#" + "".join(f"{max(0, min(255, round(float(part)))):02X}" for part in parts[:3])
    try:
        ImageColor.getrgb(candidate)
    except (TypeError, ValueError):
        return fallback
    return candidate


def _feature_polygons(feature: dict[str, Any]) -> Iterable[list[list[Sequence[float]]]]:
    geometry = feature.get("geometry") or {}
    coordinates = geometry.get("coordinates") or []
    if geometry.get("type") == "Polygon":
        yield coordinates
    elif geometry.get("type") == "MultiPolygon":
        yield from coordinates


def _all_feature_points(features: list[dict[str, Any]]) -> Iterable[Sequence[float]]:
    for feature in features:
        for polygon in _feature_polygons(feature):
            for ring in polygon:
                yield from ring


def _polar_point(
    center_x: float,
    center_y: float,
    radius: float,
    index: int,
    count: int,
) -> tuple[float, float]:
    angle = -math.pi / 2 + 2 * math.pi * index / count
    return center_x + math.cos(angle) * radius, center_y + math.sin(angle) * radius


def _numeric_sequence(values: object) -> list[float]:
    return [float(number) for value in _values(values) if (number := _number(value)) is not None]


def _values(value: object) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    try:
        return list(value)  # type: ignore[arg-type]
    except TypeError:
        return [value]


def _number(value: object) -> float | None:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _format_number(value: float) -> str:
    if abs(value - round(value)) < 0.01:
        return str(round(value))
    return f"{value:.1f}"


def _ellipsize(value: str, maximum: int) -> str:
    return value if len(value) <= maximum else value[: max(1, maximum - 1)].rstrip() + "…"


@lru_cache(maxsize=32)
def _font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    names = (
        ("DejaVuSans-Bold.ttf", "C:/Windows/Fonts/arialbd.ttf")
        if bold
        else ("DejaVuSans.ttf", "C:/Windows/Fonts/arial.ttf")
    )
    for name in names:
        try:
            return ImageFont.truetype(name, size=size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def _is_png(path: Path) -> bool:
    try:
        with path.open("rb") as stream:
            return stream.read(8) == b"\x89PNG\r\n\x1a\n"
    except OSError:
        return False
