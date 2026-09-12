from __future__ import annotations

import os
import time
from collections import OrderedDict, deque
from threading import RLock
from typing import Protocol


class RateLimiter(Protocol):
    """Contrato estructural del limitador local al proceso."""

    def is_blocked(self, key: str) -> bool: ...

    def record_failure(self, key: str) -> None: ...

    def reset(self, key: str) -> None: ...


class InMemoryRateLimiter:
    """Limitador acotado de ventana deslizante, local a un proceso de Gunicorn."""

    def __init__(self, max_attempts: int, window_seconds: int, *, max_keys: int = 10_000) -> None:
        self.max_attempts = max(1, max_attempts)
        self.window_seconds = max(1, window_seconds)
        self.max_keys = max(1, max_keys)
        self._attempts: OrderedDict[str, deque[float]] = OrderedDict()
        self._lock = RLock()

    def _prune(self, key: str, now: float) -> deque[float] | None:
        attempts = self._attempts.get(key)
        if attempts is None:
            return None
        while attempts and (now - attempts[0]) > self.window_seconds:
            attempts.popleft()
        if not attempts:
            self._attempts.pop(key, None)
            return None
        self._attempts.move_to_end(key)
        return attempts

    def is_blocked(self, key: str) -> bool:
        with self._lock:
            attempts = self._prune(key, time.monotonic())
            return len(attempts) >= self.max_attempts if attempts is not None else False

    def record_failure(self, key: str) -> None:
        with self._lock:
            now = time.monotonic()
            attempts = self._prune(key, now)
            if attempts is None:
                while len(self._attempts) >= self.max_keys:
                    self._attempts.popitem(last=False)
                attempts = deque()
                self._attempts[key] = attempts
            attempts.append(now)
            self._attempts.move_to_end(key)

    def reset(self, key: str) -> None:
        with self._lock:
            self._attempts.pop(key, None)

    def tracked_keys(self) -> int:
        with self._lock:
            return len(self._attempts)


def create_rate_limiter(
    *,
    max_attempts: int,
    window_seconds: int,
    namespace: str = "auth",
) -> RateLimiter:
    del namespace
    return InMemoryRateLimiter(
        max_attempts,
        window_seconds,
        max_keys=_env_int("RATE_LIMIT_LOCAL_MAX_KEYS", 10_000),
    )


def _env_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except ValueError:
        return default
