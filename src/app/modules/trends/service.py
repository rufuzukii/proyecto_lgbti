from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable
from dataclasses import replace
from time import perf_counter
from typing import Any

from app.infrastructure.cache import cache
from app.modules.trends.forecasting_service import generate_forecast
from app.modules.trends.historical_series import (
    audit_country_coverage,
    build_trend_scope,
    country_series,
    load_ilga_global_history,
)
from app.modules.trends.models import (
    CountryCoverage,
    ForecastResult,
    HistoricalPoint,
    TrendFilters,
    TrendScope,
)
from app.shared.data.repository import (
    ANALYTICS_CACHE_TIMEOUT_SECONDS,
    analytics_cache_generation,
    invalidate_analytics_cache,
)

logger = logging.getLogger(__name__)
TREND_CACHE_VERSION = 3
MAX_FORECAST_HORIZON = 3


def get_trend_scope() -> TrendScope:
    return build_trend_scope(_historical_dataset())


def get_historical_series(
    country_code: str,
    filters: TrendFilters | None = None,
) -> list[HistoricalPoint]:
    clean_code = str(country_code or "").strip().upper()
    selected_filters = filters or TrendFilters()
    cache_key = _series_cache_key(clean_code, selected_filters)
    cached = _cache_get(cache_key)
    if isinstance(cached, tuple) and all(isinstance(item, HistoricalPoint) for item in cached):
        return list(cached)

    started = perf_counter()
    points = _cache_get_or_compute(
        cache_key,
        lambda: country_series(
            _historical_dataset(),
            clean_code,
            start_year=selected_filters.start_year,
            end_year=selected_filters.end_year,
        ),
        cache_if=bool,
    )
    logger.info(
        "trend_series_loaded country=%s observations=%d years=%s load_ms=%.2f",
        clean_code,
        len(points),
        [point.year for point in points],
        (perf_counter() - started) * 1000,
    )
    return list(points)


def generate_trend_analysis(
    country_code: str,
    filters: TrendFilters | None = None,
    *,
    forecast_years: int = 1,
) -> ForecastResult:
    selected_filters = filters or TrendFilters()
    points = get_historical_series(country_code, selected_filters)
    country_name = next(
        (point.country_name for point in points if point.country_name),
        str(country_code or "").strip().upper(),
    )
    cache_key = _forecast_cache_key(points, country_code, selected_filters)
    cached = _cache_get(cache_key)
    if isinstance(cached, ForecastResult):
        return _result_for_horizon(cached, forecast_years)

    started = perf_counter()
    result = _cache_get_or_compute(
        cache_key,
        lambda: generate_forecast(
            points,
            country_code=str(country_code or "").strip().upper(),
            country_name=country_name,
            horizon=MAX_FORECAST_HORIZON,
        ),
        cache_if=lambda value: value.status in {"ok", "insufficient"},
    )
    logger.info(
        "trend_forecast_completed country=%s observations=%d horizon=%d model=%s "
        "mae=%s rmse=%s calculation_ms=%.2f cache_hit=false",
        result.country_code,
        len(result.historical),
        result.forecast_horizon,
        result.selected_model.value if result.selected_model else "none",
        round(result.selected_validation.mae, 3) if result.selected_validation else None,
        round(result.selected_validation.rmse, 3) if result.selected_validation else None,
        (perf_counter() - started) * 1000,
    )
    return _result_for_horizon(result, forecast_years)


def get_country_coverage() -> tuple[CountryCoverage, ...]:
    return audit_country_coverage(_historical_dataset())


def invalidate_trend_cache() -> None:
    """Invalidate series and forecasts after a Rainbow Map import."""
    invalidate_analytics_cache("ilga")


def _historical_dataset() -> tuple[HistoricalPoint, ...]:
    cache_key = _dataset_cache_key()
    cached = _cache_get(cache_key)
    if isinstance(cached, tuple) and all(isinstance(item, HistoricalPoint) for item in cached):
        return cached
    started = perf_counter()
    points = _cache_get_or_compute(
        cache_key,
        load_ilga_global_history,
        cache_if=bool,
    )
    logger.info(
        "trend_history_dataset_loaded rows=%d years=%d query_and_normalization_ms=%.2f",
        len(points),
        len({point.year for point in points if point.year is not None}),
        (perf_counter() - started) * 1000,
    )
    return points


def _dataset_cache_key() -> str:
    identity = {
        "cache_generation": analytics_cache_generation("ilga"),
        "version": TREND_CACHE_VERSION,
    }
    return _hashed_key("trend-history-dataset", identity)


def _series_cache_key(country_code: str, filters: TrendFilters) -> str:
    identity = {
        "cache_generation": analytics_cache_generation("ilga"),
        "country": country_code,
        "end_year": filters.end_year,
        "start_year": filters.start_year,
        "version": TREND_CACHE_VERSION,
    }
    return _hashed_key("trend-country-series", identity)


def _forecast_cache_key(
    points: list[HistoricalPoint],
    country_code: str,
    filters: TrendFilters,
) -> str:
    identity = {
        "cache_generation": analytics_cache_generation("ilga"),
        "country": str(country_code or "").strip().upper(),
        "end_year": filters.end_year,
        "series": [(point.year, point.value) for point in points],
        "start_year": filters.start_year,
        "version": TREND_CACHE_VERSION,
    }
    return _hashed_key("trend-forecast", identity)


def _result_for_horizon(result: ForecastResult, horizon: int) -> ForecastResult:
    requested = max(1, min(MAX_FORECAST_HORIZON, int(horizon)))
    available = min(requested, len(result.forecast))
    return replace(
        result,
        forecast=result.forecast[:available],
        requested_horizon=requested,
        forecast_horizon=available,
    )


def _hashed_key(prefix: str, identity: dict[str, Any]) -> str:
    serialized = json.dumps(identity, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    return f"{prefix}-v{TREND_CACHE_VERSION}:{digest}"


def _cache_get(key: str) -> Any:
    if not getattr(cache, "app", None):
        return None
    try:
        return cache.get(key)
    except Exception:
        logger.debug("trend_cache_read_failed", exc_info=True)
        return None


def _cache_get_or_compute[T](
    key: str,
    factory: Callable[[], T],
    *,
    cache_if: Callable[[T], bool] | None = None,
) -> T:
    if not getattr(cache, "app", None):
        return factory()
    return cache.get_or_compute(
        key,
        factory,
        timeout=ANALYTICS_CACHE_TIMEOUT_SECONDS,
        cache_if=cache_if,
    )
