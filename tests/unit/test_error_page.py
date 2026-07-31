from app.dash.layouts.error_page import render_database_unavailable_response
from app.dash_app import create_dash_app
from app.errors import DatabaseUnavailableError


def test_database_unavailable_response_returns_503() -> None:
    body, status_code, headers = render_database_unavailable_response(
        DatabaseUnavailableError("PostgreSQL")
    )

    assert status_code == 503
    assert headers["Retry-After"] == "30"
    assert "Servicio no disponible" in body
    assert "No ha sido posible cargar la información" in body
    assert "PostgreSQL" not in body
    assert "Supabase" not in body
    assert "Base de datos" not in body


def test_statistics_route_returns_503_when_database_is_unavailable(monkeypatch) -> None:
    from app import dash_app as dash_app_module

    def raise_unavailable() -> None:
        raise DatabaseUnavailableError("PostgreSQL")

    monkeypatch.setattr(
        dash_app_module,
        "assert_analytics_databases_available",
        raise_unavailable,
    )
    app = create_dash_app()

    response = app.server.test_client().get("/statistics")

    assert response.status_code == 503
    body = response.get_data(as_text=True)
    assert "No ha sido posible cargar la información" in body
    assert "Base de datos" not in body
