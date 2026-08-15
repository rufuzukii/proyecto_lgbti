from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from dash import Dash

from app.dash.layouts import home


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


def _country(code: str, name: str, score: float) -> dict[str, Any]:
    return {
        "country": name,
        "country_code": code,
        "ranking": score,
        "criteria": [
            {
                "category": "Family",
                "indicator": "Marriage equality",
                "weight": 1,
                "value": 1,
            }
        ],
    }


def test_home_map_and_2026_legal_detail_complete_independent_flow(monkeypatch) -> None:
    countries = {
        "ES": _country("ES", "Spain", 77.0),
        "FR": _country("FR", "France", 65.0),
        "DE": _country("DE", "Germany", 69.0),
    }
    document = {"year": 2026, "countries": list(countries.values())}
    monkeypatch.setattr(home, "build_navbar", lambda **_kwargs: "")
    monkeypatch.setattr(home, "current_user", SimpleNamespace(is_authenticated=False))
    monkeypatch.setattr(home, "get_latest_ilga_document", lambda: document)
    monkeypatch.setattr(home, "get_ilga_years", lambda: [2026])
    monkeypatch.setattr(home, "get_home_legal_country_detail", countries.get)

    app = Dash("home-legal-e2e", suppress_callback_exceptions=True)
    app.layout = home.build_home_layout()
    home.register_home_callbacks(app)
    components = {
        component.id: component
        for component in _walk(app.layout)
        if isinstance(getattr(component, "id", None), str)
    }
    details = _callback(app, "update_home_legal_country_details")
    select_from_map = _callback(app, "select_home_legal_country_from_map")

    initial, initial_state = details(None, "es")
    spain_code = select_from_map(
        {"points": [{"customdata": ["ES", "Puntuación", "77%"]}]},
        components["home-legal-country-select"].options,
    )
    spain, spain_state = details(spain_code, "es")
    france_code = select_from_map(
        {"points": [{"customdata": ["FR", "Puntuación", "65%"]}]},
        components["home-legal-country-select"].options,
    )
    france, france_state = details(france_code, "es")
    germany, germany_state = details("DE", "es")

    assert components["home-map-graph"].figure.data
    assert components["home-legal-country-select"].value is None
    assert "Situación legal por país en 2026" in str(components["home-legal-section"])
    assert "Selecciona un país" in str(initial)
    assert initial_state["status"] == "INITIAL"
    assert "España" in str(spain)
    assert spain_state["country_code"] == "ES"
    assert "Francia" in str(france)
    assert france_state["country_code"] == "FR"
    assert "Alemania" in str(germany)
    assert germany_state["country_code"] == "DE"
    click_inputs = [
        item
        for entry in app.callback_map.values()
        for item in entry["inputs"]
        if item["property"] == "clickData"
    ]
    assert click_inputs == [{"id": "home-map-graph", "property": "clickData"}]
    assert {item["id"] for item in _callback_entry(app, "update_home_map")["inputs"]} == {
        "home-map-year-select",
        "app-language-store",
    }
    assert components["home-legal-details-loading"].target_components == {
        "home-legal-details": "children",
        "home-legal-country-status": "children",
    }
