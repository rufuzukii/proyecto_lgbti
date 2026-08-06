from __future__ import annotations

from flask import Flask
from redis.exceptions import ConnectionError as RedisConnectionError

import app.cache as cache_module
import app.health as health_module
from app.cache import ResilientRedisCache, cache, init_cache
from app.health import register_health_endpoint


def test_development_uses_memory_only_as_explicit_fallback(monkeypatch) -> None:
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setenv("APP_ENV", "local")
    app = Flask(__name__)
    init_cache(app)

    backend = app.extensions["cache"][cache]
    assert type(backend).__name__ == "SimpleCache"
    assert cache_module.redis_health_status() == "degraded"


def test_production_without_redis_uses_null_cache(monkeypatch) -> None:
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("LOCAL_MODE", "false")
    app = Flask(__name__)
    init_cache(app)

    backend = app.extensions["cache"][cache]
    assert type(backend).__name__ == "NullCache"
    assert cache_module.redis_health_status() == "unavailable"


def test_redis_url_selects_resilient_shared_backend(monkeypatch) -> None:
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:6399/0")
    app = Flask(__name__)
    init_cache(app)

    backend = app.extensions["cache"][cache]
    assert isinstance(backend, ResilientRedisCache)


def test_redis_backend_turns_connection_failure_into_cache_miss(monkeypatch) -> None:
    backend = ResilientRedisCache(host="redis://127.0.0.1:6399/0")

    def fail_get(_self, _key):
        raise RedisConnectionError("test outage")

    monkeypatch.setattr("flask_caching.backends.rediscache.RedisCache.get", fail_get)
    assert backend.get("missing") is None


def test_health_endpoint_reports_degraded_redis_without_failing_app(monkeypatch) -> None:
    monkeypatch.setattr(health_module, "_postgresql_status", lambda: "ok")
    monkeypatch.setattr(health_module, "_mongodb_status", lambda: "ok")
    monkeypatch.setattr(health_module, "redis_health_status", lambda: "unavailable")
    monkeypatch.setattr(health_module, "_configuration_status", lambda: "ok")
    app = Flask(__name__)
    register_health_endpoint(app)

    response = app.test_client().get("/health")

    assert response.status_code == 200
    assert response.get_json() == {
        "status": "degraded",
        "services": {
            "application": "ok",
            "configuration": "ok",
            "mongodb": "ok",
            "postgresql": "ok",
            "redis": "unavailable",
        },
    }


def test_health_endpoint_returns_503_for_required_database(monkeypatch) -> None:
    monkeypatch.setattr(health_module, "_postgresql_status", lambda: "unavailable")
    monkeypatch.setattr(health_module, "_mongodb_status", lambda: "ok")
    monkeypatch.setattr(health_module, "redis_health_status", lambda: "ok")
    monkeypatch.setattr(health_module, "_configuration_status", lambda: "ok")
    app = Flask(__name__)
    register_health_endpoint(app)

    response = app.test_client().get("/health")

    assert response.status_code == 503
    assert response.get_json()["status"] == "unavailable"
