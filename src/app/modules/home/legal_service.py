from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.infrastructure.cache import cache
from app.shared.data.normalization import normalize_country_code
from app.shared.data.repository import analytics_cache_generation, get_ilga_document_by_year

HOME_LEGAL_YEAR = 2026
HOME_LEGAL_CACHE_TIMEOUT_SECONDS = 24 * 60 * 60


def get_home_legal_country_detail(country_code: str | None) -> dict[str, Any] | None:
    """Obtiene el detalle legal de un país de ILGA/Rainbow Map 2026 sin depender del mapa."""
    clean_code = normalize_country_code(country_code)
    if not clean_code:
        return None

    cache_key = home_legal_country_cache_key(clean_code)
    cached = _cache_get(cache_key)
    if isinstance(cached, dict):
        return deepcopy(cached)

    document = get_ilga_document_by_year(HOME_LEGAL_YEAR, raise_on_error=True)
    country = _find_country(document, clean_code)
    if country is None:
        return None

    detail = deepcopy(country)
    _cache_set(cache_key, detail)
    return deepcopy(detail)


def home_legal_country_cache_key(country_code: str) -> str:
    clean_code = normalize_country_code(country_code)
    generation = analytics_cache_generation("ilga")
    return f"home:legal:{HOME_LEGAL_YEAR}:{clean_code}:g{generation}"


def _find_country(
    document: dict[str, Any] | None,
    country_code: str,
) -> dict[str, Any] | None:
    if not isinstance(document, dict):
        return None
    for country in document.get("countries", []):
        if not isinstance(country, dict):
            continue
        if (
            normalize_country_code(country.get("country_code"), country.get("country"))
            == country_code
        ):
            return country
    return None


def _cache_get(key: str) -> Any:
    if not getattr(cache, "app", None):
        return None
    try:
        return cache.get(key)
    except RuntimeError:
        return None


def _cache_set(key: str, value: Any) -> None:
    if not getattr(cache, "app", None):
        return
    try:
        cache.set(key, deepcopy(value), timeout=HOME_LEGAL_CACHE_TIMEOUT_SECONDS)
    except RuntimeError:
        return
