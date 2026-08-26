from __future__ import annotations

import pytest

from app import dash_app as dash_app_module
from app.users.schemas import UserRead, UserRole, UserType
from app.users.service import UserRecord


def _record() -> UserRecord:
    return UserRecord(
        id="4cf35a2f-a5df-4c31-914d-2ca72a339139",
        username="Account user",
        email="account@example.test",
        role=UserRole.COMMON,
        organization=None,
        password_hash="hash",
        user_type=UserType.COMUN,
        active=True,
    )


def _app(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(dash_app_module, "initialize_mongo_indexes", lambda: None)
    monkeypatch.setattr(dash_app_module, "validate_csrf_token", lambda _token: True)
    return dash_app_module.create_dash_app()


def test_registration_creates_account_signs_in_and_redirects_to_requested_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created = UserRead(
        id=_record().id,
        username="New user",
        email="new@example.com",
        role=UserRole.COMMON,
        user_type=UserType.COMUN,
    )
    created_users: list[UserRead] = []
    monkeypatch.setattr(
        dash_app_module,
        "create_user",
        lambda *_args, **_kwargs: created_users.append(created) or created,
    )
    app = _app(monkeypatch)
    client = app.server.test_client()
    response = client.post(
        "/auth/register",
        data={
            "csrf_token": "valid",
            "name": "New user",
            "email": "new@example.com",
            "password": "a-secure-password",
            "next": "/es/perfil",
        },
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/es/perfil")
    assert created_users == [created]
    with client.session_transaction() as user_session:
        assert user_session["_user_id"] == created.id
        assert user_session["_fresh"] is True
        assert user_session["_security_version"] == created.session_version
        assert user_session["_permanent"] is True


def test_duplicate_email_returns_registration_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        dash_app_module,
        "create_user",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("email_exists")),
    )
    app = _app(monkeypatch)
    client = app.server.test_client()
    response = client.post(
        "/auth/register",
        data={
            "csrf_token": "valid",
            "name": "Existing user",
            "email": "account@example.com",
            "password": "a-secure-password",
        },
    )
    assert "/es/registro?" in response.headers["Location"]
    assert "error=email_exists" in response.headers["Location"]
    with client.session_transaction() as user_session:
        assert "_user_id" not in user_session


def test_non_validated_account_can_sign_in_immediately(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dash_app_module, "authenticate_user", lambda *_args: _record())
    app = _app(monkeypatch)
    response = app.server.test_client().post(
        "/auth/login",
        data={
            "csrf_token": "valid",
            "email": "account@example.test",
            "password": "a-secure-password",
            "next": "/es/perfil",
        },
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/es/perfil")


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/account/verify-email/obsolete-token"),
        ("post", "/auth/resend-verification"),
        ("post", "/auth/forgot-password"),
        ("post", "/auth/reset-password"),
    ],
)
def test_removed_email_routes_return_not_found(
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    path: str,
) -> None:
    app = _app(monkeypatch)
    response = getattr(app.server.test_client(), method)(path)
    # Dash owns a generic GET route, so a removed POST endpoint may resolve as
    # either not found or method not allowed. In both cases no legacy handler runs.
    assert response.status_code in {404, 405}


def test_account_security_migration_runs_when_index_setup_is_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    monkeypatch.setenv("MONGO_ENSURE_INDEXES_ON_STARTUP", "false")
    monkeypatch.setattr(
        dash_app_module,
        "migrate_account_security_schema",
        lambda: calls.append("migration"),
    )

    _app(monkeypatch)

    assert calls == ["migration"]
