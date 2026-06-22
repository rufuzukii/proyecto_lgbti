from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import logging
import os
from typing import Any

import psycopg
from psycopg.rows import dict_row
from pymongo import MongoClient

from app.cache import cache
from app.config import get_mongo_config, get_postgres_connect_timeout
from app.import_to_db.import_log import _resolve_postgres_dsn

logger = logging.getLogger(__name__)
ANALYTICS_CACHE_TIMEOUT_SECONDS = int(os.getenv("ANALYTICS_CACHE_TIMEOUT_SECONDS", "3600"))


@dataclass(frozen=True)
class FraIndicator:
    code: str
    category: str
    specific_category: str
    question: str

    @property
    def label(self) -> str:
        return f"{self.category} · {self.specific_category} · {self.question}"


@cache.memoize(timeout=ANALYTICS_CACHE_TIMEOUT_SECONDS)
def get_fra_categories() -> list[str]:
    query = """
        SELECT DISTINCT c.name AS category
        FROM public.categories c
        JOIN public.indicators i ON i.category_id = c.id
        WHERE i.code IS NOT NULL
        ORDER BY c.name
    """
    try:
        with psycopg.connect(
            _resolve_postgres_dsn(),
            row_factory=dict_row,
            connect_timeout=get_postgres_connect_timeout(),
        ) as conn:
            rows = conn.execute(query).fetchall()
    except Exception:
        logger.exception("fra_categories_read_failed")
        return []

    return [str(row["category"]) for row in rows if row.get("category")]


@cache.memoize(timeout=ANALYTICS_CACHE_TIMEOUT_SECONDS)
def get_fra_indicators() -> list[FraIndicator]:
    query = """
        SELECT
            i.code,
            c.name AS category,
            COALESCE(i.specific_category, '') AS specific_category,
            i.question
        FROM public.indicators i
        JOIN public.categories c ON c.id = i.category_id
        WHERE i.code IS NOT NULL
        ORDER BY c.name, i.specific_category, i.question
    """
    try:
        with psycopg.connect(
            _resolve_postgres_dsn(),
            row_factory=dict_row,
            connect_timeout=get_postgres_connect_timeout(),
        ) as conn:
            rows = conn.execute(query).fetchall()
    except Exception:
        logger.exception("fra_indicator_catalog_read_failed")
        return []

    return [
        FraIndicator(
            code=row["code"],
            category=row["category"],
            specific_category=row["specific_category"],
            question=row["question"],
        )
        for row in rows
    ]


@cache.memoize(timeout=ANALYTICS_CACHE_TIMEOUT_SECONDS)
def get_fra_mongo_indicators_by_category(category: str) -> list[FraIndicator]:
    clean_category = str(category or "").strip()
    if not clean_category:
        return []
    try:
        _ensure_analytics_indexes()
        rows = _mongo_collection("Indicator_fra").find(
            {"category": clean_category},
            {
                "_id": 0,
                "code": 1,
                "category": 1,
                "specific_category": 1,
                "question": 1,
            },
            sort=[("specific_category", 1), ("question", 1), ("code", 1)],
        )
        return [
            FraIndicator(
                code=str(row.get("code") or ""),
                category=str(row.get("category") or ""),
                specific_category=str(row.get("specific_category") or ""),
                question=str(row.get("question") or ""),
            )
            for row in rows
            if row.get("code")
        ]
    except Exception:
        logger.exception("fra_mongo_category_read_failed", extra={"category": clean_category})
        return []


@cache.memoize(timeout=ANALYTICS_CACHE_TIMEOUT_SECONDS)
def get_fra_indicator_answers(code: str) -> dict[str, Any] | None:
    clean_code = str(code or "").strip()
    if not clean_code:
        return None
    try:
        _ensure_analytics_indexes()
        return _mongo_collection("Indicator_fra").find_one(
            {"code": clean_code},
            {
                "_id": 0,
                "code": 1,
                "category": 1,
                "specific_category": 1,
                "answers": 1,
            },
        )
    except Exception:
        logger.exception("fra_indicator_values_read_failed", extra={"code": clean_code})
        return None


@cache.memoize(timeout=ANALYTICS_CACHE_TIMEOUT_SECONDS)
def get_latest_ilga_document() -> dict[str, Any] | None:
    try:
        _ensure_analytics_indexes()
        return _mongo_collection("Indicator_ilga").find_one(
            {"dataset": "ilga_rainbow_map"},
            {"_id": 0, "dataset": 1, "year": 1, "countries": 1},
            sort=[("year", -1)],
        )
    except Exception:
        logger.exception("ilga_latest_read_failed")
        return None


def invalidate_analytics_cache() -> None:
    cache.clear()


@lru_cache(maxsize=1)
def _mongo_client_and_database() -> tuple[MongoClient, str]:
    config = get_mongo_config()
    client = MongoClient(
        config.dsn(),
        serverSelectionTimeoutMS=config.server_selection_timeout_ms,
        connectTimeoutMS=config.server_selection_timeout_ms,
        socketTimeoutMS=config.server_selection_timeout_ms,
    )
    return client, config.database


def _mongo_collection(name: str):
    client, database = _mongo_client_and_database()
    return client[database][name]


@lru_cache(maxsize=1)
def _ensure_analytics_indexes() -> None:
    _mongo_collection("Indicator_fra").create_index("code", background=True)
    _mongo_collection("Indicator_fra").create_index(
        [("category", 1), ("specific_category", 1), ("question", 1)],
        background=True,
    )
    _mongo_collection("Indicator_ilga").create_index(
        [("dataset", 1), ("year", -1)],
        background=True,
    )
