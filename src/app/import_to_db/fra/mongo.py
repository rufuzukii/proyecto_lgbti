from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any

from bson import ObjectId
from pymongo import UpdateOne

from app.import_to_db.fra.validation import (
    has_valid_fra_statistic_answer,
    is_valid_fra_category,
)
from app.mongo import get_mongo_collection

INDICATOR_FRA_COLLECTION = "Indicator_fra"
FRA_DATASET_CODE = "eu_lgbtiq_survey_iii"
DEFAULT_BULK_SIZE = 500
FRA_VALUE_BUCKETS = 16


def insert_indicator_fra_json(
    file_json: dict[str, Any] | list[Any],
    *,
    bulk_size: int = DEFAULT_BULK_SIZE,
) -> int:
    documents = _normalize_documents(file_json)
    collection = get_mongo_collection(INDICATOR_FRA_COLLECTION)
    bounded_bulk_size = max(1, min(int(bulk_size), DEFAULT_BULK_SIZE))
    grouped: dict[tuple[Any, ...], tuple[dict[str, Any], dict[str, dict[str, Any]]]] = {}
    for document in documents:
        prepared = _prepare_indicator_document(document)
        answers = prepared.pop("answers", [])
        prepared.pop("_id", None)
        for answer in answers:
            value_bucket = fra_value_bucket(answer)
            bucketed = {**prepared, "value_bucket": value_bucket}
            identity = _question_identity(bucketed)
            parent, grouped_answers = grouped.setdefault(identity, (bucketed, {}))
            parent.update(bucketed)
            grouped_answers[answer["identity_key"]] = answer

    operations: list[UpdateOne] = []
    for prepared, grouped_answers in grouped.values():
        answers = list(grouped_answers.values())
        operations.append(
            UpdateOne(
                _question_filter(prepared),
                _question_update_pipeline(prepared, answers),
                upsert=True,
            )
        )
        if len(operations) >= bounded_bulk_size:
            _execute_operations(collection, operations)
            operations.clear()
    if operations:
        _execute_operations(collection, operations)

    return len(documents)


def _prepare_indicator_document(document: dict[str, Any]) -> dict[str, Any]:
    source = deepcopy(document)
    code = str(source.get("code") or "").strip()
    if not code:
        raise ValueError("invalid_json_payload")
    survey_year = _survey_year(source.get("survey_year"))
    if survey_year is None:
        raise ValueError("missing_fra_survey_year")
    prepared: dict[str, Any] = {
        "_id": _resolve_object_id(source.get("id")),
        "code": code,
        "dataset": str(source.get("dataset") or FRA_DATASET_CODE).strip(),
        "record_type": "statistic",
        "source": str(source.get("source") or "").strip(),
        "category": str(source.get("category") or "").strip(),
        "specific_category": str(source.get("specific_category") or "").strip(),
        "question": str(source.get("question") or "").strip(),
        "survey_year": survey_year,
    }
    answers: list[dict[str, Any]] = []
    for answer in source.get("answers", []):
        if not isinstance(answer, dict):
            continue
        answers.append(_prepare_answer(answer, survey_year=survey_year))
    if answers:
        prepared["answers"] = answers
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
    prepared = {
        "country": str(answer.get("country") or "").strip(),
        "country_code": str(answer.get("country_code") or "").strip(),
        "answer": str(answer.get("answer") or "").strip(),
        "percentage": answer.get("percentage"),
        "filters": _prepare_answer_filters(answer.get("filters")),
    }
    prepared["identity_key"] = _answer_identity_key(prepared, survey_year=survey_year)
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


def _question_filter(document: dict[str, Any]) -> dict[str, Any]:
    return {
        "code": document["code"],
        "category": document.get("category") or "",
        "specific_category": document.get("specific_category") or "",
        "question": document.get("question") or "",
        "survey_year": document["survey_year"],
        "value_bucket": document["value_bucket"],
    }


def _question_identity(document: dict[str, Any]) -> tuple[str, str, str, str, int, int]:
    return (
        str(document["code"]),
        str(document.get("category") or ""),
        str(document.get("specific_category") or ""),
        str(document.get("question") or ""),
        int(document["survey_year"]),
        int(document["value_bucket"]),
    )


def _execute_operations(collection: Any, operations: list[UpdateOne]) -> None:
    if len(operations) == 1:
        operation = operations[0]
        collection.update_one(operation._filter, operation._doc, upsert=True)
        return
    collection.bulk_write(operations, ordered=False)


def _question_update_pipeline(
    document: dict[str, Any], answers: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    parent_fields = {key: {"$literal": value} for key, value in document.items()}
    incoming_identity_keys = [answer["identity_key"] for answer in answers]
    return [
        {
            "$set": {
                **parent_fields,
                "answers": {
                    "$let": {
                        "vars": {
                            "existing": {"$ifNull": ["$answers", []]},
                            "incoming": {"$literal": answers},
                            "incoming_keys": {"$literal": incoming_identity_keys},
                        },
                        "in": {
                            "$cond": [
                                {
                                    "$gt": [
                                        {
                                            "$size": {
                                                "$setIntersection": [
                                                    {
                                                        "$map": {
                                                            "input": "$$existing",
                                                            "as": "answer",
                                                            "in": "$$answer.identity_key",
                                                        }
                                                    },
                                                    "$$incoming_keys",
                                                ]
                                            }
                                        },
                                        0,
                                    ]
                                },
                                {
                                    "$map": {
                                        "input": {
                                            "$objectToArray": {
                                                "$mergeObjects": [
                                                    {
                                                        "$arrayToObject": {
                                                            "$map": {
                                                                "input": "$$existing",
                                                                "as": "answer",
                                                                "in": {
                                                                    "k": "$$answer.identity_key",
                                                                    "v": "$$answer",
                                                                },
                                                            }
                                                        }
                                                    },
                                                    {
                                                        "$arrayToObject": {
                                                            "$map": {
                                                                "input": "$$incoming",
                                                                "as": "answer",
                                                                "in": {
                                                                    "k": "$$answer.identity_key",
                                                                    "v": "$$answer",
                                                                },
                                                            }
                                                        }
                                                    },
                                                ]
                                            }
                                        },
                                        "as": "pair",
                                        "in": "$$pair.v",
                                    }
                                },
                                {"$concatArrays": ["$$existing", "$$incoming"]},
                            ]
                        },
                    }
                },
            }
        }
    ]


def _answer_identity_key(answer: dict[str, Any], *, survey_year: int) -> str:
    identity = {
        "survey_year": survey_year,
        "country_code": answer.get("country_code") or "",
        "country": answer.get("country") or "",
        "answer": answer.get("answer") or "",
        "filters": answer.get("filters") or [],
    }
    serialized = json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:32]


def fra_value_bucket(answer: dict[str, Any]) -> int:
    """Keep one response/segmentation slice together while bounding document size."""
    identity = {
        "answer": answer.get("answer") or "",
        "filters": answer.get("filters") or [],
    }
    serialized = json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return int(hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:8], 16) % FRA_VALUE_BUCKETS


def _survey_year(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        year = int(value)
    except TypeError, ValueError:
        return None
    return year if 1990 <= year <= 2100 else None
