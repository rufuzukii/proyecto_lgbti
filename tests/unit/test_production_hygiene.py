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


def test_render_startup_runs_wsgi_without_opening_a_browser() -> None:
    render_config = (PROJECT_ROOT / "render.yaml").read_text(encoding="utf-8")
    start_script = (PROJECT_ROOT / "scripts" / "render_start.sh").read_text(encoding="utf-8")
    export_check = (PROJECT_ROOT / "scripts" / "check_chart_export.py").read_text(
        encoding="utf-8"
    )
    wsgi = (PROJECT_ROOT / "wsgi.py").read_text(encoding="utf-8")

    assert "bash scripts/render_start.sh" in render_config
    assert "check_chart_export.py" not in start_script
    assert "export_figures_for_report" not in export_check
    assert "exec gunicorn wsgi:server" in start_script
    assert "import_to_db" not in wsgi
    assert "backfill" not in wsgi.casefold()
    assert "rglob" not in wsgi
    assert "Datos_" not in render_config


def test_runtime_and_render_have_no_automatic_email_infrastructure() -> None:
    render_config = (PROJECT_ROOT / "render.yaml").read_text(encoding="utf-8")
    runtime_source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in PRODUCTION_ROOT.rglob("*.py")
        if path.is_file()
    )

    for marker in (
        "smtplib",
        "SMTP_HOST",
        "MAIL_SERVER",
        "GMAIL_API_CLIENT_ID",
        "send_verification_email",
        "CONTACT_MAX_ATTEMPTS",
        "CONTACT_WINDOW_SECONDS",
    ):
        assert marker not in runtime_source
        assert marker not in render_config
