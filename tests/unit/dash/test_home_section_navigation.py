from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

from dash import Dash
from dash.development.base_component import Component

import app.dash.layouts.home as home_layout
from app.dash.components.section_navigation import (
    ANONYMOUS_ACCOUNT_SECTION,
    AUTHENTICATED_ACCOUNT_SECTION,
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
CARD_PATHS = [*PRIMARY_PATHS[1:], "/es/iniciar-sesion"]


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


def test_navbar_keeps_public_report_after_primary_sections_and_hides_import(
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

    assert rendered_paths == [*PRIMARY_PATHS, "/es/informe"]
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
    cards: list[Any] = [
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
    assert len(cards) == 6
    for card in cards:
        props = card.to_plotly_json()["props"]
        assert props["aria-label"]
        assert props["data-i18n-aria-label-es"]
        assert props["data-i18n-aria-label-en"]


def test_home_account_card_links_to_profile_for_authenticated_users() -> None:
    section = build_home_section_navigation(authenticated=True)
    links: list[Any] = [
        component
        for component in _walk(section)
        if getattr(component, "className", "") == "home-section-card__link"
    ]
    cards: list[Any] = [
        component
        for component in _walk(section)
        if "home-section-card " in getattr(component, "className", "")
    ]

    assert len(cards) == 6
    assert links[-1].href == "/es/perfil"
    assert "home-section-card--profile" in cards[-1].className
    assert "Tu perfil" in str(cards[-1].to_plotly_json())


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
            for section in (
                *PRIMARY_SECTIONS[1:],
                ANONYMOUS_ACCOUNT_SECTION,
                AUTHENTICATED_ACCOUNT_SECTION,
            )
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


def test_home_cards_describe_the_current_user_facing_features() -> None:
    assert (
        "mapas, rankings, comparaciones y segmentaciones"
        in UI_TEXT["home_statistics_description"]["es"]
    )
    assert "no son predicciones oficiales" in UI_TEXT["home_trends_description"]["es"]
    assert "not official predictions" in UI_TEXT["home_trends_description"]["en"]
    assert "FELGTBI+" in UI_TEXT["home_spain_description"]["es"]
    assert "glosario" in UI_TEXT["home_didactics_description"]["es"]
    assert "sources, methodology and purpose" in UI_TEXT["home_about_description"]["en"]


def test_home_card_css_covers_themes_responsive_layout_focus_and_motion() -> None:
    styles = (
        Path(__file__).resolve().parents[3] / "src" / "app" / "dash" / "assets" / "home.css"
    ).read_text(encoding="utf-8")

    assert "grid-template-columns: repeat(3, minmax(0, 1fr));" in styles
    assert "grid-template-columns: repeat(2, minmax(0, 1fr));" in styles
    assert ".home-sections-grid," in styles
    assert ".home-section-card__link:focus-visible" in styles
    assert 'body[data-theme="dark"] .home-section-card' in styles
    assert 'body[data-theme="dark"] .home-legal-details-panel' in styles
    assert ".home-ilga-country-summary" in styles
    assert "#home-legal-details-loading" in styles
    assert "@media (prefers-reduced-motion: reduce)" in styles


def test_home_places_ilga_detail_between_map_and_navigation(monkeypatch) -> None:
    document = {"year": 2026, "countries": []}
    monkeypatch.setattr(home_layout, "get_latest_ilga_document", lambda: document)
    monkeypatch.setattr(home_layout, "get_ilga_years", lambda: [2026])
    monkeypatch.setattr(home_layout, "build_navbar", lambda **_kwargs: "")
    monkeypatch.setattr(
        home_layout,
        "current_user",
        SimpleNamespace(is_authenticated=False),
    )

    layout = home_layout.build_home_layout()
    ordered_ids_or_classes = [
        getattr(component, "id", None) or getattr(component, "className", None)
        for component in cast(Any, cast(Any, layout.children)[1]).children
    ]

    assert ordered_ids_or_classes.index("home-map-stage") < ordered_ids_or_classes.index(
        "home-legal-section"
    )
    assert ordered_ids_or_classes.index("home-legal-section") < ordered_ids_or_classes.index(
        "home-sections"
    )
    panel = next(
        component
        for component in _walk(layout)
        if getattr(component, "id", None) == "home-legal-details"
    )
    loading = next(
        component
        for component in _walk(layout)
        if getattr(component, "id", None) == "home-legal-details-loading"
    )
    assert "Selecciona un país para consultar su situación legal en 2026" in str(panel)
    assert cast(Any, loading).target_components == {
        "home-legal-details": "children",
        "home-legal-country-status": "children",
    }


def test_home_legal_detail_uses_only_its_own_country_selector(monkeypatch) -> None:
    document = {
        "year": 2026,
        "countries": [
            {
                "country": "Spain",
                "country_code": "ES",
                "ranking": 77.0,
                "criteria": [
                    {
                        "category": "Family",
                        "indicator": "Marriage equality",
                        "weight": 1,
                        "value": 1,
                    }
                ],
            }
        ],
    }
    monkeypatch.setattr(
        home_layout,
        "get_home_legal_country_detail",
        lambda code: document["countries"][0] if code == "ES" else None,
    )
    app = Dash("home-ilga-detail-test", suppress_callback_exceptions=True)
    home_layout.register_home_callbacks(app)
    callback = next(
        entry["callback"].__wrapped__
        for entry in app.callback_map.values()
        if getattr(entry.get("callback"), "__wrapped__", None)
        and entry["callback"].__wrapped__.__name__ == "update_home_legal_country_details"
    )

    initial, initial_state = callback(None, "es")
    selected, ready_state = callback("ES", "es")

    assert "Selecciona un país" in str(initial)
    assert "España" in str(selected)
    assert "matrimonio con los mismos derechos" in str(selected)
    assert initial_state["status"] == "INITIAL"
    assert ready_state == {"status": "READY", "country_code": "ES", "year": 2026}
    callback_entry = next(
        entry
        for entry in app.callback_map.values()
        if getattr(entry.get("callback"), "__wrapped__", None)
        and entry["callback"].__wrapped__.__name__ == "update_home_legal_country_details"
    )
    assert {item["id"] for item in callback_entry["inputs"]} == {
        "home-legal-country-select",
        "app-language-store",
    }
    assert all(item["property"] != "clickData" for item in callback_entry["inputs"])
