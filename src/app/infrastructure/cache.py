from __future__ import annotations

import gzip
import hashlib
import inspect
import logging
import os
import pickle
from collections import OrderedDict, defaultdict
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from functools import wraps
from threading import Lock, RLock
from time import monotonic
from typing import Any, ParamSpec, TypeVar

from flask import Flask, Response, request

logger = logging.getLogger(__name__)

P = ParamSpec("P")
R = TypeVar("R")
_MISSING = object()


@dataclass(frozen=True)
class _CacheEntry:
    payload: bytes
    expires_at: float | None


@dataclass
class _CacheFlight:
    lock: Lock = field(default_factory=Lock)
    users: int = 0


class LocalTTLCache:
    """Caché acotada, local al proceso, con TTL y protección ante cálculos simultáneos.

    Los procesos de Render no comparten esta caché. La serialización impide que un consumidor
    modifique los valores almacenados y permite limitar la memoria según el tamaño real del
    contenido.
    """

    def __init__(self) -> None:
        self.app: Flask | None = None
        self.default_timeout = 300
        self.max_entries = 512
        self.max_value_bytes = 4 * 1024 * 1024
        self.max_total_bytes = 64 * 1024 * 1024
        self.key_prefix = ""
        self._entries: OrderedDict[str, _CacheEntry] = OrderedDict()
        self._memoized_keys: dict[str, set[str]] = defaultdict(set)
        self._key_namespaces: dict[str, str] = {}
        self._total_bytes = 0
        self._lock = RLock()
        self._flight_locks: dict[str, _CacheFlight] = {}

    def init_app(self, app: Flask) -> None:
        self.app = app
        self.default_timeout = _env_int("CACHE_DEFAULT_TIMEOUT", 300, minimum=1)
        self.max_entries = _env_int("LOCAL_CACHE_MAX_ENTRIES", 512, minimum=1)
        self.max_value_bytes = _env_int(
            "LOCAL_CACHE_MAX_VALUE_BYTES", 4 * 1024 * 1024, minimum=1024
        )
        self.max_total_bytes = _env_int(
            "LOCAL_CACHE_MAX_TOTAL_BYTES", 64 * 1024 * 1024, minimum=1024
        )
        self.key_prefix = _cache_key_prefix()
        self.clear()
        app.extensions["local_ttl_cache"] = self

    def get(self, key: str) -> Any:
        namespaced = self._key(key)
        with self._lock:
            entry = self._entries.get(namespaced)
            if entry is None:
                return None
            if entry.expires_at is not None and entry.expires_at <= monotonic():
                self._delete_locked(namespaced)
                return None
            self._entries.move_to_end(namespaced)
            payload = entry.payload
        try:
            return pickle.loads(payload)
        except pickle.PickleError, EOFError, AttributeError, ImportError:
            self.delete(key)
            logger.warning("local_cache_deserialization_failed key=%s", key)
            return None

    def set(self, key: str, value: Any, timeout: int | None = None) -> bool:
        try:
            payload = pickle.dumps(value, protocol=pickle.HIGHEST_PROTOCOL)
        except pickle.PickleError, AttributeError, TypeError:
            logger.debug("local_cache_value_not_serializable key=%s", key, exc_info=True)
            return False
        if len(payload) > self.max_value_bytes or len(payload) > self.max_total_bytes:
            logger.info(
                "local_cache_value_skipped key=%s bytes=%d max_value_bytes=%d",
                key,
                len(payload),
                self.max_value_bytes,
            )
            return False

        ttl = self.default_timeout if timeout is None else max(0, int(timeout))
        expires_at = monotonic() + ttl if ttl else None
        namespaced = self._key(key)
        with self._lock:
            self._delete_locked(namespaced)
            self._entries[namespaced] = _CacheEntry(payload=payload, expires_at=expires_at)
            self._total_bytes += len(payload)
            self._evict_locked()
        return True

    def add(self, key: str, value: Any, timeout: int | None = None) -> bool:
        with self._lock:
            if self._get_entry_locked(self._key(key)) is not None:
                return False
        return self.set(key, value, timeout=timeout)

    def delete(self, key: str) -> bool:
        with self._lock:
            return self._delete_locked(self._key(key))

    def delete_many(self, *keys: str) -> int:
        with self._lock:
            return sum(self._delete_locked(self._key(key)) for key in keys)

    def get_many(self, *keys: str) -> list[Any]:
        return [self.get(key) for key in keys]

    def set_many(self, mapping: Mapping[str, Any], timeout: int | None = None) -> list[bool]:
        return [self.set(key, value, timeout=timeout) for key, value in mapping.items()]

    def has(self, key: str) -> bool:
        with self._lock:
            return self._get_entry_locked(self._key(key)) is not None

    def clear(self) -> bool:
        with self._lock:
            self._entries.clear()
            self._memoized_keys.clear()
            self._key_namespaces.clear()
            self._total_bytes = 0
        return True

    def get_or_compute(
        self,
        key: str,
        factory: Callable[[], R],
        *,
        timeout: int | None = None,
        cache_if: Callable[[R], bool] | None = None,
    ) -> R:
        cached = self.get(key)
        if cached is not None:
            return cached
        namespaced = self._key(key)
        # Las fábricas anidadas (serie de un país e histórico) necesitan bloqueos propios;
        # una colisión entre claves distintas no debe provocar un interbloqueo.
        with self._lock:
            flight = self._flight_locks.get(namespaced)
            if flight is None:
                flight = self._flight_locks[namespaced] = _CacheFlight()
            flight.users += 1
        try:
            with flight.lock:
                cached = self.get(key)
                if cached is not None:
                    return cached
                value = factory()
                if cache_if is None or cache_if(value):
                    self.set(key, value, timeout=timeout)
                return value
        finally:
            with self._lock:
                flight.users -= 1
                if not flight.users:
                    del self._flight_locks[namespaced]

    def memoize(
        self,
        timeout: int | None = None,
        source_check: bool = False,
    ) -> Callable[[Callable[P, R]], Callable[P, R]]:
        def decorator(function: Callable[P, R]) -> Callable[P, R]:
            namespace = f"{function.__module__}.{function.__qualname__}"
            source_digest = ""
            if source_check:
                try:
                    source_digest = hashlib.sha256(
                        inspect.getsource(function).encode("utf-8")
                    ).hexdigest()
                except OSError, TypeError:
                    source_digest = "source-unavailable"

            @wraps(function)
            def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
                key = self._memoize_key(namespace, source_digest, args, kwargs)

                def calculate() -> R:
                    return function(*args, **kwargs)

                value = self.get_or_compute(key, calculate, timeout=timeout)
                namespaced = self._key(key)
                with self._lock:
                    if namespaced in self._entries:
                        self._memoized_keys[namespace].add(namespaced)
                        self._key_namespaces[namespaced] = namespace
                return value

            wrapped.__dict__["_local_cache_namespace"] = namespace
            wrapped.__dict__["uncached"] = function
            return wrapped

        return decorator

    def delete_memoized(self, function: Callable[..., Any]) -> bool:
        namespace = str(
            getattr(
                function,
                "_local_cache_namespace",
                f"{function.__module__}.{function.__qualname__}",
            )
        )
        with self._lock:
            keys = tuple(self._memoized_keys.pop(namespace, ()))
            for key in keys:
                self._delete_locked(key)
        return True

    def stats(self) -> dict[str, int]:
        with self._lock:
            self._prune_expired_locked()
            return {
                "entries": len(self._entries),
                "bytes": self._total_bytes,
                "max_entries": self.max_entries,
                "max_total_bytes": self.max_total_bytes,
                "max_value_bytes": self.max_value_bytes,
            }

    def _memoize_key(
        self,
        namespace: str,
        source_digest: str,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> str:
        try:
            identity = pickle.dumps(
                (namespace, source_digest, args, sorted(kwargs.items())),
                protocol=pickle.HIGHEST_PROTOCOL,
            )
        except pickle.PickleError, AttributeError, TypeError:
            identity = repr((namespace, source_digest, args, sorted(kwargs.items()))).encode()
        digest = hashlib.sha256(identity).hexdigest()
        return f"memoize:{namespace}:{digest}"

    def _key(self, key: str) -> str:
        return f"{self.key_prefix}{key}"

    def _get_entry_locked(self, namespaced: str) -> _CacheEntry | None:
        entry = self._entries.get(namespaced)
        if entry is None:
            return None
        if entry.expires_at is not None and entry.expires_at <= monotonic():
            self._delete_locked(namespaced)
            return None
        self._entries.move_to_end(namespaced)
        return entry

    def _delete_locked(self, namespaced: str) -> bool:
        entry = self._entries.pop(namespaced, None)
        if entry is None:
            return False
        self._total_bytes -= len(entry.payload)
        namespace = self._key_namespaces.pop(namespaced, None)
        if namespace is not None:
            keys = self._memoized_keys.get(namespace)
            if keys is not None:
                keys.discard(namespaced)
                if not keys:
                    self._memoized_keys.pop(namespace, None)
        return True

    def _prune_expired_locked(self) -> None:
        now = monotonic()
        expired = [
            key
            for key, entry in self._entries.items()
            if entry.expires_at is not None and entry.expires_at <= now
        ]
        for key in expired:
            self._delete_locked(key)

    def _evict_locked(self) -> None:
        self._prune_expired_locked()
        while len(self._entries) > self.max_entries or self._total_bytes > self.max_total_bytes:
            oldest = next(iter(self._entries))
            self._delete_locked(oldest)


cache = LocalTTLCache()


def init_cache(app: Flask) -> None:
    cache.init_app(app)
    logger.info(
        "cache_backend_active backend=local_ttl max_entries=%d max_total_bytes=%d",
        cache.max_entries,
        cache.max_total_bytes,
    )

    @app.after_request
    def add_browser_cache_headers(response: Response) -> Response:
        if request.path.startswith("/_dash-component-suites/"):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        elif request.path.startswith("/assets/"):
            max_age = _env_int("STATIC_CACHE_MAX_AGE", 86400, minimum=0)
            response.headers["Cache-Control"] = (
                f"public, max-age={max_age}, stale-while-revalidate=604800"
            )
        _compress_response(response)
        return response


def local_cache_health_status() -> str:
    """Devuelve el estado de la caché del proceso sin operaciones de red."""
    return "ok" if cache.app is not None else "unavailable"


def _compress_response(response: Response) -> None:
    if (
        request.method == "HEAD"
        or response.direct_passthrough
        or response.status_code != 200
        or response.headers.get("Content-Range")
        or response.headers.get("Content-Encoding")
        or response.mimetype
        not in {
            "application/geo+json",
            "application/javascript",
            "application/json",
            "text/css",
            "text/javascript",
        }
    ):
        return
    # También la variante sin comprimir debe distinguirse en las cachés HTTP.
    # El parser de Werkzeug respeta q=0 y los comodines de Accept-Encoding.
    response.vary.add("Accept-Encoding")
    if request.accept_encodings["gzip"] <= 0:
        return
    payload = response.get_data()
    if len(payload) < _env_int("HTTP_GZIP_MIN_BYTES", 1024, minimum=256):
        return
    compressed = gzip.compress(payload, compresslevel=5, mtime=0)
    if len(compressed) >= len(payload):
        return
    response.set_data(compressed)
    response.headers["Content-Encoding"] = "gzip"


def _env_int(name: str, default: int, *, minimum: int) -> int:
    value = os.getenv(name)
    if not value:
        return default
    try:
        return max(minimum, int(value))
    except ValueError:
        return default


def _cache_key_prefix() -> str:
    app_env = os.getenv("APP_ENV", "local").strip().lower() or "local"
    version = os.getenv("CACHE_VERSION", "v1").strip() or "v1"
    return f"rainbowlens:{app_env}:{version}:cache:"
