from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
REPORTS_CSS = ROOT / "src" / "app" / "dash" / "assets" / "reports.css"


def _reports_css() -> str:
    return REPORTS_CSS.read_text(encoding="utf-8")


def test_reports_dark_theme_is_scoped_from_the_page_root() -> None:
    css = _reports_css()

    assert 'html[data-theme="dark"] .reports-shell' in css
    assert 'body[data-theme="dark"] .reports-shell' in css
    assert "--reports-panel-bg: rgba(17, 24, 39, 0.96);" in css
    assert "--reports-text: #f7f9fc;" in css
    assert "color: var(--reports-text);" in css


def test_reports_dark_theme_covers_dash_controls_and_preview_content() -> None:
    css = _reports_css()

    assert ".reports-field .DateInput_input" in css
    assert ".reports-shell .Select--multi .Select-value" in css
    assert ".reports-preview-grid" in css
    assert "--ag-background-color: var(--reports-control-bg);" in css
    assert ".reports-preview-chart .js-plotly-plot text" in css
    assert "fill: var(--reports-text) !important;" in css
