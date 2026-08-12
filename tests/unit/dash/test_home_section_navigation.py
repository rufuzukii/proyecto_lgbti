from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

from dash.development.base_component import Component

from app.dash.components.section_navigation import (
    PRIMARY_SECTIONS,
    build_home_section_navigation,
)
from app.dash.i18n import UI_TEXT
from app.dash.layouts import navigation

PRIMARY_PATHS = [
    "/es",
    "/es/estadisticas",
    "/es/tendencias",
    "/es/espana",
    "/es/didactica",
    "/es/acerca-de",
]
CARD_PATHS = PRIMARY_PATHS[1:]


def _walk(component: Any):
    if isinstance(component, Component):
        yield component
        children = getattr(component, "children", None)
        if isinstance(children, list | tuple):
            for child in children:
                yield from _walk(child)
        elif children is not None:
            yield from _walk(children)


def test_primary_sections_share_the_requested_order_and_existing_routes() -> None:
    assert [section.key for section in PRIMARY_SECTIONS] == [
        "home",
        "statistics",
        "trends",
        "spain",
        "didactica",
        "about",
    ]


def test_navbar_uses_primary_section_order_without_changing_restricted_links(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        navigation,
        "current_user",
        SimpleNamespace(is_authenticated=False, role="anonymous"),
    )

    navbar = navigation.build_navbar(active="home")
    nav_list = next(
        component
        for component in _walk(navbar)
        if getattr(component, "className", "") == "nav-links"
    )
    rendered_paths = [cast(Any, item.children).href for item in cast(list[Any], nav_list.children)]

    assert rendered_paths == PRIMARY_PATHS
    assert "/es/informe" not in rendered_paths
    assert "/es/importar" not in rendered_paths


def test_navbar_keeps_report_and_upload_access_after_the_primary_sections(monkeypatch) -> None:
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
    monkeypatch.setattr(navigation, "user_has_permission", lambda *_args: True)

    navbar = navigation.build_navbar()
    nav_list = next(
        component
        for component in _walk(navbar)
        if getattr(component, "className", "") == "nav-links"
    )

    assert [cast(Any, item.children).href for item in cast(list[Any], nav_list.children)] == [
        *PRIMARY_PATHS,
        "/es/informe",
        "/es/importar",
    ]


def test_home_cards_are_static_internal_links_with_translated_accessible_names() -> None:
    section = build_home_section_navigation()
    cards = [
        component
        for component in _walk(section)
        if "home-section-card " in getattr(component, "className", "")
    ]
    links: list[Any] = [
        component
        for component in _walk(section)
        if getattr(component, "className", "") == "home-section-card__link"
    ]

    assert [link.href for link in links] == CARD_PATHS
    assert all(link.refresh is False for link in links)
    assert len(cards) == 5
    for card in cards:
        props = card.to_plotly_json()["props"]
        assert props["aria-label"]
        assert props["data-i18n-aria-label-es"]
        assert props["data-i18n-aria-label-en"]


def test_old_ilga_presentation_block_is_removed_from_home() -> None:
    source = (
        Path(__file__).resolve().parents[3] / "src" / "app" / "dash" / "layouts" / "home.py"
    ).read_text(encoding="utf-8")

    assert "_source_summary" not in source
    assert "home-source-grid" not in source
    assert "ILGA Europe analiza" not in source


def test_home_card_copy_is_complete_in_both_languages() -> None:
    card_keys = [
        "home_sections_eyebrow",
        "home_sections_title",
        "home_sections_lead",
        *[
            key
            for section in PRIMARY_SECTIONS[1:]
            for key in (
                section.label_key,
                section.description_key,
                section.action_key,
                section.aria_key,
            )
        ],
    ]

    for key in card_keys:
        assert key is not None
        assert UI_TEXT[key]["es"].strip()
        assert UI_TEXT[key]["en"].strip()


def test_home_card_css_covers_themes_responsive_layout_focus_and_motion() -> None:
    styles = (
        Path(__file__).resolve().parents[3] / "src" / "app" / "dash" / "assets" / "home.css"
    ).read_text(encoding="utf-8")

    assert "grid-template-columns: repeat(3, minmax(0, 1fr));" in styles
    assert "grid-template-columns: repeat(2, minmax(0, 1fr));" in styles
    assert ".home-sections-grid," in styles
    assert ".home-section-card__link:focus-visible" in styles
    assert 'body[data-theme="dark"] .home-section-card' in styles
    assert "@media (prefers-reduced-motion: reduce)" in styles
