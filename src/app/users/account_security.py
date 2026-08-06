from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any, Literal, cast

from pymongo import ReturnDocument

from app.mongo import get_mongo_collection

ACCOUNT_COLLECTION = "user_account_security"
TOKEN_COLLECTION = "user_security_tokens"
SECURITY_AUDIT_COLLECTION = "user_security_audit"
TokenPurpose = Literal["email_verification", "password_reset"]


class AccountSecurityStorageError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class AccountSecurityState:
    user_id: str
    active: bool
    email_verified: bool
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
                    "email_verified": False,
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
            email_verified=True,
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
            AccountSecurityState(user_id, True, True, 0, legacy_default=True),
        )
        for user_id in unique_ids
    }


def set_account_active(user_id: str, *, active: bool) -> AccountSecurityState:
    return _update_account_state(user_id, {"active": bool(active)}, upsert_defaults=True)


def mark_email_verified(user_id: str) -> AccountSecurityState:
    return _update_account_state(user_id, {"email_verified": True}, upsert_defaults=True)


def mark_email_unverified(user_id: str) -> AccountSecurityState:
    return _update_account_state(user_id, {"email_verified": False}, upsert_defaults=True)


def increment_session_version(user_id: str) -> int:
    now = datetime.now(UTC)
    try:
        document = get_mongo_collection(ACCOUNT_COLLECTION).find_one_and_update(
            {"user_id": user_id},
            {
                "$setOnInsert": {
                    "user_id": user_id,
                    "active": True,
                    "email_verified": True,
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


def issue_security_token(
    user_id: str,
    purpose: TokenPurpose,
    *,
    ttl_seconds: int,
) -> str:
    if ttl_seconds < 60:
        raise ValueError("token_ttl_too_short")
    token = secrets.token_urlsafe(32)
    now = datetime.now(UTC)
    token_hash = _hash_token(token)
    collection = get_mongo_collection(TOKEN_COLLECTION)
    try:
        collection.update_many(
            {"user_id": user_id, "purpose": purpose, "used_at": None},
            {"$set": {"used_at": now, "invalidated_reason": "superseded"}},
        )
        collection.insert_one(
            {
                "user_id": user_id,
                "purpose": purpose,
                "token_hash": token_hash,
                "created_at": now,
                "expires_at": now + timedelta(seconds=ttl_seconds),
                "used_at": None,
            }
        )
    except Exception as exc:
        raise AccountSecurityStorageError("security_token_unavailable") from exc
    return token


def consume_security_token(token: str, purpose: TokenPurpose) -> str | None:
    if not isinstance(token, str) or len(token) < 32 or len(token) > 256:
        return None
    now = datetime.now(UTC)
    try:
        document = get_mongo_collection(TOKEN_COLLECTION).find_one_and_update(
            {
                "token_hash": _hash_token(token),
                "purpose": purpose,
                "used_at": None,
                "expires_at": {"$gt": now},
            },
            {"$set": {"used_at": now}},
            return_document=ReturnDocument.BEFORE,
        )
    except Exception as exc:
        raise AccountSecurityStorageError("security_token_unavailable") from exc
    user_id = str((document or {}).get("user_id") or "")
    return user_id or None


def record_security_event(user_id: str, action: str) -> None:
    try:
        get_mongo_collection(SECURITY_AUDIT_COLLECTION).insert_one(
            {
                "user_id": user_id,
                "action": action,
                "created_at": datetime.now(UTC),
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
            "email_verified": True,
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
        email_verified=bool(values.get("email_verified", legacy_default)),
        session_version=max(0, int(values.get("session_version") or 0)),
        legacy_default=legacy_default,
    )


def _hash_token(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()
