from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from pymongo import ReturnDocument

from app.infrastructure.mongo import get_mongo_collection, get_mongo_database
from app.modules.account.privacy.policy import get_privacy_policy_config

ACCOUNT_COLLECTION = "user_account_security"
SECURITY_AUDIT_COLLECTION = "user_security_audit"


class AccountSecurityStorageError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class AccountSecurityState:
    user_id: str
    active: bool
    session_version: int
    legacy_default: bool = False


def initialize_new_account(user_id: str) -> AccountSecurityState:
    if not user_id:
        raise ValueError("user_id_required")
    now = datetime.now(UTC)
    try:
        document = get_mongo_collection(ACCOUNT_COLLECTION).find_one_and_update(
            {"user_id": user_id},
            {
                "$setOnInsert": {
                    "user_id": user_id,
                    "active": True,
                    "session_version": 0,
                    "created_at": now,
                },
                "$set": {"updated_at": now},
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
    except Exception as exc:
        raise AccountSecurityStorageError("account_security_unavailable") from exc
    return _state_from_document(document, user_id=user_id, legacy_default=False)


def migrate_account_security_schema() -> None:
    """Remove obsolete account-verification data while retaining session security."""
    now = datetime.now(UTC)
    try:
        collection = get_mongo_collection(ACCOUNT_COLLECTION)
        for obsolete_field in (
            "admin_validated",
            "validated_at",
            "validated_by",
            "email_verified",
        ):
            collection.update_many(
                {obsolete_field: {"$exists": True}},
                {"$unset": {obsolete_field: ""}, "$set": {"updated_at": now}},
            )
        database = get_mongo_database()
        if "user_security_tokens" in database.list_collection_names():
            database.drop_collection("user_security_tokens")
    except Exception as exc:
        raise AccountSecurityStorageError("account_security_migration_failed") from exc


def get_account_security(user_id: str) -> AccountSecurityState:
    if not user_id:
        raise ValueError("user_id_required")
    try:
        document = get_mongo_collection(ACCOUNT_COLLECTION).find_one({"user_id": user_id})
    except Exception as exc:
        raise AccountSecurityStorageError("account_security_unavailable") from exc
    if document is None:
        return AccountSecurityState(
            user_id=user_id,
            active=True,
            session_version=0,
            legacy_default=True,
        )
    return _state_from_document(document, user_id=user_id, legacy_default=False)


def get_account_security_many(user_ids: list[str]) -> dict[str, AccountSecurityState]:
    unique_ids = list(dict.fromkeys(user_id for user_id in user_ids if user_id))
    if not unique_ids:
        return {}
    try:
        documents = list(
            get_mongo_collection(ACCOUNT_COLLECTION).find({"user_id": {"$in": unique_ids}})
        )
    except Exception as exc:
        raise AccountSecurityStorageError("account_security_unavailable") from exc
    by_id = {
        str(document.get("user_id")): _state_from_document(
            document,
            user_id=str(document.get("user_id")),
            legacy_default=False,
        )
        for document in documents
        if document.get("user_id")
    }
    return {
        user_id: by_id.get(
            user_id,
            AccountSecurityState(user_id, True, 0, legacy_default=True),
        )
        for user_id in unique_ids
    }


def increment_session_version(user_id: str) -> int:
    now = datetime.now(UTC)
    try:
        document = get_mongo_collection(ACCOUNT_COLLECTION).find_one_and_update(
            {"user_id": user_id},
            {
                "$setOnInsert": {
                    "user_id": user_id,
                    "active": True,
                    "created_at": now,
                },
                "$inc": {"session_version": 1},
                "$set": {"updated_at": now},
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
    except Exception as exc:
        raise AccountSecurityStorageError("account_security_unavailable") from exc
    return max(0, int((document or {}).get("session_version") or 0))


def record_security_event(user_id: str, action: str) -> None:
    now = datetime.now(UTC)
    try:
        get_mongo_collection(SECURITY_AUDIT_COLLECTION).insert_one(
            {
                "user_id": user_id,
                "action": action,
                "created_at": now,
                "expires_at": now
                + timedelta(days=get_privacy_policy_config().audit_retention_days),
            }
        )
    except Exception as exc:
        raise AccountSecurityStorageError("security_audit_unavailable") from exc


def _state_from_document(
    document: Any,
    *,
    user_id: str,
    legacy_default: bool,
) -> AccountSecurityState:
    values = cast(dict[str, Any], document or {})
    return AccountSecurityState(
        user_id=user_id,
        active=bool(values.get("active", True)),
        session_version=max(0, int(values.get("session_version") or 0)),
        legacy_default=legacy_default,
    )
