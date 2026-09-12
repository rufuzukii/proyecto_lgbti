"""Pruebas de arranque y rutas críticas de la aplicación."""

from __future__ import annotations

import pytest

from app.modules.account.users.schemas import UserRole, UserType
from app.modules.account.users.service import UserRecord
from app.shared.data import repository
from app.web import application as dash_app_module

PUBLIC_ROUTES = (
    "/es",
    "/es/estadisticas",
    "/es/tendencias",
    "/es/espana",
    "/es/didactica",
    "/es/informe",
    "/es/acerca-de",
    "/health",
)


class _FraCollection:
    def distinct(self, field, query):
        assert field == "survey_year"
        assert query == {}
        return [2023]


@pytest.fixture
def smoke_app(monkeypatch):
    record = UserRecord(
        id="7bf1c278-4ad4-4cf3-a70d-9769590c5099",
        username="Smoke user",
        email="smoke@example.test",
        role=UserRole.COMMON,
        organization=None,
        password_hash="unused-in-test",
        user_type=UserType.COMUN,
    )
    monkeypatch.setattr(dash_app_module, "initialize_mongo_indexes", lambda: None)
    monkeypatch.setattr(dash_app_module, "assert_analytics_databases_available", lambda: None)
    monkeypatch.setattr(dash_app_module, "authenticate_user", lambda _email, _password: record)
    monkeypatch.setattr(dash_app_module, "get_user_record", lambda _user_id: record)
    return dash_app_module.create_dash_app(), record


def test_public_pages_resources_and_login_smoke(smoke_app) -> None:
    app, record = smoke_app
    client = app.server.test_client()

    for route in PUBLIC_ROUTES:
        response = client.get(route)
        assert response.status_code == 200, route

    resource = client.get("/didactica/docentes/descargar/rights_country_comparison")
    assert resource.status_code == 403

    with client.session_transaction() as browser_session:
        browser_session["_csrf_token"] = "smoke-csrf"
    login = client.post(
        "/auth/login",
        data={
            "csrf_token": "smoke-csrf",
            "email": record.email,
            "password": "valid-password",
            "next": "/es/perfil",
        },
    )
    assert login.status_code == 302
    assert login.headers["Location"].endswith("/es/perfil")


def test_basic_fra_catalog_query_smoke(monkeypatch) -> None:
    monkeypatch.setattr(repository, "_mongo_collection", lambda _name: _FraCollection())
    assert repository.get_fra_years() == [2023]


def test_dash_layout_and_callback_registry_smoke(smoke_app) -> None:
    app, _record = smoke_app
    client = app.server.test_client()

    layout_response = client.get("/_dash-layout")
    dependencies_response = client.get("/_dash-dependencies")
    dependencies = dependencies_response.get_json()

    assert layout_response.status_code == 200
    assert dependencies_response.status_code == 200
    assert isinstance(dependencies, list)
    assert len(dependencies) == len(app.callback_map)
    outputs = [dependency["output"] for dependency in dependencies]
    assert len(outputs) == len(set(outputs))
