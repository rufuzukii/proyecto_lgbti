from __future__ import annotations

from flask_login import current_user

from app import dash_app as dash_app_module
from app.users.schemas import UserRole, UserType
from app.users.service import UserRecord


def test_dash_login_survives_navigation_when_proxy_identifier_changes(monkeypatch) -> None:
    record = UserRecord(
        id="4cf35a2f-a5df-4c31-914d-2ca72a339139",
        username="Session user",
        email="session@example.test",
        role=UserRole.COMMON,
        organization=None,
        password_hash="unused-in-test",
        user_type=UserType.COMUN,
    )
    monkeypatch.setattr(dash_app_module, "initialize_mongo_indexes", lambda: None)
    monkeypatch.setattr(dash_app_module, "authenticate_user", lambda _email, _password: record)
    monkeypatch.setattr(dash_app_module, "get_user_record", lambda _user_id: record)
    app = dash_app_module.create_dash_app()

    @app.server.get("/_test/session-state")
    def session_state() -> dict[str, object]:
        return {
            "authenticated": current_user.is_authenticated,
            "user_id": current_user.get_id() if current_user.is_authenticated else None,
        }

    client = app.server.test_client()
    with client.session_transaction() as browser_session:
        browser_session["_csrf_token"] = "valid-csrf-token"

    login_response = client.post(
        "/auth/login",
        data={
            "csrf_token": "valid-csrf-token",
            "email": record.email,
            "password": "valid-password",
                "next": "/es",
        },
        headers={
            "User-Agent": "session-regression-test",
            "X-Forwarded-For": "198.51.100.10",
        },
    )

    assert login_response.status_code == 302
    assert login_response.headers["Location"].endswith("/es")
    with client.session_transaction() as browser_session:
        assert browser_session.permanent is True
        assert browser_session["_user_id"] == record.id

    navigation_response = client.get(
        "/_test/session-state",
        headers={
            "User-Agent": "session-regression-test",
            "X-Forwarded-For": "198.51.100.11",
        },
    )

    assert navigation_response.status_code == 200
    assert navigation_response.get_json() == {
        "authenticated": True,
        "user_id": record.id,
    }
    assert "Expires=" in navigation_response.headers["Set-Cookie"]
