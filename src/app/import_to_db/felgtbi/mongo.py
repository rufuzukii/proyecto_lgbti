from __future__ import annotations

from copy import deepcopy
from typing import Any

from bson import ObjectId
from pymongo import MongoClient

from app.config import get_mongo_config
from app.import_to_db.felgtbi.importer import FELGTBI_SOURCE_CODE

INDICATOR_FELGTBI_COLLECTION = "Indicator_felgtbi"


def insert_indicator_felgtbi_json(file_json: dict[str, Any] | list[Any]) -> int:
    documents = _normalize_documents(file_json)
    prepared_documents = [_prepare_indicator_document(document) for document in documents]
    config = get_mongo_config()

    with MongoClient(
        config.dsn(),
        serverSelectionTimeoutMS=config.server_selection_timeout_ms,
        connectTimeoutMS=config.server_selection_timeout_ms,
        socketTimeoutMS=config.server_selection_timeout_ms,
    ) as client:
        collection = client[config.database][INDICATOR_FELGTBI_COLLECTION]
        collection.create_index("code", background=True)
        collection.create_index(
            [("year", -1), ("category", 1), ("specific_category", 1)],
            background=True,
        )
        collection.create_index([("source", 1), ("report_type", 1)], background=True)
        collection.create_index(
            [("source", 1), ("year", -1), ("report_title", 1), ("report_type", 1)],
            background=True,
        )
        for scope in _report_replacement_scopes(prepared_documents):
            collection.delete_many(scope)
        for prepared in prepared_documents:
            has_answers = "answers" in prepared
            answers = prepared.pop("answers", [])
            object_id = prepared.pop("_id", None)
            update: dict[str, Any] = {"$set": prepared}
            if object_id is not None:
                update["$setOnInsert"] = {"_id": object_id}
            if has_answers:
                update["$set"]["answers"] = answers
            else:
                update["$unset"] = {"answers": ""}
            collection.update_one(_indicator_filter(prepared), update, upsert=True)

    return len(documents)


def _report_replacement_scopes(documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    scopes: list[dict[str, Any]] = []
    seen: set[tuple[str, int, str, str]] = set()
    for document in documents:
        report_title = str(document.get("report_title") or "").strip()
        report_type = str(document.get("report_type") or "").strip()
        source = str(document.get("source") or "").strip()
        year = document.get("year")
        if not source or not report_title or year is None:
            continue
        key = (source, int(year), report_title, report_type)
        if key in seen:
            continue
        seen.add(key)
        scopes.append(
            {
                "source": source,
                "year": int(year),
                "report_title": report_title,
                "report_type": report_type,
            }
        )
    return scopes


def _prepare_indicator_document(document: dict[str, Any]) -> dict[str, Any]:
    prepared = deepcopy(document)
    if prepared.get("source") != FELGTBI_SOURCE_CODE:
        raise ValueError("invalid_felgtbi_payload")
    code = str(prepared.get("code") or "").strip()
    description = str(prepared.get("description") or "").strip()
    question = str(prepared.get("question") or description).strip()
    if not code or not question:
        raise ValueError("invalid_felgtbi_payload")

    prepared["code"] = code
    prepared["question"] = question
    if description:
        prepared["description"] = description
    else:
        prepared["description"] = question
    prepared["year"] = _int_or_none(prepared.get("year"))
    if prepared["year"] is None:
        raise ValueError("invalid_felgtbi_payload")
    prepared["_id"] = _resolve_object_id(prepared.pop("id", None))
    answers = []
    for answer in prepared.get("answers", []):
        if isinstance(answer, dict):
            answers.append(_prepare_answer(answer))
    if answers:
        prepared["answers"] = answers
    else:
        prepared.pop("answers", None)
    return prepared


def _normalize_documents(file_json: dict[str, Any] | list[Any]) -> list[dict[str, Any]]:
    if isinstance(file_json, dict):
        return [deepcopy(file_json)]
    if not isinstance(file_json, list) or not file_json:
        raise ValueError("invalid_felgtbi_payload")
    if not all(isinstance(item, dict) for item in file_json):
        raise ValueError("invalid_felgtbi_payload")
    return [deepcopy(item) for item in file_json]


def _prepare_answer(answer: dict[str, Any]) -> dict[str, Any]:
    prepared = {
        "country": answer.get("country") or "Spain",
        "country_code": answer.get("country_code") or "ES",
        "answer": answer.get("answer") or "Total",
        "value": answer.get("value", answer.get("percentage")),
        "percentage": answer.get("percentage", answer.get("value")),
        "unit": answer.get("unit") or "percent",
        "filters": _prepare_answer_filters(answer.get("filters")),
    }
    for optional_key in ("page", "sample_size", "fieldwork"):
        if answer.get(optional_key) not in (None, ""):
            prepared[optional_key] = answer[optional_key]
    return prepared


def _prepare_answer_filters(filters: Any) -> list[dict[str, str]]:
    if not isinstance(filters, list):
        return [{"type": "All", "value": "All"}]
    prepared: list[dict[str, str]] = []
    for item in filters:
        if not isinstance(item, dict):
            continue
        filter_type = str(item.get("type") or "").strip()
        filter_value = str(item.get("value") or "").strip()
        if filter_type and filter_value:
            prepared.append({"type": filter_type, "value": filter_value})
    return prepared or [{"type": "All", "value": "All"}]


def _resolve_object_id(value: Any) -> ObjectId:
    if isinstance(value, ObjectId):
        return value
    if isinstance(value, str) and ObjectId.is_valid(value):
        return ObjectId(value)
    return ObjectId()


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _indicator_filter(document: dict[str, Any]) -> dict[str, Any]:
    return {
        "code": document["code"],
        "source": document.get("source") or "",
        "year": document.get("year"),
    }
