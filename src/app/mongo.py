from __future__ import annotations

from functools import lru_cache
from typing import Any

from pymongo import MongoClient

from app.config import get_mongo_config


@lru_cache(maxsize=1)
def get_mongo_client() -> MongoClient:
    """Return the single Mongo client shared by the current process."""
    config = get_mongo_config()
    return MongoClient(
        config.dsn(),
        serverSelectionTimeoutMS=config.server_selection_timeout_ms,
        connectTimeoutMS=config.server_selection_timeout_ms,
        socketTimeoutMS=config.server_selection_timeout_ms,
        retryReads=True,
        retryWrites=True,
    )


def get_mongo_database() -> Any:
    config = get_mongo_config()
    return get_mongo_client()[config.database]


def get_mongo_collection(name: str) -> Any:
    return get_mongo_database()[name]
