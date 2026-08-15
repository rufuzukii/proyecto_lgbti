from __future__ import annotations

from pathlib import Path

from dash import Dash

from app.dash.pages import statistics as statistics_page


def _walk(component):
    if component is None:
        return
    if isinstance(component, (list, tuple)):
        for item in component:
            yield from _walk(item)
        return
    yield component
    yield from _walk(getattr(component, "children", None))


def _callback(app: Dash, name: str):
    return next(
        value["callback"].__wrapped__
        for value in app.callback_map.values()
        if getattr(value.get("callback"), "__wrapped__", None)
        and value["callback"].__wrapped__.__name__ == name
    )


def test_initial_category_and_ready_lifecycle_never_exposes_plotly_placeholders(
    monkeypatch,
) -> None:
    monkeypatch.setattr(statistics_page, "assert_analytics_databases_available", lambda: None)
    monkeypatch.setattr(statistics_page, "build_navbar", lambda **_kwargs: "")
    layout = statistics_page.build_statistics_layout()
    graphs = [component for component in _walk(layout) if type(component).__name__ == "Graph"]
    component_ids = {
        component_id
        for component in _walk(layout)
        if isinstance((component_id := getattr(component, "id", None)), str)
    }

    assert [graph.id for graph in graphs] == ["stats-map-graph"]
    assert "stats-map-graph-slot" in component_ids
    assert "stats-map-graph" in component_ids
    map_graph = next(graph for graph in graphs if graph.id == "stats-map-graph")
    map_props = map_graph.to_plotly_json()["props"]
    assert "figure" not in map_props
    assert map_props["style"]["display"] == "none"

    app = Dash("statistics-render-lifecycle-e2e", suppress_callback_exceptions=True)
    statistics_page.register_statistics_callbacks(app)
    query_state = _callback(app, "update_statistics_query_state")

    initial = query_state(None, None, None, "es")
    loading_indicators = query_state(
        None,
        None,
        {"query_token": "category-a", "phase": "loading_indicators"},
        "es",
    )
    stale = query_state(
        {"status": "ok", "query_token": "category-a"},
        {"query_token": "category-a"},
        {"query_token": "category-b"},
        "es",
    )
    rendering = query_state(
        {"status": "ok", "query_token": "category-b"},
        {"query_token": "category-a"},
        {"query_token": "category-b"},
        "es",
    )
    ready = query_state(
        {"status": "ok", "query_token": "category-b"},
        {"query_token": "category-b"},
        {"query_token": "category-b"},
        "es",
    )

    assert initial[2].endswith("is-hidden")
    assert loading_indicators[1].endswith("is-hidden")
    assert loading_indicators[2].endswith("is-hidden")
    assert "Selecciona una categoría" not in str(loading_indicators[0])
    assert stale[2].endswith("is-hidden")
    assert rendering[2].endswith("is-hidden")
    assert ready[2] == "stats-results-content"


def test_theme_relayout_guard_prevents_the_known_preinitialization_warning() -> None:
    source = Path("src/app/dash/assets/js/20_theme.js").read_text(encoding="utf-8")

    assert "if (!isPlotlyInitialized(graph))" in source
    assert "graph._fullLayout" in source
    assert "graph.data.length > 0" in source
    assert "Plotly.redraw" not in source
    assert "Plotly.react" not in source


def test_statistics_callbacks_update_the_stable_interactive_map() -> None:
    source = Path("src/app/dash/pages/statistics.py").read_text(encoding="utf-8")

    assert 'Output("stats-map-graph-slot", "children")' not in source
    assert 'Output("stats-map-graph", "figure")' in source
    assert 'Output("stats-map-graph", "style")' in source
    assert "statistics_graph_panels_must_defer_plotly_mounting" in source


def test_map_click_dependency_always_targets_the_stable_page_component(monkeypatch) -> None:
    monkeypatch.setattr(statistics_page, "assert_analytics_databases_available", lambda: None)
    monkeypatch.setattr(statistics_page, "build_navbar", lambda **_kwargs: "")
    layout = statistics_page.build_statistics_layout()
    ids = [
        component.id
        for component in _walk(layout)
        if isinstance(getattr(component, "id", None), str)
    ]
    app = Dash("statistics-map-dependency-e2e", suppress_callback_exceptions=True)
    app.layout = layout
    statistics_page.register_statistics_callbacks(app)

    selection_callback = app.callback_map["stats-selected-countries.data"]
    click_inputs = [
        item
        for item in selection_callback["inputs"]
        if item["property"] in {"clickData", "hoverData", "selectedData", "relayoutData"}
    ]

    assert click_inputs == [{"id": "stats-map-graph", "property": "clickData"}]
    assert ids.count("stats-map-graph") == 1
    assert ids.count("stats-map-graph-slot") == 1
