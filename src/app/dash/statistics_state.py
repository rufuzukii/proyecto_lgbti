from __future__ import annotations

from enum import StrEnum
from typing import Any


class StatisticsViewState(StrEnum):
    INITIAL = "initial"
    LOADING = "loading"
    READY = "ready"
    NO_DATA = "no_data"
    ERROR = "error"


def resolve_statistics_view_state(payload: dict[str, Any] | None) -> StatisticsViewState:
    """Resolve the persistent dashboard state from one completed query payload.

    ``LOADING`` is transient and is owned by ``dcc.Loading`` while a callback is
    running. Completed payloads resolve to one of the other four explicit states.
    """
    if not payload:
        return StatisticsViewState.INITIAL
    status = str(payload.get("status") or "").strip().casefold()
    if status == "ok":
        return StatisticsViewState.READY
    if status == "error":
        return StatisticsViewState.ERROR
    return StatisticsViewState.NO_DATA
