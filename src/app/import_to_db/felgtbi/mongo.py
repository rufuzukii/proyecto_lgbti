from __future__ import annotations

import hashlib
from copy import deepcopy
from typing import Any

from bson import ObjectId

from app.import_to_db.felgtbi.importer import FELGTBI_SOURCE_CODE
from app.import_to_db.felgtbi.semantics import sanitize_report_document
from app.mongo import get_mongo_collection

INDICATOR_FELGTBI_COLLECTION = "Indicator_felgtbi"


def insert_indicator_felgtbi_json(
    file_json: dict[str, Any] | list[Any],
    *,
    original_filename: str | None = None,
) -> int:
    documents = _normalize_documents(file_json)
    prepared_documents = [
        _prepare_indicator_document(document, original_filename=original_filename)
        for document in documents
    ]
    collection = get_mongo_collection(INDICATOR_FELGTBI_COLLECTION)
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
    seen: set[tuple[Any, ...]] = set()
    for document in documents:
        source_document_id = str(document.get("source_document_id") or "").strip()
        report_title = str(document.get("report_title") or "").strip()
        report_type = str(document.get("report_type") or "").strip()
        original_filename = str(document.get("original_filename") or "").strip()
        source = str(document.get("source") or "").strip()
        year = document.get("year")
        if not source:
            continue
        if source_document_id:
            key = ("source_document_id", source, source_document_id)
            scope = {"source": source, "source_document_id": source_document_id}
        elif original_filename and year is not None:
            key = ("original_filename", source, int(year), original_filename)
            scope = {"source": source, "year": int(year), "original_filename": original_filename}
        elif report_title and year is not None:
            key = ("report_title", source, int(year), report_title, report_type)
            scope = {
                "source": source,
                "year": int(year),
                "report_title": report_title,
                "report_type": report_type,
            }
        else:
            continue
        if key in seen:
            continue
        seen.add(key)
        scopes.append(scope)
    return scopes


def _prepare_indicator_document(
    document: dict[str, Any],
    *,
    original_filename: str | None = None,
) -> dict[str, Any]:
    prepared = sanitize_report_document(deepcopy(document))
    _remove_derived_image_fields(prepared)
    figure = prepared.get("figure")
    if isinstance(figure, dict):
        for key in ("bucket", "mime_type", "size", "checksum", "upload"):
            figure.pop(key, None)
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
    resolved_filename = _safe_original_filename(
        prepared.get("original_filename")
        or prepared.get("filename")
        or prepared.get("file_name")
        or prepared.get("source_file")
        or original_filename
    )
    if resolved_filename:
        prepared["original_filename"] = resolved_filename
    prepared["import_status"] = str(prepared.get("import_status") or "processed")
    if not prepared.get("source_document_id"):
        prepared["source_document_id"] = _fallback_source_document_id(prepared, resolved_filename)
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


def _remove_derived_image_fields(value: Any) -> None:
    """Keep image identity in MongoDB limited to the object storage key."""
    if isinstance(value, list):
        for item in value:
            _remove_derived_image_fields(item)
        return
    if not isinstance(value, dict):
        return

    derived_keys = {
        "asset" + "_url",
        "signed" + "_url",
        "public" + "_url",
        "image" + "_url",
        "image" + "_path",
        "url" + "_type",
        "signed" + "_url_expires_in",
    }
    for key in derived_keys:
        value.pop(key, None)
    value.pop("image" + "_upload", None)
    value.pop("image" + "_storage", None)
    for item in value.values():
        _remove_derived_image_fields(item)


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


def _safe_original_filename(value: Any) -> str:
    clean = str(value or "").replace("\\", "/").rstrip("/")
    clean = clean.rsplit("/", 1)[-1].strip()
    return clean


def _fallback_source_document_id(document: dict[str, Any], original_filename: str) -> str:
    seed = "|".join(
        str(part or "").strip()
        for part in (
            FELGTBI_SOURCE_CODE,
            original_filename,
            document.get("year"),
            document.get("report_title"),
            document.get("report_type"),
        )
    )
    digest = hashlib.sha1(seed.encode("utf-8", errors="ignore"), usedforsecurity=False).hexdigest()[
        :16
    ]
    return f"felgtbi_pdf_{digest}"


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except TypeError, ValueError:
        return None


def _indicator_filter(document: dict[str, Any]) -> dict[str, Any]:
    query = {
        "code": document["code"],
        "source": document.get("source") or "",
        "year": document.get("year"),
    }
    source_document_id = str(document.get("source_document_id") or "").strip()
    if source_document_id:
        query["source_document_id"] = source_document_id
        return query

    original_filename = str(document.get("original_filename") or "").strip()
    if original_filename:
        query["original_filename"] = original_filename
    return query
