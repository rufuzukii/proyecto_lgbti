from __future__ import annotations

import logging
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from bson import ObjectId
from pymongo import InsertOne

from app.infrastructure.mongo import get_mongo_collection
from app.modules.imports.ilga.importer import ILGA_DATASET_CODE, parse_ilga_json_text

INDICATOR_ILGA_COLLECTION = "Indicator_ilga"
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IlgaWriteOutcome:
    year: int
    countries: int
    status: str
    differences: tuple[str, ...] = ()


@dataclass(frozen=True)
class IlgaWriteSummary:
    outcomes: tuple[IlgaWriteOutcome, ...]

    @property
    def inserted_documents(self) -> int:
        return sum(outcome.status == "inserted" for outcome in self.outcomes)

    @property
    def inserted_countries(self) -> int:
        return sum(
            outcome.countries for outcome in self.outcomes if outcome.status == "inserted"
        )


def insert_indicator_ilga_json(file_json: dict[str, Any] | list[Any]) -> int:
    """Persist validated annual documents without upserts or per-country queries."""
    return write_indicator_ilga_json(file_json).inserted_documents


def write_indicator_ilga_json(
    file_json: dict[str, Any] | list[Any],
) -> IlgaWriteSummary:
    documents = _normalize_documents(file_json)
    prepared_documents = [_prepare_ilga_document(document) for document in documents]
    years = [int(document["year"]) for document in prepared_documents]
    duplicate_years = sorted(year for year in set(years) if years.count(year) > 1)
    if duplicate_years:
        raise ValueError(f"duplicate_ilga_years:{','.join(map(str, duplicate_years))}")

    collection = get_mongo_collection(INDICATOR_ILGA_COLLECTION)
    existing_by_year = {
        int(document["year"]): document
        for document in collection.find(
            {"dataset": ILGA_DATASET_CODE, "year": {"$in": years}},
        )
    }
    outcomes: list[IlgaWriteOutcome] = []
    inserts: list[InsertOne] = []
    inserted_years: list[int] = []
    for prepared in prepared_documents:
        year = int(prepared["year"])
        countries = len(prepared["countries"])
        existing = existing_by_year.get(year)
        if existing is not None:
            differences = _document_differences(existing, prepared)
            status = "existing_different" if differences else "existing_equal"
            outcomes.append(
                IlgaWriteOutcome(
                    year=year,
                    countries=countries,
                    status=status,
                    differences=differences,
                )
            )
            logger.info(
                "ilga_import_existing year=%s countries=%s status=%s differences=%s",
                year,
                countries,
                status,
                ",".join(differences) or "none",
            )
            continue
        inserts.append(InsertOne(prepared))
        inserted_years.append(year)

    if inserts:
        result = collection.bulk_write(inserts, ordered=True)
        if int(result.inserted_count) != len(inserts):
            raise RuntimeError("incomplete_ilga_bulk_write")
        countries_by_year = {
            int(document["year"]): len(document["countries"])
            for document in prepared_documents
        }
        outcomes.extend(
            IlgaWriteOutcome(
                year=year,
                countries=countries_by_year[year],
                status="inserted",
            )
            for year in inserted_years
        )
    return IlgaWriteSummary(tuple(sorted(outcomes, key=lambda outcome: outcome.year)))


def _prepare_ilga_document(document: dict[str, Any]) -> dict[str, Any]:
    if document.get("dataset") != ILGA_DATASET_CODE:
        raise ValueError("invalid_ilga_payload")

    try:
        prepared = parse_ilga_json_text(_json_dumpable_copy(document))
    except ValueError as exc:
        raise ValueError("invalid_ilga_payload") from exc
    if isinstance(prepared, list):
        # Persistence callers expose one stable exception for malformed payloads.
        raise ValueError("invalid_ilga_payload")  # noqa: TRY004

    object_id = _resolve_object_id(document.get("id"))
    prepared["_id"] = object_id
    prepared["id"] = str(object_id)
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


def _document_differences(
    existing: dict[str, Any],
    prepared: dict[str, Any],
) -> tuple[str, ...]:
    ignored = {"_id", "id"}
    existing_payload = {key: value for key, value in existing.items() if key not in ignored}
    prepared_payload = {key: value for key, value in prepared.items() if key not in ignored}
    fields = sorted(set(existing_payload) | set(prepared_payload))
    return tuple(
        field
        for field in fields
        if existing_payload.get(field) != prepared_payload.get(field)
    )
