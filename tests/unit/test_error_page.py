from typing import Any, cast

from app.core.errors import DatabaseUnavailableError
from app.web.application import create_dash_app
from app.web.error_page import (
    build_database_unavailable_layout,
    build_error_layout,
    render_database_unavailable_response,
    render_error_response,
)
from app.web.loading_modal import build_loading_modal


def test_database_unavailable_response_returns_503() -> None:
    body, status_code, headers = render_database_unavailable_response(
        DatabaseUnavailableError("PostgreSQL")
    )

    assert status_code == 503
    assert headers["Retry-After"] == "30"
    assert "Servicio no disponible" in body
    assert "No ha sido posible cargar la informaci\u00f3n" in body
    assert "PostgreSQL" not in body
    assert "Supabase" not in body
    assert "Base de datos" not in body


def test_statistics_route_returns_503_when_database_is_unavailable(monkeypatch) -> None:
    from app.web import application as dash_app_module

    def raise_unavailable() -> None:
        raise DatabaseUnavailableError("PostgreSQL")

    monkeypatch.setattr(
        dash_app_module,
        "assert_analytics_databases_available",
        raise_unavailable,
    )
    app = create_dash_app()

    response = app.server.test_client().get("/en/statistics")

    assert response.status_code == 503
    body = response.get_data(as_text=True)
    assert "No ha sido posible cargar la informaci\u00f3n" in body
    assert "Base de datos" not in body


def test_unknown_route_returns_real_localized_404() -> None:
    app = create_dash_app()

    response = app.server.test_client().get("/this-route-does-not-exist?lang=en")

    assert response.status_code == 404
    body = response.get_data(as_text=True)
    assert "404 \u2014 Page not found" in body
    assert "Back to home" in body
    assert "build_home_layout" not in body


def test_error_pages_do_not_expose_internal_details() -> None:
    bodies = [render_error_response(kind)[0] for kind in ("401", "403", "404", "500")]

    for body in bodies:
        assert "MONGO_URI" not in body
        assert "postgresql://" not in body
        assert "Traceback" not in body
        assert 'href="/es"' in body


def test_error_layout_supports_english_without_navigation(monkeypatch) -> None:
    layout = build_error_layout("insufficient_data", include_navigation=False, language="en")
    body = str(layout.to_plotly_json())

    assert len(cast(Any, layout).children) == 1
    assert "Insufficient data" in body
    assert "There is not enough data" in body
    assert "/en" in body
    monkeypatch.setattr("app.web.error_page.build_navbar", lambda **_kwargs: "navigation")
    assert build_database_unavailable_layout().children


def test_static_error_response_localizes_english_and_sets_retry_only_for_503() -> None:
    english_body, status, headers = render_error_response("403", language="en")
    _service_body, service_status, service_headers = render_error_response("503")

    assert status == 403
    assert '<html lang="en">' in english_body
    assert "Back to home" in english_body
    assert "Retry-After" not in headers
    assert service_status == 503
    assert service_headers["Retry-After"] == "30"


def test_loading_modal_exposes_bilingual_accessibility_contract() -> None:
    visible = build_loading_modal(
        element_id="loading-test",
        title=("Cargando", "Loading"),
        description=("Espera", "Please wait"),
        hidden=False,
    )
    hidden = build_loading_modal(
        element_id="loading-hidden",
        title=("Cargando", "Loading"),
        description=("Espera", "Please wait"),
    )

    assert cast(Any, visible).className == "upload-loading-overlay"
    assert cast(Any, hidden).className.endswith("is-hidden")
    dialog = cast(Any, visible).children
    props = dialog.to_plotly_json()["props"]
    assert props["role"] == "dialog"
    assert props["aria-modal"] == "true"
    assert props["aria-live"] == "assertive"
