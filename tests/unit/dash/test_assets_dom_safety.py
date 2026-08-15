from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

from app.dash.layouts import navigation

ROOT = Path(__file__).resolve().parents[3]
ASSETS_JS = ROOT / "src" / "app" / "dash" / "assets" / "js"
ASSETS_CSS = ROOT / "src" / "app" / "dash" / "assets"


def test_dash_assets_do_not_replace_react_owned_text_nodes() -> None:
    forbidden_patterns = [
        "textContent =",
        "innerText =",
        "innerHTML =",
        "appendChild(",
        "removeChild(",
        "replaceChild(",
    ]

    matches: list[str] = []
    for path in ASSETS_JS.glob("*.js"):
        content = path.read_text(encoding="utf-8")
        for pattern in forbidden_patterns:
            if pattern in content:
                matches.append(f"{path.relative_to(ROOT)} contains {pattern!r}")

    assert matches == []


def test_dash_generated_form_fields_receive_stable_accessibility_attributes() -> None:
    js = (ASSETS_JS / "25_form_accessibility.js").read_text(encoding="utf-8")

    assert "dash-dropdown-focus-target" in js
    assert "dash-range-slider-min-input" in js
    assert "dash-range-slider-max-input" in js
    assert 'field.setAttribute("name", fieldId)' in js
    assert 'field.setAttribute("aria-label"' in js
    assert 'attributeFilter: ["aria-label", "id", "name"]' in js
    assert "console.warn" not in js
    assert "console.error" not in js


def test_statistics_segmented_buttons_use_outer_dash_options() -> None:
    js = (ASSETS_JS / "30_segmented_controls.js").read_text(encoding="utf-8")
    css = (ASSETS_CSS / "statistics.css").read_text(encoding="utf-8")

    assert ".dash-options-list-option" in js
    assert "markClickedLabel" not in js
    assert (
        ".stats-survey-control .dash-options-list-option:has(.stats-segmented-input:checked)"
        in css
    )
    assert "stats-data-type-control" not in css


def test_spain_document_buttons_keep_selected_visual_state() -> None:
    segmented_js = (ASSETS_JS / "30_segmented_controls.js").read_text(encoding="utf-8")
    bootstrap_js = (ASSETS_JS / "40_bootstrap.js").read_text(encoding="utf-8")
    css = (ASSETS_CSS / "statistics.css").read_text(encoding="utf-8")

    assert ".spain-selection-control" in segmented_js
    assert 'control.querySelectorAll(".dash-options-list-option")' in segmented_js
    assert 'setActiveOption(option, Boolean(input && input.checked))' in segmented_js
    assert ".spain-document-radio-input" in bootstrap_js
    assert (
        ".spain-document-radio .dash-options-list-option.is-active "
        ".spain-document-radio-label"
    ) in css


def test_authenticated_navbar_keeps_i18n_attributes_out_of_dcc_link(monkeypatch) -> None:
    monkeypatch.setattr(
        navigation,
        "current_user",
        SimpleNamespace(
            is_authenticated=True,
            username="Usuario",
            email="usuario@example.com",
            role="common",
        ),
    )

    navbar = navigation.build_navbar(active="home")
    account_link = next(
        component
        for component in _walk(navbar)
        if getattr(component, "className", "") == "nav-link nav-account"
    )
    link_props = account_link.to_plotly_json()["props"]
    account_name = next(
        component
        for component in _walk(account_link)
        if getattr(component, "className", "") == "nav-account-name"
    )
    account_caption = next(
        component
        for component in _walk(account_link)
        if getattr(component, "className", "") == "nav-account-caption"
    )
    name_props = account_name.to_plotly_json()["props"]
    caption_props = account_caption.to_plotly_json()["props"]

    assert "data-i18n-es" not in link_props
    assert name_props["data-i18n-es"] == "Usuario"
    assert name_props["data-i18n-en"] == "Usuario"
    assert caption_props["data-i18n-es"] == "Panel personal"
    assert caption_props["data-i18n-en"] == "Personal dashboard"


def test_navbar_exposes_an_accessible_collapsible_mobile_menu(monkeypatch) -> None:
    monkeypatch.setattr(
        navigation,
        "current_user",
        SimpleNamespace(is_authenticated=False),
    )

    navbar = navigation.build_navbar(active="home")
    components = list(_walk(navbar))
    toggle = next(
        component
        for component in components
        if getattr(component, "className", "") == "nav-menu-toggle"
    )
    menu = next(
        component
        for component in components
        if getattr(component, "id", None) == "primary-navigation"
    )
    mobile_logo = next(
        component
        for component in components
        if "nav-brand-logo-mobile" in getattr(component, "className", "")
    )
    desktop_logo = next(
        component
        for component in components
        if "nav-brand-logo-desktop" in getattr(component, "className", "")
    )

    toggle_props = toggle.to_plotly_json()["props"]
    menu_props = menu.to_plotly_json()["props"]
    mobile_logo_props = mobile_logo.to_plotly_json()["props"]
    desktop_logo_props = desktop_logo.to_plotly_json()["props"]
    assert toggle_props["aria-controls"] == "primary-navigation"
    assert toggle_props["aria-expanded"] == "false"
    assert toggle_props["data-nav-menu-toggle"] == "true"
    assert toggle_props["data-i18n-title-en"] == "Menu"
    assert toggle_props["data-i18n-aria-label-en"] == "Open menu"
    assert _props(navbar)["data-i18n-aria-label-en"] == "Primary navigation"
    assert menu_props["className"] == "nav-menu"
    assert mobile_logo_props["src"].endswith("rainbow_lens_icono.png")
    assert desktop_logo_props["src"].endswith("rainbow_lens_logo.png")
    assert mobile_logo_props["alt"] == "RainbowLens Datahub"


def test_navbar_logo_uses_spa_home_navigation(monkeypatch) -> None:
    monkeypatch.setattr(
        navigation,
        "current_user",
        SimpleNamespace(is_authenticated=False),
    )

    navbar = navigation.build_navbar(active="statistics")
    brand = next(
        component
        for component in _walk(navbar)
        if getattr(component, "className", "") == "nav-brand"
    )
    props = brand.to_plotly_json()["props"]

    assert props["href"] == "/es"
    assert props["refresh"] is False
    assert props["title"] == "RainbowLens Datahub · Inicio / Home"


def test_admin_navbar_groups_user_and_admin_without_duplicating_link(monkeypatch) -> None:
    monkeypatch.setattr(
        navigation,
        "current_user",
        SimpleNamespace(
            is_authenticated=True,
            username="Administradora",
            email="admin@example.com",
            role="admin",
        ),
    )

    navbar = navigation.build_navbar(active="admin")
    components = list(_walk(navbar))
    admin_slot = next(
        component
        for component in components
        if getattr(component, "className", "") == "nav-admin-slot"
    )
    desktop_account_slot = next(
        component
        for component in components
        if "nav-account-slot-desktop" in getattr(component, "className", "")
    )
    mobile_account_slot = next(
        component
        for component in components
        if "nav-account-slot-mobile" in getattr(component, "className", "")
    )
    admin_links = [
        component
        for component in components
        if "nav-admin-cta" in getattr(component, "className", "")
    ]

    assert _props(navbar)["className"] == "navbar navbar--admin"
    assert len(admin_links) == 1
    assert _props(admin_slot)["children"] is admin_links[0]
    assert _props(_props(desktop_account_slot)["children"])["className"] == "nav-link nav-account"
    assert _props(_props(mobile_account_slot)["children"])["className"] == "nav-link nav-account"


def test_non_admin_navbar_omits_admin_and_upload_links_with_preferences(monkeypatch) -> None:
    monkeypatch.setattr(
        navigation,
        "current_user",
        SimpleNamespace(
            is_authenticated=True,
            username="Usuario",
            email="user@example.com",
            role="common",
        ),
    )

    navbar = navigation.build_navbar(active="upload")
    components = list(_walk(navbar))
    header_actions = next(
        component
        for component in components
        if getattr(component, "className", "") == "nav-header-actions"
    )
    header_children = cast(list[Any], _props(header_actions)["children"])
    assert _props(navbar)["className"] == "navbar"
    assert not any(
        "nav-admin-cta" in getattr(component, "className", "") for component in components
    )
    assert len(header_children) == 3
    assert "nav-account-slot-desktop" in _props(header_children[-1])["className"]
    assert not any(getattr(component, "href", None) == "/upload" for component in components)


def test_anonymous_navbar_does_not_expose_upload_action(monkeypatch) -> None:
    monkeypatch.setattr(
        navigation,
        "current_user",
        SimpleNamespace(is_authenticated=False, role="anonymous"),
    )

    components = list(_walk(navigation.build_navbar()))

    assert not any(getattr(component, "href", None) == "/upload" for component in components)


def test_navbar_icon_controls_have_initial_accessible_names(monkeypatch) -> None:
    monkeypatch.setattr(
        navigation,
        "current_user",
        SimpleNamespace(is_authenticated=False),
    )

    components = list(_walk(navigation.build_navbar()))
    language = next(
        component
        for component in components
        if getattr(component, "className", "") == "language-toggle"
    )
    theme = next(
        component
        for component in components
        if getattr(component, "className", "") == "theme-toggle"
    )

    assert language.to_plotly_json()["props"]["aria-label"] == "Cambiar idioma / Change language"
    assert (
        theme.to_plotly_json()["props"]["aria-label"] == "Cambiar modo de color / Change color mode"
    )


def test_responsive_css_is_loaded_last_without_important_overrides() -> None:
    responsive_css = ASSETS_CSS / "zz_responsive.css"
    legacy_responsive_css = ASSETS_CSS / "responsive" / "responsive.css"
    styles = responsive_css.read_text(encoding="utf-8")
    bootstrap = (ASSETS_JS / "40_bootstrap.js").read_text(encoding="utf-8")
    dash_app = (ROOT / "src" / "app" / "dash_app.py").read_text(encoding="utf-8")
    css_names = sorted(path.name for path in ASSETS_CSS.glob("*.css"))

    assert responsive_css.exists()
    assert not legacy_responsive_css.exists()
    assert css_names[-1] == "zz_responsive.css"
    assert "/assets/responsive/responsive.css" not in dash_app
    assert "!important" not in styles
    assert "data-nav-menu-toggle" in bootstrap
    assert 'matchMedia("(max-width: 1199px)")' in bootstrap
    assert 'setAttribute("aria-expanded"' in bootstrap
    assert "@media (max-width: 359px)" in styles
    assert ".nav-header-actions" in styles
    assert "grid-template-columns: repeat(2, minmax(0, 1fr))" in styles


def test_report_figure_error_is_hidden_after_a_successful_image_load() -> None:
    bootstrap = (ASSETS_JS / "40_bootstrap.js").read_text(encoding="utf-8")
    statistics_css = (ASSETS_CSS / "statistics.css").read_text(encoding="utf-8")

    assert ".spain-report-html .report-figure-load-error[hidden]" in statistics_css
    assert "fallback.hidden = true;" in bootstrap
    assert "fallback.hidden = false;" in bootstrap
    assert "image.hidden = false;" in bootstrap


def test_plotly_theme_waits_for_a_real_initial_plot_before_relayout() -> None:
    theme = (ASSETS_JS / "20_theme.js").read_text(encoding="utf-8")

    assert "function isPlotlyInitialized(graph)" in theme
    assert "graph._fullLayout" in theme
    assert "Array.isArray(graph.data)" in theme
    assert "graph.data.length > 0" in theme
    guard = theme.index("if (!isPlotlyInitialized(graph))")
    relayout = theme.index("window.Plotly.relayout(graph, layout)")
    assert guard < relayout


def _walk(component):
    yield component
    children = getattr(component, "children", None)
    if children is None:
        return
    if not isinstance(children, (list, tuple)):
        children = [children]
    for child in children:
        if hasattr(child, "children"):
            yield from _walk(child)


def _props(component: Any) -> dict[str, Any]:
    return cast(dict[str, Any], component.to_plotly_json()["props"])
