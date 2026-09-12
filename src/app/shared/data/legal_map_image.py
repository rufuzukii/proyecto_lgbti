"""Dibuja la exportación combinada del mapa legal sin navegador ni servicios externos."""

from __future__ import annotations

import html
import re
from contextlib import closing
from functools import lru_cache
from io import BytesIO
from typing import Any, cast

import geopandas as gpd
import plotly.graph_objects as go
from PIL import Image, ImageColor, ImageDraw, ImageFont

from app.shared.data.geography_service import europe_geojson
from app.shared.data.percentage_display import coerce_percentage


def render_legal_map_png(figure: go.Figure, *, width: int, height: int, scale: float) -> bytes:
    """Representa las trazas choropleth/table de la figura legal como un PNG en memoria."""
    background = str(figure.layout.paper_bgcolor or "#ffffff")
    with closing(
        Image.new("RGB", (round(width * scale), round(height * scale)), background)
    ) as img:
        canvas = _Canvas(img, scale)
        ink = str(figure.layout.font.color or "#252a31")
        traces = [trace for trace in cast(Any, figure).data if trace.visible is not False]
        if any(trace.type not in {"choropleth", "table"} for trace in traces):
            raise ValueError("The legal image supports choropleth and table traces only")
        maps = [trace for trace in traces if trace.type == "choropleth"]
        table = next((trace for trace in traces if trace.type == "table"), None)
        english = table is not None and _plain_text(table.header.values[1]) == "Country"
        no_data = "No data" if english else "Sin datos"

        title = _plain_text(figure.layout.title.text or "RainbowLens DataHub").splitlines()
        canvas.text((45, 28), title[0], ink, 26, bold=True, max_width=width - 90)
        if len(title) > 1:
            canvas.text((45, 68), " · ".join(title[1:]), ink, 18, max_width=width - 90)

        table_left = width * 0.72
        if maps:
            _draw_map(canvas, figure, maps, (110, 150, table_left - 45, height - 120))
            trace = next((trace for trace in maps if trace.showscale is not False), None)
            if trace is not None:
                _draw_scale(
                    canvas,
                    trace,
                    ink,
                    height,
                    no_data,
                    str(figure.layout.geo.landcolor or "#edf1f4"),
                )
        else:
            canvas.text((width * 0.35, height * 0.48), no_data, ink, 20, anchor="mt")
        if table is not None:
            _draw_table(canvas, table, (table_left, 150, width - 42, height - 90))

        for annotation in figure.layout.annotations or ():
            text = _plain_text(annotation.text or "")
            color = str(annotation.font.color or ink)
            if float(annotation.y or 0) > 1:
                canvas.text(
                    (table_left, 112), text, color, 18, bold=True, max_width=width - table_left - 42
                )
            elif float(annotation.y or 0) < 0:
                canvas.text((45, height - 45), text, color, 12, max_width=width - 90)

        output = BytesIO()
        img.save(output, format="PNG")
        return output.getvalue()


class _Canvas:
    def __init__(self, image: Image.Image, scale: float) -> None:
        self.image = image
        self.scale = scale
        self.draw = ImageDraw.Draw(image)

    def rectangle(self, bounds: tuple[float, float, float, float], color: str) -> None:
        self.draw.rectangle(tuple(value * self.scale for value in bounds), fill=color)

    def text(
        self,
        position: tuple[float, float],
        value: object,
        color: str,
        size: float,
        *,
        bold: bool = False,
        anchor: str = "lt",
        max_width: float | None = None,
    ) -> None:
        text = _plain_text(value)
        pixel_size = max(8, round(size * self.scale))
        font = _font(pixel_size, bold)
        if max_width is not None:
            limit = max_width * self.scale
            while (
                pixel_size > round(8 * self.scale) and self.draw.textlength(text, font=font) > limit
            ):
                pixel_size -= 1
                font = _font(pixel_size, bold)
            if self.draw.textlength(text, font=font) > limit:
                while text and self.draw.textlength(text + "…", font=font) > limit:
                    text = text[:-1]
                text += "…"
        self.draw.text(
            (position[0] * self.scale, position[1] * self.scale),
            text,
            fill=color,
            font=font,
            anchor=anchor,
        )


def _draw_map(
    canvas: _Canvas,
    figure: go.Figure,
    traces: list[Any],
    bounds: tuple[float, float, float, float],
) -> None:
    # La proyección Natural Earth coincide con la utilizada por el mapa de inicio.
    geojson = traces[0].geojson if traces[0].geojson is not None else europe_geojson()
    frame = gpd.GeoDataFrame.from_features(geojson, crs="EPSG:4326").to_crs(
        "+proj=natearth +lon_0=18 +datum=WGS84 +units=m +no_defs"
    )
    if frame.empty or frame.geometry.is_empty.any() or not frame.geometry.is_valid.all():
        raise ValueError("The legal map has missing or invalid country geometries")
    min_x, min_y, max_x, max_y = frame.total_bounds
    left, top, right, bottom = bounds
    factor = min((right - left) / (max_x - min_x), (bottom - top) / (max_y - min_y))
    offset_x = left + (right - left - (max_x - min_x) * factor) / 2
    offset_y = top + (bottom - top - (max_y - min_y) * factor) / 2
    ocean = str(figure.layout.geo.oceancolor or "#dcebf2")
    land = str(figure.layout.geo.landcolor or "#edf1f4")
    canvas.rectangle(bounds, ocean)
    colors_by_location = {
        str(location): _map_color(trace, value, land)
        for trace in traces
        for location, value in zip(trace.locations, trace.z, strict=True)
    }
    border = str(traces[0].marker.line.color or "#ffffff")

    for _, row in frame.iterrows():
        color = colors_by_location.get(str(row.get("country_code")))
        if color is None:
            color = colors_by_location.get(str(row.get("iso3")), land)
        geometry = row.geometry
        polygons = [geometry] if geometry.geom_type == "Polygon" else list(geometry.geoms)
        outlines = []
        # Una máscara conserva los huecos sin tapar los países dibujados dentro de ellos.
        with closing(Image.new("L", canvas.image.size, 0)) as mask:
            mask_draw = ImageDraw.Draw(mask)
            for polygon in polygons:
                for index, ring in enumerate([polygon.exterior, *polygon.interiors]):
                    points = [
                        (
                            (offset_x + (x - min_x) * factor) * canvas.scale,
                            (offset_y + (max_y - y) * factor) * canvas.scale,
                        )
                        for x, y in ring.coords
                    ]
                    mask_draw.polygon(points, fill=255 if index == 0 else 0)
                    outlines.append(points)
            canvas.image.paste(color, (0, 0), mask)
        for points in outlines:
            canvas.draw.line(points, fill=border, width=max(1, round(canvas.scale)))


def _draw_scale(
    canvas: _Canvas, trace: Any, ink: str, height: int, no_data: str, land: str
) -> None:
    top, bottom = 235, height - 270
    minimum = float(trace.zmin if trace.zmin is not None else 0)
    maximum = float(trace.zmax if trace.zmax is not None else 100)
    for y in range(top, bottom):
        value = maximum - (maximum - minimum) * (y - top) / (bottom - top - 1)
        canvas.rectangle((45, y, 61, y + 1), _map_color(trace, value, land))
    for fraction in (0, 0.25, 0.5, 0.75, 1):
        value = maximum - (maximum - minimum) * fraction
        canvas.text((68, top + (bottom - top) * fraction - 7), f"{value:g}%", ink, 12)
    canvas.rectangle((45, bottom + 38, 61, bottom + 54), land)
    canvas.text((45, bottom + 64), no_data, ink, 12)


def _map_color(trace: Any, value: object, no_data: str) -> str:
    number = coerce_percentage(value)
    if number is None:
        return no_data
    minimum = float(trace.zmin if trace.zmin is not None else 0)
    maximum = float(trace.zmax if trace.zmax is not None else 100)
    ratio = min(1.0, max(0.0, (number - minimum) / max(1e-9, maximum - minimum)))
    if trace.reversescale:
        ratio = 1 - ratio
    stops = list(trace.colorscale or ((0, "#d73027"), (1, "#177245")))
    first = stops[0]
    if ratio <= first[0]:
        return first[1]
    for second in stops[1:]:
        if ratio <= second[0]:
            weight = (ratio - first[0]) / max(1e-9, second[0] - first[0])
            start, end = ImageColor.getrgb(first[1]), ImageColor.getrgb(second[1])
            return "#" + "".join(
                f"{round(a + (b - a) * weight):02x}" for a, b in zip(start, end, strict=True)
            )
        first = second
    return stops[-1][1]


def _draw_table(canvas: _Canvas, table: Any, bounds: tuple[float, float, float, float]) -> None:
    left, top, right, bottom = bounds
    columns = list(table.cells.values)
    if len(columns) != 3 or len({len(column) for column in columns}) != 1:
        raise ValueError("The legal ranking must have three equally sized columns")
    header_height = 34
    row_height = min(26, (bottom - top - header_height) / max(1, len(columns[0])))
    size = min(14, row_height * 0.65)
    line = str(table.cells.line.color or "#d7e2dc")
    text = str(table.cells.font.color or "#252a31")
    canvas.rectangle((left, top, right, top + header_height), str(table.header.fill.color))
    for index, value in enumerate(table.header.values):
        positions = (left + 35, left + 50, right - 10)
        canvas.text(
            (positions[index], top + 9),
            value,
            str(table.header.font.color),
            13,
            bold=True,
            anchor="lt" if index == 1 else "rt",
        )
    for index, row in enumerate(zip(*columns, strict=True)):
        y = top + header_height + index * row_height
        canvas.rectangle((left, y, right, y + row_height), str(table.cells.fill.color))
        canvas.rectangle((left, y + row_height - 0.5, right, y + row_height), line)
        canvas.text((left + 35, y + 3), row[0], text, size, anchor="rt")
        canvas.text((left + 50, y + 3), row[1], text, size, max_width=right - left - 145)
        canvas.text((right - 10, y + 3), row[2], text, size, anchor="rt", max_width=80)


def _plain_text(value: object) -> str:
    text = re.sub(r"(?i)<br\s*/?>", "\n", str(value))
    return html.unescape(re.sub(r"<[^>]+>", "", text)).strip()


@lru_cache(maxsize=64)
def _font(size: int, bold: bool) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    names = ("DejaVuSans-Bold.ttf", "arialbd.ttf") if bold else ("DejaVuSans.ttf", "arial.ttf")
    for name in names:
        try:
            return ImageFont.truetype(name, size=size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)
