from __future__ import annotations

from dash import Dash

import app.dash.pages.statistics as statistics_page


def _walk(component):
    if component is None:
        return
    if isinstance(component, (list, tuple)):
        for item in component:
            yield from _walk(item)
        return
    yield component
    children = getattr(component, "children", None)
    if children is not None:
        yield from _walk(children)


def _component_by_id(component, component_id: str):
    return next(
        (item for item in _walk(component) if getattr(item, "id", None) == component_id),
        None,
    )


def _callback(app: Dash, name: str):
    return next(
        value["callback"].__wrapped__
        for value in app.callback_map.values()
        if getattr(value.get("callback"), "__wrapped__", None)
        and value["callback"].__wrapped__.__name__ == name
    )


def test_statistics_layout_defers_catalog_queries_and_hides_results(monkeypatch) -> None:
    monkeypatch.setattr(statistics_page, "assert_analytics_databases_available", lambda: None)
    monkeypatch.setattr(statistics_page, "build_navbar", lambda **_kwargs: "")
    monkeypatch.setattr(
        statistics_page,
        "_year_options",
        lambda _source: (_ for _ in ()).throw(AssertionError("unexpected year query")),
    )
    monkeypatch.setattr(
        statistics_page,
        "_category_options",
        lambda _source, _year: (_ for _ in ()).throw(AssertionError("unexpected category query")),
    )

    layout = statistics_page.build_statistics_layout()

    query_state = _component_by_id(layout, "stats-query-state")
    results = _component_by_id(layout, "stats-results-content")
    assert query_state is not None
    assert results is not None
    assert "Selecciona una categoría y un indicador para comenzar." in str(query_state)
    assert "is-hidden" in results.className.split()


def test_statistics_distinguishes_initial_empty_and_ready_states() -> None:
    app = Dash("statistics-query-state-test", suppress_callback_exceptions=True)
    statistics_page.register_statistics_callbacks(app)
    callback = _callback(app, "update_statistics_query_state")

    initial = callback(None, "es")
    no_data = callback({"status": "empty", "ranking": [], "data": []}, "en")
    ready = callback({"status": "ok", "ranking": [{"value": 1}]}, "es")

    assert "Selecciona una categoría y un indicador para comenzar." in str(initial[0])
    assert initial[1] == "stats-query-state"
    assert initial[2].endswith("is-hidden")
    assert "No data is available for this selection." in str(no_data[0])
    assert no_data[1] == "stats-query-state"
    assert no_data[2].endswith("is-hidden")
    assert ready[1].endswith("is-hidden")
    assert ready[2] == "stats-results-content"


def test_initial_statistics_selection_does_not_run_data_services(monkeypatch) -> None:
    app = Dash("statistics-query-guard-test", suppress_callback_exceptions=True)
    statistics_page.register_statistics_callbacks(app)
    callback = _callback(app, "load_statistics_data")

    def unexpected_query(*_args, **_kwargs):
        raise AssertionError("statistics service should not run without an indicator")

    monkeypatch.setattr(statistics_page, "get_fra_statistics", unexpected_query)
    monkeypatch.setattr(statistics_page, "get_ilga_statistics", unexpected_query)

    result = callback("fra", 2024, None, None, None, None, None, None, None, None, {})

    assert result is None


def test_statistics_category_catalog_waits_for_a_year(monkeypatch) -> None:
    app = Dash("statistics-category-guard-test", suppress_callback_exceptions=True)
    statistics_page.register_statistics_callbacks(app)
    callback = _callback(app, "update_categories_for_year")
    monkeypatch.setattr(
        statistics_page,
        "_category_options",
        lambda *_args: (_ for _ in ()).throw(AssertionError("unexpected category query")),
    )

    assert callback("fra", None, None) == ([], None)


def test_valid_statistics_selection_preserves_real_no_data_state(monkeypatch) -> None:
    app = Dash("statistics-no-data-test", suppress_callback_exceptions=True)
    statistics_page.register_statistics_callbacks(app)
    callback = _callback(app, "load_statistics_data")
    calls = []
    monkeypatch.setattr(statistics_page, "ctx", type("Context", (), {"triggered_id": "fra-answer-select"})())
    monkeypatch.setattr(
        statistics_page,
        "get_fra_statistics",
        lambda query: calls.append(query) or {"status": "empty", "ranking": [], "data": []},
    )

    result = callback(
        "fra",
        2024,
        "Discrimination",
        "D1",
        "Yes",
        "All",
        "All",
        "All",
        "All",
        None,
        {"code": "D1", "category": "Discrimination"},
    )

    assert result == {"status": "empty", "ranking": [], "data": []}
    assert len(calls) == 1
