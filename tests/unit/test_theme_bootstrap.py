from pathlib import Path

import app.web.application as dash_app_module
from app.web.application import DASH_INDEX_STRING
from app.web.navigation import _theme_toggle

ASSETS = Path(__file__).resolve().parents[2] / "src" / "app" / "web" / "assets"


def test_saved_theme_is_applied_before_stylesheets_load() -> None:
    theme_script = DASH_INDEX_STRING.index('localStorage.getItem("rainbowlens-theme")')
    dash_stylesheets = DASH_INDEX_STRING.index("{%css%}")

    assert theme_script < dash_stylesheets


def test_body_theme_is_applied_before_dash_mounts() -> None:
    body_theme = DASH_INDEX_STRING.index("document.body.dataset.theme")
    dash_mount = DASH_INDEX_STRING.index("{%app_entry%}")

    assert body_theme < dash_mount


def test_route_navbar_does_not_reset_theme_toggle_to_light() -> None:
    toggle = _theme_toggle()
    children = toggle.children
    assert isinstance(children, list)
    button = children[0]
    props = button.to_plotly_json()["props"]

    assert props["data-theme-toggle"] == "true"
    assert "data-theme-state" not in props


def test_dark_toggle_position_uses_persistent_document_theme() -> None:
    styles = (ASSETS / "styles.css").read_text(encoding="utf-8")

    assert ':root[data-theme="dark"] .theme-toggle .theme-toggle-dot' in styles


def test_dark_global_background_is_flat_across_dash_roots() -> None:
    styles = (ASSETS / "styles.css").read_text(encoding="utf-8")
    dark_variables = styles.split(':root[data-theme="dark"],', 1)[1].split("}", 1)[0]
    dark_roots = styles.split('html[data-theme="dark"],', 1)[1].split("}", 1)[0]

    assert "--app-background: var(--color-bg);" in dark_variables
    assert "linear-gradient(135deg, #0a0e17 0%, #111827 52%, #1b1420 100%)" not in styles
    assert "--body-gradient" not in styles
    assert 'html[data-theme="dark"] #react-entry-point' in dark_roots
    assert 'html[data-theme="dark"] #_dash-app-content' in dark_roots
    assert 'html[data-theme="dark"] .app-shell' in dark_roots
    assert 'html[data-theme="dark"] #page-content' in dark_roots
    assert "background-color: var(--color-bg);" in dark_roots
    assert "background-image: none;" in dark_roots


def test_structural_page_gradients_are_removed() -> None:
    auth_styles = (ASSETS / "auth.css").read_text(encoding="utf-8")
    privacy_styles = (ASSETS / "privacy.css").read_text(encoding="utf-8")

    assert "radial-gradient" not in auth_styles
    assert "radial-gradient" not in privacy_styles
    assert "background: var(--color-bg);" in auth_styles


def test_dark_theme_renders_dash_option_text_in_white() -> None:
    styles = (ASSETS / "styles.css").read_text(encoding="utf-8")

    assert ':root[data-theme="dark"] span.dash-options-list-option-text' in styles
    assert 'body[data-theme="dark"] span.dash-options-list-option-text' in styles
    assert "color: #fff !important;" in styles
    assert ':where(:root[data-theme="dark"], body[data-theme="dark"]) .dash-options-list-option' in styles
    assert ".dash-options-list-option-wrapper" in styles
    assert "background-color: transparent;" in styles


def test_europe_map_keeps_the_normal_ocean_colour_in_dark_mode() -> None:
    theme = (ASSETS / "js" / "20_theme.js").read_text(encoding="utf-8")

    assert 'geoOcean: "#dcebf2"' in theme
    assert 'geoOcean: dark ? "#0a0e17"' not in theme


def test_inserted_theme_controls_are_synchronized_immediately() -> None:
    bootstrap = (ASSETS / "js" / "40_bootstrap.js").read_text(encoding="utf-8")
    theme = (ASSETS / "js" / "20_theme.js").read_text(encoding="utf-8")

    assert "if (targets.themeControls)" in bootstrap
    assert "app.theme.applyToggleLabels(state.currentTheme(), state.currentLanguage())" in bootstrap
    assert "labelNode.dataset.i18nEs !== labels.es" in theme
    assert "labelNode.dataset.i18nEn !== labels.en" in theme


def test_language_store_and_initialization_preserve_saved_language() -> None:
    source = Path(dash_app_module.__file__).read_text(encoding="utf-8")

    assert 'dcc.Store(id="app-language-store", storage_type="local")' in source
    assert "const persisted =" in source
    assert "Number.isFinite(nClicks)" in source
    assert "nClicks > 0" in source
    assert "state.nextLanguage(inferred)" in source
    assert 'State("app-language-store", "data")' not in source


def test_language_is_applied_immediately_on_boot_and_route_changes() -> None:
    bootstrap = (ASSETS / "js" / "40_bootstrap.js").read_text(encoding="utf-8")
    i18n = (ASSETS / "js" / "10_i18n.js").read_text(encoding="utf-8")

    assert "if (targets.language)" in bootstrap
    assert "targets.language = false" in bootstrap
    assert "app.i18n.applyLanguage(state.currentLanguage());" in bootstrap
    assert '["alt", "aria-label", "title"]' in i18n
    assert "applyTranslatedAttributes(selected);" in i18n


def test_dash_initial_loading_text_is_replaced_by_centered_spinner() -> None:
    styles = (ASSETS / "styles.css").read_text(encoding="utf-8")
    bootstrap = (ASSETS / "js" / "40_bootstrap.js").read_text(encoding="utf-8")

    assert "._dash-loading {" in styles
    assert "color: transparent;" in styles
    assert "._dash-loading::after {" in styles
    assert "animation: rainbowlens-loader-spin" in styles
    assert "position: fixed;" in styles
    assert "justify-content: center;" in styles
    footer_rule = styles.split(".site-footer {", 1)[1].split("}", 1)[0]
    assert "display: grid;" in footer_rule
    assert '.app-shell[data-page-ready="true"] .site-footer' not in styles
    assert "syncApplicationReadyState" not in bootstrap
    assert "data-dash-is-loading" not in bootstrap


def test_footer_stays_out_of_the_loading_frame_without_layout_shift() -> None:
    styles = (ASSETS / "styles.css").read_text(encoding="utf-8")

    assert ".app-shell {" in styles
    assert "flex-direction: column;" in styles
    assert "#page-content {" in styles
    assert "flex: 1 0 auto;" in styles
    assert "#page-content:empty + .site-footer" in styles
    assert '#page-content[data-dash-is-loading="true"] + .site-footer' in styles
    assert "visibility: hidden;" in styles
