from __future__ import annotations

import os

from flask import Flask, request
from flask_caching import Cache

cache = Cache()


def init_cache(app: Flask) -> None:
    cache_type = os.getenv("CACHE_TYPE", "SimpleCache").strip() or "SimpleCache"
    redis_url = (os.getenv("CACHE_REDIS_URL") or os.getenv("REDIS_URL") or "").strip()
    if cache_type.lower() in {"redis", "rediscache"} and not redis_url:
        cache_type = "SimpleCache"

    config: dict[str, object] = {
        "CACHE_TYPE": cache_type,
        "CACHE_DEFAULT_TIMEOUT": _env_int("CACHE_DEFAULT_TIMEOUT", 300),
        "CACHE_KEY_PREFIX": _cache_key_prefix(),
    }
    if cache_type.lower() in {"redis", "rediscache"} and redis_url:
        config["CACHE_REDIS_URL"] = redis_url

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


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _cache_key_prefix() -> str:
    explicit = os.getenv("CACHE_KEY_PREFIX", "").strip()
    if explicit:
        return explicit
    app_env = os.getenv("APP_ENV", "local").strip().lower() or "local"
    version = os.getenv("CACHE_VERSION", "v1").strip() or "v1"
    return f"rainbowlens:{app_env}:{version}:cache:"
