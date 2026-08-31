from __future__ import annotations

from pathlib import Path
from typing import Any

from dash.development.base_component import Component

from app.shared.components.source_attribution import build_footer_attributions
from app.shared.data.source_attribution import FELGTBI_URL, FRA_ORGANIZATION_URL, ILGA_URL
from app.web.i18n import UI_TEXT

ROOT = Path(__file__).resolve().parents[3]
ASSETS = ROOT / "src" / "app" / "web" / "assets"
MODULES = ROOT / "src" / "app" / "modules"


def _walk(component: Any):
    if isinstance(component, Component):
        yield component
        children = getattr(component, "children", None)
        if isinstance(children, list | tuple):
            for child in children:
                yield from _walk(child)
        elif children is not None:
            yield from _walk(children)


def test_application_owned_quoted_copy_uses_guillemets() -> None:
    statistics = (MODULES / "statistics" / "page.py").read_text(encoding="utf-8")
    didactica = (MODULES / "didactics" / "page.py").read_text(encoding="utf-8")

    assert "«{answer}»" in statistics
    assert "«{correct_term}»" in didactica
    assert '"{answer}" in "{indicator}"' not in statistics


def test_footer_attributions_are_uniform_and_use_the_requested_copy() -> None:
    footer = build_footer_attributions(language="es")
    body = str(footer.to_plotly_json())
    cards = [
        item
        for item in _walk(footer)
        if getattr(item, "className", None) == "footer-attribution-block"
    ]
    hrefs = {getattr(item, "href", None) for item in _walk(footer)}

    assert len(cards) == 3
    assert {FRA_ORGANIZATION_URL, ILGA_URL, FELGTBI_URL} <= hrefs
    assert "Fuente:" not in body
    assert UI_TEXT["footer_attribution_fra_text"]["es"] == (
        "European Union Agency for Fundamental Rights (FRA), EU LGBTI/LGBTIQ "
        "Surveys 2019 y 2023. Datos procesados y visualizados por RainbowLens "
        "DataHub. La FRA no participa en esta adaptación."
    )
    assert UI_TEXT["footer_attribution_ilga_text"]["es"] == (
        "ILGA-Europe. Los datos han sido procesados y adaptados para su visualización "
        "en RainbowLens DataHub. RainbowLens DataHub no está afiliada ni representa "
        "oficialmente a ILGA-Europe."
    )
    assert UI_TEXT["footer_attribution_felgtbi_text"]["es"] == (
        "Federación Estatal de Lesbianas, Gais, Trans, Bisexuales, Intersexuales y más — "
        "FELGTBI+. Contenido procesado y adaptado para su visualización en RainbowLens "
        "DataHub. RainbowLens DataHub no está afiliada ni representa oficialmente a "
        "FELGTBI+."
    )
    assert UI_TEXT["footer_attribution_fra_text"]["es"] in body
    assert UI_TEXT["footer_attribution_ilga_text"]["es"] in body
    assert UI_TEXT["footer_attribution_felgtbi_text"]["es"] in body

    css = (ASSETS / "styles.css").read_text(encoding="utf-8")
    assert ".footer-attribution-block" in css
    assert "grid-template-columns: repeat(3, minmax(0, 1fr));" in css
    responsive_footer = css.split("@media (max-width: 900px)", 1)[1].split("}", 2)[0]
    assert "grid-template-columns: 1fr;" in responsive_footer


def test_home_context_uses_natural_height_and_a_theme_divider() -> None:
    css = (ASSETS / "home.css").read_text(encoding="utf-8")
    layout = (ROOT / "src" / "app" / "modules" / "home" / "page.py").read_text(
        encoding="utf-8"
    )

    assert "#home-legal-details-loading {\n  min-height: 0;" in css
    assert ".home-legal-context-divider:not(:empty)" in css
    assert "border-top: 1px solid var(--panel-border);" in css
    assert "country-status-anchor home-legal-context-divider" in layout


def test_statistics_map_is_large_shared_and_responsive() -> None:
    shared_css = (ASSETS / "styles.css").read_text(encoding="utf-8")
    statistics_css = (ASSETS / "statistics.css").read_text(encoding="utf-8")
    page = (MODULES / "statistics" / "page.py").read_text(encoding="utf-8")
    home_page = (ROOT / "src/app/modules/home/page.py").read_text(encoding="utf-8")

    assert 'className="stats-mapbox-graph europe-map-container"' in page
    assert 'className="home-europe-map europe-map-container"' in home_page
    assert ".europe-map-container {" in shared_css
    assert "height: min(68vh, 680px);" in shared_css
    assert "height: 58vh;" in shared_css
    assert "height: 52vh;" in shared_css
    assert ".stats-mapbox-graph {\n  height:" not in statistics_css
    assert ".stats-mapbox-graph.europe-map-container {" in statistics_css
    assert "height: min(74vh, 760px) !important;" in statistics_css


def test_report_workflow_is_centered_vertical_and_download_is_last() -> None:
    page = (MODULES / "reports" / "page.py").read_text(encoding="utf-8")
    css = (ASSETS / "reports.css").read_text(encoding="utf-8")

    assert "reports-config-grid" not in page
    assert "grid-template-columns: repeat(2" not in css.split(
        ".reports-filters-grid", 1
    )[1].split("}", 1)[0]
    assert "width: min(100%, 840px);" not in css
    design_system = (ASSETS / "z_design_system.css").read_text(encoding="utf-8")
    header_rule = design_system.split(".app-page-header {", 1)[1].split("}", 1)[0]
    assert "border: 0;" in header_rule
    assert "background: transparent;" in header_rule
    assert "box-shadow: none;" in header_rule
    assert "width: 100%;" in header_rule
    assert 'class_name="reports-header"' in page
    workflow_children = css.split(".reports-workflow > * {", 1)[1].split("}", 1)[0]
    assert "width: 100%;" in workflow_children
    assert "min-width: 0;" in workflow_children
    assert "reports-preview-actions" not in css
    assert "reports-download-actions" not in css
    assert 'className="reports-actions reports-final-actions"' in page
    assert page.index("_hr_purpose_panel()") < page.index("_configuration_panel(")
    assert "Informe orientado a RRHH" in page
    assert page.index('className="reports-card reports-plan-summary"') < page.index(
        'id="report-preview-button"'
    )
    assert page.index('id="report-download-button"') < page.index(
        'id="report-preview-content"'
    )


def test_dark_button_overrides_keep_text_readable() -> None:
    admin = (ASSETS / "admin.css").read_text(encoding="utf-8")
    didactica = (ASSETS / "didactica.css").read_text(encoding="utf-8")

    assert ':root[data-theme="dark"] .admin-user-search-button' in admin
    assert ':root[data-theme="dark"] .didactica-button-secondary' in didactica
    assert "color: var(--color-text);" in admin
    assert "color: var(--color-text);" in didactica
