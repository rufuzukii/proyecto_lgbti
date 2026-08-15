from __future__ import annotations

from enum import StrEnum
from typing import Any


class StatisticsViewState(StrEnum):
    INITIAL = "initial"
    LOADING_INDICATORS = "loading_indicators"
    LOADING_STATISTICS = "loading_statistics"
    SURVEY_EMPTY = "survey_empty"
    READY = "ready"
    NO_DATA = "no_data"
    ERROR = "error"


def resolve_statistics_view_state(
    payload: dict[str, Any] | None,
    ready_payload: dict[str, Any] | None = None,
    active_payload: dict[str, Any] | None = None,
) -> StatisticsViewState:
    """Resolve the persistent dashboard state from one completed query payload.

    A successful query remains in ``LOADING_STATISTICS`` until the render callback
    confirms that every dashboard output for the same query token is ready.
    """
    active_phase = str((active_payload or {}).get("phase") or "").strip().casefold()
    if active_phase == StatisticsViewState.SURVEY_EMPTY:
        return StatisticsViewState.SURVEY_EMPTY
    if not payload:
        if active_phase == StatisticsViewState.LOADING_INDICATORS:
            return StatisticsViewState.LOADING_INDICATORS
        if active_phase == StatisticsViewState.LOADING_STATISTICS:
            return StatisticsViewState.LOADING_STATISTICS
        return StatisticsViewState.INITIAL
    query_token = str(payload.get("query_token") or "").strip()
    active_token = str((active_payload or {}).get("query_token") or "").strip()
    if query_token and active_token and query_token != active_token:
        return StatisticsViewState.LOADING_STATISTICS
    status = str(payload.get("status") or "").strip().casefold()
    if status == StatisticsViewState.LOADING_INDICATORS:
        return StatisticsViewState.LOADING_INDICATORS
    if status == StatisticsViewState.LOADING_STATISTICS:
        return StatisticsViewState.LOADING_STATISTICS
    if status == "ok":
        ready_token = str((ready_payload or {}).get("query_token") or "").strip()
        if query_token and query_token != ready_token:
            return StatisticsViewState.LOADING_STATISTICS
        return StatisticsViewState.READY
    if status == "error":
        return StatisticsViewState.ERROR
    return StatisticsViewState.NO_DATA
