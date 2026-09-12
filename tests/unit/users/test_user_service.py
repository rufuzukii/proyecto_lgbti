from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Self

import pytest
from werkzeug.security import generate_password_hash

from app.modules.account.privacy import service as privacy_service
from app.modules.account.users import service
from app.modules.account.users.account_security import AccountSecurityState
from app.modules.account.users.schemas import MAX_PASSWORD_LENGTH, UserRole, UserType


@dataclass
class _Result:
    row: dict[str, Any] | None = None
    rowcount: int = 1

    def fetchone(self) -> dict[str, Any] | None:
        return self.row


class _Connection:
    def __init__(self, result: _Result) -> None:
        self.result = result
        self.committed = False
        self.calls: list[tuple[str, tuple[Any, ...] | None]] = []

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, query: str, params: tuple[Any, ...] | None = None) -> _Result:
        self.calls.append((query, params))
        return self.result

    def commit(self) -> None:
        self.committed = True


def _record(*, active: bool = True) -> service.UserRecord:
    return service.UserRecord(
        id="00000000-0000-0000-0000-000000000001",
        username="Alex",
        email="alex@example.test",
        role=UserRole.COMMON,
        organization="RainbowLens",
        password_hash=generate_password_hash("valid-password"),
        user_type=UserType.COMUN,
        active=active,
    )


def _row() -> dict[str, Any]:
    record = _record()
    return {
        "id": record.id,
        "username": record.username,
        "email": record.email,
        "organization": record.organization,
        "password_hash": record.password_hash,
        "user_type": UserType.COMUN.value,
    }


@pytest.mark.parametrize(
    ("email", "password"),
    [
        ("", "valid-password"),
        ("alex@example.test", ""),
        ("alex@example.test", "x" * (MAX_PASSWORD_LENGTH + 1)),
    ],
)
def test_authentication_rejects_incomplete_or_oversized_credentials(
    monkeypatch: pytest.MonkeyPatch,
    email: str,
    password: str,
) -> None:
    monkeypatch.setattr(
        service,
        "get_user_record_by_email",
        lambda _email: pytest.fail("storage must not be queried"),
    )

    result = service.authenticate_user(email, password)

    assert result is None


@pytest.mark.parametrize(
    ("record", "password", "accepted"),
    [
        (None, "valid-password", False),
        (_record(), "wrong-password", False),
        (_record(active=False), "valid-password", False),
        (_record(), "valid-password", True),
    ],
)
def test_authentication_requires_a_valid_password_and_active_account(
    monkeypatch: pytest.MonkeyPatch,
    record: service.UserRecord | None,
    password: str,
    accepted: bool,
) -> None:
    monkeypatch.setattr(service, "get_user_record_by_email", lambda _email: record)

    result = service.authenticate_user("alex@example.test", password)

    assert (result is not None) is accepted


def test_profile_email_change_invalidates_existing_sessions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = _record()
    updated_row = {**_row(), "email": "new@example.com", "username": "Alex Updated"}
    connection = _Connection(_Result(row=updated_row))
    incremented: list[str] = []
    events: list[tuple[str, str]] = []
    monkeypatch.setattr(service, "get_user_record", lambda _user_id: record)
    monkeypatch.setattr(service, "_connect", lambda: connection)
    monkeypatch.setattr(service, "increment_session_version", incremented.append)
    monkeypatch.setattr(
        service,
        "_record_security_event_safely",
        lambda user_id, action: events.append((user_id, action)),
    )
    monkeypatch.setattr(
        service,
        "_account_state",
        lambda user_id: AccountSecurityState(user_id, True, 1),
    )

    updated = service.update_user_profile(
        user_id=record.id,
        username="Alex Updated",
        email="new@example.com",
        current_password="valid-password",
    )

    assert updated.email == "new@example.com"
    assert updated.session_version == 1
    assert incremented == [record.id]
    assert events == [(record.id, "email_changed")]
    assert connection.committed is True


def test_admin_deletion_maps_cross_store_error_to_public_validation_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(**_kwargs: str) -> None:
        raise privacy_service.AccountDeletionError("storage_unavailable")

    monkeypatch.setattr(privacy_service, "delete_user_account_as_admin", fail)

    with pytest.raises(privacy_service.AccountDeletionError, match="storage_unavailable"):
        privacy_service.delete_user_account_as_admin(
            user_id=_record().id,
            actor_user_id="00000000-0000-0000-0000-000000000002",
        )
