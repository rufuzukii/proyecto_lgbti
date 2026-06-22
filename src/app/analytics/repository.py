from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any

import psycopg
from psycopg.rows import dict_row
from pymongo import MongoClient

from app.cache import cache
from app.config import get_mongo_config
from app.import_to_db.import_log import _resolve_postgres_dsn

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FraIndicator:
    code: str
    category: str
    specific_category: str
    question: str

    @property
    def label(self) -> str:
        return f"{self.category} · {self.specific_category} · {self.question}"


@cache.memoize()
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
        with psycopg.connect(_resolve_postgres_dsn(), row_factory=dict_row) as conn:
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


@cache.memoize()
def get_fra_indicator_answers(code: str) -> dict[str, Any] | None:
    clean_code = str(code or "").strip()
    if not clean_code:
        return None
    try:
        config = get_mongo_config()
        with MongoClient(config.dsn(), serverSelectionTimeoutMS=5000) as client:
            return client[config.database]["Indicator_fra"].find_one(
                {"code": clean_code},
                {"_id": 0},
            )
    except Exception:
        logger.exception("fra_indicator_values_read_failed", extra={"code": clean_code})
        return None


@cache.memoize()
def get_latest_ilga_document() -> dict[str, Any] | None:
    try:
        config = get_mongo_config()
        with MongoClient(config.dsn(), serverSelectionTimeoutMS=5000) as client:
            return client[config.database]["Indicator_ilga"].find_one(
                {"dataset": "ilga_rainbow_map"},
                {"_id": 0},
                sort=[("year", -1)],
            )
    except Exception:
        logger.exception("ilga_latest_read_failed")
        return None


def invalidate_analytics_cache() -> None:
    cache.clear()
