from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PRODUCTION_ROOT = PROJECT_ROOT / "src"
FORBIDDEN_WORKSTATION_MARKERS = (
    "C:\\Users\\",
    "http://localhost",
    "https://localhost",
    "Datos_FRA_2023",
    "Datos_ILGA",
    "Datos_FELGBT",
)


def test_production_source_has_no_workstation_or_local_dataset_paths() -> None:
    violations: list[str] = []
    for path in PRODUCTION_ROOT.rglob("*"):
        if not path.is_file() or path.suffix not in {".py", ".js", ".css", ".md"}:
            continue
        content = path.read_text(encoding="utf-8")
        for marker in FORBIDDEN_WORKSTATION_MARKERS:
            if marker in content:
                violations.append(f"{path.relative_to(PROJECT_ROOT)}: {marker}")

    assert violations == []


def test_render_startup_runs_only_the_wsgi_application() -> None:
    render_config = (PROJECT_ROOT / "render.yaml").read_text(encoding="utf-8")
    wsgi = (PROJECT_ROOT / "wsgi.py").read_text(encoding="utf-8")

    assert "gunicorn wsgi:server" in render_config
    assert "import_to_db" not in wsgi
    assert "backfill" not in wsgi.casefold()
    assert "rglob" not in wsgi
    assert "Datos_" not in render_config
