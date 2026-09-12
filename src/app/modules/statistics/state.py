from __future__ import annotations

from enum import StrEnum
from typing import Any


class StatisticsViewState(StrEnum):
    INITIAL = "initial"
    LOADING_INDICATORS = "loading_indicators"
    AWAITING_INDICATOR = "awaiting_indicator"
    AWAITING_FILTER = "awaiting_filter"
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
    """Resuelve el estado persistente del panel a partir de una consulta terminada.

    Una consulta correcta permanece en ``LOADING_STATISTICS`` hasta que el callback de
    representación confirma todos los resultados correspondientes al mismo token.
    """
    active_phase = str((active_payload or {}).get("phase") or "").strip().casefold()
    has_category = bool(str(category or "").strip())
    has_indicator = bool(str(indicator or "").strip())
    has_complete_selection = has_category and has_indicator
    if active_phase == StatisticsViewState.SURVEY_EMPTY:
        return StatisticsViewState.SURVEY_EMPTY
    if not payload:
        # En algunas secuencias del navegador, los Inputs de categoría e indicador
        # llegan antes que el almacén de consulta del cliente. Si ambos están
        # seleccionados, INITIAL ya no representa el estado real.
        if has_complete_selection:
            return StatisticsViewState.LOADING_STATISTICS
        if active_phase == StatisticsViewState.LOADING_INDICATORS:
            return StatisticsViewState.LOADING_INDICATORS
        if active_phase == StatisticsViewState.LOADING_STATISTICS:
            return StatisticsViewState.LOADING_STATISTICS
        if has_category:
            if active_phase == StatisticsViewState.AWAITING_INDICATOR:
                return StatisticsViewState.AWAITING_INDICATOR
            # El Input de categoría puede adelantarse al catálogo del cliente:
            # en ese momento se cargan indicadores, no se está en INITIAL.
            return StatisticsViewState.LOADING_INDICATORS
        return StatisticsViewState.INITIAL
    status = str(payload.get("status") or "").strip().casefold()
    if status == StatisticsViewState.LOADING_INDICATORS:
        return StatisticsViewState.LOADING_INDICATORS
    if status == StatisticsViewState.LOADING_STATISTICS:
        return StatisticsViewState.LOADING_STATISTICS
    if status == StatisticsViewState.AWAITING_INDICATOR:
        return StatisticsViewState.AWAITING_INDICATOR
    if status == StatisticsViewState.AWAITING_FILTER:
        return StatisticsViewState.AWAITING_FILTER
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
    if has_complete_selection and payload_indicator and payload_indicator != str(indicator).strip():
        return StatisticsViewState.LOADING_STATISTICS
    if status == "ok":
        ready_token = str((ready_payload or {}).get("query_token") or "").strip()
        if query_token and query_token != ready_token:
            return StatisticsViewState.LOADING_STATISTICS
        return StatisticsViewState.READY
    return StatisticsViewState.NO_DATA
