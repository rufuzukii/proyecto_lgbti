from __future__ import annotations

import logging
import os
from functools import lru_cache
from threading import Lock
from time import monotonic
from typing import Any, ClassVar

from flask import Flask, request
from flask_caching import Cache
from flask_caching.backends.rediscache import RedisCache
from redis import Redis
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)


class ResilientRedisCache(RedisCache):
    """Redis backend that degrades to cache misses during transient outages."""

    _failure_log_lock: ClassVar[Lock] = Lock()
    _last_failure_log: ClassVar[float] = 0.0

    @classmethod
    def _report_failure(cls, operation: str) -> None:
        now = monotonic()
        with cls._failure_log_lock:
            if now - cls._last_failure_log < 30:
                return
            cls._last_failure_log = now
        logger.warning("redis_cache_operation_failed operation=%s", operation)

    def get(self, key: str) -> Any:
        try:
            return super().get(key)
        except (RedisError, OSError):
            self._report_failure("get")
            return None

    def set(self, key: str, value: Any, timeout: int | None = None) -> Any:
        try:
            return super().set(key, value, timeout)
        except (RedisError, OSError):
            self._report_failure("set")
            return False

    def add(self, key: str, value: Any, timeout: int | None = None) -> Any:
        try:
            return super().add(key, value, timeout)
        except (RedisError, OSError):
            self._report_failure("add")
            return False

    def delete(self, key: str) -> bool:
        try:
            return super().delete(key)
        except (RedisError, OSError):
            self._report_failure("delete")
            return False

    def delete_many(self, *keys: str) -> Any:
        try:
            return super().delete_many(*keys)
        except (RedisError, OSError):
            self._report_failure("delete_many")
            return 0

    def clear(self) -> bool:
        try:
            return super().clear()
        except (RedisError, OSError):
            self._report_failure("clear")
            return False

    def get_many(self, *keys: str) -> list[Any]:
        try:
            return super().get_many(*keys)
        except (RedisError, OSError):
            self._report_failure("get_many")
            return [None] * len(keys)

    def set_many(self, mapping: dict[str, Any], timeout: int | None = None) -> list[Any]:
        try:
            return super().set_many(mapping, timeout)
        except (RedisError, OSError):
            self._report_failure("set_many")
            return []

    def has(self, key: str) -> bool:
        try:
            return super().has(key)
        except (RedisError, OSError):
            self._report_failure("has")
            return False

    def inc(self, key: str, delta: int = 1) -> Any:
        try:
            return super().inc(key, delta)
        except (RedisError, OSError):
            self._report_failure("inc")
            return None

    def dec(self, key: str, delta: int = 1) -> Any:
        try:
            return super().dec(key, delta)
        except (RedisError, OSError):
            self._report_failure("dec")
            return None


cache = Cache()


def init_cache(app: Flask) -> None:
    redis_url = _redis_url()
    production = _is_production()

    config: dict[str, object] = {
        "CACHE_DEFAULT_TIMEOUT": _env_int("CACHE_DEFAULT_TIMEOUT", 300),
        "CACHE_KEY_PREFIX": _cache_key_prefix(),
    }
    if redis_url:
        config.update(
            {
                "CACHE_TYPE": "app.cache.ResilientRedisCache",
                "CACHE_REDIS_URL": redis_url,
                "CACHE_OPTIONS": {
                    "socket_connect_timeout": _env_float("REDIS_CONNECT_TIMEOUT_SECONDS", 1.0),
                    "socket_timeout": _env_float("REDIS_SOCKET_TIMEOUT_SECONDS", 1.0),
                    "health_check_interval": _env_int("REDIS_HEALTH_CHECK_INTERVAL_SECONDS", 30),
                    "retry_on_timeout": False,
                },
            }
        )
        logger.info("cache_backend_active backend=redis")
    elif production:
        config["CACHE_TYPE"] = "NullCache"
        logger.warning("cache_backend_inactive backend=null reason=missing_redis_url")
    else:
        config["CACHE_TYPE"] = "SimpleCache"
        logger.info("cache_backend_active backend=memory environment=development")

    cache.init_app(app, config=config)

    @app.after_request
    def add_browser_cache_headers(response):
        if request.path.startswith("/_dash-component-suites/"):
            response.headers["Cache-Control"] = "no-cache, max-age=0, must-revalidate"
        elif request.path.startswith("/assets/"):
            response.headers["Cache-Control"] = (
                f"public, max-age={_env_int('STATIC_CACHE_MAX_AGE', 86400)}"
            )
        return response


def redis_health_status() -> str:
    """Return Redis health without disclosing connection details."""
    redis_url = _redis_url()
    if not redis_url:
        return "unavailable" if _is_production() else "degraded"

    try:
        client = _redis_health_client(redis_url)
        return "ok" if client.ping() else "unavailable"
    except (RedisError, OSError, ValueError):
        return "unavailable"


@lru_cache(maxsize=1)
def _redis_health_client(redis_url: str) -> Redis:
    return Redis.from_url(
        redis_url,
        socket_connect_timeout=_env_float("REDIS_CONNECT_TIMEOUT_SECONDS", 1.0),
        socket_timeout=_env_float("REDIS_SOCKET_TIMEOUT_SECONDS", 1.0),
        health_check_interval=_env_int("REDIS_HEALTH_CHECK_INTERVAL_SECONDS", 30),
    )


def _redis_url() -> str:
    return (os.getenv("REDIS_URL") or "").strip()


def _is_production() -> bool:
    environment = os.getenv("APP_ENV", "local").strip().casefold()
    local_mode = os.getenv("LOCAL_MODE", "").strip().casefold()
    return environment == "production" and local_mode not in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if not value:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _cache_key_prefix() -> str:
    explicit = os.getenv("CACHE_KEY_PREFIX", "").strip()
    if explicit:
        return explicit
    app_env = os.getenv("APP_ENV", "local").strip().lower() or "local"
    version = os.getenv("CACHE_VERSION", "v1").strip() or "v1"
    return f"rainbowlens:{app_env}:{version}:cache:"
