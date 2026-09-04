from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
REPORTS_CSS = ROOT / "src" / "app" / "web" / "assets" / "reports.css"
AUTH_CSS = ROOT / "src" / "app" / "web" / "assets" / "auth.css"
GLOBAL_CSS = ROOT / "src" / "app" / "web" / "assets" / "styles.css"


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

    assert ".reports-field .DateInput_input" not in css
    assert ".reports-field .dash-datepicker" not in css
    assert ".reports-shell .Select--multi .Select-value" in css
    assert ".reports-preview-grid" in css
    assert "--ag-background-color: var(--reports-control-bg);" in css
    assert ".reports-preview-chart .js-plotly-plot text" in css
    assert "fill: var(--reports-text) !important;" in css


def test_report_chart_narratives_keep_black_text_in_dark_mode() -> None:
    css = _reports_css()
    rule = css.split(
        'html[data-theme="dark"] textarea.reports-chart-narrative,', 1
    )[1].split("}", 1)[0]

    assert 'body[data-theme="dark"] textarea.reports-chart-narrative' in rule
    assert 'html[data-theme="dark"] textarea.reports-section-narrative' in rule
    assert 'body[data-theme="dark"] textarea.reports-section-narrative' in rule
    assert "background: #ffffff !important;" in rule
    assert "color: #000000 !important;" in rule
    assert "caret-color: #000000;" in rule


def test_profile_personalisation_and_login_notice_are_responsive_and_dark_compatible() -> None:
    reports_css = _reports_css()
    auth_css = AUTH_CSS.read_text(encoding="utf-8")
    global_css = GLOBAL_CSS.read_text(encoding="utf-8")

    assert ".reports-hr-explanation" in reports_css
    assert ".reports-filters-grid" in reports_css
    assert ".reports-field.has-error .Select-control" in reports_css
    assert ".reports-field-error" in reports_css
    assert ".reports-plan-summary" in reports_css
    assert ".reports-steps" not in reports_css
    assert ".reports-objective-options" not in reports_css
    assert "reports-advanced" not in reports_css
    assert "@media (max-width: 820px)" in reports_css
    assert "@media (max-width: 520px)" in reports_css
    assert ".auth-toast" in auth_css
    assert "width: min(24rem, calc(100vw - 1.5rem));" in auth_css
    assert 'body[data-theme="dark"] .auth-message-info' in global_css
