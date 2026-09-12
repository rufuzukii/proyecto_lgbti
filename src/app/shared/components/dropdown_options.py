from __future__ import annotations

import json
import logging
import math
from collections.abc import Iterable, Mapping
from typing import Any

logger = logging.getLogger(__name__)

DropdownValue = str | int | float | bool


def build_dropdown_options(
    items: Iterable[Mapping[str, Any]],
    *,
    context: str = "dropdown",
) -> list[dict[str, DropdownValue]]:
    """Devuelve opciones Dash estables con etiquetas y valores primitivos.

    Descarta las filas inválidas sin inventar textos alternativos. Prevalece la primera
    aparición de cada valor para mantener actualizaciones deterministas.
    """
    options: list[dict[str, DropdownValue]] = []
    seen: set[str] = set()
    discarded: dict[str, int] = {}

    for item in items:
        if not isinstance(item, Mapping):
            _increment(discarded, "not_mapping")
            continue
        label = _option_label(item.get("label"))
        value = _option_value(item.get("value"))
        if label is None:
            _increment(discarded, "invalid_label")
            continue
        if value is None:
            _increment(discarded, "invalid_value")
            continue

        marker = json.dumps(
            [type(value).__name__, value],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        if marker in seen:
            _increment(discarded, "duplicate_value")
            continue
        seen.add(marker)

        option: dict[str, DropdownValue] = {"label": label, "value": value}
        if isinstance(item.get("disabled"), bool):
            option["disabled"] = item["disabled"]
        title = _option_label(item.get("title"))
        if title is not None:
            option["title"] = title
        search = _option_label(item.get("search"))
        if search is not None:
            option["search"] = search
        options.append(option)

    if discarded:
        logger.warning(
            "dropdown_options_discarded context=%s reasons=%s",
            context,
            ",".join(f"{reason}:{count}" for reason, count in sorted(discarded.items())),
        )
    return options


def option_value_or_none(
    options: Iterable[Mapping[str, Any]],
    current: Any,
) -> DropdownValue | None:
    """Conserva la selección solo si su valor primitivo existe en las nuevas opciones."""
    current_value = _option_value(current)
    if current_value is None:
        return None
    return next(
        (
            value
            for option in options
            if (value := _option_value(option.get("value"))) == current_value
        ),
        None,
    )


def _option_label(value: Any) -> str | None:
    if isinstance(value, bool):
        return str(value)
    if not isinstance(value, (str, int, float)):
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    clean = str(value).strip()
    return clean or None


def _option_value(value: Any) -> DropdownValue | None:
    if not isinstance(value, (str, int, float, bool)):
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
    return value


def _increment(counts: dict[str, int], key: str) -> None:
    counts[key] = counts.get(key, 0) + 1
