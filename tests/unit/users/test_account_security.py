from __future__ import annotations

from copy import deepcopy
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


def test_new_accounts_start_active_and_not_admin_validated(monkeypatch) -> None:
    _collections(monkeypatch)
    created = account_security.initialize_new_account("user-1")
    loaded = account_security.get_account_security("user-1")
    assert created.active is True
    assert created.admin_validated is False
    assert created.validated_at is None
    assert loaded == created


def test_admin_validation_is_persistent_and_attributed(monkeypatch) -> None:
    _collections(monkeypatch)
    account_security.initialize_new_account("user-1")
    validated = account_security.mark_admin_validated("user-1", "admin-1")
    loaded = account_security.get_account_security("user-1")
    assert validated.admin_validated is True
    assert validated.validated_by == "admin-1"
    assert validated.validated_at is not None
    assert loaded == validated


def test_admin_cannot_validate_own_account(monkeypatch) -> None:
    _collections(monkeypatch)
    try:
        account_security.mark_admin_validated("admin-1", "admin-1")
    except ValueError as exc:
        assert str(exc) == "self_manage"
    else:
        raise AssertionError("self validation must be rejected")


def test_schema_migration_defaults_existing_accounts_and_removes_legacy_email_data(
    monkeypatch,
) -> None:
    collections = _collections(monkeypatch)
    security = collections.setdefault(account_security.ACCOUNT_COLLECTION, _MemoryCollection())
    security.documents.append({"user_id": "legacy", "email_verified": True})
    database = _MemoryDatabase(["user_security_tokens"])
    monkeypatch.setattr(account_security, "get_mongo_database", lambda: database)
    account_security.migrate_account_validation_schema()
    assert security.documents[0]["admin_validated"] is False
    assert "email_verified" not in security.documents[0]
    assert database.dropped == ["user_security_tokens"]


def test_session_version_is_persistent_without_changing_validation(monkeypatch) -> None:
    _collections(monkeypatch)
    account_security.initialize_new_account("user-1")
    session_version = account_security.increment_session_version("user-1")
    loaded = account_security.get_account_security("user-1")
    assert session_version == 1
    assert loaded.admin_validated is False
    assert loaded.session_version == 1
