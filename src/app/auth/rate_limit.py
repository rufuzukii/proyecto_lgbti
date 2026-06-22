from __future__ import annotations

from collections import defaultdict, deque
import logging
import os
import time
from uuid import uuid4

import redis
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)


class RateLimiter:
    def is_blocked(self, key: str) -> bool:
        raise NotImplementedError

    def record_failure(self, key: str) -> None:
        raise NotImplementedError

    def reset(self, key: str) -> None:
        raise NotImplementedError


class InMemoryRateLimiter(RateLimiter):
    def __init__(self, max_attempts: int, window_seconds: int) -> None:
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._attempts: dict[str, deque[float]] = defaultdict(deque)

    def _prune(self, key: str, now: float) -> None:
        attempts = self._attempts[key]
        while attempts and (now - attempts[0]) > self.window_seconds:
            attempts.popleft()

    def is_blocked(self, key: str) -> bool:
        now = time.time()
        self._prune(key, now)
        return len(self._attempts[key]) >= self.max_attempts

    def record_failure(self, key: str) -> None:
        now = time.time()
        self._prune(key, now)
        self._attempts[key].append(now)

    def reset(self, key: str) -> None:
        self._attempts.pop(key, None)


class RedisRateLimiter(RateLimiter):
    def __init__(
        self,
        *,
        client: redis.Redis,
        max_attempts: int,
        window_seconds: int,
        namespace: str,
    ) -> None:
        self.client = client
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self.namespace = namespace

    def is_blocked(self, key: str) -> bool:
        redis_key = self._redis_key(key)
        now = time.time()
        self._prune(redis_key, now)
        return int(self.client.zcard(redis_key)) >= self.max_attempts

    def record_failure(self, key: str) -> None:
        redis_key = self._redis_key(key)
        now = time.time()
        self._prune(redis_key, now)
        member = f"{now}:{uuid4().hex}"
        pipe = self.client.pipeline(transaction=True)
        pipe.zadd(redis_key, {member: now})
        pipe.expire(redis_key, self.window_seconds)
        pipe.execute()

    def reset(self, key: str) -> None:
        self.client.delete(self._redis_key(key))

    def _prune(self, redis_key: str, now: float) -> None:
        self.client.zremrangebyscore(redis_key, 0, now - self.window_seconds)

    def _redis_key(self, key: str) -> str:
        return f"rainbowlens:rate_limit:{self.namespace}:{key}"


def create_rate_limiter(
    *,
    max_attempts: int,
    window_seconds: int,
    namespace: str = "auth",
) -> RateLimiter:
    redis_url = (
        os.getenv("RATE_LIMIT_REDIS_URL")
        or os.getenv("REDIS_URL")
        or ""
    ).strip()
    if not redis_url:
        return InMemoryRateLimiter(max_attempts, window_seconds)

    client = redis.Redis.from_url(redis_url)
    try:
        client.ping()
    except RedisError:
        logger.exception("rate_limiter_redis_unavailable")
        return InMemoryRateLimiter(max_attempts, window_seconds)

    return RedisRateLimiter(
        client=client,
        max_attempts=max_attempts,
        window_seconds=window_seconds,
        namespace=namespace,
    )
