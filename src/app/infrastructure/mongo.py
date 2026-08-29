from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

from pymongo import MongoClient

from app.core.config import get_mongo_config


@lru_cache(maxsize=1)
def get_mongo_client() -> MongoClient:
    """Return the single Mongo client shared by the current process."""
    config = get_mongo_config()
    return MongoClient(
        config.dsn(),
        serverSelectionTimeoutMS=config.server_selection_timeout_ms,
        connectTimeoutMS=config.server_selection_timeout_ms,
        socketTimeoutMS=_env_int("MONGO_SOCKET_TIMEOUT_MS", 10_000),
        maxPoolSize=_env_int("MONGO_MAX_POOL_SIZE", 12),
        minPoolSize=0,
        maxIdleTimeMS=_env_int("MONGO_MAX_IDLE_TIME_MS", 60_000),
        waitQueueTimeoutMS=_env_int("MONGO_WAIT_QUEUE_TIMEOUT_MS", 2_000),
        retryReads=True,
        retryWrites=True,
    )


def get_mongo_database() -> Any:
    config = get_mongo_config()
    return get_mongo_client()[config.database]


def get_mongo_collection(name: str) -> Any:
    return get_mongo_database()[name]


def _env_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except ValueError:
        return default
