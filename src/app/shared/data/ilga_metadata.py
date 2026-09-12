from __future__ import annotations

from copy import deepcopy
from typing import Any

_NORMALIZED_SOURCE_SCALES: dict[int, dict[str, Any]] = {
    2011: {
        "applied": True,
        "method": "linear_min_max",
        "original_min": -7,
        "original_max": 17,
        "target_min": 0,
        "target_max": 100,
    },
    2012: {
        "applied": True,
        "method": "linear_min_max",
        "original_min": -12,
        "original_max": 30,
        "target_min": 0,
        "target_max": 100,
    },
}


def ilga_normalization_metadata(year: int) -> dict[str, Any]:
    """Devuelve los metadatos anuales de la escala ILGA sin transformar puntuaciones."""
    return deepcopy(_NORMALIZED_SOURCE_SCALES.get(int(year), {"applied": False}))


def normalized_ilga_source_scale(value: Any) -> dict[str, Any] | None:
    """Devuelve metadatos validados de normalización de escala, o ``None`` si no corresponde."""
    if not isinstance(value, dict) or value.get("applied") is not True:
        return None
    required = (
        "method",
        "original_min",
        "original_max",
        "target_min",
        "target_max",
    )
    if any(key not in value for key in required):
        return None
    return {"applied": True, **{key: value[key] for key in required}}
