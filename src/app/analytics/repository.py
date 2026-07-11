from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import logging
import os
from typing import Any

import psycopg
from psycopg.rows import dict_row
from pymongo import MongoClient
from pymongo.errors import AutoReconnect, ConfigurationError, NetworkTimeout

from app.cache import cache
from app.config import get_mongo_config, get_postgres_connect_timeout, get_postgres_dsn
from app.errors import DatabaseUnavailableError

logger = logging.getLogger(__name__)
ANALYTICS_CACHE_TIMEOUT_SECONDS = int(os.getenv("ANALYTICS_CACHE_TIMEOUT_SECONDS", "3600"))
MONGO_UNAVAILABLE_ERRORS = (AutoReconnect, ConfigurationError, NetworkTimeout)


@dataclass(frozen=True) # frozen=true significa que el objeto no puede ser modificado
class FraIndicator:
    code: str
    category: str
    specific_category: str
    question: str

    @property
    def label(self) -> str:
        return f"{self.category} · {self.specific_category} · {self.question}"


@dataclass(frozen=True)
class FelgtbiIndicator:
    code: str
    year: int
    category: str
    specific_category: str
    topic: str
    question: str
    description: str
    report_title: str
    report_type: str
    value: float | None = None

    @property
    def label(self) -> str:
        return f"{self.year} - {self.report_title} - {self.description or self.question}"


def assert_analytics_databases_available() -> None:
    try:
        with psycopg.connect(
            get_postgres_dsn(),
            connect_timeout=get_postgres_connect_timeout(),
        ) as conn:
            conn.execute("SELECT 1").fetchone()
    except psycopg.OperationalError as exc:
        raise DatabaseUnavailableError("PostgreSQL") from exc

    try:
        client, _database = _mongo_client_and_database()
        client.admin.command("ping")
    except MONGO_UNAVAILABLE_ERRORS as exc:
        raise DatabaseUnavailableError("MongoDB") from exc


@cache.memoize(timeout=ANALYTICS_CACHE_TIMEOUT_SECONDS)
def get_categories() -> list[str]:
    query = """
        SELECT name
        FROM public.categories
        ORDER BY name
    """
    try:
        with psycopg.connect(
            get_postgres_dsn(),
            row_factory=dict_row,
            connect_timeout=get_postgres_connect_timeout(),
        ) as conn:
            rows = conn.execute(query).fetchall()
    except Exception:
        logger.exception("categories_read_failed")
        return []

    return [str(row["name"]) for row in rows if row.get("name")]


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
            get_postgres_dsn(),
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
            get_postgres_dsn(),
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
def get_felgtbi_categories() -> list[str]:
    try:
        _ensure_analytics_indexes()
        mongo_categories = {
            str(category).strip()
            for category in _mongo_collection("Indicator_felgtbi").distinct(
                "category",
                {"source": "felgtbi_estado_lgtbi"},
            )
            if str(category).strip()
        }
    except Exception:
        logger.exception("felgtbi_categories_read_failed")
        return []

    postgres_categories = get_categories()
    ordered = [category for category in postgres_categories if category in mongo_categories]
    remaining = sorted(mongo_categories.difference(ordered))
    return [*ordered, *remaining]


@cache.memoize(timeout=ANALYTICS_CACHE_TIMEOUT_SECONDS)
def get_felgtbi_years(category: str | None = None) -> list[int]:
    query: dict[str, Any] = {"source": "felgtbi_estado_lgtbi"}
    clean_category = str(category or "").strip()
    if clean_category:
        query["category"] = clean_category
    try:
        _ensure_analytics_indexes()
        years = _mongo_collection("Indicator_felgtbi").distinct("year", query)
    except Exception:
        logger.exception("felgtbi_years_read_failed", extra={"category": clean_category})
        return []

    clean_years: list[int] = []
    for year in years:
        try:
            clean_years.append(int(year))
        except (TypeError, ValueError):
            continue
    return sorted(set(clean_years), reverse=True)


@cache.memoize(timeout=ANALYTICS_CACHE_TIMEOUT_SECONDS)
def get_felgtbi_indicators_by_category(
    category: str,
    year: int | str | None = None,
) -> list[FelgtbiIndicator]:
    clean_category = str(category or "").strip()
    if not clean_category:
        return []
    query: dict[str, Any] = {"source": "felgtbi_estado_lgtbi", "category": clean_category}
    if year is not None and str(year).strip():
        try:
            query["year"] = int(year)
        except (TypeError, ValueError):
            return []
    try:
        _ensure_analytics_indexes()
        rows = _mongo_collection("Indicator_felgtbi").find(
            query,
            {
                "_id": 0,
                "code": 1,
                "year": 1,
                "category": 1,
                "specific_category": 1,
                "topic": 1,
                "topics": 1,
                "question": 1,
                "description": 1,
                "subsection_title": 1,
                "report_title": 1,
                "report_type": 1,
                "answers": 1,
            },
            sort=[("year", -1), ("report_title", 1), ("topic", 1), ("description", 1)],
        )
        return [
            FelgtbiIndicator(
                code=str(row.get("code") or ""),
                year=int(row.get("year") or 0),
                category=str(row.get("category") or ""),
                specific_category=str(row.get("specific_category") or ""),
                topic=str(row.get("topic") or ""),
                question=str(row.get("subsection_title") or row.get("question") or ""),
                description=str(row.get("description") or row.get("question") or ""),
                report_title=str(row.get("report_title") or ""),
                report_type=str(row.get("report_type") or ""),
                value=_first_percentage(row.get("answers")),
            )
            for row in rows
            if row.get("code")
        ]
    except Exception:
        logger.exception("felgtbi_category_read_failed", extra={"category": clean_category})
        return []


@cache.memoize(timeout=ANALYTICS_CACHE_TIMEOUT_SECONDS)
def get_felgtbi_indicator_answers(code: str) -> dict[str, Any] | None:
    clean_code = str(code or "").strip()
    if not clean_code:
        return None
    try:
        _ensure_analytics_indexes()
        return _mongo_collection("Indicator_felgtbi").find_one(
            {"source": "felgtbi_estado_lgtbi", "code": clean_code},
            {
                "_id": 0,
                "source": 1,
                "code": 1,
                "year": 1,
                "report_title": 1,
                "report_type": 1,
                "category": 1,
                "specific_category": 1,
                "topic": 1,
                "topics": 1,
                "question": 1,
                "description": 1,
                "section_title": 1,
                "subsection_title": 1,
                "figure_caption": 1,
                "figure": 1,
                "paragraphs": 1,
                "content_html": 1,
                "data_points": 1,
                "visual_context": 1,
                "sample_size": 1,
                "fieldwork": 1,
                "answers": 1,
            },
        )
    except Exception:
        logger.exception("felgtbi_indicator_values_read_failed", extra={"code": clean_code})
        return None


@cache.memoize(timeout=ANALYTICS_CACHE_TIMEOUT_SECONDS)
def get_ilga_years() -> list[int]:
    try:
        _ensure_analytics_indexes()
        years = _mongo_collection("Indicator_ilga").distinct(
            "year",
            {"dataset": "ilga_rainbow_map"},
        )
    except Exception:
        logger.exception("ilga_years_read_failed")
        return []

    clean_years = []
    for year in years:
        try:
            clean_years.append(int(year))
        except (TypeError, ValueError):
            continue
    return sorted(clean_years, reverse=True)


@cache.memoize(timeout=ANALYTICS_CACHE_TIMEOUT_SECONDS)
def get_ilga_document_by_year(year: int | str | None) -> dict[str, Any] | None:
    try:
        clean_year = int(year) if year is not None and str(year).strip() else None
    except (TypeError, ValueError):
        clean_year = None

    if clean_year is None:
        return get_latest_ilga_document()

    try:
        _ensure_analytics_indexes()
        return _mongo_collection("Indicator_ilga").find_one(
            {"dataset": "ilga_rainbow_map", "year": clean_year},
            {"_id": 0, "dataset": 1, "year": 1, "countries": 1},
        )
    except Exception:
        logger.exception("ilga_year_read_failed", extra={"year": clean_year})
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


@cache.memoize(timeout=ANALYTICS_CACHE_TIMEOUT_SECONDS)
def get_latest_ilga_criteria_categories() -> list[str]:
    document = get_latest_ilga_document()
    if not isinstance(document, dict):
        return []

    categories = set()
    for country in document.get("countries", []):
        if not isinstance(country, dict):
            continue
        criteria = country.get("criteria")
        if not isinstance(criteria, list):
            continue
        for criterion in criteria:
            if not isinstance(criterion, dict):
                continue
            category = str(criterion.get("category") or "").strip()
            if category:
                categories.add(category)
    return sorted(categories)


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


def _first_percentage(answers: Any) -> float | None:
    if not isinstance(answers, list):
        return None
    for answer in answers:
        if not isinstance(answer, dict):
            continue
        value = answer.get("percentage", answer.get("value"))
        if isinstance(value, (int, float)):
            return float(value)
    return None


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
    _mongo_collection("Indicator_felgtbi").create_index("code", background=True)
    _mongo_collection("Indicator_felgtbi").create_index(
        [("year", -1), ("category", 1), ("specific_category", 1)],
        background=True,
    )
    _mongo_collection("Indicator_felgtbi").create_index(
        [("source", 1), ("report_type", 1)],
        background=True,
    )
