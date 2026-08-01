from __future__ import annotations

import hashlib
import logging
import os
import re
import time
from dataclasses import dataclass
from functools import lru_cache
from threading import Lock
from typing import Any, cast

import psycopg
from psycopg.rows import dict_row
from pymongo.errors import AutoReconnect, ConfigurationError, NetworkTimeout

from app.cache import cache
from app.config import get_mongo_config, get_postgres_connect_timeout, get_postgres_dsn
from app.errors import DatabaseUnavailableError
from app.import_to_db.felgtbi.semantics import sanitize_report_document
from app.mongo import get_mongo_client

logger = logging.getLogger(__name__)
ANALYTICS_CACHE_TIMEOUT_SECONDS = int(os.getenv("ANALYTICS_CACHE_TIMEOUT_SECONDS", "3600"))
ANALYTICS_HEALTH_CHECK_TTL_SECONDS = int(os.getenv("ANALYTICS_HEALTH_CHECK_TTL_SECONDS", "15"))
SPAIN_COLLECTIONS_CACHE_TIMEOUT_SECONDS = int(
    os.getenv("SPAIN_COLLECTIONS_CACHE_TIMEOUT_SECONDS", "300")
)
MONGO_UNAVAILABLE_ERRORS = (AutoReconnect, ConfigurationError, NetworkTimeout)
COUNTRY_LGBTI_STATUS_COLLECTION = "country_lgbti_status"
DEFAULT_FELGTBI_COLLECTION = "Indicator_felgtbi"
FELGTBI_SOURCE_CODE = "felgtbi_estado_lgtbi"
SPAIN_COLLECTION_LABELS = {
    DEFAULT_FELGTBI_COLLECTION: ("Estado LGBTIQ+ en España", "LGBTIQ+ status in Spain"),
}
SPAIN_COLLECTION_INCLUDE_TOKENS = ("felgtbi", "lgtbi", "spain", "espana", "españa", "estado_lgtbi")
SPAIN_COLLECTION_EXCLUDED_PREFIXES = (
    "system.",
    "_",
    "tmp",
    "temp",
    "audit",
    "migration",
    "migrations",
)
SPAIN_COLLECTION_EXCLUDED_NAMES = {
    "fs.files",
    "fs.chunks",
    "indicator_fra",
    "indicator_ilga",
    "schema_migrations",
    "migration_history",
    COUNTRY_LGBTI_STATUS_COLLECTION,
}
SPAIN_FILENAME_FIELD_PATHS = (
    "original_filename",
    "filename",
    "file_name",
    "source_file",
    "metadata.original_filename",
    "metadata.filename",
    "metadata.file_name",
    "metadata.source_file",
    "file_metadata.original_filename",
    "file_metadata.filename",
    "file_metadata.file_name",
    "file_metadata.source_file",
    "upload.original_filename",
    "upload.filename",
    "upload.file_name",
    "upload.source_file",
)
SPAIN_DOCUMENT_PROCESSED_STATUSES = {
    "processed",
    "procesado",
    "approved",
    "aprobado",
    "imported",
    "importado",
    "completed",
    "complete",
    "ready",
    "ok",
    "success",
    "active",
    "available",
}
SPAIN_DOCUMENT_BLOCKED_STATUSES = {
    "pending",
    "pendiente",
    "queued",
    "processing",
    "procesando",
    "running",
    "failed",
    "error",
    "invalid",
    "rejected",
    "rechazado",
}
_health_check_lock = Lock()
_health_check_ok_until = 0.0
_section_cache_metrics_lock = Lock()
_section_cache_requests = 0
_section_cache_hits = 0


@dataclass(frozen=True)  # frozen=true significa que el objeto no puede ser modificado
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


@dataclass(frozen=True)
class FelgtbiDocument:
    id: str
    label: str
    original_filename: str
    year: int | None
    report_title: str
    report_type: str
    section_count: int
    filter_fields: tuple[tuple[str, Any], ...]


@dataclass(frozen=True)
class SpainCollection:
    name: str
    label_es: str
    label_en: str


def assert_analytics_databases_available() -> None:
    global _health_check_ok_until

    now = time.monotonic()
    if now < _health_check_ok_until:
        return

    with _health_check_lock:
        now = time.monotonic()
        if now < _health_check_ok_until:
            return

        _assert_analytics_databases_available_uncached()
        _health_check_ok_until = now + max(0, ANALYTICS_HEALTH_CHECK_TTL_SECONDS)


def _assert_analytics_databases_available_uncached() -> None:
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
            row_factory=cast(Any, dict_row),
            connect_timeout=get_postgres_connect_timeout(),
        ) as conn:
            rows = conn.execute(query).fetchall()
    except Exception:
        logger.exception("categories_read_failed")
        return []

    rows = cast(list[dict[str, Any]], rows)
    return [str(row["name"]) for row in rows if row.get("name")]


@cache.memoize(timeout=ANALYTICS_CACHE_TIMEOUT_SECONDS)
def get_fra_categories() -> list[str]:
    try:
        categories = _mongo_collection("Indicator_fra").distinct(
            "category",
            {"code": {"$exists": True, "$ne": ""}},
        )
    except Exception:
        logger.exception("fra_categories_read_failed")
        return []
    return sorted(
        {str(category).strip() for category in categories if str(category or "").strip()},
        key=str.casefold,
    )


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
            row_factory=cast(Any, dict_row),
            connect_timeout=get_postgres_connect_timeout(),
        ) as conn:
            rows = conn.execute(query).fetchall()
    except Exception:
        logger.exception("fra_indicator_catalog_read_failed")
        return []

    rows = cast(list[dict[str, Any]], rows)
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
def get_fra_indicator_answers(code: str, category: str | None = None) -> dict[str, Any] | None:
    clean_code = str(code or "").strip()
    if not clean_code:
        return None
    query: dict[str, Any] = {"code": clean_code}
    clean_category = str(category or "").strip()
    if clean_category:
        query["category"] = clean_category
    try:
        documents = list(
            _mongo_collection("Indicator_fra").find(
                query,
                {
                    "_id": 0,
                    "code": 1,
                    "category": 1,
                    "specific_category": 1,
                    "question": 1,
                    "answers": 1,
                },
            )
        )
        if not documents:
            return None

        document = dict(documents[0])
        document["answers"] = [
            answer
            for item in documents
            for answer in (item.get("answers") or [])
            if isinstance(answer, dict)
        ]
        if len(documents) > 1:
            logger.info(
                "fra_indicator_documents_merged code=%s documents=%d answers=%d",
                clean_code,
                len(documents),
                len(document["answers"]),
                extra={
                    "indicator_code": clean_code,
                    "document_count": len(documents),
                    "answer_count": len(document["answers"]),
                },
            )
        return document
    except Exception:
        logger.exception("fra_indicator_values_read_failed", extra={"code": clean_code})
        return None


@cache.memoize(timeout=ANALYTICS_CACHE_TIMEOUT_SECONDS)
def get_fra_indicator_documents(codes: tuple[str, ...]) -> list[dict[str, Any]]:
    """Load and merge several FRA indicators with one MongoDB query."""
    clean_codes = tuple(
        sorted({str(code or "").strip() for code in codes if str(code or "").strip()})
    )
    if not clean_codes:
        return []
    try:
        documents = list(
            _mongo_collection("Indicator_fra").find(
                {"code": {"$in": list(clean_codes)}},
                {
                    "_id": 0,
                    "code": 1,
                    "category": 1,
                    "specific_category": 1,
                    "question": 1,
                    "answers": 1,
                },
            )
        )
    except Exception:
        logger.exception("fra_radar_indicators_read_failed", extra={"codes": clean_codes})
        return []

    merged: dict[str, dict[str, Any]] = {}
    for document in documents:
        code = str(document.get("code") or "").strip()
        if not code:
            continue
        target = merged.setdefault(
            code,
            {
                "code": code,
                "category": document.get("category"),
                "specific_category": document.get("specific_category"),
                "question": document.get("question"),
                "answers": [],
            },
        )
        target["answers"].extend(
            answer for answer in (document.get("answers") or []) if isinstance(answer, dict)
        )
    return [merged[code] for code in clean_codes if code in merged]


@cache.memoize(timeout=ANALYTICS_CACHE_TIMEOUT_SECONDS)
def get_fra_years(code: str | None = None) -> list[int]:
    query: dict[str, Any] = {}
    clean_code = str(code or "").strip()
    if clean_code:
        query["code"] = clean_code
    try:
        raw_dates = _mongo_collection("Indicator_fra").distinct("answers.date", query)
    except Exception:
        logger.exception("fra_years_read_failed", extra={"code": clean_code})
        return []

    years: set[int] = set()
    for raw_date in raw_dates:
        text = str(raw_date or "")
        for token in text.replace("/", "-").split("-"):
            token = token.strip()
            if token.isdigit() and len(token) == 4:
                years.add(int(token))
    return sorted(years, reverse=True)


@cache.memoize(timeout=ANALYTICS_CACHE_TIMEOUT_SECONDS)
def get_ilga_criteria_categories_by_year(year: int | str | None = None) -> list[str]:
    document = get_ilga_document_by_year(year)
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


@cache.memoize(timeout=ANALYTICS_CACHE_TIMEOUT_SECONDS)
def get_ilga_criteria_by_year(
    year: int | str | None = None,
    category: str | None = None,
) -> list[dict[str, Any]]:
    document = get_ilga_document_by_year(year)
    if not isinstance(document, dict):
        return []

    clean_category = str(category or "").strip()
    criteria_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for country in document.get("countries", []):
        if not isinstance(country, dict):
            continue
        criteria = country.get("criteria")
        if not isinstance(criteria, list):
            continue
        for criterion in criteria:
            if not isinstance(criterion, dict):
                continue
            criterion_category = str(criterion.get("category") or "").strip()
            if clean_category and criterion_category != clean_category:
                continue
            indicator = str(criterion.get("indicator") or "").strip()
            if not indicator:
                continue
            key = (criterion_category, indicator)
            criteria_by_key.setdefault(
                key,
                {
                    "category": criterion_category,
                    "indicator": indicator,
                    "weight": criterion.get("weight"),
                    "description": "",
                },
            )
    return list(criteria_by_key.values())


@cache.memoize(timeout=SPAIN_COLLECTIONS_CACHE_TIMEOUT_SECONDS)
def get_spain_available_collections() -> list[SpainCollection]:
    try:
        client, database_name = _mongo_client_and_database()
        collection_names = [
            str(name or "").strip()
            for name in client[database_name].list_collection_names()
            if str(name or "").strip()
        ]
    except Exception:
        logger.exception("spain_collections_read_failed")
        return []

    valid_names = [
        name
        for name in collection_names
        if not _is_technical_collection_name(name)
        and _collection_has_spain_interface_documents(name)
    ]
    valid_names = sorted(set(valid_names), key=_spain_collection_sort_key)
    collections = [
        SpainCollection(
            name=name,
            label_es=_spain_collection_label(name, language="es"),
            label_en=_spain_collection_label(name, language="en"),
        )
        for name in valid_names
    ]
    logger.debug(
        "spain_collections_discovered",
        extra={
            "mongo_collection_count": len(collection_names),
            "valid_spain_collection_count": len(valid_names),
            "option_count": len(collections),
        },
    )
    return collections


def get_spain_collection_options(language: str = "es") -> list[dict[str, str]]:
    clean_language = language if language in {"es", "en"} else "es"
    options = []
    for collection in get_spain_available_collections():
        label = collection.label_en if clean_language == "en" else collection.label_es
        options.append({"label": label, "value": collection.name})
    return options


@cache.memoize(timeout=ANALYTICS_CACHE_TIMEOUT_SECONDS)
def get_felgtbi_documents(collection_name: str | None = None) -> list[FelgtbiDocument]:
    resolved_collection = _resolve_spain_collection_name(collection_name)
    if not resolved_collection:
        return []
    try:
        rows = _mongo_collection(resolved_collection).find(
            _spain_collection_query(resolved_collection),
            _spain_document_projection(),
            sort=[
                ("year", -1),
                ("original_filename", 1),
                ("filename", 1),
                ("file_name", 1),
                ("source_file", 1),
                ("report_title", 1),
                ("page", 1),
                ("code", 1),
            ],
        )
        documents = _group_spain_documents(rows, resolved_collection)
    except Exception:
        logger.exception(
            "felgtbi_documents_read_failed",
            extra={"collection": resolved_collection},
        )
        return []
    return _deduplicate_spain_document_labels(documents)


def get_felgtbi_document_options(collection_name: str | None = None) -> list[dict[str, str]]:
    return [
        {"label": document.label, "value": document.id, "title": document.label}
        for document in get_felgtbi_documents(collection_name)
    ]


@cache.memoize(timeout=ANALYTICS_CACHE_TIMEOUT_SECONDS)
def get_felgtbi_document_years(
    document_id: str | None = None,
    collection_name: str | None = None,
) -> list[int]:
    resolved_collection = _resolve_spain_collection_name(collection_name)
    document = _resolve_felgtbi_document(document_id, resolved_collection)
    if not resolved_collection or document is None:
        return []

    query = _spain_document_query(resolved_collection, document)
    try:
        years = _mongo_collection(resolved_collection).distinct("year", query)
    except Exception:
        logger.exception(
            "felgtbi_document_years_read_failed",
            extra={"document": str(document_id or ""), "collection": resolved_collection},
        )
        return []

    clean_years: list[int] = []
    for year in years:
        try:
            clean_years.append(int(year))
        except TypeError, ValueError:
            continue
    return sorted(set(clean_years), reverse=True)


@cache.memoize(timeout=ANALYTICS_CACHE_TIMEOUT_SECONDS)
def get_felgtbi_indicators_by_document(
    document_id: str,
    year: int | str | None = None,
    collection_name: str | None = None,
) -> list[FelgtbiIndicator]:
    resolved_collection = _resolve_spain_collection_name(collection_name)
    document = _resolve_felgtbi_document(document_id, resolved_collection)
    if not resolved_collection or document is None:
        return []

    query = _spain_document_query(resolved_collection, document)
    if year is not None and str(year).strip():
        try:
            query["year"] = int(year)
        except TypeError, ValueError:
            return []
    try:
        rows = _mongo_collection(resolved_collection).find(
            query,
            _spain_navigation_projection(),
            sort=[
                ("year", -1),
                ("page", 1),
                ("section_title", 1),
                ("topic", 1),
                ("description", 1),
                ("code", 1),
            ],
        )
        return [_row_to_felgtbi_indicator(row) for row in rows if _has_navigable_spain_section(row)]
    except Exception:
        logger.exception(
            "felgtbi_document_read_failed",
            extra={"document": str(document_id or ""), "collection": resolved_collection},
        )
        return []


@cache.memoize(timeout=ANALYTICS_CACHE_TIMEOUT_SECONDS)
def get_felgtbi_categories(collection_name: str | None = None) -> list[str]:
    resolved_collection = _resolve_spain_collection_name(collection_name)
    if not resolved_collection:
        return []
    try:
        mongo_categories = {
            str(category).strip()
            for category in _mongo_collection(resolved_collection).distinct(
                "category",
                _spain_collection_query(resolved_collection),
            )
            if str(category).strip()
        }
    except Exception:
        logger.exception(
            "felgtbi_categories_read_failed",
            extra={"collection": resolved_collection},
        )
        return []

    return sorted(mongo_categories)


@cache.memoize(timeout=ANALYTICS_CACHE_TIMEOUT_SECONDS)
def get_felgtbi_years(
    category: str | None = None,
    collection_name: str | None = None,
) -> list[int]:
    resolved_collection = _resolve_spain_collection_name(collection_name)
    if not resolved_collection:
        return []
    query = _spain_collection_query(resolved_collection)
    clean_category = str(category or "").strip()
    if clean_category:
        query["category"] = clean_category
    try:
        years = _mongo_collection(resolved_collection).distinct("year", query)
    except Exception:
        logger.exception(
            "felgtbi_years_read_failed",
            extra={"category": clean_category, "collection": resolved_collection},
        )
        return []

    clean_years: list[int] = []
    for year in years:
        try:
            clean_years.append(int(year))
        except TypeError, ValueError:
            continue
    return sorted(set(clean_years), reverse=True)


@cache.memoize(timeout=ANALYTICS_CACHE_TIMEOUT_SECONDS)
def get_felgtbi_indicators_by_category(
    category: str,
    year: int | str | None = None,
    collection_name: str | None = None,
) -> list[FelgtbiIndicator]:
    resolved_collection = _resolve_spain_collection_name(collection_name)
    if not resolved_collection:
        return []
    clean_category = str(category or "").strip()
    if not clean_category:
        return []
    query = _spain_collection_query(resolved_collection)
    query["category"] = clean_category
    if year is not None and str(year).strip():
        try:
            query["year"] = int(year)
        except TypeError, ValueError:
            return []
    try:
        rows = _mongo_collection(resolved_collection).find(
            query,
            _spain_navigation_projection(),
            sort=[("year", -1), ("report_title", 1), ("topic", 1), ("description", 1)],
        )
        return [_row_to_felgtbi_indicator(row) for row in rows if _has_navigable_spain_section(row)]
    except Exception:
        logger.exception(
            "felgtbi_category_read_failed",
            extra={"category": clean_category, "collection": resolved_collection},
        )
        return []


def get_felgtbi_indicator_answers(
    code: str,
    collection_name: str | None = None,
    *,
    document_id: str | None = None,
) -> dict[str, Any] | None:
    resolved_collection = _resolve_spain_collection_name(collection_name)
    if not resolved_collection:
        return None
    clean_code = str(code or "").strip()
    if not clean_code:
        return None
    section_cache_key = _felgtbi_section_cache_key(
        resolved_collection,
        document_id,
        clean_code,
    )
    cached = cache.get(section_cache_key)
    if isinstance(cached, dict):
        hit_ratio = _record_section_cache_request(hit=True)
        logger.debug(
            "felgtbi_section_cache_hit",
            extra={
                "collection": resolved_collection,
                "document": str(document_id or ""),
                "code": clean_code,
                "cache_hit_ratio": hit_ratio,
                "mongo_query_count": 0,
            },
        )
        return cached
    hit_ratio = _record_section_cache_request(hit=False)
    document = _resolve_felgtbi_document(document_id, resolved_collection) if document_id else None
    if document_id and document is None:
        return None
    try:
        query = (
            _spain_document_query(resolved_collection, document)
            if document is not None
            else _spain_collection_query(resolved_collection)
        )
        query["code"] = clean_code
        started_at = time.perf_counter()
        result = _mongo_collection(resolved_collection).find_one(
            query,
            {
                "_id": 0,
                "source": 1,
                "source_document_id": 1,
                "original_filename": 1,
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
                "paragraphs_before_figure": 1,
                "paragraphs_after_figure": 1,
                "content_html": 1,
                "data_points": 1,
                "visual_context": 1,
                "page": 1,
                "schema_version": 1,
                "content_order": 1,
                "extraction": 1,
                "sample_size": 1,
                "fieldwork": 1,
                "answers": 1,
            },
        )
        query_ms = (time.perf_counter() - started_at) * 1000
        if result is None:
            return None
        processing_started_at = time.perf_counter()
        cleaned = sanitize_report_document(result)
        processing_ms = (time.perf_counter() - processing_started_at) * 1000
        serialization_started_at = time.perf_counter()
        payload_bytes = len(_json_dumps_stable(cleaned).encode("utf-8"))
        serialization_ms = (time.perf_counter() - serialization_started_at) * 1000
        cache.set(
            section_cache_key,
            cleaned,
            timeout=ANALYTICS_CACHE_TIMEOUT_SECONDS,
        )
        logger.debug(
            "felgtbi_section_loaded",
            extra={
                "collection": resolved_collection,
                "document": str(document_id or ""),
                "code": clean_code,
                "mongo_query_ms": round(query_ms, 2),
                "processing_ms": round(processing_ms, 2),
                "serialization_ms": round(serialization_ms, 2),
                "payload_bytes": payload_bytes,
                "mongo_query_count": 1,
                "cache_hit_ratio": hit_ratio,
            },
        )
        return cleaned
    except Exception:
        logger.exception(
            "felgtbi_indicator_values_read_failed",
            extra={
                "code": clean_code,
                "collection": resolved_collection,
                "document": str(document_id or ""),
            },
        )
        return None


@cache.memoize(timeout=ANALYTICS_CACHE_TIMEOUT_SECONDS)
def get_ilga_years() -> list[int]:
    try:
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
        except TypeError, ValueError:
            continue
    return sorted(clean_years, reverse=True)


@cache.memoize(timeout=ANALYTICS_CACHE_TIMEOUT_SECONDS)
def get_ilga_document_by_year(year: int | str | None) -> dict[str, Any] | None:
    try:
        clean_year = int(year) if year is not None and str(year).strip() else None
    except TypeError, ValueError:
        clean_year = None

    if clean_year is None:
        return get_latest_ilga_document()

    try:
        return _mongo_collection("Indicator_ilga").find_one(
            {"dataset": "ilga_rainbow_map", "year": clean_year},
            {"_id": 0, "dataset": 1, "year": 1, "countries": 1},
        )
    except Exception:
        logger.exception("ilga_year_read_failed", extra={"year": clean_year})
        return None


@cache.memoize(timeout=ANALYTICS_CACHE_TIMEOUT_SECONDS)
def get_ilga_history_documents() -> list[dict[str, Any]]:
    """Load the projected ILGA history once for temporal and combined analysis."""
    try:
        return list(
            _mongo_collection("Indicator_ilga").find(
                {"dataset": "ilga_rainbow_map"},
                {"_id": 0, "year": 1, "countries": 1},
                sort=[("year", 1)],
            )
        )
    except Exception:
        logger.exception("ilga_history_read_failed")
        return []


@cache.memoize(timeout=ANALYTICS_CACHE_TIMEOUT_SECONDS)
def get_latest_ilga_document() -> dict[str, Any] | None:
    try:
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


@cache.memoize(timeout=ANALYTICS_CACHE_TIMEOUT_SECONDS)
def get_country_lgbti_status_records(
    country_codes: tuple[str, ...],
    requested_year: int | None = None,
) -> list[dict[str, Any]]:
    clean_codes = []
    seen = set()
    for country_code in country_codes:
        clean_code = str(country_code or "").strip().upper()
        if clean_code and clean_code not in seen:
            seen.add(clean_code)
            clean_codes.append(clean_code)
    if not clean_codes:
        return []

    query: dict[str, Any] = {
        "country_code": {"$in": clean_codes},
        "active": True,
    }
    if requested_year is not None:
        query["year"] = {"$lte": int(requested_year)}

    try:
        rows = list(
            _mongo_collection(COUNTRY_LGBTI_STATUS_COLLECTION).find(
                query,
                {"_id": 0},
                sort=[("country_code", 1), ("year", -1)],
            )
        )
    except Exception:
        logger.exception(
            "country_lgbti_status_read_failed",
            extra={"country_codes": clean_codes, "requested_year": requested_year},
        )
        return []

    latest_by_code: dict[str, dict[str, Any]] = {}
    for row in rows:
        code = str(row.get("country_code") or "").strip().upper()
        if code and code not in latest_by_code:
            latest_by_code[code] = row
    return [latest_by_code[code] for code in clean_codes if code in latest_by_code]


def get_country_lgbti_status_record(
    country_code: str,
    year: int,
    *,
    active_only: bool = False,
) -> dict[str, Any] | None:
    clean_code = str(country_code or "").strip().upper()
    if not clean_code:
        return None
    try:
        clean_year = int(year)
    except TypeError, ValueError:
        return None

    query: dict[str, Any] = {"country_code": clean_code, "year": clean_year}
    if active_only:
        query["active"] = True

    try:
        return _mongo_collection(COUNTRY_LGBTI_STATUS_COLLECTION).find_one(query, {"_id": 0})
    except Exception:
        logger.exception(
            "country_lgbti_status_record_read_failed",
            extra={"country_code": clean_code, "year": clean_year},
        )
        return None


def upsert_country_lgbti_status_record(record: dict[str, Any]) -> None:
    clean_code = str(record.get("country_code") or "").strip().upper()
    year = record.get("year")
    if year is None:
        raise ValueError("invalid_country_lgbti_status_year")
    clean_year = int(year)
    try:
        _mongo_collection(COUNTRY_LGBTI_STATUS_COLLECTION).update_one(
            {"country_code": clean_code, "year": clean_year},
            {"$set": record},
            upsert=True,
        )
    except Exception:
        logger.exception(
            "country_lgbti_status_record_upsert_failed",
            extra={"country_code": clean_code, "year": clean_year},
        )
        raise


def deactivate_country_lgbti_status_record(country_code: str, year: int) -> bool:
    clean_code = str(country_code or "").strip().upper()
    clean_year = int(year)
    try:
        result = _mongo_collection(COUNTRY_LGBTI_STATUS_COLLECTION).update_one(
            {"country_code": clean_code, "year": clean_year},
            {"$set": {"active": False}},
            upsert=False,
        )
    except Exception:
        logger.exception(
            "country_lgbti_status_record_deactivate_failed",
            extra={"country_code": clean_code, "year": clean_year},
        )
        raise
    return bool(result.matched_count)


def invalidate_analytics_cache() -> None:
    global _section_cache_hits, _section_cache_requests
    cache.clear()
    with _section_cache_metrics_lock:
        _section_cache_requests = 0
        _section_cache_hits = 0


def _felgtbi_section_cache_key(
    collection_name: str,
    document_id: str | None,
    code: str,
) -> str:
    identity = f"{collection_name}\0{document_id or ''}\0{code}"
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    return f"felgtbi-section-v2:{digest}"


def _record_section_cache_request(*, hit: bool) -> float:
    global _section_cache_hits, _section_cache_requests
    with _section_cache_metrics_lock:
        _section_cache_requests += 1
        if hit:
            _section_cache_hits += 1
        return round(_section_cache_hits / _section_cache_requests, 4)


@lru_cache(maxsize=1)
def _mongo_client_and_database() -> tuple[Any, str]:
    config = get_mongo_config()
    return get_mongo_client(), config.database


def _mongo_collection(name: str):
    client, database = _mongo_client_and_database()
    return client[database][name]


def _resolve_spain_collection_name(collection_name: str | None) -> str:
    clean_collection = str(collection_name or "").strip()
    available = {collection.name for collection in get_spain_available_collections()}
    if clean_collection and clean_collection in available:
        return clean_collection
    if DEFAULT_FELGTBI_COLLECTION in available:
        return DEFAULT_FELGTBI_COLLECTION
    return next(iter(sorted(available, key=_spain_collection_sort_key)), "")


def _spain_collection_query(collection_name: str) -> dict[str, Any]:
    if collection_name == DEFAULT_FELGTBI_COLLECTION:
        return {"source": FELGTBI_SOURCE_CODE}
    return {}


def _spain_document_query(collection_name: str, document: FelgtbiDocument) -> dict[str, Any]:
    query = _spain_collection_query(collection_name)
    for field, value in document.filter_fields:
        query[field] = value
    return query


def _resolve_felgtbi_document(
    document_id: str | None, collection_name: str | None
) -> FelgtbiDocument | None:
    clean_id = str(document_id or "").strip()
    if not clean_id:
        return None
    for document in get_felgtbi_documents(collection_name):
        if document.id == clean_id:
            return document
    return None


def _group_spain_documents(rows: Any, collection_name: str) -> list[FelgtbiDocument]:
    groups: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        if not _is_processed_spain_document(row):
            continue
        if not _is_pdf_backed_spain_document(row):
            continue
        if not _has_navigable_spain_section(row):
            continue

        document_id, filter_fields = _spain_document_identity(row, collection_name)
        label = _spain_document_display_name(row)
        if not label:
            label = _fallback_spain_document_label(row, document_id)
        group = groups.setdefault(
            document_id,
            {
                "label": label,
                "original_filename": _spain_source_filename(row),
                "year": _int_or_none(row.get("year")),
                "report_title": _clean_text(row.get("report_title")),
                "report_type": _clean_text(row.get("report_type")),
                "filter_fields": filter_fields,
                "section_count": 0,
            },
        )
        group["section_count"] += 1
        if not group["original_filename"]:
            group["original_filename"] = _spain_source_filename(row)
        if group["year"] is None:
            group["year"] = _int_or_none(row.get("year"))
        if not group["report_title"]:
            group["report_title"] = _clean_text(row.get("report_title"))
        if not group["report_type"]:
            group["report_type"] = _clean_text(row.get("report_type"))

    documents = [
        FelgtbiDocument(
            id=document_id,
            label=str(group["label"]),
            original_filename=str(group["original_filename"]),
            year=group["year"],
            report_title=str(group["report_title"]),
            report_type=str(group["report_type"]),
            section_count=int(group["section_count"]),
            filter_fields=tuple(group["filter_fields"]),
        )
        for document_id, group in groups.items()
    ]
    return sorted(
        documents,
        key=lambda document: (
            -(document.year or 0),
            document.label.casefold(),
            document.id,
        ),
    )


def _spain_document_identity(
    row: dict[str, Any], collection_name: str
) -> tuple[str, tuple[tuple[str, Any], ...]]:
    source_document_id = _clean_text(
        row.get("source_document_id")
        or _nested_value(row, "metadata.source_document_id")
        or _nested_value(row, "file_metadata.source_document_id")
    )
    if source_document_id:
        return f"document:{source_document_id}", (("source_document_id", source_document_id),)

    filename_field, filename_value = _spain_filename_field(row)
    filter_fields: list[tuple[str, Any]] = []
    if filename_field and filename_value:
        filter_fields.append((filename_field, filename_value))

    year = _int_or_none(row.get("year"))
    if year is not None:
        filter_fields.append(("year", year))

    report_title = _clean_text(row.get("report_title"))
    if report_title:
        filter_fields.append(("report_title", report_title))

    report_type = _clean_text(row.get("report_type"))
    if report_type:
        filter_fields.append(("report_type", report_type))

    if not filter_fields and row.get("_id") is not None:
        object_id = str(row["_id"])
        return f"legacy-object:{object_id}", (("_id", row["_id"]),)

    seed = _json_dumps_stable(
        {
            "collection": collection_name,
            "filter_fields": filter_fields,
        }
    )
    digest = hashlib.sha1(seed.encode("utf-8"), usedforsecurity=False).hexdigest()[:16]
    return f"legacy:{digest}", tuple(filter_fields)


def _deduplicate_spain_document_labels(documents: list[FelgtbiDocument]) -> list[FelgtbiDocument]:
    by_label: dict[str, list[FelgtbiDocument]] = {}
    for document in documents:
        by_label.setdefault(document.label, []).append(document)

    result: list[FelgtbiDocument] = []
    for label, matches in by_label.items():
        if len(matches) == 1:
            result.extend(matches)
            continue
        years = [document.year for document in matches if document.year is not None]
        years_are_unique = len(years) == len(matches) and len(set(years)) == len(matches)
        for index, document in enumerate(matches, start=1):
            if years_are_unique and document.year is not None and str(document.year) not in label:
                suffix = str(document.year)
            else:
                suffix = str(index)
            result.append(
                FelgtbiDocument(
                    id=document.id,
                    label=f"{document.label} - {suffix}",
                    original_filename=document.original_filename,
                    year=document.year,
                    report_title=document.report_title,
                    report_type=document.report_type,
                    section_count=document.section_count,
                    filter_fields=document.filter_fields,
                )
            )
    return sorted(
        result,
        key=lambda document: (
            -(document.year or 0),
            document.label.casefold(),
            document.id,
        ),
    )


def _spain_document_display_name(row: dict[str, Any]) -> str:
    filename = _spain_source_filename(row)
    if filename:
        return _display_name_from_pdf_filename(filename)
    for field in (
        "metadata.display_name",
        "metadata.title",
        "file_metadata.display_name",
        "file_metadata.title",
        "report_title",
    ):
        candidate = _clean_text(_nested_value(row, field))
        if candidate:
            return candidate
    return ""


def _fallback_spain_document_label(row: dict[str, Any], document_id: str) -> str:
    year = _int_or_none(row.get("year"))
    if year is not None:
        return f"Documento {year}"
    suffix = str(document_id or "").split(":", 1)[-1][:8]
    return f"Documento {suffix or 'FELGTBI+'}"


def _spain_source_filename(row: dict[str, Any]) -> str:
    _field, value = _spain_filename_field(row)
    return value


def _spain_filename_field(row: dict[str, Any]) -> tuple[str, str]:
    for field in SPAIN_FILENAME_FIELD_PATHS:
        value = _clean_text(_nested_value(row, field))
        if value:
            return field, value
    return "", ""


def _display_name_from_pdf_filename(value: str) -> str:
    filename = _basename(value)
    if filename.lower().endswith(".pdf"):
        filename = filename[:-4]
    return _normalize_lgbtiq_display_label(filename.strip())


def _normalize_lgbtiq_display_label(value: str) -> str:
    label = re.sub(r"(?<![A-Za-z])LGTBI\+", "LGBTIQ+", value)
    label = re.sub(r"(?<![A-Za-z])LGBTI\+", "LGBTIQ+", label)
    return re.sub(r"(?<![A-Za-z])LGBTIQ(?!\+)", "LGBTIQ+", label)


def _basename(value: str) -> str:
    clean = _clean_text(value).replace("\\", "/").rstrip("/")
    if not clean:
        return ""
    return clean.rsplit("/", 1)[-1].strip()


def _is_pdf_backed_spain_document(row: dict[str, Any]) -> bool:
    filename = _spain_source_filename(row)
    if not filename:
        return True
    basename = _basename(filename)
    suffix = basename.rsplit(".", 1)[-1].casefold() if "." in basename else ""
    return not suffix or suffix == "pdf"


def _is_processed_spain_document(row: dict[str, Any]) -> bool:
    statuses = [
        _clean_text(row.get(field)).casefold()
        for field in ("import_status", "status", "processing_status", "state")
        if _clean_text(row.get(field))
    ]
    if not statuses:
        return True
    if any(status in SPAIN_DOCUMENT_BLOCKED_STATUSES for status in statuses):
        return False
    return any(status in SPAIN_DOCUMENT_PROCESSED_STATUSES for status in statuses)


def _nested_value(row: dict[str, Any], field_path: str) -> Any:
    current: Any = row
    for part in field_path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _spain_document_projection() -> dict[str, int]:
    return {
        "_id": 1,
        "source": 1,
        "source_document_id": 1,
        "original_filename": 1,
        "filename": 1,
        "file_name": 1,
        "source_file": 1,
        "metadata.source_document_id": 1,
        "metadata.original_filename": 1,
        "metadata.filename": 1,
        "metadata.file_name": 1,
        "metadata.source_file": 1,
        "metadata.display_name": 1,
        "metadata.title": 1,
        "file_metadata.source_document_id": 1,
        "file_metadata.original_filename": 1,
        "file_metadata.filename": 1,
        "file_metadata.file_name": 1,
        "file_metadata.source_file": 1,
        "file_metadata.display_name": 1,
        "file_metadata.title": 1,
        "upload.original_filename": 1,
        "upload.filename": 1,
        "upload.file_name": 1,
        "upload.source_file": 1,
        "year": 1,
        "report_title": 1,
        "report_type": 1,
        "import_status": 1,
        "status": 1,
        "processing_status": 1,
        "state": 1,
        "code": 1,
        "category": 1,
        "specific_category": 1,
        "question": 1,
        "description": 1,
        "section_title": 1,
        "subsection_title": 1,
        "figure_caption": 1,
        "page": 1,
    }


def _spain_navigation_projection() -> dict[str, int]:
    return {
        "_id": 0,
        "source": 1,
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
        "section_title": 1,
        "answers.percentage": 1,
        "answers.value": 1,
        "page": 1,
    }


def _has_navigable_spain_section(document: dict[str, Any]) -> bool:
    if not _clean_text(document.get("code")) or _int_or_none(document.get("year")) is None:
        return False
    return bool(
        _clean_text(document.get("subsection_title"))
        or _clean_text(document.get("question"))
        or _clean_text(document.get("description"))
        or _clean_text(document.get("figure_caption"))
    )


def _row_to_felgtbi_indicator(row: dict[str, Any]) -> FelgtbiIndicator:
    return FelgtbiIndicator(
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


def _json_dumps_stable(value: Any) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _is_spain_collection_name(name: str) -> bool:
    normalized = _normalize_collection_name(name)
    return any(token in normalized for token in SPAIN_COLLECTION_INCLUDE_TOKENS)


def _collection_has_spain_interface_documents(name: str) -> bool:
    name_matches = _is_spain_collection_name(name)
    country_clauses: list[dict[str, Any]] = [
        {"source": FELGTBI_SOURCE_CODE},
        {"country": "Spain"},
        {"country_code": "ES"},
    ]
    if name_matches:
        country_clauses.extend(
            [
                {"answers.country": "Spain"},
                {"answers.country_code": "ES"},
            ]
        )
    try:
        document = _mongo_collection(name).find_one(
            {
                "code": {"$exists": True, "$nin": ["", None]},
                "category": {"$exists": True, "$nin": ["", None]},
                "year": {"$exists": True, "$nin": ["", None]},
                "$or": [
                    *country_clauses,
                ],
            },
            {
                "_id": 0,
                "code": 1,
                "category": 1,
                "year": 1,
                "source": 1,
                "country": 1,
                "country_code": 1,
                "answers.country": 1,
                "answers.country_code": 1,
            },
            max_time_ms=1000,
        )
    except Exception:
        logger.debug("spain_collection_probe_failed", extra={"collection": name}, exc_info=True)
        return False
    return bool(document)


def _has_valid_spain_section(document: dict[str, Any]) -> bool:
    return (
        _has_valid_spain_information(document)
        or _has_valid_spain_image(document)
        or _has_valid_spain_chart(document)
    )


def _has_valid_spain_chart(document: dict[str, Any]) -> bool:
    return (
        _answers_have_numeric_value(document.get("answers"))
        or _data_points_have_numeric_value(document.get("data_points"))
        or _has_valid_spain_image(document)
    )


def _has_valid_spain_image(document: dict[str, Any]) -> bool:
    return bool(_spain_figure_storage_path(document))


def _has_valid_spain_information(document: dict[str, Any]) -> bool:
    question = _clean_text(document.get("question") or document.get("subsection_title"))
    section = _clean_text(document.get("specific_category") or document.get("section_title"))
    description = _clean_text(document.get("description"))
    if description and description not in {question, section} and len(description) >= 16:
        return True

    if _clean_text(document.get("content_html")):
        return True
    if _text_list_has_value(document.get("paragraphs")):
        return True
    if _text_list_has_value(document.get("paragraphs_before_figure")):
        return True
    if _text_list_has_value(document.get("paragraphs_after_figure")):
        return True
    if _clean_text(document.get("figure_caption")):
        return True
    if _clean_text(document.get("sample_size")) or _clean_text(document.get("fieldwork")):
        return True

    figure = (
        cast(dict[str, Any], document.get("figure"))
        if isinstance(document.get("figure"), dict)
        else {}
    )
    for key in ("caption", "title", "alt_text", "source", "note", "methodology"):
        if _clean_text(figure.get(key)):
            return True

    context = (
        cast(dict[str, Any], document.get("visual_context"))
        if isinstance(document.get("visual_context"), dict)
        else {}
    )
    for key in ("title", "description", "caption", "source", "note", "methodology"):
        if _clean_text(context.get(key)):
            return True
    return False


def _answers_have_numeric_value(answers: Any) -> bool:
    if not isinstance(answers, list):
        return False
    return any(
        isinstance(answer, dict)
        and isinstance(answer.get("percentage", answer.get("value")), (int, float))
        for answer in answers
    )


def _data_points_have_numeric_value(data_points: Any) -> bool:
    if not isinstance(data_points, list):
        return False
    for point in data_points:
        if not isinstance(point, dict):
            continue
        if isinstance(point.get("value", point.get("percentage")), (int, float)):
            return True
    return False


def _spain_figure_storage_path(document: dict[str, Any]) -> str:
    figure = (
        cast(dict[str, Any], document.get("figure"))
        if isinstance(document.get("figure"), dict)
        else {}
    )
    storage_path = _clean_text(figure.get("storage_path"))
    if not storage_path or "://" in storage_path or storage_path.startswith("/"):
        return ""
    return storage_path


def _text_list_has_value(value: Any) -> bool:
    return isinstance(value, list) and any(_clean_text(item) for item in value)


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _is_technical_collection_name(name: str) -> bool:
    clean_name = str(name or "").strip()
    normalized = _normalize_collection_name(clean_name)
    if not clean_name or clean_name.lower() in SPAIN_COLLECTION_EXCLUDED_NAMES:
        return True
    if any(clean_name.lower().startswith(prefix) for prefix in SPAIN_COLLECTION_EXCLUDED_PREFIXES):
        return True
    tokens = set(normalized.split("_"))
    return bool(
        tokens.intersection(
            {"cache", "backup", "bak", "scratch", "temporary", "test", "log", "logs"}
        )
    )


def _spain_collection_sort_key(name: str) -> tuple[int, str]:
    clean_name = str(name or "").strip()
    return (
        0 if clean_name == DEFAULT_FELGTBI_COLLECTION else 1,
        _spain_collection_label(clean_name),
    )


def _spain_collection_label(name: str, *, language: str = "es") -> str:
    clean_name = str(name or "").strip()
    labels = SPAIN_COLLECTION_LABELS.get(clean_name)
    if labels:
        return labels[1] if language == "en" else labels[0]
    return _readable_collection_label(clean_name, language=language)


def _readable_collection_label(name: str, *, language: str = "es") -> str:
    tokens = [token for token in re.split(r"[^0-9A-Za-zÀ-ÿ]+", str(name or "")) if token]
    if not tokens:
        return "Fuente de datos" if language == "es" else "Data source"
    normalized_tokens = {token.lower() for token in tokens}
    if {"felgtbi", "discrimination", "reports"}.issubset(normalized_tokens):
        return (
            "FELGTBI - Discrimination reports"
            if language == "en"
            else "FELGTBI - Informes de discriminación"
        )

    translations_es = {
        "felgtbi": "FELGTBI",
        "lgtbi": "LGBTIQ+",
        "lgbti": "LGBTIQ+",
        "lgbtiq": "LGBTIQ+",
        "spain": "España",
        "espana": "España",
        "españa": "España",
        "estado": "Estado",
        "discrimination": "Discriminación",
        "reports": "Informes",
        "report": "Informe",
        "indicator": "Indicadores",
        "indicators": "Indicadores",
        "survey": "Encuesta",
        "data": "Datos",
    }
    translations_en = {
        "felgtbi": "FELGTBI",
        "lgtbi": "LGBTIQ+",
        "lgbti": "LGBTIQ+",
        "lgbtiq": "LGBTIQ+",
        "spain": "Spain",
        "espana": "Spain",
        "españa": "Spain",
        "estado": "Status",
        "discrimination": "Discrimination",
        "reports": "Reports",
        "report": "Report",
        "indicator": "Indicators",
        "indicators": "Indicators",
        "survey": "Survey",
        "data": "Data",
    }
    translations = translations_en if language == "en" else translations_es
    label_parts = [translations.get(token.lower(), _title_token(token)) for token in tokens]
    label = " ".join(label_parts)
    return label.replace("FELGTBI LGBTIQ+", "FELGTBI")


def _title_token(token: str) -> str:
    if token.isupper() or token.isdigit():
        return token
    return token[:1].upper() + token[1:].lower()


def _normalize_collection_name(name: str) -> str:
    return re.sub(r"[^0-9a-záéíóúüñ_]+", "_", str(name or "").strip().lower())


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


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except TypeError, ValueError:
        return None
