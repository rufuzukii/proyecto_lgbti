from __future__ import annotations

from copy import deepcopy
from typing import Any

from bson import ObjectId
from app.mongo import get_mongo_collection
from app.import_to_db.ilga.importer import ILGA_DATASET_CODE, parse_ilga_json_text

INDICATOR_ILGA_COLLECTION = "Indicator_ilga"


def insert_indicator_ilga_json(file_json: dict[str, Any] | list[Any]) -> int:
    documents = _normalize_documents(file_json)
    collection = get_mongo_collection(INDICATOR_ILGA_COLLECTION)
    for document in documents:
        prepared = _prepare_ilga_document(document)
        collection.update_one(
            {"dataset": prepared["dataset"], "year": prepared["year"]},
            {"$setOnInsert": prepared},
            upsert=True,
        )
    return len(documents)


def _prepare_ilga_document(document: dict[str, Any]) -> dict[str, Any]:
    if document.get("dataset") != ILGA_DATASET_CODE:
        raise ValueError("invalid_ilga_payload")

    try:
        prepared = parse_ilga_json_text(_json_dumpable_copy(document))
    except ValueError as exc:
        raise ValueError("invalid_ilga_payload") from exc
    if isinstance(prepared, list):
        raise ValueError("invalid_ilga_payload")

    prepared["_id"] = _resolve_object_id(document.get("id"))
    return prepared


def _normalize_documents(file_json: dict[str, Any] | list[Any]) -> list[dict[str, Any]]:
    if isinstance(file_json, dict):
        return [deepcopy(file_json)]
    if not isinstance(file_json, list) or not file_json:
        raise ValueError("invalid_ilga_payload")
    if not all(isinstance(item, dict) for item in file_json):
        raise ValueError("invalid_ilga_payload")
    return [deepcopy(item) for item in file_json]


def _resolve_object_id(value: Any) -> ObjectId:
    if isinstance(value, ObjectId):
        return value
    if isinstance(value, str) and ObjectId.is_valid(value):
        return ObjectId(value)
    return ObjectId()


def _json_dumpable_copy(document: dict[str, Any]) -> str:
    import json

    clean_document = deepcopy(document)
    clean_document.pop("_id", None)
    return json.dumps(clean_document)
