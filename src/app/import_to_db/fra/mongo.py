from __future__ import annotations

from copy import deepcopy
from typing import Any

from bson import ObjectId

from app.import_to_db.fra.validation import (
    has_valid_fra_statistic_answer,
    is_valid_fra_category,
)
from app.mongo import get_mongo_collection
from app.source_attribution import source_storage_fields

INDICATOR_FRA_COLLECTION = "Indicator_fra"


def insert_indicator_fra_json(file_json: dict[str, Any] | list[Any]) -> int:
    documents = _normalize_documents(file_json)
    collection = get_mongo_collection(INDICATOR_FRA_COLLECTION)
    for document in documents:
        prepared = _prepare_indicator_document(document)
        answers = prepared.pop("answers", [])
        object_id = prepared.pop("_id", None)
        update: dict[str, Any] = {"$set": prepared}
        if object_id is not None:
            update["$setOnInsert"] = {"_id": object_id}
        if answers:
            update["$addToSet"] = {"answers": {"$each": answers}}
        collection.update_one(_question_filter(prepared), update, upsert=True)

    return len(documents)


def _prepare_indicator_document(document: dict[str, Any]) -> dict[str, Any]:
    prepared = deepcopy(document)
    code = (prepared.get("code") or "").strip()
    if not code:
        raise ValueError("invalid_json_payload")
    prepared["code"] = code
    prepared["record_type"] = "statistic"
    survey_year = _survey_year(prepared.get("survey_year"))
    if survey_year is None:
        raise ValueError("missing_fra_survey_year")
    prepared["survey_year"] = survey_year
    prepared.update(
        source_storage_fields(
            "fra",
            year=survey_year,
            accessed_at=str((prepared.get("metadata") or {}).get("date") or "")
            if isinstance(prepared.get("metadata"), dict)
            else "",
        )
    )
    prepared["_id"] = _resolve_object_id(prepared.pop("id", None))
    prepared.pop("external_code", None)
    prepared.pop("datasets", None)
    answers = []
    for answer in prepared.get("answers", []):
        if not isinstance(answer, dict):
            continue
        answers.append(_prepare_answer(answer, survey_year=survey_year))
    prepared.pop("questions", None)
    prepared.pop("validation", None)
    prepared.pop("hyperlink", None)
    if answers:
        prepared["answers"] = answers
    else:
        prepared.pop("answers", None)
    if not is_valid_fra_category(prepared.get("category")):
        raise ValueError("invalid_fra_category")
    if not has_valid_fra_statistic_answer(prepared):
        raise ValueError("invalid_fra_statistic_document")
    return prepared


def _normalize_documents(file_json: dict[str, Any] | list[Any]) -> list[dict[str, Any]]:
    if (
        isinstance(file_json, dict)
        and file_json.get("code")
        and isinstance(file_json.get("answers"), list)
    ):
        return [deepcopy(file_json)]
    if isinstance(file_json, dict) and isinstance(file_json.get("questions"), list):
        questions = file_json["questions"]
        if not questions or not all(isinstance(item, dict) for item in questions):
            raise ValueError("invalid_json_payload")
        return [deepcopy(item) for item in questions]
    if isinstance(file_json, dict):
        return [deepcopy(file_json)]
    if not isinstance(file_json, list) or not file_json:
        raise ValueError("invalid_json_payload")
    if not all(isinstance(item, dict) for item in file_json):
        raise ValueError("invalid_json_payload")
    return [deepcopy(item) for item in file_json]


def _prepare_answer(answer: dict[str, Any], *, survey_year: int) -> dict[str, Any]:
    return {
        "country": answer.get("country") or "",
        "country_code": answer.get("country_code") or "",
        "answer": answer.get("answer") or "",
        "percentage": answer.get("percentage"),
        "survey_year": _survey_year(answer.get("survey_year")) or survey_year,
        "filters": _prepare_answer_filters(answer.get("filters")),
    }


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


def _question_filter(document: dict[str, Any]) -> dict[str, Any]:
    return {
        "code": document["code"],
        "category": document.get("category") or "",
        "specific_category": document.get("specific_category") or "",
        "question": document.get("question") or "",
        "survey_year": document["survey_year"],
    }


def _survey_year(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        year = int(value)
    except TypeError, ValueError:
        return None
    return year if 1990 <= year <= 2100 else None
