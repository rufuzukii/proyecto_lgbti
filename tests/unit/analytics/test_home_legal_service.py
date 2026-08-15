from __future__ import annotations

from typing import Any

import app.analytics.home_legal_service as service


class _MemoryCache:
    app = object()

    def __init__(self) -> None:
        self.values: dict[str, Any] = {}

    def get(self, key: str) -> Any:
        return self.values.get(key)

    def set(self, key: str, value: Any, timeout: int | None = None) -> bool:
        self.values[key] = value
        return True


def test_home_legal_service_uses_only_2026_and_caches_by_iso(monkeypatch) -> None:
    calls: list[tuple[int, bool]] = []
    document = {
        "year": 2026,
        "countries": [{"country": "Spain", "country_code": "ES", "criteria": []}],
    }

    def load(year: int, *, raise_on_error: bool = False):
        calls.append((year, raise_on_error))
        return document

    memory_cache = _MemoryCache()
    monkeypatch.setattr(service, "cache", memory_cache)
    monkeypatch.setattr(service, "analytics_cache_generation", lambda _source: 4)
    monkeypatch.setattr(service, "get_ilga_document_by_year", load)

    first = service.get_home_legal_country_detail("es")
    first["country"] = "Changed locally"
    second = service.get_home_legal_country_detail("ES")

    assert calls == [(2026, True)]
    assert second["country"] == "Spain"
    assert "home:legal:2026:ES:g4" in memory_cache.values


def test_home_legal_service_never_falls_back_to_another_country(monkeypatch) -> None:
    monkeypatch.setattr(service, "cache", _MemoryCache())
    monkeypatch.setattr(service, "analytics_cache_generation", lambda _source: 0)
    monkeypatch.setattr(
        service,
        "get_ilga_document_by_year",
        lambda _year, **_kwargs: {
            "year": 2026,
            "countries": [{"country": "France", "country_code": "FR", "criteria": []}],
        },
    )

    assert service.get_home_legal_country_detail("ES") is None
