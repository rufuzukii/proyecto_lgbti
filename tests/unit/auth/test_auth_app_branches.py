from __future__ import annotations

import pytest

from app.core.auth import app as auth_app
from app.modules.account.users.schemas import UserRead, UserRole, UserType
from app.modules.account.users.service import UserRecord, UserStorageError


class _Limiter:
    def __init__(self, *, blocked: bool = False) -> None:
        self.blocked = blocked
        self.failures: list[str] = []
        self.resets: list[str] = []

    def is_blocked(self, _key: str) -> bool:
        return self.blocked

    def record_failure(self, key: str) -> None:
        self.failures.append(key)

    def reset(self, key: str) -> None:
        self.resets.append(key)


def _user(*, active: bool = True, session_version: int = 0) -> UserRead:
    return UserRead(
        id="user-1",
        username="Test user",
        email="user@example.test",
        role=UserRole.COMMON,
        user_type=UserType.COMUN,
        active=active,
        session_version=session_version,
    )


def _record() -> UserRecord:
    return UserRecord(
        id="user-1",
        username="Test user",
        email="user@example.test",
        role=UserRole.COMMON,
        organization=None,
        password_hash="hash",
        user_type=UserType.COMUN,
    )


def _app(monkeypatch, limiter: _Limiter | None = None):
    selected = limiter or _Limiter()
    monkeypatch.setattr(auth_app, "create_rate_limiter", lambda **_kwargs: selected)
    return auth_app.create_auth_app(), selected


def test_registration_rejects_non_json_invalid_and_rate_limited_payloads(monkeypatch) -> None:
    application, limiter = _app(monkeypatch)
    client = application.test_client()

    assert client.post("/auth/register", data="not-json").status_code == 400
    invalid = client.post("/auth/register", json={"email": "bad"})
    assert invalid.status_code == 400
    assert limiter.failures

    blocked_app, _blocked = _app(monkeypatch, _Limiter(blocked=True))
    blocked = blocked_app.test_client().post(
        "/auth/register",
        json={
            "name": "Test user",
            "email": "user@example.com",
            "password": "long-enough-password",
        },
    )
    assert blocked.status_code == 429


@pytest.mark.parametrize(
    ("exception", "status", "message"),
    [
        (ValueError("duplicate"), 400, "registration_failed"),
        (UserStorageError("offline"), 503, "storage_not_configured"),
    ],
)
def test_registration_maps_domain_and_storage_failures(
    monkeypatch, exception: Exception, status: int, message: str
) -> None:
    monkeypatch.setattr(
        auth_app,
        "create_user",
        lambda _payload: (_ for _ in ()).throw(exception),
    )
    application, _limiter = _app(monkeypatch)

    response = application.test_client().post(
        "/auth/register",
        json={
            "name": "Test user",
            "email": "user@example.com",
            "password": "long-enough-password",
        },
    )

    assert response.status_code == status
    assert response.get_json()["message"] == message


def test_login_rejects_payload_shape_types_rate_limit_and_credentials(monkeypatch) -> None:
    application, limiter = _app(monkeypatch)
    client = application.test_client()
    assert client.post("/auth/login", data="not-json").status_code == 400
    assert client.post("/auth/login", json={"email": 4, "password": []}).status_code == 400

    monkeypatch.setattr(auth_app, "authenticate_user", lambda *_args: None)
    invalid = client.post("/auth/login", json={"email": "user@example.test", "password": "wrong"})
    assert invalid.status_code == 401
    assert limiter.failures

    blocked_app, _blocked = _app(monkeypatch, _Limiter(blocked=True))
    blocked = blocked_app.test_client().post(
        "/auth/login", json={"email": "user@example.test", "password": "password"}
    )
    assert blocked.status_code == 429


def test_login_maps_storage_error_and_success_then_logout(monkeypatch) -> None:
    monkeypatch.setattr(
        auth_app,
        "authenticate_user",
        lambda *_args: (_ for _ in ()).throw(UserStorageError("offline")),
    )
    application, _limiter = _app(monkeypatch)
    response = application.test_client().post(
        "/auth/login", json={"email": "user@example.test", "password": "password"}
    )
    assert response.status_code == 503

    monkeypatch.setattr(auth_app, "authenticate_user", lambda *_args: _record())
    monkeypatch.setattr(auth_app, "get_user", lambda _user_id: _user())
    application, limiter = _app(monkeypatch)
    client = application.test_client()
    login = client.post("/auth/login", json={"email": "user@example.test", "password": "password"})
    assert login.status_code == 200
    assert client.get("/auth/me").get_json()["user_id"] == "user-1"
    assert limiter.resets
    assert client.post("/auth/logout").get_json() == {"status": "ok"}
    assert client.get("/auth/me").get_json() == {"role": "anonymous", "user": None}


@pytest.mark.parametrize(
    ("loaded", "stored_version"),
    [
        (None, None),
        (_user(active=False), None),
        (_user(session_version=2), 1),
    ],
)
def test_user_loader_rejects_missing_inactive_and_stale_sessions(
    monkeypatch, loaded: UserRead | None, stored_version: int | None
) -> None:
    monkeypatch.setattr(auth_app, "get_user", lambda _user_id: loaded)
    application, _limiter = _app(monkeypatch)
    client = application.test_client()
    with client.session_transaction() as browser_session:
        browser_session["_user_id"] = "user-1"
        browser_session["_fresh"] = True
        if stored_version is not None:
            browser_session["_security_version"] = stored_version

    assert client.get("/auth/me").get_json() == {"role": "anonymous", "user": None}


def test_user_loader_maps_storage_failure_to_anonymous(monkeypatch) -> None:
    monkeypatch.setattr(
        auth_app,
        "get_user",
        lambda _user_id: (_ for _ in ()).throw(UserStorageError("offline")),
    )
    application, _limiter = _app(monkeypatch)
    client = application.test_client()
    with client.session_transaction() as browser_session:
        browser_session["_user_id"] = "user-1"
        browser_session["_fresh"] = True

    assert client.get("/auth/me").get_json()["user"] is None


def test_auth_user_conversion_handles_missing_user_type(monkeypatch) -> None:
    record = _record()
    record.user_type = None
    converted = auth_app._auth_user_from_record(record)
    assert converted.user_type is None
    monkeypatch.setattr(
        auth_app,
        "rate_limit_key",
        lambda *, subject, scope: f"{scope}:{subject}",
    )
    assert auth_app._rate_key(None) == "login:"
    assert auth_app._rate_key(" USER@EXAMPLE.COM ") == "login:user@example.com"
    assert auth_app._rate_key("ignored", include_email=False) == "registration:"
