from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import app.api as api_module
import app.api.routers.reports as reports_router
from app.api import create_api_app
from app.reports.service import ReportGenerationError

GENERAL_KEY = "g" * 32
ADMIN_KEY = "a" * 32


@pytest.fixture
def api_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    # Arrange
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("LOCAL_MODE", "true")
    monkeypatch.setenv("API_KEYS", GENERAL_KEY)
    monkeypatch.setenv("ADMIN_API_KEYS", ADMIN_KEY)

    # Act
    app = create_api_app()

    # Assert
    return TestClient(app)


def test_fastapi_health_uses_the_real_health_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    report = {
        "status": "unavailable",
        "services": {
            "application": "ok",
            "local_cache": "unavailable",
        },
    }
    monkeypatch.setattr(api_module, "build_health_report", lambda: report)
    client = TestClient(create_api_app())

    # Act
    response = client.get("/health")

    # Assert
    assert response.status_code == 503
    assert response.json() == report
    assert "uri" not in response.text.casefold()


def test_report_endpoint_generates_a_pdf_from_validated_input(
    api_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    captured = []

    def fake_generate(configuration):
        captured.append(configuration)
        return SimpleNamespace(pdf_bytes=b"%PDF-1.7\n", filename="informe.pdf")

    monkeypatch.setattr(reports_router, "generate_report_pdf", fake_generate)

    # Act
    response = api_client.post(
        "/reports",
        headers={"X-API-Key": GENERAL_KEY},
        json={
            "source": "ilga",
            "year": 2026,
            "countries": ["es", "fr"],
            "language": "es",
        },
    )

    # Assert
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"] == 'attachment; filename="informe.pdf"'
    assert response.content.startswith(b"%PDF")
    assert captured[0].countries == ("ES", "FR")


def test_report_endpoint_rejects_invalid_input_before_generation(
    api_client: TestClient,
) -> None:
    # Arrange
    payload = {"source": "fra", "year": 1800}

    # Act
    response = api_client.post(
        "/reports",
        headers={"X-API-Key": GENERAL_KEY},
        json=payload,
    )

    # Assert
    assert response.status_code == 422
    assert response.json() == {"detail": "invalid_request"}


def test_report_endpoint_hides_generation_details(
    api_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    monkeypatch.setattr(
        reports_router,
        "generate_report_pdf",
        lambda _configuration: (_ for _ in ()).throw(ReportGenerationError("mongo secret")),
    )

    # Act
    response = api_client.post(
        "/reports",
        headers={"X-API-Key": GENERAL_KEY},
        json={"source": "fra"},
    )

    # Assert
    assert response.status_code == 422
    assert response.json() == {"detail": "report_generation_failed"}
    assert "mongo secret" not in response.text


def test_fastapi_has_no_duplicate_application_routes(api_client: TestClient) -> None:
    # Arrange
    ignored_paths = {"/docs", "/docs/oauth2-redirect", "/openapi.json", "/redoc"}

    # Act
    registered: list[tuple[str, str]] = []

    def collect_routes(route: object) -> None:
        path = getattr(route, "path", None)
        if isinstance(path, str) and path not in ignored_paths:
            registered.extend((method, path) for method in getattr(route, "methods", set()))
        original_router = getattr(route, "original_router", None)
        if original_router is not None:
            collect_routes(original_router)
        for child in getattr(route, "routes", []):
            collect_routes(child)

    collect_routes(api_client.app)

    # Assert
    assert {
        ("GET", "/health"),
        ("POST", "/reports"),
    }.issubset(set(registered))
    assert len(registered) == len(set(registered))
