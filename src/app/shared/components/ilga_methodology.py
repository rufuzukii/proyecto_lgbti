from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from dash import html
from dash.development.base_component import Component

from app.shared.data.ilga_metadata import normalized_ilga_source_scale
from app.web.i18n import ui_text


def build_ilga_normalization_note(
    normalization: Any,
    *,
    language: str = "es",
    class_name: str = "",
) -> Component | None:
    metadata = normalized_ilga_source_scale(normalization)
    if metadata is None:
        return None
    return _note_component([metadata], language=language, class_name=class_name)


def build_ilga_series_normalization_note(
    points: Iterable[Any],
    *,
    language: str = "es",
    class_name: str = "",
) -> Component | None:
    normalized_by_year: dict[int, dict[str, Any]] = {}
    for point in points:
        if not bool(_point_value(point, "normalization_applied", False)):
            continue
        year = _point_value(point, "year")
        if not isinstance(year, int):
            continue
        normalized_by_year[year] = {
            "applied": True,
            "method": str(_point_value(point, "normalization_method", "")),
            "original_min": _point_value(point, "original_scale_min"),
            "original_max": _point_value(point, "original_scale_max"),
            "target_min": _point_value(point, "target_scale_min"),
            "target_max": _point_value(point, "target_scale_max"),
            "year": year,
        }
    if not normalized_by_year:
        return None
    return _note_component(
        [normalized_by_year[year] for year in sorted(normalized_by_year)],
        language=language,
        class_name=class_name,
    )


def _note_component(
    metadata_items: list[dict[str, Any]],
    *,
    language: str,
    class_name: str,
) -> Component:
    scales = []
    for metadata in metadata_items:
        year = metadata.get("year")
        prefix = f"{year}: " if year is not None and len(metadata_items) > 1 else ""
        scales.append(
            html.Li(
                prefix
                + ui_text("ilga_normalization_note_scale", language).format(
                    original_min=_display_number(metadata["original_min"]),
                    original_max=_display_number(metadata["original_max"]),
                )
            )
        )
    classes = " ".join(filter(None, ("ilga-methodology-note", class_name)))
    return html.Aside(
        [
            html.Strong(ui_text("ilga_normalization_note_title", language)),
            html.P(
                ui_text(
                    "ilga_normalization_series_note_body"
                    if len(metadata_items) > 1
                    else "ilga_normalization_note_body",
                    language,
                )
            ),
            html.Ul(scales),
            html.P(
                ui_text("ilga_normalization_note_caution", language),
                className="ilga-methodology-note__caution",
            ),
        ],
        className=classes,
        role="note",
    )


def _display_number(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "?"
    return str(int(number)) if number.is_integer() else str(number)


def _point_value(point: Any, key: str, default: Any = None) -> Any:
    if isinstance(point, Mapping):
        return point.get(key, default)
    return getattr(point, key, default)
