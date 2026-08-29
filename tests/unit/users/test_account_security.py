from __future__ import annotations

from copy import deepcopy
from typing import Any

from pymongo import ReturnDocument

from app.modules.account.users import account_security


class _MemoryCollection:
    def __init__(self) -> None:
        self.documents: list[dict[str, Any]] = []

    def find_one(self, query: dict[str, Any]) -> dict[str, Any] | None:
        return next((deepcopy(item) for item in self.documents if _matches(item, query)), None)

    def find(self, query: dict[str, Any]) -> list[dict[str, Any]]:
        return [deepcopy(item) for item in self.documents if _matches(item, query)]

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
        document = {key: value for key, value in query.items() if not isinstance(value, dict)}
        _apply_update(document, update, inserting=True)
        self.documents.append(document)
        return deepcopy(document) if return_document == ReturnDocument.AFTER else None


class _MemoryDatabase:
    def __init__(self, names: list[str]) -> None:
        self.names = names
        self.dropped: list[str] = []

    def list_collection_names(self) -> list[str]:
        return self.names

    def drop_collection(self, name: str) -> None:
        self.dropped.append(name)


def _matches(document: dict[str, Any], query: dict[str, Any]) -> bool:
    for key, expected in query.items():
        actual = document.get(key)
        if isinstance(expected, dict):
            if "$in" in expected and actual not in expected["$in"]:
                return False
            if "$exists" in expected and (key in document) is not expected["$exists"]:
                return False
        elif actual != expected:
            return False
    return True


def _apply_update(document: dict[str, Any], update: dict[str, Any], *, inserting: bool) -> None:
    if inserting:
        document.update(deepcopy(update.get("$setOnInsert") or {}))
    document.update(deepcopy(update.get("$set") or {}))
    for key in (update.get("$unset") or {}):
        document.pop(key, None)
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


def test_new_accounts_start_active_with_an_initial_session_version(monkeypatch) -> None:
    collections = _collections(monkeypatch)
    created = account_security.initialize_new_account("user-1")
    loaded = account_security.get_account_security("user-1")
    assert created.active is True
    assert created.session_version == 0
    assert loaded == created
    stored = collections[account_security.ACCOUNT_COLLECTION].documents[0]
    assert set(stored).isdisjoint({"admin_validated", "validated_at", "validated_by"})


def test_schema_migration_removes_all_legacy_account_verification_data(
    monkeypatch,
) -> None:
    collections = _collections(monkeypatch)
    security = collections.setdefault(account_security.ACCOUNT_COLLECTION, _MemoryCollection())
    security.documents.append(
        {
            "user_id": "legacy",
            "active": True,
            "session_version": 2,
            "email_verified": True,
            "admin_validated": True,
            "validated_at": "legacy-date",
            "validated_by": "legacy-admin",
        }
    )
    database = _MemoryDatabase(["user_security_tokens"])
    monkeypatch.setattr(account_security, "get_mongo_database", lambda: database)
    account_security.migrate_account_security_schema()
    assert set(security.documents[0]).isdisjoint(
        {"email_verified", "admin_validated", "validated_at", "validated_by"}
    )
    assert security.documents[0]["active"] is True
    assert security.documents[0]["session_version"] == 2
    assert database.dropped == ["user_security_tokens"]


def test_session_version_is_persistent(monkeypatch) -> None:
    _collections(monkeypatch)
    account_security.initialize_new_account("user-1")
    session_version = account_security.increment_session_version("user-1")
    loaded = account_security.get_account_security("user-1")
    assert session_version == 1
    assert loaded.session_version == 1
