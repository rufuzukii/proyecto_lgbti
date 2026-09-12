from __future__ import annotations

import math
from typing import Any


def safe_chart_float(value: Any) -> float | None:
    """Devuelve un número finito para gráficas y conserva la ausencia de datos."""
    try:
        numeric = float(value)
    except TypeError, ValueError, OverflowError:
        return None
    return numeric if math.isfinite(numeric) else None


def safe_chart_int(value: Any) -> int | None:
    number = safe_chart_float(value)
    if number is None or not number.is_integer():
        return None
    return int(number)
