from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from dash import Dash
from dash.exceptions import PreventUpdate

from app.dash.layouts import home
from app.dash.routes import localized_route_context


def _walk(component: Any):
    if component is None:
        return
    if isinstance(component, (list, tuple)):
        for child in component:
            yield from _walk(child)
        return
    yield component
    yield from _walk(getattr(component, "children", None))


def _callback(app: Dash, name: str):
    return next(
        entry["callback"].__wrapped__
        for entry in app.callback_map.values()
        if getattr(entry.get("callback"), "__wrapped__", None)
        and entry["callback"].__wrapped__.__name__ == name
    )


def _callback_entry(app: Dash, name: str) -> dict[str, Any]:
    return next(
        entry
        for entry in app.callback_map.values()
        if getattr(entry.get("callback"), "__wrapped__", None)
        and entry["callback"].__wrapped__.__name__ == name
    )


def _country(code: str, name: str, ranking: float) -> dict[str, Any]:
    return {
        "country": name,
        "country_code": code,
        "ranking": ranking,
        "criteria": [
            {
                "category": "Family",
                "indicator": "Marriage equality",
                "weight": 1,
                "value": 1,
            }
        ],
    }


def _app(monkeypatch) -> Dash:
    monkeypatch.setattr(home, "build_navbar", lambda **_kwargs: "")
    monkeypatch.setattr(home, "current_user", SimpleNamespace(is_authenticated=False))
    monkeypatch.setattr(
        home,
        "get_latest_ilga_document",
        lambda: {"year": 2026, "countries": [_country("ES", "Spain", 77.0)]},
    )
    monkeypatch.setattr(home, "get_ilga_years", lambda: [2026])
    app = Dash("home-independent-test", suppress_callback_exceptions=True)
    app.layout = home.build_home_layout()
    home.register_home_callbacks(app)
    return app


def test_initial_home_keeps_map_visible_and_legal_selector_empty(monkeypatch) -> None:
    app = _app(monkeypatch)
    components = {
        component.id: component
        for component in _walk(app.layout)
        if isinstance(getattr(component, "id", None), str)
    }

    assert components["home-map-graph"].figure.data
    assert components["home-legal-country-select"].value is None
    assert "Situación legal por país en 2026" in str(components["home-legal-section"])
    assert "Selecciona un país para consultar su situación legal en 2026" in str(
        components["home-legal-details"]
    )


def test_initial_legal_country_title_uses_the_active_route_language(monkeypatch) -> None:
    monkeypatch.setattr(home, "build_navbar", lambda **_kwargs: "")
    monkeypatch.setattr(home, "current_user", SimpleNamespace(is_authenticated=False))
    monkeypatch.setattr(
        home,
        "get_latest_ilga_document",
        lambda: {"year": 2026, "countries": [_country("ES", "Spain", 77.0)]},
    )
    monkeypatch.setattr(home, "get_ilga_years", lambda: [2026])

    with localized_route_context("en"):
        layout = home.build_home_layout()
    legal_section = next(
        component
        for component in _walk(layout)
        if getattr(component, "id", None) == "home-legal-section"
    )
    title = next(
        component
        for component in _walk(legal_section)
        if getattr(component, "className", None) == "home-ilga-detail-title"
    )
    visible_title = getattr(getattr(title, "children", None), "children", None)

    assert visible_title == "Legal situation by country in 2026"
    assert visible_title != "Situación legal por país en 2026"


def test_map_click_updates_only_legal_selector_by_iso(monkeypatch) -> None:
    app = _app(monkeypatch)
    legal_entry = _callback_entry(app, "update_home_legal_country_details")
    selection_entry = _callback_entry(app, "select_home_legal_country_from_map")
    selection_callback = selection_entry["callback"].__wrapped__
    selector = next(
        component
        for component in _walk(app.layout)
        if getattr(component, "id", None) == "home-legal-country-select"
    )
    all_click_inputs = [
        item
        for entry in app.callback_map.values()
        for item in entry["inputs"]
        if item["property"] == "clickData"
    ]

    initial, state = legal_entry["callback"].__wrapped__(None, "es")

    assert all_click_inputs == [{"id": "home-map-graph", "property": "clickData"}]
    assert (
        selection_callback(
            {"points": [{"customdata": ["ES", "Puntuación", "77%"]}]}, selector.options
        )
        == "ES"
    )
    assert (
        selection_callback(
            {"points": [{"customdata": ["FR", "Puntuación", "65%"]}]}, selector.options
        )
        == "FR"
    )
    assert "Selecciona un país" in str(initial)
    assert state["status"] == "INITIAL"
    assert {item["id"] for item in legal_entry["inputs"]} == {
        "home-legal-country-select",
        "app-language-store",
    }
    assert {item["id"] for item in selection_entry["inputs"]} == {"home-map-graph"}
    assert selection_entry["state"] == [{"id": "home-legal-country-select", "property": "options"}]
    assert selection_entry["output"].component_id == "home-legal-country-select"
    map_entry = _callback_entry(app, "update_home_map")
    assert all(output.component_id != "home-legal-country-select" for output in map_entry["output"])


@pytest.mark.parametrize(
    "click_data",
    [
        None,
        {},
        {"points": []},
        {"points": [{}]},
        {"points": [{"customdata": ["ZZ"]}]},
        {"points": [{"customdata": ["Spain"]}]},
    ],
)
def test_invalid_map_click_does_not_change_legal_selector(monkeypatch, click_data) -> None:
    app = _app(monkeypatch)
    selection_callback = _callback(app, "select_home_legal_country_from_map")
    selector = next(
        component
        for component in _walk(app.layout)
        if getattr(component, "id", None) == "home-legal-country-select"
    )

    with pytest.raises(PreventUpdate):
        selection_callback(click_data, selector.options)


def test_changing_legal_country_updates_only_detail_and_never_map(monkeypatch) -> None:
    countries = {
        "ES": _country("ES", "Spain", 77.0),
        "FR": _country("FR", "France", 65.0),
    }
    monkeypatch.setattr(home, "get_home_legal_country_detail", countries.get)
    app = _app(monkeypatch)
    legal_callback = _callback(app, "update_home_legal_country_details")
    map_entry = _callback_entry(app, "update_home_map")

    spain, spain_state = legal_callback("ES", "es")
    france, france_state = legal_callback("FR", "es")

    assert "España" in str(spain)
    assert "Francia" in str(france)
    assert spain_state["country_code"] == "ES"
    assert france_state["country_code"] == "FR"
    assert {item["id"] for item in map_entry["inputs"]} == {
        "home-map-year-select",
        "app-language-store",
    }


def test_legal_detail_reports_no_data_and_error_with_explicit_states(monkeypatch) -> None:
    app = _app(monkeypatch)
    callback = _callback(app, "update_home_legal_country_details")
    monkeypatch.setattr(home, "get_home_legal_country_detail", lambda _code: None)

    no_data, no_data_state = callback("MC", "es")

    def fail(_code: str):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(home, "get_home_legal_country_detail", fail)
    error, error_state = callback("ES", "en")

    assert "No hay información legal disponible para este país en 2026" in str(no_data)
    assert no_data_state["status"] == "NO_DATA"
    assert "legal information could not be loaded" in str(error)
    assert error_state["status"] == "ERROR"


def test_loading_is_scoped_to_legal_results_and_not_the_map(monkeypatch) -> None:
    app = _app(monkeypatch)
    loading = next(
        component
        for component in _walk(app.layout)
        if getattr(component, "id", None) == "home-legal-details-loading"
    )
    loading_ids = {
        component.id
        for component in _walk(loading)
        if isinstance(getattr(component, "id", None), str)
    }

    assert loading.target_components == {
        "home-legal-details": "children",
        "home-legal-country-status": "children",
    }
    assert "home-map-graph" not in loading_ids


def test_legal_container_css_covers_dark_theme_and_mobile_width() -> None:
    styles = Path("src/app/dash/assets/home.css").read_text(encoding="utf-8")

    assert 'body[data-theme="dark"] .home-legal-section' in styles
    assert 'body[data-theme="dark"] .home-legal-details-panel' in styles
    assert ".home-legal-country-dropdown," in styles
    assert "max-width: 100%;" in styles
    assert "@media (max-width: 760px)" in styles
    assert ".home-legal-country-control" in styles
    assert "max-width: none;" in styles
