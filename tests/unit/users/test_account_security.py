from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest
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
    for key in update.get("$unset") or {}:
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


def test_missing_security_document_uses_explicit_legacy_default(monkeypatch) -> None:
    _collections(monkeypatch)

    state = account_security.get_account_security("legacy-user")

    assert state == account_security.AccountSecurityState(
        "legacy-user", True, 0, legacy_default=True
    )
    with pytest.raises(ValueError, match="user_id_required"):
        account_security.get_account_security("")
    with pytest.raises(ValueError, match="user_id_required"):
        account_security.initialize_new_account("")


def test_many_security_states_deduplicate_ids_and_fill_legacy_defaults(monkeypatch) -> None:
    collections = _collections(monkeypatch)
    security = collections.setdefault(account_security.ACCOUNT_COLLECTION, _MemoryCollection())
    security.documents.append({"user_id": "known", "active": False, "session_version": -4})

    states = account_security.get_account_security_many(["known", "", "missing", "known"])

    assert list(states) == ["known", "missing"]
    assert states["known"].active is False
    assert states["known"].session_version == 0
    assert states["missing"].legacy_default is True
    assert account_security.get_account_security_many([]) == {}


@pytest.mark.parametrize(
    ("operation", "message"),
    [
        (lambda: account_security.initialize_new_account("user"), "account_security_unavailable"),
        (lambda: account_security.get_account_security("user"), "account_security_unavailable"),
        (
            lambda: account_security.get_account_security_many(["user"]),
            "account_security_unavailable",
        ),
        (
            lambda: account_security.increment_session_version("user"),
            "account_security_unavailable",
        ),
    ],
)
def test_security_storage_errors_are_mapped(monkeypatch, operation, message: str) -> None:
    class BrokenCollection:
        def __getattr__(self, _name):
            def fail(*_args, **_kwargs):
                raise RuntimeError("mongo offline")

            return fail

    monkeypatch.setattr(account_security, "get_mongo_collection", lambda _name: BrokenCollection())

    with pytest.raises(account_security.AccountSecurityStorageError, match=message):
        operation()


def test_migration_maps_database_errors(monkeypatch) -> None:
    class BrokenCollection:
        def update_many(self, *_args, **_kwargs):
            raise RuntimeError("mongo offline")

    monkeypatch.setattr(account_security, "get_mongo_collection", lambda _name: BrokenCollection())
    with pytest.raises(
        account_security.AccountSecurityStorageError,
        match="account_security_migration_failed",
    ):
        account_security.migrate_account_security_schema()


def test_security_audit_records_retention_and_maps_failures(monkeypatch) -> None:
    inserted: list[dict[str, Any]] = []

    class AuditCollection:
        def insert_one(self, document):
            inserted.append(document)

    monkeypatch.setattr(account_security, "get_mongo_collection", lambda _name: AuditCollection())
    monkeypatch.setattr(
        account_security,
        "get_privacy_policy_config",
        lambda: type("Policy", (), {"audit_retention_days": 30})(),
    )

    account_security.record_security_event("user-1", "password_changed")

    assert inserted[0]["user_id"] == "user-1"
    assert inserted[0]["action"] == "password_changed"
    assert (inserted[0]["expires_at"] - inserted[0]["created_at"]).days == 30

    class BrokenAudit:
        def insert_one(self, _document):
            raise RuntimeError("offline")

    monkeypatch.setattr(account_security, "get_mongo_collection", lambda _name: BrokenAudit())
    with pytest.raises(
        account_security.AccountSecurityStorageError,
        match="security_audit_unavailable",
    ):
        account_security.record_security_event("user-1", "password_changed")
