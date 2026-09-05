from __future__ import annotations

from collections import deque
from types import SimpleNamespace
from typing import Any, Self, cast

import pytest

from app.modules.account.users import service
from app.modules.account.users.account_security import (
    AccountSecurityState,
    AccountSecurityStorageError,
)
from app.modules.account.users.schemas import (
    MAX_PASSWORD_LENGTH,
    MIN_PASSWORD_LENGTH,
    UserRegister,
    UserRole,
    UserType,
)


class _Result:
    def __init__(self, *, row=None, rows=None) -> None:
        self.row = row
        self.rows = rows or []

    def fetchone(self):
        return self.row

    def fetchall(self):
        return self.rows


class _Connection:
    def __init__(self, results: list[_Result]) -> None:
        self.results = deque(results)
        self.calls: list[tuple[str, tuple[Any, ...] | None]] = []
        self.committed = False

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, query: str, params=None):
        self.calls.append((query, params))
        return self.results.popleft()

    def commit(self) -> None:
        self.committed = True


def _row(**overrides: Any) -> dict[str, Any]:
    return {
        "id": "00000000-0000-0000-0000-000000000001",
        "username": "Alex",
        "email": "alex@example.com",
        "organization": None,
        "password_hash": "hash",
        "user_type": "comun",
        **overrides,
    }


def _register(**overrides: Any) -> UserRegister:
    return UserRegister.model_validate(
        {
            "name": "Alex",
            "email": "alex@example.com",
            "password": "long-enough-password",
            **overrides,
        }
    )


def test_user_catalog_and_page_map_security_states(monkeypatch) -> None:
    rows = [_row(), _row(id="user-2", username=None, user_type="admin")]
    connection = _Connection([_Result(rows=rows)])
    monkeypatch.setattr(service, "_connect", lambda: connection)
    monkeypatch.setattr(
        service,
        "get_account_security_many",
        lambda ids: {
            ids[0]: AccountSecurityState(ids[0], False, 4),
            ids[1]: AccountSecurityState(ids[1], True, 1),
        },
    )

    users = service.list_users()

    assert [(item.role, item.active, item.session_version) for item in users] == [
        (UserRole.COMMON, False, 4),
        (UserRole.ADMIN, True, 1),
    ]
    assert users[1].organization == "No organization"


def test_user_page_clamps_size_page_and_escapes_search(monkeypatch) -> None:
    connection = _Connection([_Result(row={"total": 0}), _Result(rows=[])])
    monkeypatch.setattr(service, "_connect", lambda: connection)
    monkeypatch.setattr(service, "get_account_security_many", lambda _ids: {})

    page = service.list_users_page(search="50%_", page=-3, page_size=500)

    assert (page.page, page.page_size, page.page_count, page.total) == (1, 100, 1, 0)
    count_params = connection.calls[0][1]
    assert count_params is not None and count_params[1] == r"%50\%\_%"


def test_user_lookup_handles_blank_missing_and_security_state(monkeypatch) -> None:
    assert service.get_user_record("") is None
    assert service.get_user_record_by_email("bad") is None

    missing = _Connection([_Result(row=None)])
    monkeypatch.setattr(service, "_connect", lambda: missing)
    assert service.get_user_record("user-1") is None

    found = _Connection([_Result(row=_row())])
    monkeypatch.setattr(service, "_connect", lambda: found)
    monkeypatch.setattr(
        service,
        "_account_state",
        lambda user_id: AccountSecurityState(user_id, False, 3),
    )
    record = service.get_user_record_by_email(" ALEX@EXAMPLE.COM ")
    assert record is not None and record.active is False and record.session_version == 3
    assert found.calls[0][1] == ("alex@example.com",)
    monkeypatch.setattr(service, "get_user_record", lambda _user_id: record)
    assert service.get_user(record.id) is not None


@pytest.mark.parametrize(
    ("payload", "error"),
    [
        (SimpleNamespace(email="bad", name="Alex", organization=None), "invalid_email"),
        (
            SimpleNamespace(email="alex@example.com", name="A", organization=None),
            "invalid_username",
        ),
        (
            SimpleNamespace(email="alex@example.com", name="Alex", organization="x" * 121),
            "invalid_organization",
        ),
    ],
)
def test_create_user_validates_non_pydantic_callers(payload, error: str) -> None:
    payload.password = SimpleNamespace(get_secret_value=lambda: "long-enough-password")
    with pytest.raises(ValueError, match=error):
        service.create_user(payload)


@pytest.mark.parametrize("length", [MIN_PASSWORD_LENGTH - 1, MAX_PASSWORD_LENGTH + 1, 128])
def test_create_user_rejects_passwords_outside_policy_for_non_pydantic_callers(
    length: int,
) -> None:
    payload = SimpleNamespace(
        email="alex@example.com",
        name="Alex",
        organization=None,
        password=SimpleNamespace(get_secret_value=lambda: "x" * length),
    )

    with pytest.raises(ValueError, match="weak_password"):
        service.create_user(cast(Any, payload))


def test_create_user_assigns_role_initializes_security_and_commits(monkeypatch) -> None:
    connection = _Connection([_Result(row=_row(user_type="admin"))])
    monkeypatch.setattr(service, "_connect", lambda: connection)
    monkeypatch.setattr(
        service,
        "initialize_new_account",
        lambda user_id: AccountSecurityState(user_id, True, 0),
    )

    created = service.create_user(_register(), role=UserRole.ADMIN)

    assert created.role == UserRole.ADMIN
    assert connection.committed is True
    params = connection.calls[0][1]
    assert params is not None
    assert params[2] == UserType.ADMIN.value


def test_create_user_maps_missing_row_and_security_storage(monkeypatch) -> None:
    monkeypatch.setattr(service, "_connect", lambda: _Connection([_Result(row=None)]))
    with pytest.raises(service.UserStorageError, match="user_creation_failed"):
        service.create_user(_register())

    monkeypatch.setattr(service, "_connect", lambda: _Connection([_Result(row=_row())]))
    monkeypatch.setattr(
        service,
        "initialize_new_account",
        lambda _user_id: (_ for _ in ()).throw(AccountSecurityStorageError("offline")),
    )
    with pytest.raises(service.UserStorageError, match="account_security_unavailable"):
        service.create_user(_register())


@pytest.mark.parametrize(
    ("record", "kwargs", "error"),
    [
        (None, {}, "user_not_found"),
        (_row(password_hash=None), {}, "invalid_current_password"),
    ],
)
def test_profile_update_rejects_missing_user_or_password(
    monkeypatch, record, kwargs, error
) -> None:
    mapped = service._row_to_user_record(record) if record else None
    monkeypatch.setattr(service, "get_user_record", lambda _user_id: mapped)
    with pytest.raises(ValueError, match=error):
        service.update_user_profile(
            user_id="user-1",
            username="Alex",
            email="alex@example.com",
            current_password="wrong",
            **kwargs,
        )


@pytest.mark.parametrize(
    ("username", "email", "new_password", "error"),
    [
        ("A", "alex@example.com", "", "invalid_username"),
        ("Alex", "bad", "", "invalid_email"),
        ("Alex", "alex@example.com", "short", "weak_password"),
    ],
)
def test_profile_update_validates_changed_fields(
    monkeypatch, username: str, email: str, new_password: str, error: str
) -> None:
    record = service._row_to_user_record(_row(password_hash="known"))
    monkeypatch.setattr(service, "get_user_record", lambda _user_id: record)
    monkeypatch.setattr(service, "check_password_hash", lambda *_args: True)

    with pytest.raises(ValueError, match=error):
        service.update_user_profile(
            user_id=record.id,
            username=username,
            email=email,
            current_password="valid",
            new_password=new_password,
        )


def test_profile_update_maps_missing_row_and_security_failure(monkeypatch) -> None:
    record = service._row_to_user_record(_row(password_hash="known"))
    monkeypatch.setattr(service, "get_user_record", lambda _user_id: record)
    monkeypatch.setattr(service, "check_password_hash", lambda *_args: True)
    monkeypatch.setattr(service, "_connect", lambda: _Connection([_Result(row=None)]))
    with pytest.raises(ValueError, match="user_not_found"):
        service.update_user_profile(
            user_id=record.id,
            username="Alex",
            email="alex@example.com",
            current_password="valid",
        )

    monkeypatch.setattr(
        service,
        "_connect",
        lambda: _Connection([_Result(row=_row(email="new@example.com"))]),
    )
    monkeypatch.setattr(
        service,
        "increment_session_version",
        lambda _user_id: (_ for _ in ()).throw(AccountSecurityStorageError("offline")),
    )
    with pytest.raises(service.UserStorageError, match="account_security_unavailable"):
        service.update_user_profile(
            user_id=record.id,
            username="Alex",
            email="new@example.com",
            current_password="valid",
        )


def test_user_mapping_helpers_handle_unknown_roles_and_security_errors(monkeypatch) -> None:
    assert service._parse_user_type("owner") is None
    assert service._role_from_user_type("owner") == UserRole.COMMON
    assert service._normalize_optional_text(None) is None
    assert service._normalize_optional_text("  ") is None
    monkeypatch.setattr(
        service,
        "get_account_security_many",
        lambda _ids: (_ for _ in ()).throw(AccountSecurityStorageError("offline")),
    )
    with pytest.raises(service.UserStorageError, match="account_security_unavailable"):
        service._rows_to_user_reads([_row()])
    monkeypatch.setattr(
        service,
        "get_account_security",
        lambda _id: (_ for _ in ()).throw(AccountSecurityStorageError("offline")),
    )
    with pytest.raises(service.UserStorageError, match="account_security_unavailable"):
        service._account_state("user-1")
