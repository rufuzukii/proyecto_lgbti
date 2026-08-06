from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import app.api as api_module
import app.api.routers.data_io as data_io_router
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
            "postgresql": "unavailable",
            "mongodb": "ok",
            "redis": "degraded",
            "configuration": "ok",
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


def test_education_endpoint_returns_real_lightweight_units(api_client: TestClient) -> None:
    # Arrange
    headers = {"X-API-Key": GENERAL_KEY}

    # Act
    response = api_client.get("/edu/units", headers=headers)

    # Assert
    assert response.status_code == 200
    units = response.json()
    assert units
    assert set(units[0]) == {"id", "title", "description", "duration_minutes"}
    assert set(units[0]["title"]) == {"es", "en"}


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


def test_data_import_queues_review_without_direct_persistence(
    api_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Arrange
    csv_path = tmp_path / "rainbow.csv"
    csv_path.write_text("Country,Score\nSpain,70\n", encoding="utf-8")
    queued = []
    monkeypatch.setattr(data_io_router, "IMPORT_BASE_DIR", tmp_path.resolve())
    monkeypatch.setattr(
        data_io_router,
        "parse_ilga_csv",
        lambda path, year: {"source_type": "ILGA_RAINBOW", "year": year, "path": path.name},
    )
    monkeypatch.setattr(
        data_io_router,
        "register_pending_import",
        lambda *, file_name, file_json: queued.append((file_name, file_json)),
    )

    # Act
    response = api_client.post(
        "/data/import",
        headers={"X-API-Key": ADMIN_KEY},
        json={"rainbow_csv": "rainbow.csv", "year": 2026},
    )

    # Assert
    assert response.status_code == 202
    assert response.json() == {
        "status": "pending_review",
        "sources": ["rainbow.csv"],
        "queued": 1,
    }
    assert len(queued) == 1
    assert queued[0][1][0]["year"] == 2026


@pytest.mark.parametrize(
    ("payload", "expected_detail"),
    [
        ({}, "import_source_required"),
        ({"rainbow_csv": "../outside.csv"}, "invalid_import_csv"),
    ],
)
def test_data_import_rejects_missing_or_unsafe_sources(
    api_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    payload: dict[str, str],
    expected_detail: str,
) -> None:
    # Arrange
    monkeypatch.setattr(data_io_router, "IMPORT_BASE_DIR", tmp_path.resolve())

    # Act
    response = api_client.post(
        "/data/import",
        headers={"X-API-Key": ADMIN_KEY},
        json=payload,
    )

    # Assert
    assert response.status_code == 400
    assert response.json() == {"detail": expected_detail}


def test_removed_placeholder_routes_are_not_registered(api_client: TestClient) -> None:
    # Arrange
    general_headers = {"X-API-Key": GENERAL_KEY}
    admin_headers = {"X-API-Key": ADMIN_KEY}

    # Act
    chart_response = api_client.get("/charts/export", headers=general_headers)
    data_response = api_client.get("/data/export", headers=admin_headers)
    legacy_report_response = api_client.get("/reports", headers=general_headers)

    # Assert
    assert chart_response.status_code == 404
    assert data_response.status_code == 404
    assert legacy_report_response.status_code == 405


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
        ("GET", "/edu/units"),
        ("POST", "/reports"),
        ("POST", "/data/import"),
    }.issubset(set(registered))
    assert len(registered) == len(set(registered))


def test_admin_import_cannot_be_called_with_a_general_key(api_client: TestClient) -> None:
    # Arrange
    headers = {"X-API-Key": GENERAL_KEY}

    # Act
    response = api_client.post("/data/import", headers=headers, json={})

    # Assert
    assert response.status_code == 401
