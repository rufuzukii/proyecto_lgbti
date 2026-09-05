from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from app.shared.data.normalization import normalize_country_code, normalize_text_key

RANKING_PAGE_SIZE = 5


@dataclass(frozen=True, slots=True)
class RankingPage:
    """A clamped page over an already-loaded, deterministically sorted ranking."""

    rows: list[dict[str, Any]]
    page: int
    page_count: int
    total_items: int
    start: int
    end: int

    @property
    def has_previous(self) -> bool:
        return self.page > 0

    @property
    def has_next(self) -> bool:
        return self.page + 1 < self.page_count


def paginate_ranking(
    rows: list[dict[str, Any]],
    page: int | None,
    *,
    selected_countries: list[str] | None = None,
    page_size: int = RANKING_PAGE_SIZE,
) -> RankingPage:
    """Sort and paginate ranking rows without issuing another data query.

    Numeric values are ordered from highest to lowest. Missing values remain
    missing, are placed after numeric rows and never become a synthetic zero.
    """

    if page_size <= 0:
        raise ValueError("page_size_must_be_positive")

    # Positions belong to the complete ranking, not to an individual page or
    # to the current selection.  Attach them before filtering so pagination
    # cannot reset positions or split ties incorrectly.
    ordered = _with_global_positions(sorted(rows, key=_ranking_sort_key))
    selected = _selected_country_keys(selected_countries)
    candidates = [row for row in ordered if not selected or _row_country_key(row) in selected]
    total_items = len(candidates)
    page_count = max(1, math.ceil(total_items / page_size))
    requested_page = max(0, int(page or 0))
    current_page = min(requested_page, page_count - 1)
    offset = current_page * page_size
    page_rows = candidates[offset : offset + page_size]
    start = offset + 1 if page_rows else 0
    end = offset + len(page_rows)
    return RankingPage(
        rows=page_rows,
        page=current_page,
        page_count=page_count,
        total_items=total_items,
        start=start,
        end=end,
    )


def _with_global_positions(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    positioned: list[dict[str, Any]] = []
    previous_value: float | None = None
    previous_position: int | None = None
    for index, source_row in enumerate(rows, start=1):
        row = dict(source_row)
        value = _numeric_value(row.get("value"))
        if value is None:
            position = None
        elif previous_position is not None and value == previous_value:
            position = previous_position
        else:
            position = index
        row["position"] = position
        positioned.append(row)
        if value is not None:
            previous_value = value
            previous_position = position
    return positioned


def _ranking_sort_key(row: dict[str, Any]) -> tuple[int, float, str]:
    value = _numeric_value(row.get("value"))
    country = normalize_text_key(row.get("country") or row.get("iso") or "")
    if value is None:
        return (1, 0.0, country)
    return (0, -value, country)


def _numeric_value(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str) and not value.strip():
        return None
    try:
        numeric = float(value)
    except TypeError, ValueError:
        return None
    return numeric if math.isfinite(numeric) else None


def _selected_country_keys(values: list[str] | None) -> set[str]:
    keys: set[str] = set()
    for value in values or []:
        country_code = normalize_country_code(value)
        keys.add(country_code or normalize_text_key(value))
    return {key for key in keys if key}


def _row_country_key(row: dict[str, Any]) -> str:
    country_code = normalize_country_code(row.get("iso"))
    return country_code or normalize_text_key(row.get("country") or "")
