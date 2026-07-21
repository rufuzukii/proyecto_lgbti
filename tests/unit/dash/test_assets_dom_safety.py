from pathlib import Path
from types import SimpleNamespace

import app.dash.layouts.navigation as navigation


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


def test_statistics_segmented_buttons_use_outer_dash_options() -> None:
    js = (ASSETS_JS / "30_segmented_controls.js").read_text(encoding="utf-8")
    css = (ASSETS_CSS / "statistics.css").read_text(encoding="utf-8")

    assert ".dash-options-list-option" in js
    assert "markClickedLabel" not in js
    assert ".stats-data-type-control .dash-options-list-option:has(.stats-segmented-input:checked)" in css
    assert "stats-data-type-control--fra .stats-segmented-label:nth-of-type" not in css
    assert "stats-data-type-control--ilga .stats-segmented-label:nth-of-type" not in css


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
    account_child = account_link.children
    assert account_child is not None
    child_props = account_child.to_plotly_json()["props"]

    assert "data-i18n-es" not in link_props
    assert child_props["data-i18n-es"] == "Usuario"
    assert child_props["data-i18n-en"] == "Usuario"


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
