from __future__ import annotations

from flask_login import current_user

from app import dash_app as dash_app_module
from app.dash.layouts import user_page
from app.privacy.models import DeletionOutcome, PersonalDataInventory
from app.privacy.service import AccountDeletionError
from app.users.schemas import UserRole, UserType
from app.users.service import UserRecord

USER_ID = "7bf1c278-4ad4-4cf3-a70d-9769590c5099"


def _record() -> UserRecord:
    return UserRecord(
        id=USER_ID,
        username="Privacy user",
        email="privacy@example.com",
        role=UserRole.COMMON,
        organization="Rainbow Org",
        password_hash="not-used-by-route-mock",
        user_type=UserType.COMUN,
    )


def _app(monkeypatch):
    record = _record()
    monkeypatch.setattr(dash_app_module, "initialize_mongo_indexes", lambda: None)
    monkeypatch.setattr(dash_app_module, "assert_analytics_databases_available", lambda: None)
    monkeypatch.setattr(dash_app_module, "authenticate_user", lambda _email, _password: record)
    monkeypatch.setattr(dash_app_module, "get_user_record", lambda _user_id: record)
    monkeypatch.setattr(
        user_page,
        "get_personal_data_inventory",
        lambda _user_id: PersonalDataInventory(profile=True, teacher_games=1),
    )
    app = dash_app_module.create_dash_app()

    @app.server.get("/_test/privacy-session")
    def privacy_session() -> dict[str, object]:
        return {
            "authenticated": current_user.is_authenticated,
            "user_id": current_user.get_id() if current_user.is_authenticated else None,
        }

    return app


def test_privacy_route_footer_banner_and_personal_management_are_reachable(monkeypatch) -> None:
    # Arrange
    app = _app(monkeypatch)
    client = app.server.test_client()

    # Act
    privacy_response = client.get("/es/privacidad")
    privacy_response_en = client.get("/en/privacy")
    anonymous_layout = client.get("/_dash-layout").get_json()
    with client.session_transaction() as browser_session:
        browser_session["_csrf_token"] = "valid"
    client.post(
        "/auth/login",
        data={
            "csrf_token": "valid",
            "email": "privacy@example.com",
            "password": "password",
            "next": "/es/perfil",
        },
    )
    authenticated_layout = client.get("/_dash-layout").get_json()

    # Assert
    assert privacy_response.status_code == 200
    assert privacy_response_en.status_code == 200
    assert "privacy-notice" not in str(anonymous_layout)
    assert "/es/privacidad" in str(anonymous_layout)
    assert "Personal data management" not in str(anonymous_layout)
    assert "Personal data management" not in str(authenticated_layout)


def test_reinforced_deletion_rejects_bad_credentials_then_closes_session(monkeypatch) -> None:
    # Arrange
    app = _app(monkeypatch)

    def delete_account(**values: object) -> DeletionOutcome:
        if values.get("password") != "correct-password":
            raise AccountDeletionError("invalid_password")
        assert values["user_id"] == USER_ID
        assert values["email"] == "privacy@example.com"
        assert values["confirmation_checked"] is True
        assert values["confirmation_text"] == "ELIMINAR MI CUENTA"
        return DeletionOutcome(status="completed")

    monkeypatch.setattr(dash_app_module, "delete_user_account", delete_account)
    client = app.server.test_client()
    with client.session_transaction() as browser_session:
        browser_session["_csrf_token"] = "valid"
    client.post(
        "/auth/login",
        data={
            "csrf_token": "valid",
            "email": "privacy@example.com",
            "password": "password",
        },
    )
    with client.session_transaction() as browser_session:
        privacy_csrf = browser_session["_csrf_token"]

    # Act
    rejected = client.post(
        "/privacy/delete-account",
        data={
            "csrf_token": privacy_csrf,
            "email": "privacy@example.com",
            "password": "wrong",
            "confirmation_checked": "yes",
            "confirmation_text": "ELIMINAR MI CUENTA",
            "language": "es",
        },
    )
    session_after_rejection = client.get("/_test/privacy-session").get_json()
    completed = client.post(
        "/privacy/delete-account",
        data={
            "csrf_token": privacy_csrf,
            "email": "privacy@example.com",
            "password": "correct-password",
            "confirmation_checked": "yes",
            "confirmation_text": "ELIMINAR MI CUENTA",
            "language": "es",
        },
    )
    session_after_completion = client.get("/_test/privacy-session").get_json()

    # Assert
    assert "privacy_error=invalid_password" in rejected.headers["Location"]
    assert session_after_rejection == {"authenticated": True, "user_id": USER_ID}
    assert completed.headers["Location"].endswith("/es/privacidad/cuenta-eliminada")
    assert session_after_completion == {"authenticated": False, "user_id": None}
    assert "Expires=Thu, 01 Jan 1970" in completed.headers.get("Set-Cookie", "")
