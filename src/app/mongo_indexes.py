from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any

from pymongo import ASCENDING, DESCENDING, IndexModel
from pymongo.errors import OperationFailure

from app.fra_surveys import FRA_SURVEYS
from app.mongo import get_mongo_collection, get_mongo_database
from app.privacy.policy import get_privacy_policy_config

logger = logging.getLogger(__name__)

NON_REPORT_COLLECTIONS = {
    "country_lgbti_status",
    "Indicator_ilga",
    *(survey.collection for survey in FRA_SURVEYS),
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
    ensure_fra_indexes()
    _ensure_collection_indexes(
        "Indicator_ilga",
        [
            IndexModel(
                [("dataset", ASCENDING), ("year", DESCENDING)],
                unique=True,
                name="ilga_dataset_year",
            )
        ],
    )
    spain_indexes = felgtbi_index_models()
    for collection_name in spain_report_collection_names():
        _ensure_collection_indexes(collection_name, spain_indexes)
    _initialize_non_report_indexes()


def ensure_fra_indexes() -> None:
    """Create only the indexes required by FRA import and Statistics queries."""
    indexes = [
            IndexModel([("code", ASCENDING)], name="fra_code"),
            IndexModel(
                [
                    ("code", ASCENDING),
                    ("category", ASCENDING),
                    ("specific_category", ASCENDING),
                    ("question", ASCENDING),
                    ("survey_year", ASCENDING),
                    ("value_bucket", ASCENDING),
                ],
                unique=True,
                name="fra_question_year_bucket_unique",
            ),
            IndexModel(
                [("dataset", ASCENDING), ("survey_year", DESCENDING)],
                name="fra_dataset_survey_year",
            ),
            IndexModel(
                [
                    ("category", ASCENDING),
                    ("specific_category", ASCENDING),
                    ("question", ASCENDING),
                    ("code", ASCENDING),
                ],
                name="fra_category_question_code",
            ),
            IndexModel(
                [
                    ("category", ASCENDING),
                    ("survey_year", DESCENDING),
                    ("specific_category", ASCENDING),
                    ("question", ASCENDING),
                    ("code", ASCENDING),
                ],
                name="fra_category_year_question_code",
            ),
            IndexModel(
                [("survey_year", DESCENDING), ("code", ASCENDING)],
                name="fra_year_code",
            ),
        ]
    for survey in FRA_SURVEYS:
        if not survey.enabled:
            continue
        _ensure_collection_indexes(survey.collection, indexes)
        _drop_obsolete_indexes(
            survey.collection,
            {"fra_category_question_code_year", "fra_question_year_unique"},
        )


def felgtbi_index_models() -> list[IndexModel]:
    """Indexes aligned with the Spain catalog, navigation and detail queries."""
    return [
        IndexModel(
            [("source", ASCENDING), ("year", DESCENDING), ("source_document_id", ASCENDING)],
            name="felgtbi_year_documents",
        ),
        IndexModel(
            [
                ("source", ASCENDING),
                ("source_document_id", ASCENDING),
                ("page", ASCENDING),
                ("code", ASCENDING),
            ],
            name="felgtbi_document_navigation",
        ),
        IndexModel(
            [("source", ASCENDING), ("source_document_id", ASCENDING), ("code", ASCENDING)],
            name="felgtbi_document_indicator",
        ),
    ]


def _initialize_non_report_indexes() -> None:
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
        ],
    )
    _ensure_collection_indexes(
        "didactica_progress",
        [IndexModel([("user_id", ASCENDING)], unique=True, name="didactica_user_unique")],
    )
    _ensure_collection_indexes(
        "didactica_docente_games",
        [
            IndexModel([("id", ASCENDING)], unique=True, name="docente_game_id_unique"),
            IndexModel(
                [("owner_id", ASCENDING), ("updated_at", DESCENDING)],
                name="docente_games_by_owner",
            ),
        ],
    )
    _ensure_collection_indexes(
        "user_admin_audit",
        [
            IndexModel(
                [("target_user_id", ASCENDING), ("created_at", DESCENDING)],
                name="user_audit_by_target",
            ),
            IndexModel(
                [("actor_user_id", ASCENDING), ("created_at", DESCENDING)],
                name="user_audit_by_actor",
            ),
            IndexModel([("expires_at", ASCENDING)], expireAfterSeconds=0, name="user_audit_ttl"),
        ],
    )
    _ensure_collection_indexes(
        "user_account_security",
        [IndexModel([("user_id", ASCENDING)], unique=True, name="account_security_user")],
    )
    _ensure_collection_indexes(
        "user_security_tokens",
        [
            IndexModel(
                [("purpose", ASCENDING), ("token_hash", ASCENDING)],
                unique=True,
                name="security_token_hash",
            ),
            IndexModel(
                [("user_id", ASCENDING), ("purpose", ASCENDING), ("used_at", ASCENDING)],
                name="security_tokens_by_user",
            ),
            IndexModel([("expires_at", ASCENDING)], expireAfterSeconds=0, name="security_token_ttl"),
        ],
    )
    _ensure_collection_indexes(
        "user_security_audit",
        [
            IndexModel(
                [("user_id", ASCENDING), ("created_at", DESCENDING)],
                name="security_audit_by_user",
            ),
            IndexModel(
                [("expires_at", ASCENDING)],
                expireAfterSeconds=0,
                name="security_audit_ttl",
            ),
        ],
    )
    _ensure_collection_indexes(
        "user_deletion_requests",
        [
            IndexModel(
                [("user_id", ASCENDING)],
                unique=True,
                sparse=True,
                name="deletion_request_user_unique",
            ),
            IndexModel(
                [("expires_at", ASCENDING)],
                expireAfterSeconds=0,
                name="deletion_request_ttl",
            ),
        ],
    )
    _backfill_audit_expiry("user_admin_audit")
    _backfill_audit_expiry("user_security_audit")


def ensure_ilga_unique_index() -> None:
    """Safely upgrade the annual ILGA identity index after checking legacy data."""
    collection = get_mongo_collection("Indicator_ilga")
    duplicates = list(
        collection.aggregate(
            [
                {
                    "$group": {
                        "_id": {"dataset": "$dataset", "year": "$year"},
                        "documents": {"$sum": 1},
                    }
                },
                {"$match": {"documents": {"$gt": 1}}},
                {"$limit": 1},
            ]
        )
    )
    if duplicates:
        duplicate = duplicates[0].get("_id") or {}
        raise ValueError(
            "duplicate_ilga_documents:"
            f"{duplicate.get('dataset')}:{duplicate.get('year')}"
        )

    desired = IndexModel(
        [("dataset", ASCENDING), ("year", DESCENDING)],
        unique=True,
        name="ilga_dataset_year",
    )
    desired_key = _index_key(dict(desired.document))
    existing = _list_indexes(collection)
    incompatible = next(
        (
            index
            for index in existing
            if _index_key(index) == desired_key and not bool(index.get("unique", False))
        ),
        None,
    )
    if incompatible is not None:
        collection.drop_index(str(incompatible["name"]))
        logger.info(
            "mongo_index_replaced collection=Indicator_ilga old_index=%s new_index=ilga_dataset_year",
            incompatible["name"],
        )
    _ensure_collection_indexes("Indicator_ilga", [desired])


def _backfill_audit_expiry(collection_name: str) -> None:
    """Apply the configured retention to legacy audit rows once."""

    retention_days = get_privacy_policy_config().audit_retention_days
    try:
        get_mongo_collection(collection_name).update_many(
            {"expires_at": {"$exists": False}},
            [
                {
                    "$set": {
                        "expires_at": {
                            "$dateAdd": {
                                "startDate": {"$ifNull": ["$created_at", datetime.now(UTC)]},
                                "unit": "day",
                                "amount": retention_days,
                            }
                        }
                    }
                }
            ],
        )
    except Exception:
        logger.warning(
            "mongo_audit_retention_backfill_failed",
            extra={"collection": collection_name},
            exc_info=True,
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


def _drop_obsolete_indexes(collection_name: str, names: set[str]) -> None:
    """Remove only explicitly superseded indexes after replacements exist."""
    collection = get_mongo_collection(collection_name)
    existing_names = {str(index.get("name") or "") for index in _list_indexes(collection)}
    for name in sorted(names.intersection(existing_names)):
        collection.drop_index(name)
        logger.info(
            "mongo_obsolete_index_removed collection=%s index=%s",
            collection_name,
            name,
        )


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
