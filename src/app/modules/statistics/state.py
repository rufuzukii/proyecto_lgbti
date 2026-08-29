from __future__ import annotations

from enum import StrEnum
from typing import Any


class StatisticsViewState(StrEnum):
    INITIAL = "initial"
    LOADING_INDICATORS = "loading_indicators"
    AWAITING_INDICATOR = "awaiting_indicator"
    LOADING_STATISTICS = "loading_statistics"
    SURVEY_EMPTY = "survey_empty"
    READY = "ready"
    NO_DATA = "no_data"
    ERROR = "error"


def resolve_statistics_view_state(
    payload: dict[str, Any] | None,
    ready_payload: dict[str, Any] | None = None,
    active_payload: dict[str, Any] | None = None,
    *,
    category: str | None = None,
    indicator: str | None = None,
) -> StatisticsViewState:
    """Resolve the persistent dashboard state from one completed query payload.

    A successful query remains in ``LOADING_STATISTICS`` until the render callback
    confirms that every dashboard output for the same query token is ready.
    """
    active_phase = str((active_payload or {}).get("phase") or "").strip().casefold()
    has_category = bool(str(category or "").strip())
    has_indicator = bool(str(indicator or "").strip())
    has_complete_selection = has_category and has_indicator
    if active_phase == StatisticsViewState.SURVEY_EMPTY:
        return StatisticsViewState.SURVEY_EMPTY
    if not payload:
        # Direct category/indicator Inputs reach the server before the
        # clientside query store in some browser schedules. Once both are
        # selected, INITIAL is no longer a truthful state.
        if has_complete_selection:
            return StatisticsViewState.LOADING_STATISTICS
        if active_phase == StatisticsViewState.LOADING_INDICATORS:
            return StatisticsViewState.LOADING_INDICATORS
        if active_phase == StatisticsViewState.LOADING_STATISTICS:
            return StatisticsViewState.LOADING_STATISTICS
        if has_category:
            if active_phase == StatisticsViewState.AWAITING_INDICATOR:
                return StatisticsViewState.AWAITING_INDICATOR
            # A category Input can reach the server before the clientside
            # catalog state. It is loading indicators, never INITIAL.
            return StatisticsViewState.LOADING_INDICATORS
        return StatisticsViewState.INITIAL
    status = str(payload.get("status") or "").strip().casefold()
    if status == StatisticsViewState.LOADING_INDICATORS:
        return StatisticsViewState.LOADING_INDICATORS
    if status == StatisticsViewState.LOADING_STATISTICS:
        return StatisticsViewState.LOADING_STATISTICS
    if status == StatisticsViewState.AWAITING_INDICATOR:
        return StatisticsViewState.AWAITING_INDICATOR
    query_token = str(payload.get("query_token") or "").strip()
    active_token = str((active_payload or {}).get("query_token") or "").strip()
    if query_token and active_token and query_token != active_token:
        return StatisticsViewState.LOADING_STATISTICS
    if status == "error":
        return StatisticsViewState.ERROR
    ready_status = str((ready_payload or {}).get("status") or "").strip().casefold()
    if status == "ok" and ready_status == StatisticsViewState.ERROR:
        return StatisticsViewState.ERROR
    if status == "ok" and ready_status == StatisticsViewState.LOADING_STATISTICS:
        return StatisticsViewState.LOADING_STATISTICS
    if not has_complete_selection and (category is not None or indicator is not None):
        if has_category:
            if active_phase == StatisticsViewState.LOADING_INDICATORS:
                return StatisticsViewState.LOADING_INDICATORS
            return StatisticsViewState.AWAITING_INDICATOR
        return StatisticsViewState.INITIAL
    payload_indicator = str(payload.get("indicator_code") or "").strip()
    if (
        has_complete_selection
        and payload_indicator
        and payload_indicator != str(indicator).strip()
    ):
        return StatisticsViewState.LOADING_STATISTICS
    if status == "ok":
        ready_token = str((ready_payload or {}).get("query_token") or "").strip()
        if query_token and query_token != ready_token:
            return StatisticsViewState.LOADING_STATISTICS
        return StatisticsViewState.READY
    return StatisticsViewState.NO_DATA
