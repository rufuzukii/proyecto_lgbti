from __future__ import annotations

import pytest

from app import dash_app as dash_app_module
from app.users.schemas import UserRead, UserRole, UserType
from app.users.service import UserRecord

USER_ID = "4cf35a2f-a5df-4c31-914d-2ca72a339139"


def _record(*, role: UserRole = UserRole.COMMON, admin_validated: bool = False) -> UserRecord:
    return UserRecord(
        id=USER_ID,
        username="E2E user",
        email="e2e@example.com",
        role=role,
        organization=None,
        password_hash="test-hash",
        user_type=UserType.ADMIN if role == UserRole.ADMIN else UserType.COMUN,
        active=True,
        admin_validated=admin_validated,
        session_version=0,
    )


def _app(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(dash_app_module, "initialize_mongo_indexes", lambda: None)
    monkeypatch.setattr(dash_app_module, "assert_analytics_databases_available", lambda: None)
    monkeypatch.setattr(dash_app_module, "validate_csrf_token", lambda _token: True)
    return dash_app_module.create_dash_app()


def test_registration_and_immediate_login_complete_flow(monkeypatch) -> None:
    # Arrange
    created = UserRead(
        id=USER_ID,
        username="E2E user",
        email="e2e@example.test",
        role=UserRole.COMMON,
        user_type=UserType.COMUN,
        admin_validated=False,
    )
    monkeypatch.setattr(dash_app_module, "create_user", lambda *_args, **_kwargs: created)
    monkeypatch.setattr(
        dash_app_module,
        "get_user_record",
        lambda _user_id: _record(),
    )
    monkeypatch.setattr(
        dash_app_module,
        "authenticate_user",
        lambda email, password: _record()
            if (email, password) == ("e2e@example.com", "a-secure-password")
        else None,
    )
    client = _app(monkeypatch).server.test_client()

    # Act
    registration = client.post(
        "/auth/register",
        data={
            "csrf_token": "valid",
            "name": "E2E user",
            "email": "e2e@example.com",
            "password": "a-secure-password",
        },
    )
    login = client.post(
        "/auth/login",
        data={
            "csrf_token": "valid",
            "email": "e2e@example.com",
            "password": "a-secure-password",
            "next": "/es/perfil",
        },
    )
    protected_page = client.get("/es/perfil")

    # Assert
    assert "notice=account_created" in registration.headers["Location"]
    assert login.headers["Location"].endswith("/es/perfil")
    assert protected_page.status_code == 200


def test_admin_management_is_enforced_server_side_and_updates_a_user(monkeypatch) -> None:
    # Arrange
    current = {"role": UserRole.COMMON}
    updates: list[dict[str, object]] = []
    monkeypatch.setattr(
        dash_app_module,
        "authenticate_user",
        lambda _email, _password: _record(role=current["role"]),
    )
    monkeypatch.setattr(
        dash_app_module,
        "get_user_record",
        lambda _user_id: _record(role=current["role"]),
    )
    monkeypatch.setattr(
        dash_app_module,
        "update_user_as_admin",
        lambda **kwargs: updates.append(kwargs) or _record(),
    )
    client = _app(monkeypatch).server.test_client()
    client.post(
        "/auth/login",
        data={"csrf_token": "valid", "email": "admin@example.test", "password": "password"},
    )

    # Act
    denied = client.post("/admin/users", data={"csrf_token": "valid", "action": "update"})
    current["role"] = UserRole.ADMIN
    client.post("/auth/logout", data={"csrf_token": "valid"})
    client.post(
        "/auth/login",
        data={"csrf_token": "valid", "email": "admin@example.test", "password": "password"},
    )
    accepted = client.post(
        "/admin/users",
        data={
            "csrf_token": "valid",
            "action": "update",
            "user_id": "7bf1c278-4ad4-4cf3-a70d-9769590c5099",
            "username": "Managed user",
            "email": "managed@example.test",
            "role": "teacher",
            "organization": "School",
            "version": "v1",
        },
    )

    # Assert
    assert "error=access_denied" in denied.headers["Location"]
    assert "status=user_updated" in accepted.headers["Location"]
    assert updates[0]["actor_user_id"] == USER_ID
    assert updates[0]["role"] == "teacher"


def test_admin_validation_is_server_side_and_persistent_after_refresh(monkeypatch) -> None:
    validated: set[str] = set()
    target_id = "7bf1c278-4ad4-4cf3-a70d-9769590c5099"
    monkeypatch.setattr(
        dash_app_module,
        "authenticate_user",
        lambda _email, _password: _record(role=UserRole.ADMIN),
    )
    monkeypatch.setattr(
        dash_app_module,
        "get_user_record",
        lambda _user_id: _record(role=UserRole.ADMIN),
    )
    monkeypatch.setattr(
        dash_app_module,
        "validate_user_as_admin",
        lambda *, user_id, actor_user_id: validated.add(user_id),
    )
    client = _app(monkeypatch).server.test_client()
    client.post(
        "/auth/login",
        data={"csrf_token": "valid", "email": "admin@example.test", "password": "password"},
    )
    response = client.post(
        "/admin/users",
        data={"csrf_token": "valid", "action": "validate", "user_id": target_id},
    )
    refreshed_state = target_id in validated
    assert "status=user_validated" in response.headers["Location"]
    assert refreshed_state is True


def test_common_user_cannot_validate_an_account(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        dash_app_module,
        "authenticate_user",
        lambda _email, _password: _record(role=UserRole.COMMON),
    )
    monkeypatch.setattr(
        dash_app_module,
        "get_user_record",
        lambda _user_id: _record(role=UserRole.COMMON),
    )
    monkeypatch.setattr(
        dash_app_module,
        "validate_user_as_admin",
        lambda **_kwargs: calls.append("called"),
    )
    client = _app(monkeypatch).server.test_client()
    client.post(
        "/auth/login",
        data={"csrf_token": "valid", "email": "user@example.test", "password": "password"},
    )

    response = client.post(
        "/admin/users",
        data={
            "csrf_token": "valid",
            "action": "validate",
            "user_id": "7bf1c278-4ad4-4cf3-a70d-9769590c5099",
        },
    )

    assert "error=access_denied" in response.headers["Location"]
    assert calls == []


def test_unknown_route_is_a_localized_http_404(monkeypatch) -> None:
    # Arrange
    client = _app(monkeypatch).server.test_client()

    # Act
    response = client.get("/route-that-does-not-exist?lang=en")

    # Assert
    assert response.status_code == 404
    assert "404 — Page not found" in response.get_data(as_text=True)
