from __future__ import annotations

from typing import Any

import pandas as pd


def safe_chart_float(value: Any) -> float | None:
    """Return a finite chart number while preserving missing values as missing."""
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if pd.notna(numeric) else None


def safe_chart_int(value: Any) -> int | None:
    number = safe_chart_float(value)
    if number is None or not number.is_integer():
        return None
    return int(number)
