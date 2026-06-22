from __future__ import annotations

from copy import deepcopy
from typing import Any

from bson import ObjectId
from pymongo import MongoClient

from app.config import get_mongo_config

INDICATOR_ILGA_COLLECTION = "Indicator_ilga"


def insert_indicator_ilga_json(file_json: dict[str, Any] | list[Any]) -> int:
    documents = _normalize_documents(file_json)
    config = get_mongo_config()

    with MongoClient(config.dsn(), serverSelectionTimeoutMS=5000) as client:
        collection = client[config.database][INDICATOR_ILGA_COLLECTION]
        for document in documents:
            prepared = _prepare_ilga_document(document)
            collection.update_one(
                {
                    "dataset": prepared["dataset"],
                    "year": prepared["year"],
                },
                {
                    "$setOnInsert": prepared,
                },
                upsert=True,
            )
    return len(documents)


def _prepare_ilga_document(document: dict[str, Any]) -> dict[str, Any]:
    prepared = deepcopy(document)
    if prepared.get("dataset") != "ilga_rainbow_map":
        raise ValueError("invalid_ilga_payload")

    year = prepared.get("year")
    countries = prepared.get("countries")
    if not isinstance(year, int) or not isinstance(countries, list) or not countries:
        raise ValueError("invalid_ilga_payload")

    prepared["_id"] = _resolve_object_id(prepared.pop("id", None))
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
