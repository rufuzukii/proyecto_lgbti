from __future__ import annotations

from decimal import Decimal, InvalidOperation
import math
from typing import Any


MISSING_PERCENTAGE_COLOR = "#9ca3af"


def coerce_percentage(
    value: Any,
    *,
    logger: Any | None = None,
    context: dict[str, Any] | None = None,
) -> float | None:
    if value is None:
        return None
    try:
        if value != value:
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, bool):
        _warn_invalid_percentage(value, logger=logger, context=context)
        return None

    clean_value: Any = value
    if isinstance(value, str):
        clean_value = value.strip()
        if not clean_value:
            return None
        clean_value = clean_value.replace("%", "").replace(",", ".").strip()

    try:
        numeric_value = float(clean_value)
    except (TypeError, ValueError):
        _warn_invalid_percentage(value, logger=logger, context=context)
        return None

    if not math.isfinite(numeric_value):
        _warn_invalid_percentage(value, logger=logger, context=context)
        return None
    return numeric_value


def format_percentage(value: Any) -> str | None:
    decimal_value = _percentage_decimal(value)
    if decimal_value is None:
        return None
    if decimal_value == 0:
        return "0%"
    if decimal_value == decimal_value.to_integral_value():
        return f"{int(decimal_value)}%"

    text = format(decimal_value.normalize(), "f").rstrip("0").rstrip(".")
    return f"{text}%"


def prepare_percentage_display_values(
    values: list[Any],
    *,
    normalize_when_total_is_not_100: bool = False,
    logger: Any | None = None,
    context: dict[str, Any] | None = None,
) -> tuple[list[float | int | None], bool]:
    parsed: list[tuple[int, float]] = []
    output: list[float | int | None] = [None] * len(values)
    for index, value in enumerate(values):
        parsed_value = coerce_percentage(value, logger=logger, context=context)
        if parsed_value is None:
            continue
        parsed.append((index, parsed_value))
        output[index] = parsed_value

    if not normalize_when_total_is_not_100 or not parsed:
        return output, False

    total = math.fsum(value for _index, value in parsed)
    if math.isclose(total, 100.0, rel_tol=0.0, abs_tol=1e-9):
        return output, False
    normalization_total = math.fsum(max(0.0, value) for _index, value in parsed)
    if normalization_total <= 0:
        if logger is not None:
            extra = {"total": total}
            if context:
                extra.update(context)
            logger.warning("percentage_normalization_skipped_non_positive_total", extra=extra)
        return output, False

    normalized = _largest_remainder_percentages(parsed, normalization_total)
    normalized_output: list[float | int | None] = [None] * len(values)
    for index, percentage in normalized.items():
        normalized_output[index] = percentage
    return normalized_output, True


def _largest_remainder_percentages(values: list[tuple[int, float]], total: float) -> dict[int, int]:
    exact_values = [
        (index, max(0.0, value) / total * 100.0)
        for index, value in values
    ]
    allocations = {
        index: int(math.floor(exact_value))
        for index, exact_value in exact_values
    }
    missing_points = 100 - sum(allocations.values())
    if missing_points <= 0:
        return allocations

    remainders = sorted(
        (
            (exact_value - math.floor(exact_value), exact_value, index)
            for index, exact_value in exact_values
        ),
        reverse=True,
    )
    for _remainder, _exact_value, index in remainders[:missing_points]:
        allocations[index] += 1
    return allocations


def _percentage_decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
        value = value.replace("%", "").replace(",", ".").strip()

    try:
        decimal_value = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not decimal_value.is_finite():
        return None
    return decimal_value


def _warn_invalid_percentage(
    value: Any,
    *,
    logger: Any | None,
    context: dict[str, Any] | None,
) -> None:
    if logger is None:
        return
    extra = {"invalid_percentage": repr(value)}
    if context:
        extra.update(context)
    logger.warning("invalid_percentage_value", extra=extra)
