from __future__ import annotations

import gzip
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Lock

import pytest
from flask import Flask

import app.core.health as health_module
from app.core.auth.rate_limit import InMemoryRateLimiter
from app.core.health import register_health_endpoint
from app.infrastructure.cache import LocalTTLCache, cache, init_cache, local_cache_health_status


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


def test_nested_cache_calculations_do_not_deadlock_on_hash_collisions() -> None:
    # Un proceso separado detecta la regresión por tiempo límite sin bloquear la suite.
    # Las claves colisionan en la antigua tabla de 64 bloqueos.
    script = """
from app.infrastructure.cache import LocalTTLCache
cache = LocalTTLCache()
buckets = {}
for index in range(65):
    key = f'entry-{index}'
    bucket = hash(cache._key(key)) % 64
    if bucket in buckets:
        outer, inner = buckets[bucket], key
        break
    buckets[bucket] = key
assert cache.get_or_compute(outer, lambda: cache.get_or_compute(inner, lambda: 42)) == 42
assert cache.get(outer) == cache.get(inner) == 42
assert not cache._flight_locks
"""
    subprocess.run([sys.executable, "-c", script], check=True, timeout=10)


def test_failed_or_uncached_calculations_release_their_lock_catalog() -> None:
    local = LocalTTLCache()

    def fail():
        raise ValueError("fixture failure")

    with pytest.raises(ValueError, match="fixture failure"):
        local.get_or_compute("retry", fail)
    assert local.get_or_compute("retry", lambda: 42) == 42
    for index in range(100):
        local.get_or_compute(str(index), lambda: None)
    assert not local._flight_locks


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


@pytest.mark.parametrize(
    ("accepted", "compressed"),
    [("gzip", True), ("gzip;q=0", False), ("notgzip", False), ("identity", False),
     ("*;q=1", True), ("gzip;q=0, *;q=1", False)],
)
def test_compression_respects_encoding_quality_and_varies_all_responses(
    accepted: str, compressed: bool,
) -> None:
    app = Flask(__name__)
    init_cache(app)

    @app.get("/payload")
    def payload():
        return {"rows": ["repeated-value"] * 500}, 200, {"Vary": "Origin"}

    response = app.test_client().get("/payload", headers={"Accept-Encoding": accepted})
    assert (response.headers.get("Content-Encoding") == "gzip") is compressed
    assert set(response.vary) == {"Origin", "Accept-Encoding"}
    decoded = gzip.decompress(response.data) if compressed else response.data
    assert b"repeated-value" in decoded


def test_partial_responses_are_not_recompressed() -> None:
    app = Flask(__name__)
    init_cache(app)

    @app.get("/partial")
    def partial():
        return "a" * 2000, 206, {"Content-Type": "text/css", "Content-Range": "bytes 0-1999/4000"}

    response = app.test_client().get("/partial", headers={"Accept-Encoding": "gzip"})
    assert response.status_code == 206
    assert "Content-Encoding" not in response.headers
    assert response.data == b"a" * 2000


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
