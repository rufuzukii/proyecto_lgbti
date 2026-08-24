from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from typing import Any

from pymongo import ReturnDocument

from app.users import account_security


class _MemoryCollection:
    def __init__(self) -> None:
        self.documents: list[dict[str, Any]] = []

    def find_one(self, query: dict[str, Any]) -> dict[str, Any] | None:
        return next((deepcopy(item) for item in self.documents if _matches(item, query)), None)

    def find(self, query: dict[str, Any]) -> list[dict[str, Any]]:
        return [deepcopy(item) for item in self.documents if _matches(item, query)]

    def insert_one(self, document: dict[str, Any]) -> object:
        self.documents.append(deepcopy(document))
        return object()

    def update_many(self, query: dict[str, Any], update: dict[str, Any]) -> object:
        for document in self.documents:
            if _matches(document, query):
                _apply_update(document, update, inserting=False)
        return object()

    def find_one_and_update(
        self,
        query: dict[str, Any],
        update: dict[str, Any],
        *,
        upsert: bool = False,
        return_document: bool = ReturnDocument.BEFORE,
    ) -> dict[str, Any] | None:
        for document in self.documents:
            if _matches(document, query):
                before = deepcopy(document)
                _apply_update(document, update, inserting=False)
                return deepcopy(document) if return_document == ReturnDocument.AFTER else before
        if not upsert:
            return None
        document = {
            key: value
            for key, value in query.items()
            if not isinstance(value, dict)
        }
        _apply_update(document, update, inserting=True)
        self.documents.append(document)
        return deepcopy(document) if return_document == ReturnDocument.AFTER else None


def _matches(document: dict[str, Any], query: dict[str, Any]) -> bool:
    for key, expected in query.items():
        actual = document.get(key)
        if isinstance(expected, dict):
            if "$in" in expected and actual not in expected["$in"]:
                return False
            if "$gt" in expected and not (actual is not None and actual > expected["$gt"]):
                return False
        elif actual != expected:
            return False
    return True


def _apply_update(document: dict[str, Any], update: dict[str, Any], *, inserting: bool) -> None:
    if inserting:
        document.update(deepcopy(update.get("$setOnInsert") or {}))
    document.update(deepcopy(update.get("$set") or {}))
    for key, increment in (update.get("$inc") or {}).items():
        document[key] = int(document.get(key) or 0) + int(increment)


def _collections(monkeypatch) -> dict[str, _MemoryCollection]:
    collections: dict[str, _MemoryCollection] = {}
    monkeypatch.setattr(
        account_security,
        "get_mongo_collection",
        lambda name: collections.setdefault(name, _MemoryCollection()),
    )
    return collections


def test_new_accounts_start_active_but_unverified(monkeypatch) -> None:
    # Arrange
    _collections(monkeypatch)

    # Act
    created = account_security.initialize_new_account("user-1")
    loaded = account_security.get_account_security("user-1")

    # Assert
    assert created.active is True
    assert created.email_verified is False
    assert loaded == created


def test_legacy_accounts_without_metadata_remain_compatible(monkeypatch) -> None:
    # Arrange
    _collections(monkeypatch)

    # Act
    state = account_security.get_account_security("legacy-user")

    # Assert
    assert state.active is True
    assert state.email_verified is True
    assert state.legacy_default is True


def test_token_is_hashed_single_use_and_purpose_specific(monkeypatch) -> None:
    # Arrange
    collections = _collections(monkeypatch)

    # Act
    token = account_security.issue_security_token(
        "user-1",
        "email_verification",
        ttl_seconds=600,
    )
    wrong_purpose = account_security.consume_security_token(token, "password_reset")
    first_use = account_security.consume_security_token(token, "email_verification")
    second_use = account_security.consume_security_token(token, "email_verification")

    # Assert
    stored = collections[account_security.TOKEN_COLLECTION].documents[0]
    assert token not in str(stored)
    assert len(stored["token_hash"]) == 64
    assert wrong_purpose is None
    assert first_use == "user-1"
    assert second_use is None


def test_issuing_a_new_token_invalidates_the_previous_one(monkeypatch) -> None:
    # Arrange
    _collections(monkeypatch)
    previous = account_security.issue_security_token(
        "user-1", "password_reset", ttl_seconds=600
    )

    # Act
    current = account_security.issue_security_token("user-1", "password_reset", ttl_seconds=600)

    # Assert
    assert account_security.consume_security_token(previous, "password_reset") is None
    assert account_security.consume_security_token(current, "password_reset") == "user-1"


def test_expired_token_is_rejected(monkeypatch) -> None:
    # Arrange
    collections = _collections(monkeypatch)
    token = account_security.issue_security_token(
        "user-1", "email_verification", ttl_seconds=600
    )
    collections[account_security.TOKEN_COLLECTION].documents[0]["expires_at"] = (
        datetime.now(UTC) - timedelta(seconds=1)
    )

    # Act / Assert
    assert account_security.consume_security_token(token, "email_verification") is None


def test_session_version_is_persistent_without_changing_technical_active_state(
    monkeypatch,
) -> None:
    # Arrange
    _collections(monkeypatch)
    account_security.initialize_new_account("user-1")

    # Act
    session_version = account_security.increment_session_version("user-1")
    loaded = account_security.get_account_security("user-1")

    # Assert
    assert session_version == 1
    assert loaded.active is True
    assert loaded.session_version == 1
