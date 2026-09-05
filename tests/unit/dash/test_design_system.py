from __future__ import annotations

from pathlib import Path

from dash.development.base_component import Component

from app.shared.components.page_structure import build_page_header, page_section, surface
from app.web.i18n import text

ROOT = Path(__file__).resolve().parents[3]
ASSETS = ROOT / "src" / "app" / "web" / "assets"


def test_shared_page_primitives_expose_stable_visual_classes() -> None:
    header = build_page_header(
        eyebrow=text("Sección", "Section"),
        title=text("Título", "Title"),
        description=text("Descripción", "Description"),
        class_name="example-header",
    )
    card = surface("Contenido", class_name="example-card")
    section = page_section("Contenido", class_name="example-section")

    assert isinstance(header, Component)
    assert getattr(header, "className", None) == "app-page-header example-header"
    assert getattr(card, "className", None) == "app-surface example-card"
    assert getattr(section, "className", None) == "app-page-section example-section"


def test_design_tokens_cover_surfaces_spacing_controls_and_page_widths() -> None:
    styles = (ASSETS / "styles.css").read_text(encoding="utf-8")
    for token in (
        "--surface-shadow:",
        "--control-height:",
        "--radius-pill:",
        "--space-1:",
        "--space-7:",
        "--page-max-width: 1500px;",
    ):
        assert token in styles


def test_primary_pages_use_the_shared_page_and_header_language() -> None:
    sources = {
        "home": ROOT / "src/app/modules/home/page.py",
        "statistics": ROOT / "src/app/modules/statistics/page.py",
        "trends": ROOT / "src/app/modules/trends/layout.py",
        "spain": ROOT / "src/app/modules/spain/page.py",
        "didactica": ROOT / "src/app/modules/didactics/page.py",
        "reports": ROOT / "src/app/modules/reports/page.py",
        "about": ROOT / "src/app/web/about.py",
        "privacy": ROOT / "src/app/modules/account/privacy_page.py",
    }
    for name, path in sources.items():
        source = path.read_text(encoding="utf-8")
        assert "app-page" in source, name
        assert "app-page-header" in source or "build_page_header" in source, name


def test_home_map_is_a_shared_rounded_chart_surface() -> None:
    home = (ROOT / "src/app/modules/home/page.py").read_text(encoding="utf-8")
    design = (ASSETS / "z_design_system.css").read_text(encoding="utf-8")

    assert 'className="home-map-stage app-surface app-chart-card"' in home
    assert ".home-map-stage.app-surface" in design
    assert "border-radius: var(--radius-lg);" in design


def test_home_and_didactica_have_real_shared_headers_with_eyebrows() -> None:
    home = (ROOT / "src/app/modules/home/page.py").read_text(encoding="utf-8")
    didactica = (ROOT / "src/app/modules/didactics/page.py").read_text(encoding="utf-8")

    assert 'title=text("Inicio", "Home")' in home
    assert 'class_name="home-page-header"' in home
    assert 'eyebrow=text("Recursos educativos", "Educational resources")' in didactica
    assert "html.H2(" in home[home.index('id="home-map-title"') - 250 :]


def test_navbar_has_a_border_but_no_lower_shadow() -> None:
    styles = (ASSETS / "styles.css").read_text(encoding="utf-8")
    navbar = styles.split(".navbar {", 1)[1].split("}", 1)[0]

    assert "border-bottom: 1px solid var(--nav-border);" in navbar
    assert "box-shadow" not in navbar


def test_statistics_buttons_fit_their_labels_at_all_breakpoints() -> None:
    statistics = (ASSETS / "statistics.css").read_text(encoding="utf-8")
    fit_rule = statistics.split("/* Keep every Statistics action proportional to its label. */", 1)[
        1
    ].split("}", 1)[0]

    for selector in (
        ".stats-create-report-link",
        ".stats-chart-export-button",
        ".stats-clear-selection",
        ".stats-ranking-page-button",
        ".stats-temporal-selection-button",
    ):
        assert selector in fit_rule
    assert "min-height: 44px;" in fit_rule
    assert "max-width: 100%;" in fit_rule
    assert "white-space: normal;" in fit_rule
    assert "width: fit-content;" in fit_rule

    survey = statistics.split(".stats-survey-control {", 1)[1].split("}", 1)[0]
    survey_option = statistics.split(".stats-survey-control .dash-options-list-option {", 1)[
        1
    ].split("}", 1)[0]
    compact_card = statistics.split(".stats-filter-card-compact .stats-filter-card-body {", 1)[
        1
    ].split("}", 1)[0]
    compact_title = statistics.split(".stats-filter-card-compact .stats-filter-card-title {", 1)[
        1
    ].split("}", 1)[0]
    assert "display: grid;" in survey
    assert "grid-template-columns: repeat(2, minmax(0, 1fr));" in survey
    assert "gap: 1rem;" in survey
    assert "width: min(78%, 52rem);" in survey
    assert "min-height: 72px;" in survey_option
    assert "width: 100%;" in survey_option
    assert "display: flex;" in compact_card
    assert "flex-direction: column;" in compact_card
    assert "align-items: center;" in compact_card
    assert "justify-content: center;" in compact_card
    assert "text-align: center;" in compact_title
    assert "text-transform: none;" in compact_title

    mobile = statistics.split("@media (max-width: 767px)", 1)[1]
    assert "align-items: flex-start;" in mobile
    assert "justify-content: flex-start;" in mobile
    assert "grid-template-columns: repeat(3," not in mobile
    compact_mobile = statistics.split("@media (max-width: 480px)", 1)[1]
    assert "grid-template-columns: minmax(0, 1fr);" in compact_mobile
    assert "width: 100%;\n  }\n\n  .stats-clear-selection" not in mobile
