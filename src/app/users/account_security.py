from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from pymongo import ReturnDocument

from app.mongo import get_mongo_collection, get_mongo_database
from app.privacy.policy import get_privacy_policy_config

ACCOUNT_COLLECTION = "user_account_security"
SECURITY_AUDIT_COLLECTION = "user_security_audit"


class AccountSecurityStorageError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class AccountSecurityState:
    user_id: str
    active: bool
    admin_validated: bool
    validated_at: datetime | None
    validated_by: str | None
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
                    "admin_validated": False,
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


def migrate_account_validation_schema() -> None:
    """Replace obsolete email-verification state and remove its token collection."""
    now = datetime.now(UTC)
    try:
        collection = get_mongo_collection(ACCOUNT_COLLECTION)
        collection.update_many(
            {"admin_validated": {"$exists": False}},
            {"$set": {"admin_validated": False, "updated_at": now}},
        )
        collection.update_many(
            {"email_verified": {"$exists": True}},
            {"$unset": {"email_verified": ""}, "$set": {"updated_at": now}},
        )
        database = get_mongo_database()
        if "user_security_tokens" in database.list_collection_names():
            database.drop_collection("user_security_tokens")
    except Exception as exc:
        raise AccountSecurityStorageError("account_validation_migration_failed") from exc


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
            admin_validated=False,
            validated_at=None,
            validated_by=None,
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
            AccountSecurityState(user_id, True, False, None, None, 0, legacy_default=True),
        )
        for user_id in unique_ids
    }


def mark_admin_validated(user_id: str, actor_user_id: str) -> AccountSecurityState:
    if not user_id or not actor_user_id:
        raise ValueError("validation_actor_required")
    if user_id == actor_user_id:
        raise ValueError("self_manage")
    now = datetime.now(UTC)
    return _update_account_state(
        user_id,
        {
            "admin_validated": True,
            "validated_at": now,
            "validated_by": actor_user_id,
        },
        upsert_defaults=True,
    )


def increment_session_version(user_id: str) -> int:
    now = datetime.now(UTC)
    try:
        document = get_mongo_collection(ACCOUNT_COLLECTION).find_one_and_update(
            {"user_id": user_id},
            {
                "$setOnInsert": {
                    "user_id": user_id,
                    "active": True,
                    "admin_validated": False,
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


def _update_account_state(
    user_id: str,
    changes: dict[str, Any],
    *,
    upsert_defaults: bool,
) -> AccountSecurityState:
    now = datetime.now(UTC)
    update: dict[str, Any] = {"$set": {**changes, "updated_at": now}}
    if upsert_defaults:
        defaults = {
            "user_id": user_id,
            "active": True,
            "admin_validated": False,
            "session_version": 0,
            "created_at": now,
        }
        for key in changes:
            defaults.pop(key, None)
        update["$setOnInsert"] = defaults
    try:
        document = get_mongo_collection(ACCOUNT_COLLECTION).find_one_and_update(
            {"user_id": user_id},
            update,
            upsert=upsert_defaults,
            return_document=ReturnDocument.AFTER,
        )
    except Exception as exc:
        raise AccountSecurityStorageError("account_security_unavailable") from exc
    return _state_from_document(document, user_id=user_id, legacy_default=False)


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
        admin_validated=bool(values.get("admin_validated", False)),
        validated_at=(
            values.get("validated_at") if isinstance(values.get("validated_at"), datetime) else None
        ),
        validated_by=(str(values["validated_by"]) if values.get("validated_by") else None),
        session_version=max(0, int(values.get("session_version") or 0)),
        legacy_default=legacy_default,
    )
