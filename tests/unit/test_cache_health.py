from __future__ import annotations

import gzip
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Lock

from flask import Flask

import app.health as health_module
from app.auth.rate_limit import InMemoryRateLimiter
from app.cache import cache, init_cache, local_cache_health_status
from app.health import register_health_endpoint


def test_production_uses_bounded_local_cache_without_external_service(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("LOCAL_CACHE_MAX_ENTRIES", "2")
    app = Flask(__name__)
    init_cache(app)

    cache.set("first", {"value": 1})
    cache.set("second", {"value": 2})
    cache.set("third", {"value": 3})

    assert cache.get("first") is None
    assert cache.get("third") == {"value": 3}
    assert cache.stats()["entries"] == 2
    assert local_cache_health_status() == "ok"


def test_local_cache_does_not_expose_mutable_cached_state(monkeypatch) -> None:
    monkeypatch.setenv("LOCAL_CACHE_MAX_ENTRIES", "10")
    app = Flask(__name__)
    init_cache(app)
    original = {"items": [1]}
    cache.set("value", original)

    loaded = cache.get("value")
    loaded["items"].append(2)

    assert cache.get("value") == {"items": [1]}


def test_local_cache_ttl_expiration(monkeypatch) -> None:
    app = Flask(__name__)
    init_cache(app)
    cache.set("expired", "value", timeout=1)
    entry = cache._entries[cache._key("expired")]
    cache._entries[cache._key("expired")] = type(entry)(entry.payload, 0.0)

    assert cache.get("expired") is None


def test_local_cache_coalesces_simultaneous_calculations() -> None:
    app = Flask(__name__)
    init_cache(app)
    barrier = Barrier(8)
    counter_lock = Lock()
    calculations = 0

    def request_value() -> dict[str, int]:
        nonlocal calculations
        barrier.wait()

        def calculate() -> dict[str, int]:
            nonlocal calculations
            with counter_lock:
                calculations += 1
            return {"value": 42}

        return cache.get_or_compute("shared", calculate)

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(lambda _index: request_value(), range(8)))

    assert results == [{"value": 42}] * 8
    assert calculations == 1


def test_local_rate_limiter_has_a_bounded_identity_catalog() -> None:
    limiter = InMemoryRateLimiter(max_attempts=2, window_seconds=300, max_keys=2)
    limiter.record_failure("first")
    limiter.record_failure("second")
    limiter.record_failure("third")

    assert limiter.tracked_keys() == 2
    assert limiter.is_blocked("first") is False


def test_large_json_responses_are_compressed_and_static_assets_are_cacheable() -> None:
    app = Flask(__name__)
    init_cache(app)

    @app.get("/payload")
    def payload():
        return {"rows": ["repeated-value"] * 500}

    @app.get("/assets/versioned.css")
    def asset():
        return "body{}", 200, {"Content-Type": "text/css"}

    client = app.test_client()
    response = client.get("/payload", headers={"Accept-Encoding": "gzip"})
    asset_response = client.get("/assets/versioned.css")

    assert response.headers["Content-Encoding"] == "gzip"
    assert b"repeated-value" in gzip.decompress(response.data)
    assert response.headers["Vary"] == "Accept-Encoding"
    assert "stale-while-revalidate" in asset_response.headers["Cache-Control"]


def test_health_endpoint_is_lightweight_and_does_not_probe_databases(monkeypatch) -> None:
    monkeypatch.setattr(health_module, "local_cache_health_status", lambda: "ok")
    app = Flask(__name__)
    register_health_endpoint(app)

    response = app.test_client().get("/health")

    assert response.status_code == 200
    assert response.get_json() == {
        "status": "ok",
        "services": {"application": "ok", "local_cache": "ok"},
    }


def test_health_endpoint_degrades_when_local_cache_is_not_initialized(monkeypatch) -> None:
    monkeypatch.setattr(health_module, "local_cache_health_status", lambda: "unavailable")
    app = Flask(__name__)
    register_health_endpoint(app)

    response = app.test_client().get("/health")

    assert response.status_code == 200
    assert response.get_json()["status"] == "degraded"
