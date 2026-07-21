from __future__ import annotations

from functools import lru_cache
import logging
from typing import Any, Iterable, Mapping

from pymongo import ASCENDING, DESCENDING, IndexModel
from pymongo.errors import OperationFailure

from app.mongo import get_mongo_collection, get_mongo_database

logger = logging.getLogger(__name__)

NON_REPORT_COLLECTIONS = {
    "country_lgbti_status",
    "Indicator_fra",
    "Indicator_ilga",
}


def spain_report_collection_names() -> set[str]:
    database = get_mongo_database()
    return {
        "Indicator_felgtbi",
        *(
            name
            for name in database.list_collection_names()
            if name not in NON_REPORT_COLLECTIONS
            and any(token in name.casefold() for token in ("felgtbi", "lgtbi", "spain"))
        ),
    }


@lru_cache(maxsize=1)
def initialize_mongo_indexes() -> None:
    """Create application indexes once at process startup or from the setup CLI."""
    _ensure_collection_indexes(
        "Indicator_fra",
        [
            IndexModel([("code", ASCENDING)], name="fra_code"),
            IndexModel(
                [
                    ("category", ASCENDING),
                    ("specific_category", ASCENDING),
                    ("question", ASCENDING),
                    ("code", ASCENDING),
                ],
                name="fra_category_question_code",
            ),
        ]
    )
    _ensure_collection_indexes(
        "Indicator_ilga",
        [IndexModel([("dataset", ASCENDING), ("year", DESCENDING)], name="ilga_dataset_year")]
    )
    spain_indexes = [
        IndexModel([("code", ASCENDING)], name="felgtbi_code"),
        IndexModel([("source_document_id", ASCENDING)], name="felgtbi_document"),
        IndexModel([("original_filename", ASCENDING)], name="felgtbi_filename"),
        IndexModel(
            [("source", ASCENDING), ("category", ASCENDING), ("year", DESCENDING)],
            name="felgtbi_source_category_year",
        ),
        IndexModel(
            [
                ("source", ASCENDING),
                ("source_document_id", ASCENDING),
                ("year", DESCENDING),
                ("page", ASCENDING),
                ("code", ASCENDING),
            ],
            name="felgtbi_document_sections",
        ),
        IndexModel(
            [("source", ASCENDING), ("original_filename", ASCENDING), ("year", DESCENDING)],
            name="felgtbi_source_filename_year",
        ),
        IndexModel(
            [("source", ASCENDING), ("report_type", ASCENDING)],
            name="felgtbi_source_report_type",
        ),
        IndexModel(
            [("source", ASCENDING), ("question", ASCENDING), ("year", DESCENDING)],
            name="felgtbi_source_question_year",
        ),
    ]
    for collection_name in spain_report_collection_names():
        _ensure_collection_indexes(collection_name, spain_indexes)
    _ensure_collection_indexes(
        "country_lgbti_status",
        [
            IndexModel(
                [("country_code", ASCENDING), ("year", ASCENDING)],
                unique=True,
                name="country_year_unique",
            ),
            IndexModel(
                [("active", ASCENDING), ("country_code", ASCENDING), ("year", DESCENDING)],
                name="active_country_year",
            ),
        ]
    )


def _ensure_collection_indexes(
    collection_name: str,
    index_models: Iterable[IndexModel],
) -> None:
    """Create only indexes not already covered by an equivalent key definition.

    MongoDB considers two indexes with the same keys and options equivalent even
    when their names differ. Checking the key definition first keeps startup
    idempotent for databases that already contain automatically named indexes
    such as ``code_1``.
    """
    collection = get_mongo_collection(collection_name)
    existing = _list_indexes(collection)
    for index_model in index_models:
        desired = dict(index_model.document)
        desired_key = _index_key(desired)
        matching_key = next(
            (index for index in existing if _index_key(index) == desired_key),
            None,
        )
        if matching_key is not None:
            if _index_satisfies(matching_key, desired):
                logger.debug(
                    "mongo_index_reused",
                    extra={
                        "collection": collection_name,
                        "existing_index": matching_key.get("name"),
                        "requested_index": desired.get("name"),
                    },
                )
            else:
                logger.warning(
                    "mongo_index_definition_conflict",
                    extra={
                        "collection": collection_name,
                        "existing_index": matching_key.get("name"),
                        "requested_index": desired.get("name"),
                    },
                )
            continue

        matching_name = next(
            (index for index in existing if index.get("name") == desired.get("name")),
            None,
        )
        if matching_name is not None:
            logger.warning(
                "mongo_index_name_conflict",
                extra={
                    "collection": collection_name,
                    "index": desired.get("name"),
                },
            )
            continue

        try:
            collection.create_indexes([index_model])
        except OperationFailure as exc:
            if exc.code == 85 and _equivalent_index_exists(collection, desired):
                logger.debug(
                    "mongo_index_reused_after_concurrent_creation",
                    extra={"collection": collection_name, "index": desired.get("name")},
                )
                existing = _list_indexes(collection)
                continue
            raise
        existing.append(desired)


def _list_indexes(collection: Any) -> list[dict[str, Any]]:
    try:
        return [dict(index) for index in collection.list_indexes()]
    except OperationFailure as exc:
        if exc.code == 26:  # NamespaceNotFound: the first index creates the collection.
            return []
        raise


def _equivalent_index_exists(collection: Any, desired: Mapping[str, Any]) -> bool:
    desired_key = _index_key(desired)
    return any(
        _index_key(index) == desired_key and _index_satisfies(index, desired)
        for index in _list_indexes(collection)
    )


def _index_key(index: Mapping[str, Any]) -> tuple[tuple[str, Any], ...]:
    key = index.get("key")
    if isinstance(key, Mapping):
        return tuple((str(field), direction) for field, direction in key.items())
    return ()


def _index_satisfies(existing: Mapping[str, Any], desired: Mapping[str, Any]) -> bool:
    if bool(desired.get("unique", False)) and not bool(existing.get("unique", False)):
        return False
    if bool(existing.get("sparse", False)) != bool(desired.get("sparse", False)):
        return False
    for option in (
        "expireAfterSeconds",
        "partialFilterExpression",
        "collation",
        "wildcardProjection",
        "hidden",
    ):
        if existing.get(option) != desired.get(option):
            return False
    return True


if __name__ == "__main__":
    initialize_mongo_indexes()
