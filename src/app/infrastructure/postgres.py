from __future__ import annotations

import atexit
import os
from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache
from typing import Any

from psycopg import Connection
from psycopg_pool import ConnectionPool

from app.core.config import get_postgres_connect_timeout, get_postgres_dsn


@lru_cache(maxsize=1)
def get_postgres_pool() -> ConnectionPool:
    """Devuelve el pool PostgreSQL diferido, local al proceso y ajustado a los hilos de Render."""
    return ConnectionPool(
        conninfo=get_postgres_dsn(),
        min_size=0,
        max_size=_env_int("POSTGRES_POOL_MAX_SIZE", 6),
        max_idle=_env_float("POSTGRES_POOL_MAX_IDLE_SECONDS", 60.0),
        timeout=_env_float("POSTGRES_POOL_WAIT_TIMEOUT_SECONDS", 3.0),
        kwargs={"connect_timeout": get_postgres_connect_timeout()},
        open=False,
        name="rainbowlens-postgres",
    )


@contextmanager
def postgres_connection(*, row_factory: Any | None = None) -> Iterator[Connection[Any]]:
    """Presta una conexión y restaura su formato de filas antes de devolverla al pool."""
    pool = get_postgres_pool()
    if pool.closed:
        pool.open(wait=False)
    with pool.connection() as connection:
        previous_factory = connection.row_factory
        if row_factory is not None:
            connection.row_factory = row_factory
        try:
            yield connection
        finally:
            connection.row_factory = previous_factory


def close_postgres_pool() -> None:
    if get_postgres_pool.cache_info().currsize:
        get_postgres_pool().close()
    get_postgres_pool.cache_clear()


def _env_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return max(0.1, float(os.getenv(name, str(default))))
    except ValueError:
        return default


atexit.register(close_postgres_pool)
