from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from werkzeug.security import generate_password_hash

from app.privacy import service
from app.privacy.models import PersonalDataInventory
from app.users.schemas import UserRole, UserType
from app.users.service import UserRecord

USER_ID = "7bf1c278-4ad4-4cf3-a70d-9769590c5099"


def _record(*, user_type: UserType = UserType.COMUN) -> UserRecord:
    return UserRecord(
        id=USER_ID,
        username="Alex",
        email="alex@example.com",
        role=UserRole.ADMIN if user_type == UserType.ADMIN else UserRole.COMMON,
        organization="Rainbow Org",
        password_hash=generate_password_hash("correct-password"),
        user_type=user_type,
    )


def _confirmation(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "email": "Alex@example.com",
        "password": "correct-password",
        "confirmation_checked": True,
        "confirmation_text": "ELIMINAR MI CUENTA",
        "language": "es",
    }
    values.update(overrides)
    return values


def test_deletion_confirmation_accepts_only_current_credentials_and_exact_phrase() -> None:
    # Arrange
    record = _record()

    # Act / Assert
    service.validate_deletion_confirmation(record, **_confirmation())  # type: ignore[arg-type]
    for override, expected in (
        ({"email": "other@example.com"}, "invalid_email"),
        ({"password": "wrong"}, "invalid_password"),
        ({"confirmation_checked": False}, "confirmation_required"),
        ({"confirmation_text": "eliminar mi cuenta"}, "invalid_confirmation_text"),
    ):
        with pytest.raises(service.AccountDeletionError, match=expected):
            service.validate_deletion_confirmation(
                record, **_confirmation(**override)  # type: ignore[arg-type]
            )


def test_english_confirmation_uses_the_english_phrase() -> None:
    # Arrange / Act / Assert
    service.validate_deletion_confirmation(
        _record(),
        **_confirmation(language="en", confirmation_text="DELETE MY ACCOUNT"),  # type: ignore[arg-type]
    )


def test_already_deleted_user_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange
    monkeypatch.setattr(service, "get_user_record", lambda _user_id: None)

    # Act
    result = service.delete_user_account(user_id=USER_ID, **_confirmation())  # type: ignore[arg-type]

    # Assert
    assert result.status == "already_deleted"


def test_deletion_orchestrates_all_stores_before_postgres(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    events: list[str] = []
    inventory = PersonalDataInventory(profile=True, teacher_games=2)
    monkeypatch.setattr(service, "get_personal_data_inventory", lambda _user_id: inventory)
    monkeypatch.setattr(service, "_assert_not_last_admin", lambda _record: events.append("guard"))
    monkeypatch.setattr(
        service, "_start_or_resume_job", lambda _user_id, _inventory: events.append("job")
    )
    monkeypatch.setattr(
        service,
        "_delete_private_mongo_data",
        lambda _user_id: events.append("mongo") or {"teacher_games": 2},
    )
    monkeypatch.setattr(
        service,
        "_delete_personal_supabase_objects",
        lambda _user_id: events.append("supabase") or 0,
    )
    monkeypatch.setattr(
        service,
        "_delete_security_state",
        lambda _user_id: events.append("security") or {"account_security": 1},
    )
    monkeypatch.setattr(
        service,
        "_anonymize_audits",
        lambda _user_id, _subject: events.append("audits") or {"security_audit_events": 1},
    )
    monkeypatch.setattr(
        service,
        "_delete_postgres_account",
        lambda _user_id: events.append("postgres") or {"user_profile": 1},
    )
    monkeypatch.setattr(service, "_invalidate_user_cache", lambda: events.append("cache"))
    monkeypatch.setattr(service, "_mark_stage_safely", lambda _user_id, _stage: None)
    monkeypatch.setattr(service, "_complete_job", lambda _user_id, _subject: events.append("done"))

    # Act
    result = service._execute_account_deletion(_record(), actor_user_id=None)

    # Assert
    assert result.status == "completed"
    assert events == [
        "guard",
        "job",
        "mongo",
        "supabase",
        "security",
        "audits",
        "postgres",
        "cache",
        "done",
    ]
    assert result.deleted["user_profile"] == 1
    assert result.anonymized["security_audit_events"] == 1


def test_partial_failure_remains_pending_and_does_not_reach_postgres(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    events: list[str] = []
    monkeypatch.setattr(
        service,
        "get_personal_data_inventory",
        lambda _user_id: PersonalDataInventory(profile=True),
    )
    monkeypatch.setattr(service, "_assert_not_last_admin", lambda _record: None)
    monkeypatch.setattr(service, "_start_or_resume_job", lambda *_args: events.append("job"))
    monkeypatch.setattr(
        service,
        "_delete_private_mongo_data",
        lambda _user_id: (_ for _ in ()).throw(RuntimeError("mongo unavailable")),
    )
    monkeypatch.setattr(service, "_record_job_failure", lambda *_args: events.append("pending"))
    monkeypatch.setattr(service, "_delete_postgres_account", lambda _user_id: events.append("sql"))

    # Act / Assert
    with pytest.raises(service.AccountDeletionError, match="deletion_incomplete"):
        service._execute_account_deletion(_record(), actor_user_id=None)
    assert events == ["job", "pending"]


def test_last_administrator_is_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange
    class _Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def execute(self, _query: str, _params: object):
            return SimpleNamespace(fetchall=lambda: [{"id": USER_ID}])

    monkeypatch.setattr(service.psycopg, "connect", lambda *_args, **_kwargs: _Connection())
    monkeypatch.setattr(
        service,
        "get_account_security_many",
        lambda user_ids: {
            user_id: SimpleNamespace(active=True)
            for user_id in user_ids
        },
    )

    # Act / Assert
    with pytest.raises(service.AccountDeletionError, match="last_admin"):
        service._assert_not_last_admin(_record(user_type=UserType.ADMIN))


def test_supabase_public_dataset_objects_are_not_treated_as_personal() -> None:
    assert service._delete_personal_supabase_objects(USER_ID) == 0


def test_audit_anonymization_removes_direct_identifiers(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange
    calls: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = {}

    class _Collection:
        def __init__(self, name: str) -> None:
            self.name = name

        def update_many(self, query: dict[str, Any], update: dict[str, Any]):
            calls.setdefault(self.name, []).append((query, update))
            return SimpleNamespace(modified_count=1)

    monkeypatch.setattr(service, "get_mongo_collection", lambda name: _Collection(name))

    # Act
    result = service._anonymize_audits(USER_ID, "deleted:abc")

    # Assert
    assert result["security_audit_events"] == 1
    updates = [update for items in calls.values() for _query, update in items]
    assert any("user_id" in update["$unset"] for update in updates)
    assert any("before" in update["$unset"] and "after" in update["$unset"] for update in updates)


def test_inventory_counts_only_real_user_linked_stores(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange
    class _Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def execute(self, _query: str, _params: object):
            return SimpleNamespace(fetchone=lambda: {"profile": True, "import_logs": 2})

    counts = {
        service.ACCOUNT_COLLECTION: 1,
        service.GAMES_COLLECTION: 3,
        service.SECURITY_AUDIT_COLLECTION: 4,
        service.ADMIN_AUDIT_COLLECTION: 5,
    }
    monkeypatch.setattr(service.psycopg, "connect", lambda *_args, **_kwargs: _Connection())
    monkeypatch.setattr(
        service,
        "get_mongo_collection",
        lambda name: SimpleNamespace(count_documents=lambda _query: counts[name]),
    )

    # Act
    inventory = service.get_personal_data_inventory(USER_ID)

    # Assert
    assert inventory.profile is True
    assert inventory.import_logs == 2
    assert inventory.teacher_games == 3
    assert inventory.admin_audit_events == 5
    assert inventory.supabase_objects == 0
    assert inventory.persisted_reports == 0


def test_portability_export_excludes_passwords_tokens_and_internal_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    class _Result:
        def __init__(self, *, row: object = None, rows: object = None) -> None:
            self.row = row
            self.rows = rows

        def fetchone(self):
            return self.row

        def fetchall(self):
            return self.rows or []

    class _Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def execute(self, query: str, _params: object):
            if "from public.users" in query.casefold():
                return _Result(
                    row={
                        "username": "Alex",
                        "email": "alex@example.com",
                        "organization": "Rainbow Org",
                        "user_type": "comun",
                        "created_at": None,
                    }
                )
            return _Result(rows=[])

    class _Collection:
        def __init__(self, name: str) -> None:
            self.name = name

        def find_one(self, _query: object, _projection: object):
            if self.name == service.ACCOUNT_COLLECTION:
                return {"active": True}
            return None

        def find(self, _query: object, _projection: object):
            return []

    monkeypatch.setattr(service, "get_user_record", lambda _user_id: _record())
    monkeypatch.setattr(service.psycopg, "connect", lambda *_args, **_kwargs: _Connection())
    monkeypatch.setattr(service, "get_mongo_collection", lambda name: _Collection(name))

    # Act
    exported = service.build_personal_data_export(USER_ID)
    serialized = str(exported).casefold()

    # Assert
    assert exported["account"]["email"] == "alex@example.com"
    assert "password_hash" not in serialized
    assert "token_hash" not in serialized
    assert USER_ID not in serialized


def test_deletion_job_upsert_does_not_update_the_same_path_twice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    captured: dict[str, Any] = {}

    class _Collection:
        def update_one(self, _query: object, update: dict[str, Any], *, upsert: bool) -> None:
            captured.update(update)
            assert upsert is True

    monkeypatch.setattr(service, "get_mongo_collection", lambda _name: _Collection())

    # Act
    service._start_or_resume_job(USER_ID, PersonalDataInventory(profile=True))

    # Assert
    assert "attempts" in captured["$inc"]
    assert "attempts" not in captured["$setOnInsert"]
