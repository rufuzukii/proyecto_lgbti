from __future__ import annotations

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from flask import Flask, session
from pydantic import ValidationError

from app.api import create_api_app
from app.api.security import _load_api_keys, require_admin_api_key, require_api_key
from app.auth.app import create_auth_app
from app.config import get_app_config
from app.dash_app import _safe_next
from app.http_security import client_ip, configure_flask_security, rate_limit_key
from app.logging_config import redact_sensitive_text
from app.users import service as user_service
from app.users.schemas import UserRegister


def test_flask_security_sets_headers_cookies_and_auth_request_limit() -> None:
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "local-test-secret"
    configure_flask_security(
        app,
        production=True,
        cookie_name="rainbowlens_test_session",
        max_auth_request_bytes=32,
    )

    @app.get("/")
    def index() -> str:
        session["test"] = True
        return "ok"

    @app.post("/mutate")
    def mutate() -> str:
        return "ok"

    client = app.test_client()
    response = client.get("/")

    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Strict-Transport-Security"].startswith("max-age=")
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
    cookie = response.headers["Set-Cookie"]
    assert "__Host-rainbowlens_test_session=" in cookie
    assert "Secure" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=Lax" in cookie
    assert client.post("/auth/login", data=b"x" * 33).status_code == 413
    assert (
        client.post(
            "/mutate",
            base_url="https://localhost",
            headers={"Origin": "https://attacker.example"},
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/mutate",
            base_url="https://localhost",
            headers={"Origin": "https://localhost"},
        ).status_code
        == 200
    )


def test_client_identity_does_not_trust_forwarded_header_or_expose_pii() -> None:
    app = Flask(__name__)
    with app.test_request_context(
        "/",
        environ_base={"REMOTE_ADDR": "203.0.113.8"},
        headers={"X-Forwarded-For": "198.51.100.4"},
    ):
        assert client_ip() == "203.0.113.8"
        key = rate_limit_key(subject="person@example.com", scope="login")

    assert len(key) == 64
    assert "person@example.com" not in key
    assert "203.0.113.8" not in key


@pytest.mark.parametrize(
    "unsafe_target",
    [
        "https://example.com",
        "//example.com",
        "/\\example.com",
        "/%2f%2fexample.com",
        "/auth/logout",
        "/user#external-fragment",
    ],
)
def test_post_auth_redirect_rejects_unsafe_targets(unsafe_target: str) -> None:
    assert _safe_next(unsafe_target) == "/user"


def test_post_auth_redirect_allows_known_internal_target() -> None:
    assert _safe_next("/upload?source=FRA") == "/upload?source=FRA"


def test_production_secret_has_a_minimum_length(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("LOCAL_MODE", "false")
    monkeypatch.setenv("SECRET_KEY", "too-short")

    with pytest.raises(RuntimeError, match="at least 32"):
        get_app_config()


def test_logs_redact_credentials_and_configured_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configured_secret = "configured-secret-value"
    monkeypatch.setenv("SECRET_KEY", configured_secret)

    redacted = redact_sensitive_text(
        "postgresql://user:database-password@db.example/app "
        f"token=browser-token value={configured_secret}"
    )

    assert "database-password" not in redacted
    assert "browser-token" not in redacted
    assert configured_secret not in redacted
    assert redacted.count("***") >= 3


def test_user_registration_validates_email_and_masks_password() -> None:
    with pytest.raises(ValidationError):
        UserRegister.model_validate(
            {
                "name": "Test user",
                "email": "not-an-email",
                "password": "long-enough-password",
            }
        )
    with pytest.raises(ValidationError):
        UserRegister.model_validate(
            {
                "name": "Test user",
                "email": "user@example.com",
                "password": "short",
            }
        )

    payload = UserRegister.model_validate(
        {
            "name": "Test user",
            "email": "user@example.com",
            "password": "long-enough-password",
        }
    )

    assert "long-enough-password" not in repr(payload)
    assert payload.password.get_secret_value() == "long-enough-password"


def test_unknown_login_performs_a_dummy_password_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checked_hashes: list[str] = []
    monkeypatch.setattr(user_service, "get_user_record_by_email", lambda _email: None)

    def fake_password_check(password_hash: str, password: str) -> bool:
        checked_hashes.append(password_hash)
        assert password == "incorrect-password"
        return False

    monkeypatch.setattr(user_service, "check_password_hash", fake_password_check)

    assert user_service.authenticate_user("missing@example.com", "incorrect-password") is None
    assert checked_hashes == [user_service._DUMMY_PASSWORD_HASH]


def test_service_revalidates_emails_from_non_pydantic_callers() -> None:
    assert user_service._normalize_email(" Person@Example.COM ") == "person@example.com"
    assert user_service._normalize_email("not-an-email") == ""


def test_user_text_normalization_removes_control_and_bidi_characters() -> None:
    assert user_service._normalize_user_text("  Alice\u202e\n ") == "Alice"


def test_admin_role_parser_rejects_unknown_values() -> None:
    with pytest.raises(ValueError, match="invalid_role"):
        user_service._parse_admin_role("owner")


def test_api_keys_are_long_and_admin_scope_is_separate(monkeypatch: pytest.MonkeyPatch) -> None:
    general_key = "g" * 32
    admin_key = "a" * 32
    monkeypatch.setenv("API_KEYS", f"short,{general_key}")
    monkeypatch.setenv("ADMIN_API_KEYS", admin_key)

    assert _load_api_keys("API_KEYS") == {general_key}
    require_api_key(general_key)
    require_admin_api_key(admin_key)
    with pytest.raises(HTTPException) as exc_info:
        require_admin_api_key(general_key)
    assert exc_info.value.status_code == 401


def test_production_api_hides_schema_and_protects_admin_routes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    general_key = "g" * 32
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("LOCAL_MODE", "false")
    monkeypatch.setenv("SECRET_KEY", "s" * 32)
    monkeypatch.setenv("API_KEYS", general_key)
    monkeypatch.setenv("ADMIN_API_KEYS", "a" * 32)
    client = TestClient(create_api_app())

    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404
    chart_response = client.get("/charts/export", headers={"X-API-Key": general_key})
    assert chart_response.status_code == 200
    assert chart_response.headers["Strict-Transport-Security"].startswith("max-age=")
    assert client.get("/users/", headers={"X-API-Key": general_key}).status_code == 401


def test_registration_failure_does_not_disclose_existing_email(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("LOCAL_MODE", "true")
    monkeypatch.setattr(
        "app.auth.app.create_user",
        lambda _payload: (_ for _ in ()).throw(ValueError("email_exists")),
    )
    app = create_auth_app()

    response = app.test_client().post(
        "/auth/register",
        json={
            "name": "Test user",
            "email": "existing@example.com",
            "password": "long-enough-password",
        },
    )

    assert response.status_code == 400
    assert response.get_json() == {
        "status": "error",
        "message": "registration_failed",
    }
