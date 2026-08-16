from __future__ import annotations

from pathlib import Path
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


def _document() -> dict[str, Any]:
    return {
        "year": 2026,
        "countries": [
            {"country_code": "ES", "country": "Spain", "ranking": 78},
            {"country_code": "MT", "country": "Malta", "ranking": 89},
            {"country_code": "DE", "country": "Germany", "ranking": 67.5},
        ],
    }


def _app(monkeypatch) -> Dash:
    monkeypatch.setattr(home, "build_navbar", lambda **_kwargs: "")
    monkeypatch.setattr(home, "current_user", SimpleNamespace(is_authenticated=False))
    monkeypatch.setattr(home, "get_latest_ilga_document", _document)
    monkeypatch.setattr(home, "get_ilga_years", lambda: [2026])
    app = Dash("home-ranking-test", suppress_callback_exceptions=True)
    app.layout = home.build_home_layout()
    home.register_home_callbacks(app)
    return app


def test_home_places_one_accessible_ranking_beside_the_existing_map(monkeypatch) -> None:
    app = _app(monkeypatch)
    components = {
        component.id: component
        for component in _walk(app.layout)
        if isinstance(getattr(component, "id", None), str)
    }

    ranking = components["home-legal-ranking"]
    ranking_rows = [
        component
        for component in _walk(ranking)
        if getattr(component, "className", None) == "home-legal-ranking-row"
    ]

    assert len(ranking_rows) == 3
    assert "Malta" in str(ranking_rows[0])
    assert "89%" in str(ranking_rows[0])
    assert "Alemania" in str(ranking_rows[-1])
    assert components["home-map-export-button"].to_plotly_json()["props"]["aria-label"]
    assert components["home-map-graph"].figure.data


def test_map_and_ranking_share_one_document_query_and_translate_together(monkeypatch) -> None:
    app = _app(monkeypatch)
    calls: list[int | None] = []
    monkeypatch.setattr(
        home,
        "get_ilga_document_by_year",
        lambda year: calls.append(year) or _document(),
    )
    callback = _callback(app, "update_home_map")

    result = callback(2026, "en")

    assert calls == [2026]
    assert "Country ranking" in str(result[5])
    assert [row["country_name"] for row in result[6]] == ["Malta", "Spain", "Germany"]
    assert len(calls) == 1


def test_export_callback_reuses_map_and_ranking_state_without_a_database_query(
    monkeypatch,
) -> None:
    app = _app(monkeypatch)
    components = {
        component.id: component
        for component in _walk(app.layout)
        if isinstance(getattr(component, "id", None), str)
    }
    monkeypatch.setattr(home, "get_ilga_document_by_year", lambda _year: None)
    monkeypatch.setattr(home, "export_legal_map_png", lambda _figure: b"\x89PNG\r\n\x1a\n")
    callback = _callback(app, "download_home_legal_map")

    download, status, class_name = callback(
        {"theme": "dark", "request": 1},
        components["home-map-graph"].figure.to_dict(),
        components["home-legal-ranking-store"].data,
        2026,
        "es",
    )

    assert download["filename"] == "rainbowlens_ranking_legal_europa_2026.png"
    assert download["type"] == "image/png"
    assert status == ""
    assert class_name.endswith("is-hidden")

    callback_entry = next(
        entry
        for entry in app.callback_map.values()
        if getattr(entry.get("callback"), "__wrapped__", None)
        and entry["callback"].__wrapped__.__name__ == "download_home_legal_map"
    )
    assert callback_entry["inputs"] == [
        {"id": "home-map-export-request", "property": "data"}
    ]


def test_home_ranking_css_is_dark_mode_safe_and_stacks_below_the_map() -> None:
    css = Path("src/app/dash/assets/home.css").read_text(encoding="utf-8")

    assert "grid-template-columns: minmax(0, 2.35fr) minmax(240px, 0.85fr);" in css
    assert "@media (max-width: 1050px)" in css
    assert ".home-map-visual-grid {\n    grid-template-columns: minmax(0, 1fr);" in css
    assert 'body[data-theme="dark"] .home-legal-ranking' in css
    assert ".home-legal-ranking-list" in css
    assert "overflow-y: auto;" in css
