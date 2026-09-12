from __future__ import annotations

import math
from collections import Counter
from collections.abc import Iterable
from decimal import Decimal, InvalidOperation
from typing import Any

MISSING_PERCENTAGE_COLOR = "#9ca3af"
MISSING_PERCENTAGE_STRINGS = frozenset({"", "n/a", "na", "null", "none", "nan"})


def normalize_percentage(
    value: Any,
    *,
    logger: Any | None = None,
    context: dict[str, Any] | None = None,
) -> float | None:
    """Normaliza puntos porcentuales FRA e ILGA almacenados en una escala de 0 a 100.

    Un decimal como ``0.42`` sigue siendo ``0.42`` puntos porcentuales. No se interpreta como
    proporción porque los campos persistidos ya representan porcentajes.
    """
    if is_missing_percentage_value(value):
        return None
    if isinstance(value, bool):
        _warn_invalid_percentage(value, logger=logger, context=context)
        return None
    if isinstance(value, (dict, list, set, tuple, bytes, bytearray)):
        _warn_invalid_percentage(value, logger=logger, context=context)
        return None

    clean_value: Any = value
    if isinstance(value, str):
        clean_value = value.strip()
        if clean_value.endswith("%"):
            clean_value = clean_value[:-1].strip()
        if "%" in clean_value or ("," in clean_value and "." in clean_value):
            _warn_invalid_percentage(value, logger=logger, context=context)
            return None
        clean_value = clean_value.replace(",", ".")

    try:
        numeric_value = float(clean_value)
    except TypeError, ValueError:
        _warn_invalid_percentage(value, logger=logger, context=context)
        return None

    if math.isnan(numeric_value):
        return None
    if not math.isfinite(numeric_value) or not 0 <= numeric_value <= 100:
        _warn_invalid_percentage(value, logger=logger, context=context)
        return None
    return numeric_value


def coerce_percentage(
    value: Any,
    *,
    logger: Any | None = None,
    context: dict[str, Any] | None = None,
) -> float | None:
    """Alias de compatibilidad para el normalizador central de porcentajes."""
    return normalize_percentage(value, logger=logger, context=context)


def normalize_percentage_values(
    values: Iterable[Any],
    *,
    logger: Any | None = None,
    context: dict[str, Any] | None = None,
) -> list[float | None]:
    """Normaliza un lote y emite como máximo un aviso contextual."""
    normalized: list[float | None] = []
    invalid_values: Counter[str] = Counter()
    for value in values:
        parsed = normalize_percentage(value)
        normalized.append(parsed)
        if parsed is None and not is_missing_percentage_value(value):
            invalid_values[_display_invalid_percentage(value)] += 1

    if logger is not None and invalid_values:
        count = sum(invalid_values.values())
        values_summary = [
            f"{value} ({occurrences})" if occurrences > 1 else value
            for value, occurrences in invalid_values.most_common(12)
        ]
        context_text = _format_log_context(context)
        message = f"invalid_percentage_values count={count} values={values_summary!r}"
        if context_text:
            message = f"{message} {context_text}"
        extra = {
            "invalid_percentage_count": count,
            "invalid_percentage_values": values_summary,
        }
        if context:
            extra.update(context)
        logger.warning(message, extra=extra)
    return normalized


def is_missing_percentage_value(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip().casefold() in MISSING_PERCENTAGE_STRINGS
    if isinstance(value, (bool, dict, list, set, tuple, bytes, bytearray)):
        return False
    if type(value).__name__ == "NAType" and type(value).__module__.startswith("pandas"):
        return True
    try:
        return math.isnan(float(value))
    except TypeError, ValueError, OverflowError:
        return False


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
    normalized_values = normalize_percentage_values(values, logger=logger, context=context)
    for index, parsed_value in enumerate(normalized_values):
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
    exact_values = [(index, max(0.0, value) / total * 100.0) for index, value in values]
    allocations = {index: math.floor(exact_value) for index, exact_value in exact_values}
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
    normalized = normalize_percentage(value)
    if normalized is None:
        return None

    try:
        decimal_value = Decimal(str(normalized))
    except InvalidOperation, ValueError:
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
    display_value = _display_invalid_percentage(value)
    extra = {"invalid_percentage": display_value}
    if context:
        extra.update(context)
    context_text = _format_log_context(context)
    message = f"invalid_percentage_value value={display_value}"
    if context_text:
        message = f"{message} {context_text}"
    logger.warning(message, extra=extra)


def _display_invalid_percentage(value: Any) -> str:
    return repr(value).replace("\r", "\\r").replace("\n", "\\n")[:160]


def _format_log_context(context: dict[str, Any] | None) -> str:
    clean_context = context or {}
    return " ".join(
        f"{key}={clean_context[key]!r}"
        for key in sorted(clean_context)
        if clean_context[key] is not None
    )
