from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ASSETS = ROOT / "src" / "app" / "dash" / "assets"


def test_common_page_container_has_fluid_shared_dimensions() -> None:
    styles = (ASSETS / "styles.css").read_text(encoding="utf-8")
    responsive = (ASSETS / "zz_responsive.css").read_text(encoding="utf-8")
    assert "--page-max-width: 1600px" in styles
    assert "--page-horizontal-padding: clamp(" in styles
    assert ".app-page-container.app-page-container" in responsive
    assert "max-width: var(--page-max-width)" in responsive
    assert "padding-inline: var(--page-horizontal-padding)" in responsive
    assert "overflow-x: clip" in responsive


def test_primary_pages_share_the_container_and_about_is_not_capped_at_1100() -> None:
    source_files = (
        "dash/layouts/home.py",
        "dash/layouts/about.py",
        "dash/layouts/user_page.py",
        "dash/pages/statistics.py",
        "dash/pages/spain.py",
        "dash/pages/didactica.py",
        "dash/pages/privacy.py",
        "dash/pages/reports.py",
        "dash/pages/upload.py",
        "dash/pages/admin/users.py",
        "dash/pages/admin/imports.py",
        "trends/layout.py",
    )
    for relative in source_files:
        source = (ROOT / "src" / "app" / relative).read_text(encoding="utf-8")
        assert "app-page-container" in source, relative

    about_css = (ASSETS / "home.css").read_text(encoding="utf-8")
    about_block = about_css[about_css.index(".about-shell"):about_css.index(".about-eyebrow")]
    assert "6vw" not in about_block
    assert "max-width: 1100px" not in about_block


def test_responsive_breakpoints_cover_desktop_tablet_and_mobile() -> None:
    responsive = (ASSETS / "zz_responsive.css").read_text(encoding="utf-8")
    about = (ASSETS / "home.css").read_text(encoding="utf-8")
    didactica = (ASSETS / "didactica.css").read_text(encoding="utf-8")
    for breakpoint in ("1600px", "1199px", "1120px", "599px"):
        assert breakpoint in responsive
    assert "1100px" in about
    assert "760px" in about
    assert "680px" in didactica


def test_user_dashboard_keeps_one_centered_column_on_large_screens() -> None:
    auth = (ASSETS / "auth.css").read_text(encoding="utf-8")
    dashboard_rule = auth.split(".user-dashboard-grid {", 1)[1].split("}", 1)[0]
    shell_rule = auth.split(".user-dashboard-shell {", 1)[1].split("}", 1)[0]

    assert "grid-template-columns: minmax(0, 1fr);" in dashboard_rule
    assert "max-width: 960px;" in dashboard_rule
    assert "margin-inline: auto;" in dashboard_rule
    assert "max-width: 960px;" in shell_rule
    assert "1.55fr" not in auth
