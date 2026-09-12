from __future__ import annotations

import pytest

from app.modules.account.users.schemas import UserRead, UserRole, UserType
from app.modules.account.users.service import UserRecord
from app.web import application as dash_app_module

USER_ID = "4cf35a2f-a5df-4c31-914d-2ca72a339139"


def _record(*, role: UserRole = UserRole.COMMON) -> UserRecord:
    return UserRecord(
        id=USER_ID,
        username="E2E user",
        email="e2e@example.com",
        role=role,
        organization=None,
        password_hash="test-hash",
        user_type=UserType.ADMIN if role == UserRole.ADMIN else UserType.COMUN,
        active=True,
        session_version=0,
    )


def _app(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(dash_app_module, "initialize_mongo_indexes", lambda: None)
    monkeypatch.setattr(dash_app_module, "assert_analytics_databases_available", lambda: None)
    monkeypatch.setattr(dash_app_module, "validate_csrf_token", lambda _token: True)
    return dash_app_module.create_dash_app()


def test_registration_automatically_starts_the_session(monkeypatch) -> None:
    created = UserRead(
        id=USER_ID,
        username="E2E user",
        email="e2e@example.test",
        role=UserRole.COMMON,
        user_type=UserType.COMUN,
    )
    monkeypatch.setattr(dash_app_module, "create_user", lambda *_args, **_kwargs: created)
    monkeypatch.setattr(
        dash_app_module,
        "get_user_record",
        lambda _user_id: _record(),
    )
    client = _app(monkeypatch).server.test_client()

    registration = client.post(
        "/auth/register",
        data={
            "csrf_token": "valid",
            "name": "E2E user",
            "email": "e2e@example.com",
            "password": "a-secure-password",
            "next": "/es/perfil",
        },
    )
    protected_page = client.get("/es/perfil")

    assert registration.headers["Location"].endswith("/es/perfil")
    assert protected_page.status_code == 200
    with client.session_transaction() as user_session:
        assert user_session["_user_id"] == USER_ID
        assert user_session["_fresh"] is True


def test_admin_management_is_enforced_server_side_and_updates_a_user(monkeypatch) -> None:
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

    assert "error=access_denied" in denied.headers["Location"]
    assert "status=user_updated" in accepted.headers["Location"]
    assert updates[0]["actor_user_id"] == USER_ID
    assert updates[0]["role"] == "teacher"


def test_admin_ajax_update_returns_the_saved_row_without_a_redirect(monkeypatch) -> None:
    updated = UserRead(
        id="7bf1c278-4ad4-4cf3-a70d-9769590c5099",
        username="Managed user",
        email="managed@example.test",
        role=UserRole.COMMON,
        organization="School",
        user_type=UserType.DOCENTE,
        version="v2",
    )
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
    monkeypatch.setattr(dash_app_module, "update_user_as_admin", lambda **_kwargs: updated)
    client = _app(monkeypatch).server.test_client()
    client.post(
        "/auth/login",
        data={"csrf_token": "valid", "email": "admin@example.test", "password": "password"},
    )
    assert updated.user_type is not None

    response = client.post(
        "/admin/users",
        data={
            "csrf_token": "valid",
            "action": "update",
            "user_id": updated.id,
            "username": updated.username,
            "email": updated.email,
            "role": updated.user_type.value,
            "organization": updated.organization,
            "version": "v1",
        },
        headers={"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"},
    )

    assert response.status_code == 200
    assert response.get_json() == {
        "ok": True,
        "user": {
            "id": updated.id,
            "username": "Managed user",
            "email": "managed@example.test",
            "organization": "School",
            "role": "docente",
            "version": "v2",
        },
    }


def test_admin_ajax_update_failure_returns_json_for_an_in_place_retry(monkeypatch) -> None:
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

    def reject_update(**_kwargs):
        raise ValueError("invalid_email")

    monkeypatch.setattr(dash_app_module, "update_user_as_admin", reject_update)
    client = _app(monkeypatch).server.test_client()
    client.post(
        "/auth/login",
        data={"csrf_token": "valid", "email": "admin@example.test", "password": "password"},
    )

    response = client.post(
        "/admin/users",
        data={"csrf_token": "valid", "action": "update"},
        headers={"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"},
    )

    assert response.status_code == 400
    assert response.get_json() == {"ok": False, "error": "invalid_email"}


def test_unknown_route_is_a_localized_http_404(monkeypatch) -> None:
    client = _app(monkeypatch).server.test_client()

    response = client.get("/route-that-does-not-exist?lang=en")

    assert response.status_code == 404
    assert "404 — Page not found" in response.get_data(as_text=True)


@pytest.mark.parametrize("language", ["es", "en"])
@pytest.mark.parametrize("scenario", ["valid", "invalid_document", "common", "csrf"])
def test_felgtbi_approval_route_checks_permissions_and_keeps_failed_proposals(
    monkeypatch, language, scenario
) -> None:
    from app.modules.imports import felgtbi, fra
    from app.modules.imports.felgtbi.mongo import _prepare_indicator_document
    from app.modules.imports.import_log import PendingImportLog
    from app.web.routes import route_path

    role = UserRole.COMMON if scenario == "common" else UserRole.ADMIN
    events = []
    document = {
        "source": "felgtbi_estado_lgtbi",
        "code": "report-section",
        "year": None if scenario == "invalid_document" else 2026,
        "question": "Contexto del informe",
        "paragraphs": ["Texto de prueba sin estadisticas FRA"],
    }
    pending = PendingImportLog(
        id="controlled-import",
        user_id=USER_ID,
        user_label="Test",
        file_name="report.pdf",
        file_json=[document],
    )

    def persist(documents, *, original_filename):
        for item in documents:
            _prepare_indicator_document(item, original_filename=original_filename)
        events.append("persist")

    monkeypatch.setattr(dash_app_module, "authenticate_user", lambda *_: _record(role=role))
    monkeypatch.setattr(dash_app_module, "get_user_record", lambda _: _record(role=role))
    monkeypatch.setattr(dash_app_module, "get_pending_import_log", lambda _: pending)
    monkeypatch.setattr(dash_app_module, "delete_import_log", lambda _: events.append("delete"))
    monkeypatch.setattr(
        dash_app_module, "invalidate_analytics_cache", lambda _: events.append("cache")
    )
    monkeypatch.setattr(felgtbi, "insert_indicator_felgtbi_json", persist)
    monkeypatch.setattr(
        fra, "upsert_indicators_from_json", lambda _: pytest.fail("FELGTBI sent to FRA catalog")
    )
    client = _app(monkeypatch).server.test_client()
    client.post(
        "/auth/login",
        data={"csrf_token": "valid", "email": "admin@example.test", "password": "password"},
    )
    if scenario == "csrf":
        monkeypatch.setattr(dash_app_module, "validate_csrf_token", lambda _: False)

    response = client.post(
        "/admin/imports",
        data={
            "csrf_token": "valid",
            "action": "insert",
            "import_id": pending.id,
            "language": language,
        },
    )

    assert response.status_code == 302
    target = route_path("admin_imports", language)
    assert target is not None
    if scenario == "valid":
        assert response.headers["Location"] == target + "?status=import_inserted"
        assert events == ["persist", "cache", "delete"]
    else:
        error = {
            "invalid_document": "invalid_felgtbi_payload",
            "common": "access_denied",
            "csrf": "csrf",
        }[scenario]
        assert response.headers["Location"] == target + "?error=" + error
        assert events == []
