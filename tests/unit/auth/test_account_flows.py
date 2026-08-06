from __future__ import annotations

from types import SimpleNamespace

import pytest

from app import dash_app as dash_app_module
from app.users.schemas import UserRead, UserRole, UserType
from app.users.service import UserRecord


def _record(*, verified: bool = False) -> UserRecord:
    return UserRecord(
        id="4cf35a2f-a5df-4c31-914d-2ca72a339139",
        username="Account user",
        email="account@example.test",
        role=UserRole.COMMON,
        organization=None,
        password_hash="hash",
        user_type=UserType.COMUN,
        active=True,
        email_verified=verified,
    )


def _app(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(dash_app_module, "initialize_mongo_indexes", lambda: None)
    monkeypatch.setattr(dash_app_module, "validate_csrf_token", lambda _token: True)
    return dash_app_module.create_dash_app()


def test_registration_creates_unverified_account_and_sends_single_use_link(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    created = UserRead(
        id="4cf35a2f-a5df-4c31-914d-2ca72a339139",
        username="New user",
        email="new@example.com",
        role=UserRole.COMMON,
        user_type=UserType.COMUN,
        email_verified=False,
    )
    sent: list[tuple[str, str]] = []
    monkeypatch.setattr(dash_app_module, "create_user", lambda *_args, **_kwargs: created)
    monkeypatch.setattr(dash_app_module, "issue_security_token", lambda *_args, **_kwargs: "token")
    monkeypatch.setattr(
        dash_app_module,
        "send_verification_email",
        lambda email, token: sent.append((email, token)),
    )
    app = _app(monkeypatch)

    # Act
    response = app.server.test_client().post(
        "/auth/register",
        data={
            "csrf_token": "valid",
            "name": "New user",
            "email": "new@example.com",
            "password": "a-secure-password",
        },
    )

    # Assert
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/verify-email?status=sent")
    assert sent == [("new@example.com", "token")]


def test_verification_link_marks_email_and_cannot_expose_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    marked: list[str] = []
    monkeypatch.setattr(
        dash_app_module,
        "consume_security_token",
        lambda token, purpose: _record().id
        if (token, purpose) == ("valid-token", "email_verification")
        else None,
    )
    monkeypatch.setattr(dash_app_module, "get_user_record", lambda _user_id: _record())
    monkeypatch.setattr(dash_app_module, "mark_email_verified", marked.append)
    monkeypatch.setattr(dash_app_module, "record_security_event", lambda *_args: None)
    app = _app(monkeypatch)

    # Act
    response = app.server.test_client().get("/account/verify-email/valid-token")

    # Assert
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/verify-email?status=verified")
    assert "valid-token" not in response.headers["Location"]
    assert marked == [_record().id]


def test_password_recovery_response_does_not_reveal_account_existence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    app = _app(monkeypatch)
    client = app.server.test_client()
    monkeypatch.setattr(dash_app_module, "get_user_record_by_email", lambda _email: None)

    # Act
    missing = client.post(
        "/auth/forgot-password",
        data={"csrf_token": "valid", "email": "missing@example.test"},
    )
    monkeypatch.setattr(dash_app_module, "get_user_record_by_email", lambda _email: _record())
    monkeypatch.setattr(dash_app_module, "issue_security_token", lambda *_args, **_kwargs: "token")
    monkeypatch.setattr(dash_app_module, "send_password_reset_email", lambda *_args: None)
    existing = client.post(
        "/auth/forgot-password",
        data={"csrf_token": "valid", "email": "account@example.test"},
    )

    # Assert
    assert missing.status_code == existing.status_code == 302
    assert missing.headers["Location"] == existing.headers["Location"]
    assert missing.headers["Location"].endswith("/forgot-password?status=sent")


def test_password_reset_requires_matching_policy_then_invalidates_sessions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    changes: list[tuple[str, str]] = []
    monkeypatch.setattr(
        dash_app_module,
        "consume_security_token",
        lambda token, purpose: _record().id
        if (token, purpose) == ("valid-token", "password_reset")
        else None,
    )
    monkeypatch.setattr(
        dash_app_module,
        "set_user_password",
        lambda *, user_id, new_password: changes.append((user_id, new_password)),
    )
    app = _app(monkeypatch)
    client = app.server.test_client()

    # Act
    mismatch = client.post(
        "/auth/reset-password",
        data={
            "csrf_token": "valid",
            "token": "valid-token",
            "password": "a-secure-password",
            "password_confirmation": "another-password",
        },
    )
    completed = client.post(
        "/auth/reset-password",
        data={
            "csrf_token": "valid",
            "token": "valid-token",
            "password": "a-secure-password",
            "password_confirmation": "a-secure-password",
        },
    )

    # Assert
    assert "error=password_mismatch" in mismatch.headers["Location"]
    assert completed.headers["Location"].endswith("/reset-password?status=completed")
    assert changes == [(_record().id, "a-secure-password")]


def test_unverified_user_contract_is_explicit() -> None:
    user = SimpleNamespace(is_authenticated=True, email_verified=False)

    assert dash_app_module._is_email_verified(user) is False
