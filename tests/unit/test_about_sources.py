import logging
from typing import Any
from unittest.mock import patch

from app.dash.components.ilga_criteria import build_ilga_country_criteria_panel
from app.dash.layouts.about import build_about_layout
from app.source_attribution import FRA_SURVEYS

REQUIRED_URLS = {
    "https://felgtbi.org/que-hacemos/investigacion/estado-lgtbi/",
    "https://fra.europa.eu/en/publications-and-resources/data-and-maps/2024/eu-lgbtiq-survey-iii",
    "https://rainbowmap.ilga-europe.org",
    "https://fra.europa.eu/sites/default/files/fra_uploads/fra-2024-lgbtiq-equality_en.pdf",
    "https://commission.europa.eu/strategy-and-policy/policies/justice-and-fundamental-rights/combatting-discrimination/lesbian-gay-bi-trans-and-intersex-equality/lgbtiq-equality-strategy-2026-2030_en",
    "https://op.europa.eu/webpub/com/factsheets/lgbti/en/",
}
REQUIRED_URLS.update(url for _, url in FRA_SURVEYS.values())


def test_about_sources_include_required_external_links() -> None:
    with patch("app.dash.layouts.about.build_navbar", return_value=""):
        layout = build_about_layout()

    links = [component for component in _walk(layout) if _component_prop(component, "href")]
    links_by_href = {_component_prop(component, "href"): component for component in links}

    assert REQUIRED_URLS.issubset(links_by_href)
    for url in REQUIRED_URLS:
        link = links_by_href[url]
        assert _component_prop(link, "target") == "_blank"
        assert _component_prop(link, "rel") == "noopener noreferrer"
        accessible_label = _component_prop(link, "aria-label") or _text_content(link)
        assert "pestaña nueva" in accessible_label


def test_about_source_cards_include_integrated_context_without_about_cards() -> None:
    with patch("app.dash.layouts.about.build_navbar", return_value=""):
        layout = build_about_layout()

    about_cards = [
        component
        for component in _walk(layout)
        if _component_prop(component, "className") == "about-card"
    ]
    resource_cards = [
        component
        for component in _walk(layout)
        if _component_prop(component, "className") == "about-resource-card"
    ]
    translated_nodes = [
        component for component in _walk(layout) if _component_prop(component, "data-i18n-en")
    ]

    assert about_cards == []
    assert _find_by_id_or_none(layout, "sources-attributions") is None
    assert "Fuentes y atribuciones" not in _text_content(layout)
    assert "Sources and attributions" not in _text_content(layout)
    assert "Fuentes oficiales" not in _text_content(layout)
    assert "Para profundizar" not in _text_content(layout)
    for year in FRA_SURVEYS:
        assert f"Encuesta FRA {year}" in _text_content(layout)
        assert any(
            _component_prop(component, "data-i18n-en") == f"FRA Survey {year}"
            for component in translated_nodes
        )
    assert any(
        "ILGA Europe evalúa leyes y políticas públicas" in _text_content(card)
        and "En la aplicación, estos datos permiten comparar países" in _text_content(card)
        for card in resource_cards
    )
    assert any(
        _component_prop(component, "data-i18n-en") == "Recommended sources for further reading"
        for component in translated_nodes
    )
    assert any(
        _component_prop(component, "data-i18n-en")
        == "Annual comparison of the legal and policy situation of LGBTIQ+ "
        "people in 49 European countries."
        for component in translated_nodes
    )


def test_about_no_longer_contains_interactive_ilga_explorer() -> None:
    with patch("app.dash.layouts.about.build_navbar", return_value=""):
        layout = build_about_layout()

    assert _find_by_id_or_none(layout, "about-ilga-country") is None
    assert _find_by_id_or_none(layout, "about-ilga-criteria") is None
    assert "Indicadores registrados en" not in _text_content(layout)
    assert "ILGA Europe evalúa leyes y políticas públicas" in _text_content(layout)


def test_shared_ilga_criterion_uses_specific_or_neutral_metadata_without_warning(caplog) -> None:
    country = {
        "country": "Spain",
        "country_code": "ES",
        "ranking": 77.0,
        "criteria": [
            {
                "category": "Custom category",
                "indicator": "Dataset-specific criterion",
                "weight": 1,
                "value": 0.5,
            }
        ],
    }
    with caplog.at_level(logging.WARNING):
        panel = build_ilga_country_criteria_panel(country)

    assert "Criterio jurídico" in _text_content(panel)
    assert "legal_criterion_metadata_missing" not in caplog.text


def test_shared_ilga_criterion_shows_percentage_and_ranking_contribution() -> None:
    country = {
        "country": "Spain",
        "country_code": "ES",
        "ranking": 77.0,
        "criteria": [
            {
                "category": "Equality & non-discrimination",
                "indicator": "Constitution (sexual orientation)",
                "weight": 0.16,
                "value": 1,
            },
            {
                "category": "Custom category",
                "indicator": "Dataset-specific criterion",
                "weight": 1.1,
                "value": 0.5,
            },
        ],
    }

    panel = build_ilga_country_criteria_panel(country)
    tables = [
        component
        for component in _walk(panel)
        if _component_prop(component, "className") == "ilga-indicator-card__metadata"
    ]

    assert len(tables) == 2
    assert "100 %" in _text_content(tables[0])
    assert "0.16 puntos" in _text_content(tables[0])
    assert "50 %" in _text_content(tables[1])
    assert "0.55 puntos" in _text_content(tables[1])


def _walk(component: Any):
    yield component
    children = getattr(component, "children", None)
    if children is None:
        return
    if isinstance(children, (list, tuple)):
        for child in children:
            if hasattr(child, "children") or hasattr(child, "to_plotly_json"):
                yield from _walk(child)
    elif hasattr(children, "children") or hasattr(children, "to_plotly_json"):
        yield from _walk(children)


def _find_by_id(component: Any, component_id: str) -> Any:
    for child in _walk(component):
        if _component_prop(child, "id") == component_id:
            return child
    raise AssertionError(f"component not found: {component_id}")


def _find_by_id_or_none(component: Any, component_id: str) -> Any | None:
    for child in _walk(component):
        if _component_prop(child, "id") == component_id:
            return child
    return None


def _component_prop(component: Any, name: str) -> Any:
    value = getattr(component, name, None)
    if value is not None:
        return value
    if hasattr(component, "to_plotly_json"):
        return component.to_plotly_json().get("props", {}).get(name)
    return None


def _text_content(component: Any) -> str:
    children = getattr(component, "children", None)
    if isinstance(component, str):
        return component
    if children is None:
        return ""
    if isinstance(children, str):
        return children
    if isinstance(children, (list, tuple)):
        return " ".join(_text_content(child) for child in children)
    return _text_content(children)
