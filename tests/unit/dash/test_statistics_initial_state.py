from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any, cast

from dash import Dash, dcc

import app.dash.pages.statistics as statistics_page
from app.dash.statistics_state import StatisticsViewState, resolve_statistics_view_state


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

    loading = cast(Any, _component_by_id(layout, "stats-dashboard-loading"))
    store = _component_by_id(loading, "stats-data-store")
    assert isinstance(loading, dcc.Loading)
    loading_props = cast(Any, loading.to_plotly_json()["props"])
    assert store is not None
    assert loading_props["delay_show"] == 200
    assert loading_props["overlay_style"] == {"visibility": "hidden"}
    assert loading_props["target_components"] == {
        "stats-data-store": "data",
        "stats-map-graph": "figure",
    }
    graphs = [item for item in _walk(layout) if type(item).__name__ == "Graph"]
    assert graphs
    assert all(item.figure == {} for item in graphs)


def test_heatmap_spans_the_grid_and_uses_a_local_responsive_scroll_container(
    monkeypatch,
) -> None:
    monkeypatch.setattr(statistics_page, "build_navbar", lambda **_kwargs: "")
    layout = statistics_page.build_statistics_layout()
    heatmap = _component_by_id(layout, "stats-combined-heatmap")
    panel = next(
        item
        for item in _walk(layout)
        if "stats-heatmap-panel" in str(getattr(item, "className", ""))
    )

    assert heatmap is not None
    assert "stats-panel-wide" in panel.className.split()
    assert "stats-chart-horizontal-scroll" in str(panel)


def test_ranked_reason_help_is_bilingual_and_absent_for_standard_questions() -> None:
    spanish = statistics_page._fra_response_help("ranked_reason", "es")
    english = statistics_page._fra_response_help("ranked_reason", "en")

    assert "¿Cómo interpretar estas respuestas?" in str(spanish)
    assert "primera razón en importancia" in str(spanish)
    assert "How should these responses be interpreted?" in str(english)
    assert "the most important reason" in str(english)
    assert statistics_page._fra_response_help("standard", "es") is None


def test_heatmap_and_ranked_reason_styles_cover_mobile_and_dark_mode() -> None:
    css = Path("src/app/dash/assets/statistics.css").read_text(encoding="utf-8")

    assert ".stats-heatmap-panel" in css
    assert "grid-column: 1 / -1" in css
    assert ".stats-chart-horizontal-scroll" in css
    assert "overflow-x: auto" in css
    assert "body[data-theme=\"dark\"] .stats-response-help" in css
    assert "min-width: 680px" in css


def test_statistics_distinguishes_initial_empty_and_ready_states() -> None:
    app = Dash("statistics-query-state-test", suppress_callback_exceptions=True)
    statistics_page.register_statistics_callbacks(app)
    callback = _callback(app, "update_statistics_query_state")

    initial = callback(None, "es")
    no_data = callback({"status": "empty", "ranking": [], "data": []}, "en")
    error = callback({"status": "error", "ranking": []}, "es")
    ready = callback({"status": "ok", "ranking": [{"value": 1}]}, "es")

    assert "Selecciona una categoría y un indicador para comenzar." in str(initial[0])
    assert initial[1] == "stats-query-state"
    assert initial[2].endswith("is-hidden")
    assert "No data is available for this selection." in str(no_data[0])
    assert no_data[1] == "stats-query-state"
    assert no_data[2].endswith("is-hidden")
    assert "No se han podido cargar las estadísticas." in str(error[0])
    assert error[2].endswith("is-hidden")
    assert ready[1].endswith("is-hidden")
    assert ready[2] == "stats-results-content"


def test_statistics_view_states_are_explicit() -> None:
    assert resolve_statistics_view_state(None) is StatisticsViewState.INITIAL
    assert resolve_statistics_view_state({"status": "ok"}) is StatisticsViewState.READY
    assert resolve_statistics_view_state({"status": "empty"}) is StatisticsViewState.NO_DATA
    assert resolve_statistics_view_state({"status": "invalid"}) is StatisticsViewState.NO_DATA
    assert resolve_statistics_view_state({"status": "error"}) is StatisticsViewState.ERROR


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

    assert callback("fra", None, "es", None) == ([], None)


def test_statistics_dropdown_ids_are_unique_and_do_not_persist_stale_values(monkeypatch) -> None:
    monkeypatch.setattr(statistics_page, "build_navbar", lambda **_kwargs: "")
    layout = statistics_page.build_statistics_layout()
    dropdowns = [item for item in _walk(layout) if type(item).__name__ == "Dropdown"]
    ids = [item.id for item in dropdowns]

    assert not [component_id for component_id, count in Counter(ids).items() if count > 1]
    assert all(
        item.to_plotly_json()["props"].get("persistence") in {None, False} for item in dropdowns
    )


def test_valid_statistics_selection_preserves_real_no_data_state(monkeypatch) -> None:
    app = Dash("statistics-no-data-test", suppress_callback_exceptions=True)
    statistics_page.register_statistics_callbacks(app)
    callback = _callback(app, "load_statistics_data")
    calls = []
    monkeypatch.setattr(
        statistics_page, "ctx", type("Context", (), {"triggered_id": "fra-answer-select"})()
    )
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


def test_statistics_service_failure_becomes_controlled_error_state(monkeypatch) -> None:
    app = Dash("statistics-error-test", suppress_callback_exceptions=True)
    statistics_page.register_statistics_callbacks(app)
    callback = _callback(app, "load_statistics_data")
    monkeypatch.setattr(
        statistics_page,
        "ctx",
        type("Context", (), {"triggered_id": "fra-answer-select"})(),
    )
    monkeypatch.setattr(
        statistics_page,
        "get_fra_statistics",
        lambda _query: (_ for _ in ()).throw(RuntimeError("database unavailable")),
    )

    result = callback(
        "fra",
        2023,
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

    assert result["status"] == "error"
    assert result["ranking"] == []


def test_statistics_loading_message_tracks_the_refresh_phase(monkeypatch) -> None:
    app = Dash("statistics-loading-message-test", suppress_callback_exceptions=True)
    statistics_page.register_statistics_callbacks(app)
    callback = _callback(app, "update_statistics_loading_message")
    monkeypatch.setattr(
        statistics_page,
        "ctx",
        type("Context", (), {"triggered_id": "stats-category-select"})(),
    )

    message = callback(None, None, None, None, None, None, None, None, "es")

    assert "Cargando indicadores..." in str(message)
