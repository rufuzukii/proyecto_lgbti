from __future__ import annotations

import hashlib
import json
import logging
from time import perf_counter
from typing import Any

from app.analytics.repository import ANALYTICS_CACHE_TIMEOUT_SECONDS
from app.cache import cache
from app.trends.analysis import analyze_historical_series
from app.trends.data import (
    list_categories,
    list_indicators,
    list_variants,
    load_historical_points,
)
from app.trends.models import (
    HistoricalPoint,
    SeriesMetadata,
    SeriesVariant,
    TrendAnalysis,
    TrendFilters,
    TrendIndicator,
    TrendScope,
    TrendSource,
)

logger = logging.getLogger(__name__)
TREND_CACHE_VERSION = 1


def get_category_options(source: str | None) -> list[str]:
    return list_categories(_source(source))


def get_indicator_options(source: str | None, category: str | None) -> list[TrendIndicator]:
    return list_indicators(_source(source), str(category or ""))


def get_series_variants(indicator_token: str | None) -> list[SeriesVariant]:
    if not indicator_token:
        return []
    indicator = TrendIndicator.from_token(indicator_token)
    if indicator.source == TrendSource.ILGA:
        return [SeriesVariant()]
    return list_variants(load_historical_points(indicator))


def get_trend_scope(indicator_token: str | None, series_key: str | None) -> TrendScope:
    if not indicator_token:
        return TrendScope(countries=(), years=())
    indicator = TrendIndicator.from_token(indicator_token)
    variant = SeriesVariant.from_token(series_key)
    points = _filter_variant(load_historical_points(indicator), variant)
    countries = tuple(
        sorted(
            {
                (point.country_code, point.country_name or point.country_code)
                for point in points
                if point.country_code
            },
            key=lambda item: item[1].casefold(),
        )
    )
    years = tuple(
        sorted(
            {
                int(point.year)
                for point in points
                if point.year is not None and point.value is not None
            }
        )
    )
    return TrendScope(countries=countries, years=years)


def get_historical_series(
    source: str,
    indicator_id: str,
    country_code: str,
    filters: TrendFilters,
) -> list[HistoricalPoint]:
    started = perf_counter()
    indicator = TrendIndicator.from_token(indicator_id)
    resolved_source = _source(source)
    if indicator.source != resolved_source:
        raise ValueError("trend_source_indicator_mismatch")
    clean_country = str(country_code or "").strip().upper()
    cache_key = _series_cache_key(resolved_source, indicator_id, clean_country, filters)
    cached = _cache_get(cache_key)
    if isinstance(cached, tuple) and all(isinstance(point, HistoricalPoint) for point in cached):
        return list(cached)

    variant = SeriesVariant.from_token(filters.series_key)
    points = [
        point
        for point in _filter_variant(load_historical_points(indicator), variant)
        if point.country_code.upper() == clean_country
        and (
            filters.start_year is None
            or (point.year is not None and point.year >= filters.start_year)
        )
        and (
            filters.end_year is None or (point.year is not None and point.year <= filters.end_year)
        )
    ]
    years = sorted({int(point.year) for point in points if point.year is not None})
    logger.info(
        "trend_series_loaded source=%s country=%s years=%s observations=%d",
        resolved_source.value,
        clean_country,
        years,
        len(points),
        extra={
            "source": resolved_source.value,
            "indicator": indicator.indicator_id,
            "country": clean_country,
            "years": years,
            "observations": len(points),
            "query_ms": round((perf_counter() - started) * 1000, 3),
        },
    )
    if points:
        _cache_set(cache_key, tuple(points))
    return points


def generate_trend_analysis(
    source: str,
    indicator_token: str,
    country_code: str,
    filters: TrendFilters,
    *,
    forecast_years: int,
) -> tuple[TrendAnalysis, SeriesMetadata]:
    indicator = TrendIndicator.from_token(indicator_token)
    variant = SeriesVariant.from_token(filters.series_key)
    points = get_historical_series(source, indicator_token, country_code, filters)
    country_name = next(
        (point.country_name for point in points if point.country_name), country_code
    )
    sample = points[0] if points else None
    metadata = SeriesMetadata(
        source=indicator.source,
        indicator_id=indicator.indicator_id,
        indicator_label=indicator.label,
        category=indicator.category,
        country_code=str(country_code or "").strip().upper(),
        country_name=country_name,
        response=variant.response,
        filters=variant.filters,
        unit=sample.unit if sample else "percentage_score",
        scale_min=sample.scale_min if sample else 0.0,
        scale_max=sample.scale_max if sample else 100.0,
        methodology=sample.methodology if sample else _default_methodology(indicator.source),
    )
    return (
        analyze_historical_series(points, metadata, forecast_years=forecast_years),
        metadata,
    )


def invalidate_trend_cache() -> None:
    """Invalidate trends together with the shared analytics cache after dataset mutations."""
    cache.clear()


def _filter_variant(points: list[HistoricalPoint], variant: SeriesVariant) -> list[HistoricalPoint]:
    return [
        point
        for point in points
        if point.response == variant.response and point.filters == variant.filters
    ]


def _series_cache_key(
    source: TrendSource,
    indicator_token: str,
    country_code: str,
    filters: TrendFilters,
) -> str:
    identity = {
        "country": country_code,
        "end_year": filters.end_year,
        "indicator": indicator_token,
        "series": filters.series_key,
        "source": source.value,
        "start_year": filters.start_year,
        "version": TREND_CACHE_VERSION,
    }
    serialized = json.dumps(identity, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return f"trend-series-v{TREND_CACHE_VERSION}:{hashlib.sha256(serialized.encode()).hexdigest()}"


def _cache_get(key: str) -> Any:
    if not getattr(cache, "app", None):
        return None
    try:
        return cache.get(key)
    except Exception:
        logger.debug("trend_cache_read_failed", exc_info=True)
        return None


def _cache_set(key: str, value: tuple[HistoricalPoint, ...]) -> None:
    if not getattr(cache, "app", None):
        return
    try:
        cache.set(key, value, timeout=ANALYTICS_CACHE_TIMEOUT_SECONDS)
    except Exception:
        logger.debug("trend_cache_write_failed", exc_info=True)


def _source(value: str | None) -> TrendSource:
    try:
        return TrendSource(str(value or ""))
    except ValueError as exc:
        raise ValueError("invalid_trend_source") from exc


def _default_methodology(source: TrendSource) -> str:
    return "ilga_rainbow_map" if source == TrendSource.ILGA else "fra_lgbtiq_survey"
