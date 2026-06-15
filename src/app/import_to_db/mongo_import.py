from __future__ import annotations

from copy import deepcopy
from typing import Any

from pymongo import MongoClient

from app.config import get_mongo_config

INDICATOR_FRA_COLLECTION = "Indicator_fra"


def insert_indicator_fra_json(file_json: dict[str, Any] | list[Any]) -> int:
    documents = _normalize_documents(file_json)
    config = get_mongo_config()

    with MongoClient(config.dsn(), serverSelectionTimeoutMS=5000) as client:
        collection = client[config.database][INDICATOR_FRA_COLLECTION]
        for document in documents:
            prepared = _prepare_indicator_document(document)
            answers = prepared.pop("answers", [])
            update: dict[str, Any] = {
                "$set": prepared,
                "$setOnInsert": {"answers": []},
            }
            if answers:
                update["$addToSet"] = {"answers": {"$each": answers}}
            collection.update_one({"code": prepared["code"]}, update, upsert=True)

    return len(documents)


def _prepare_indicator_document(document: dict[str, Any]) -> dict[str, Any]:
    prepared = deepcopy(document)
    code = (prepared.get("code") or prepared.get("external_code") or "").strip()
    if not code:
        raise ValueError("invalid_json_payload")
    prepared["code"] = code
    metadata = prepared.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    answers = []
    first_hyperlink = metadata.get("hyperlink") or ""
    for answer in prepared.get("answers", []):
        if not isinstance(answer, dict):
            continue
        clean_answer = deepcopy(answer)
        hyperlink = clean_answer.pop("hyperlink", "")
        if hyperlink and not first_hyperlink:
            first_hyperlink = hyperlink
        answers.append(clean_answer)
    if first_hyperlink:
        metadata["hyperlink"] = first_hyperlink
    prepared["metadata"] = metadata
    prepared["answers"] = answers
    return prepared


def _normalize_documents(file_json: dict[str, Any] | list[Any]) -> list[dict[str, Any]]:
    if isinstance(file_json, dict):
        return [deepcopy(file_json)]
    if not isinstance(file_json, list) or not file_json:
        raise ValueError("invalid_json_payload")
    if not all(isinstance(item, dict) for item in file_json):
        raise ValueError("invalid_json_payload")
    return [deepcopy(item) for item in file_json]
