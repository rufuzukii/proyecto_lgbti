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
        "_category_options",
        lambda _year, _language="es": (_ for _ in ()).throw(
            AssertionError("unexpected category query")
        ),
    )

    layout = statistics_page.build_statistics_layout()

    query_state = _component_by_id(layout, "stats-query-state")
    results = _component_by_id(layout, "stats-results-content")
    assert query_state is not None
    assert results is not None
    assert query_state.children is None
    assert "is-hidden" in query_state.className.split()
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
        "stats-dashboard-ready-store": "data",
        "stats-active-query-store": "data",
        "stats-survey-catalog-store": "data",
        "stats-indicator-catalog-store": "data",
    }
    graphs = [item for item in _walk(layout) if type(item).__name__ == "Graph"]
    assert [graph.id for graph in graphs] == ["stats-map-graph"]
    assert _component_by_id(layout, "stats-map-graph-slot") is not None
    assert _component_by_id(layout, "stats-map-ranking") is not None
    map_graph = cast(Any, _component_by_id(layout, "stats-map-graph"))
    map_props = map_graph.to_plotly_json()["props"]
    assert "figure" not in map_props
    assert map_props["style"] == {"width": "100%", "display": "none"}
    survey = cast(Any, _component_by_id(layout, "stats-survey-select"))
    assert survey.value == "fra_survey_iii"
    assert [option["value"] for option in survey.options] == [
        "fra_survey_iii",
        "fra_survey_ii",
    ]
    assert _component_by_id(layout, "stats-source-select") is None
    assert _component_by_id(layout, "stats-year-select") is None
    assert _component_by_id(layout, "ilga-criterion-select") is None


def test_statistics_header_places_fixed_guidance_before_report_action() -> None:
    rendered = str(statistics_page._header())

    title = "Estadísticas europeas LGBTIQ+"
    introduction = (
        "Explora la realidad sociodemográfica, la protección legal y la relación "
        "entre ambas."
    )
    instruction = (
        "Para generar una respuesta, selecciona una Categoría y un Indicador."
    )
    report_action = "stats-create-report-link"

    assert title in rendered
    assert introduction in rendered
    assert instruction in rendered
    assert "To generate a result, select a Category and an Indicator." in rendered
    assert rendered.index(title) < rendered.index(introduction)
    assert rendered.index(introduction) < rendered.index(instruction)
    assert rendered.index(instruction) < rendered.index(report_action)


def test_combined_visual_slots_are_available_in_the_initial_layout(
    monkeypatch,
) -> None:
    monkeypatch.setattr(statistics_page, "build_navbar", lambda **_kwargs: "")
    layout = statistics_page.build_statistics_layout()
    assert _component_by_id(layout, "stats-quadrant-graph-slot") is not None
    assert _component_by_id(layout, "stats-ranking-gap-graph-slot") is not None
    assert _component_by_id(layout, "stats-median-difference-graph-slot") is None
    assert _component_by_id(layout, "stats-combined-interpretation") is None


def test_ranked_reason_help_is_bilingual_and_absent_for_standard_questions() -> None:
    spanish = statistics_page._fra_response_help("ranked_reason", "es")
    english = statistics_page._fra_response_help("ranked_reason", "en")

    assert "¿Cómo interpretar estas respuestas?" in str(spanish)
    assert "primera razón en importancia" in str(spanish)
    assert "How should these responses be interpreted?" in str(english)
    assert "the most important reason" in str(english)
    assert statistics_page._fra_response_help("standard", "es") is None


def test_chart_help_and_ranked_reason_styles_cover_mobile_and_dark_mode() -> None:
    css = Path("src/app/dash/assets/statistics.css").read_text(encoding="utf-8")

    assert "grid-column: 1 / -1" in css
    assert ".stats-chart-horizontal-scroll" in css
    assert "overflow-x: auto" in css
    assert 'body[data-theme="dark"] .stats-response-help' in css
    assert ".stats-combined-chart-panel" in css
    assert "min-width: 620px" in css
    assert ".stats-availability-legend" not in css
    assert ".stats-response-distribution-item" in css
    assert "grid-template-columns: minmax(0, 1fr) auto" in css
    assert "white-space: nowrap" in css
    assert ".stats-european-average-reference" in css
    assert (
        "grid-template-columns: minmax(150px, 0.22fr) minmax(320px, 1fr) "
        "minmax(220px, 0.34fr)" in css
    )
    assert "grid-template-columns: repeat(2, minmax(0, 1fr));" in css
    assert "grid-auto-flow: column" in css
    assert ".stats-country-legend" in css


def test_disabled_statistics_filters_remain_legible_and_responsive() -> None:
    css = Path("src/app/dash/assets/statistics.css").read_text(encoding="utf-8")

    assert ".stats-controls .Select.is-disabled > .Select-control" in css
    assert "cursor: not-allowed" in css
    assert "opacity: 0.78" in css
    assert ".stats-segmentation-card.is-disabled" in css
    assert ".stats-segmentation-row.is-disabled" in css
    assert "background: color-mix(in srgb, var(--panel-muted)" in css
    mobile = css.split("@media (max-width: 767px)", maxsplit=1)[1]
    assert ".stats-indicator-card .stats-fra-controls" in mobile
    assert "grid-template-columns: 1fr" in mobile


def test_large_response_distribution_matches_the_compact_tablet_layout() -> None:
    css = Path("src/app/dash/assets/statistics.css").read_text(encoding="utf-8")
    desktop_rule = css.split("@media (min-width: 1200px)", maxsplit=1)[1].split(
        "@media (max-width: 767px)", maxsplit=1
    )[0]

    assert ".stats-response-distribution ul" in desktop_rule
    assert "grid-auto-flow: row" in desktop_rule
    assert "grid-template-columns: repeat(2, minmax(0, 1fr))" in desktop_rule
    assert ".stats-response-distribution-label" in desktop_rule
    assert ".stats-response-distribution-value" in desktop_rule
    assert "font-size: 0.84rem" in desktop_rule


def test_redundant_european_distribution_graph_is_absent(monkeypatch) -> None:
    monkeypatch.setattr(statistics_page, "build_navbar", lambda **_kwargs: "")
    layout = statistics_page.build_statistics_layout()

    assert _component_by_id(layout, "stats-distribution-graph") is None
    assert _component_by_id(layout, "stats-ranking-graph") is None
    assert _component_by_id(layout, "stats-ranking-graph-slot") is not None
    average_panel = cast(Any, _component_by_id(layout, "stats-average-panel"))
    assert "is-hidden" in average_panel.className.split()
    assert "is-hidden" in statistics_page._average_panel_class([]).split()
    assert "is-hidden" not in statistics_page._average_panel_class(["ES"]).split()


def test_statistics_distinguishes_initial_empty_and_ready_states() -> None:
    app = Dash("statistics-query-state-test", suppress_callback_exceptions=True)
    statistics_page.register_statistics_callbacks(app)
    callback = _callback(app, "update_statistics_query_state")

    initial = callback(None, None, None, None, None, "es")
    no_data = callback(
        {"status": "empty", "ranking": [], "data": []},
        None,
        None,
        "Education",
        "C9_E",
        "en",
    )
    error = callback(
        {"status": "error", "ranking": []}, None, None, "Education", "C9_E", "es"
    )
    ready = callback(
        {"status": "ok", "ranking": [{"value": 1}]},
        None,
        None,
        "Education",
        "C9_E",
        "es",
    )
    loading = callback(
        {"status": "ok", "query_token": "new", "ranking": [{"value": 1}]},
        {"query_token": "old"},
        {"query_token": "new"},
        "Education",
        "C9_E",
        "es",
    )

    assert initial[0] is None
    assert initial[1].endswith("is-hidden")
    assert initial[2].endswith("is-hidden")
    assert "No data is available for this selection." in str(no_data[0])
    assert no_data[1] == "stats-query-state"
    assert no_data[2].endswith("is-hidden")
    assert "No se han podido cargar las estadísticas." in str(error[0])
    assert error[2].endswith("is-hidden")
    assert ready[1].endswith("is-hidden")
    assert ready[2] == "stats-results-content"
    assert loading[1].endswith("is-hidden")
    assert loading[2].endswith("is-hidden")


def test_valid_indicator_never_returns_to_initial_while_new_result_is_pending() -> None:
    assert (
        resolve_statistics_view_state(
            None,
            None,
            {"phase": "initial"},
            category="Education",
            indicator="C9_E",
        )
        is StatisticsViewState.LOADING_STATISTICS
    )
    assert (
        resolve_statistics_view_state(
            {"status": "ok", "indicator_code": "OLD"},
            None,
            {"phase": "initial"},
            category="Education",
            indicator="C9_E",
        )
        is StatisticsViewState.LOADING_STATISTICS
    )


def test_statistics_view_states_are_explicit() -> None:
    assert resolve_statistics_view_state(None) is StatisticsViewState.INITIAL
    assert (
        resolve_statistics_view_state({"status": "loading_indicators"})
        is StatisticsViewState.LOADING_INDICATORS
    )
    assert (
        resolve_statistics_view_state(
            {"status": "ok", "query_token": "new"}, {"query_token": "old"}
        )
        is StatisticsViewState.LOADING_STATISTICS
    )
    assert (
        resolve_statistics_view_state(
            {"status": "empty", "query_token": "stale"},
            None,
            {"query_token": "current"},
        )
        is StatisticsViewState.LOADING_STATISTICS
    )
    assert resolve_statistics_view_state({"status": "ok"}) is StatisticsViewState.READY
    assert (
        resolve_statistics_view_state(None, None, {"phase": "survey_empty"})
        is StatisticsViewState.SURVEY_EMPTY
    )
    assert resolve_statistics_view_state({"status": "empty"}) is StatisticsViewState.NO_DATA
    assert resolve_statistics_view_state({"status": "invalid"}) is StatisticsViewState.NO_DATA
    assert resolve_statistics_view_state({"status": "error"}) is StatisticsViewState.ERROR
    assert (
        resolve_statistics_view_state(
            None,
            None,
            {"phase": "loading_indicators", "query_token": "category-change"},
        )
        is StatisticsViewState.LOADING_INDICATORS
    )
    assert (
        resolve_statistics_view_state(
            None,
            None,
            {"phase": "awaiting_indicator", "query_token": "category-ready"},
            category="Education",
            indicator=None,
        )
        is StatisticsViewState.AWAITING_INDICATOR
    )
    assert (
        resolve_statistics_view_state(
            None,
            None,
            {"phase": "initial"},
            category="Education",
            indicator=None,
        )
        is StatisticsViewState.LOADING_INDICATORS
    )


def test_indicator_catalog_prevents_initial_prompt_during_category_loading() -> None:
    source = Path("src/app/dash/pages/statistics.py").read_text(encoding="utf-8")

    assert 'id="stats-indicator-catalog-store"' in source
    assert "indicatorCatalogReady" in source
    assert source.index('phase = "loading_indicators"') < source.index(
        'phase = "initial"'
    )
    assert 'phase = "awaiting_indicator"' in source


def test_initial_statistics_selection_does_not_run_data_services(monkeypatch) -> None:
    app = Dash("statistics-query-guard-test", suppress_callback_exceptions=True)
    statistics_page.register_statistics_callbacks(app)
    callback = _callback(app, "load_statistics_data")

    def unexpected_query(*_args, **_kwargs):
        raise AssertionError("statistics service should not run without an indicator")

    monkeypatch.setattr(statistics_page, "get_fra_statistics", unexpected_query)
    monkeypatch.setattr(statistics_page, "get_combined_statistics_analysis", unexpected_query)

    result = callback("fra_survey_iii", None, None, None, None, None, None, None, {})

    assert result is None


def test_ready_indicator_controls_trigger_the_initial_statistics_query() -> None:
    app = Dash("statistics-control-trigger-test", suppress_callback_exceptions=True)
    statistics_page.register_statistics_callbacks(app)
    callback_registration = next(
        value
        for value in app.callback_map.values()
        if getattr(value.get("callback"), "__wrapped__", None)
        and value["callback"].__wrapped__.__name__ == "load_statistics_data"
    )

    input_ids = {item["id"] for item in callback_registration["inputs"]}
    state_ids = {item["id"] for item in callback_registration["state"]}

    assert "stats-fra-control-store" in input_ids
    assert "stats-fra-control-store" not in state_ids


def test_statistics_category_catalog_rejects_an_unknown_survey(monkeypatch) -> None:
    app = Dash("statistics-category-guard-test", suppress_callback_exceptions=True)
    statistics_page.register_statistics_callbacks(app)
    callback = _callback(app, "update_categories_for_survey")
    monkeypatch.setattr(
        statistics_page,
        "_category_options",
        lambda *_args: (_ for _ in ()).throw(AssertionError("unexpected category query")),
    )
    assert callback("unknown", "es", None) == (
        [],
        None,
        {"survey_id": "unknown", "loaded": True, "has_data": False},
    )


def test_changing_survey_resets_category_and_exposes_empty_catalog(monkeypatch) -> None:
    app = Dash("statistics-survey-reset-test", suppress_callback_exceptions=True)
    statistics_page.register_statistics_callbacks(app)
    callback = _callback(app, "update_categories_for_survey")
    monkeypatch.setattr(
        statistics_page,
        "ctx",
        type("Context", (), {"triggered_id": "stats-survey-select"})(),
    )
    monkeypatch.setattr(statistics_page, "_category_options", lambda _year, _language: [])

    assert callback("fra_survey_ii", "es", "Discrimination") == (
        [],
        None,
        {
            "survey_id": "fra_survey_ii",
            "year": 2019,
            "loaded": True,
            "has_data": False,
        },
    )

def test_statistics_dropdown_ids_are_unique_and_do_not_persist_stale_values(monkeypatch) -> None:
    monkeypatch.setattr(statistics_page, "build_navbar", lambda **_kwargs: "")
    layout = statistics_page.build_statistics_layout()
    dropdowns = [item for item in _walk(layout) if type(item).__name__ == "Dropdown"]
    ids = [item.id for item in dropdowns]

    assert not [component_id for component_id, count in Counter(ids).items() if count > 1]
    assert all(
        item.to_plotly_json()["props"].get("persistence") in {None, False} for item in dropdowns
    )


def test_critical_statistics_callback_ids_exist_once_in_page_layout(monkeypatch) -> None:
    monkeypatch.setattr(statistics_page, "build_navbar", lambda **_kwargs: "")
    layout = statistics_page.build_statistics_layout()
    ids = [
        item.id
        for item in _walk(layout)
        if isinstance(getattr(item, "id", None), str)
    ]
    counts = Counter(ids)

    assert counts["stats-map-graph"] == 1
    assert counts["stats-map-graph-slot"] == 1
    assert counts["stats-selected-countries"] == 1
    assert counts["stats-clear-countries"] == 1

    app = Dash("statistics-layout-contract", suppress_callback_exceptions=True)
    app.layout = layout
    statistics_page.register_statistics_callbacks(app)
    selection_callback = app.callback_map["stats-selected-countries.data"]
    selection_input_ids = {item["id"] for item in selection_callback["inputs"]}
    assert {
        "stats-map-graph",
        "stats-clear-countries",
        "stats-data-store",
    }.issubset(counts)
    assert selection_input_ids.issubset(counts)


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
        "fra_survey_iii",
        "Discrimination",
        "D1",
        "Yes",
        "All",
        "All",
        "All",
        "All",
        {"code": "D1", "category": "Discrimination"},
    )

    assert result["status"] == "empty"
    assert result["ranking"] == []
    assert result["data"] == []
    assert result["query_token"].startswith('["fra_survey_iii",2023')
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
        "fra_survey_iii",
        "Discrimination",
        "D1",
        "Yes",
        "All",
        "All",
        "All",
        "All",
        {"code": "D1", "category": "Discrimination"},
    )

    assert result["status"] == "error"
    assert result["ranking"] == []


def test_bathroom_school_indicator_reaches_a_terminal_state_without_unrelated_radar(
    monkeypatch,
) -> None:
    app = Dash("statistics-bathroom-indicator-regression", suppress_callback_exceptions=True)
    statistics_page.register_statistics_callbacks(app)
    callback = _callback(app, "load_statistics_data")
    monkeypatch.setattr(
        statistics_page,
        "ctx",
        type("Context", (), {"triggered_id": "stats-fra-control-store"})(),
    )
    monkeypatch.setattr(
        statistics_page,
        "get_fra_statistics",
        lambda query: {
            "status": "ok",
            "source": "FRA",
            "year": query.year,
            "indicator_code": query.question_code,
            "indicator": "Problems when going to bathroom and changing rooms at school",
            "answer": query.answer,
            "ranking": [{"country": "Spain", "iso": "ES", "value": 0}],
            "detail_data": [],
        },
    )
    monkeypatch.setattr(
        statistics_page,
        "get_combined_statistics_analysis",
        lambda *_args, **_kwargs: {"status": "ok", "rows": []},
    )

    result = callback(
        "fra_survey_iii",
        "Education",
        "C9_E",
        "Often",
        "All",
        "All",
        "All",
        "All",
        {"code": "C9_E", "category": "Education"},
    )

    assert result["status"] == "ok"
    assert result["indicator_code"] == "C9_E"
    assert result["ranking"][0]["value"] == 0
    assert "experience_legal_radar" not in result


def test_figure_failure_closes_loading_with_an_explicit_error_state(monkeypatch) -> None:
    app = Dash("statistics-render-error", suppress_callback_exceptions=True)
    statistics_page.register_statistics_callbacks(app)
    callback = _callback(app, "render_statistics")
    monkeypatch.setattr(
        statistics_page,
        "ctx",
        type("Context", (), {"triggered_id": "stats-data-store"})(),
    )
    monkeypatch.setattr(
        statistics_page,
        "_render_dashboard",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("invalid row")),
    )

    outputs = callback(
        {"status": "ok", "query_token": "C9_E", "indicator_code": "C9_E"},
        [],
        [],
        "es",
        0,
        {"query_token": "C9_E"},
    )

    assert outputs[-1] == {"query_token": "C9_E", "status": "error"}
    assert (
        resolve_statistics_view_state(
            {"status": "ok", "query_token": "C9_E"},
            outputs[-1],
            {"query_token": "C9_E"},
        )
        is StatisticsViewState.ERROR
    )


def test_statistics_loading_uses_spinner_only_without_message_callback(monkeypatch) -> None:
    monkeypatch.setattr(statistics_page, "assert_analytics_databases_available", lambda: None)
    monkeypatch.setattr(statistics_page, "build_navbar", lambda **_kwargs: "")
    layout = statistics_page.build_statistics_layout()
    loading = cast(Any, _component_by_id(layout, "stats-dashboard-loading"))
    spinner_children = loading.custom_spinner.children

    assert spinner_children[0].className == "context-loading-spinner"
    assert spinner_children[1].className == "sr-only"
    assert _component_by_id(layout, "stats-loading-message") is None

    app = Dash("statistics-loading-spinner-test", suppress_callback_exceptions=True)
    statistics_page.register_statistics_callbacks(app)
    callback_names = {
        value["callback"].__wrapped__.__name__
        for value in app.callback_map.values()
        if getattr(value.get("callback"), "__wrapped__", None)
    }
    assert "update_statistics_loading_message" not in callback_names
