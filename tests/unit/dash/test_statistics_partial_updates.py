from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import plotly.graph_objects as go
from dash import Dash, no_update
from dash._utils import to_json

from app.modules.statistics import page as statistics


def _callback(app: Dash, name: str):
    return next(
        value["callback"].__wrapped__
        for value in app.callback_map.values()
        if getattr(value.get("callback"), "__wrapped__", None)
        and value["callback"].__wrapped__.__name__ == name
    )


def _result() -> dict:
    return {
        "status": "ok",
        "source": "ILGA-Europe",
        "indicator": "Asylum law",
        "year": 2026,
        "ranking": [
            {"country": "Spain", "iso": "ES", "value": 100.0},
            {"country": "France", "iso": "FR", "value": 0.0},
        ],
        "history": [],
    }


def test_complete_map_figure_updates_the_stable_graph_and_reveals_it() -> None:
    outputs: list[Any] = [no_update] * 33
    figure = go.Figure(go.Scattergeo(locations=["ES"]))
    outputs[2] = figure

    converted = statistics._dashboard_component_outputs(outputs)

    assert converted[2] is figure
    assert converted[3] == {"width": "100%"}
    assert all(output is no_update for index, output in enumerate(converted) if index not in {2, 3})


def test_partial_dashboard_update_does_not_touch_the_stable_map() -> None:
    converted = statistics._dashboard_component_outputs([no_update] * 33)

    assert converted[2] is no_update
    assert converted[3] is no_update


def test_hidden_temporal_and_average_panels_accept_missing_figures() -> None:
    """A hidden optional panel must not turn a valid dashboard into HTTP 500."""
    outputs: list[Any] = [no_update] * 33
    outputs[6] = None
    outputs[7] = "stats-panel-wrapper stats-temporal-wrapper is-hidden"
    outputs[9] = None
    outputs[10] = "stats-panel stats-average-panel is-hidden"

    converted = statistics._dashboard_component_outputs(outputs)

    assert converted[7] is None
    assert converted[8].endswith("is-hidden")
    assert converted[10] is None
    assert converted[11].endswith("is-hidden")


def test_main_statistics_callback_returns_complete_json_safe_contract(monkeypatch) -> None:
    app = Dash("statistics-full-callback-contract", suppress_callback_exceptions=True)
    statistics.register_statistics_callbacks(app)
    callback = _callback(app, "render_statistics")
    figure = go.Figure(go.Bar(x=["ES", "FR"], y=[0, None]))
    dashboard: list[Any] = [no_update] * 33
    dashboard[0:28] = [
        "ready",
        "stats-status stats-status-ok",
        figure,
        [],
        True,
        [],
        None,
        "stats-panel-wrapper stats-temporal-wrapper is-hidden",
        figure,
        None,
        "stats-panel stats-average-panel is-hidden",
        figure,
        "stats-panel",
        [],
        figure,
        {"width": "100%"},
        "stats-panel",
        [],
        None,
        "stats-panel is-hidden",
        None,
        "stats-panel is-hidden",
        [],
        None,
        "stats-analytics-block is-hidden",
        None,
        [{"field": "value"}],
        [{"country": "Spain", "value": 0}, {"country": "France", "value": None}],
    ]
    dashboard[28:33] = [{"width": "100%"}, {"width": "100%"}, False, "", "hidden"]
    monkeypatch.setattr(statistics, "ctx", SimpleNamespace(triggered_id="stats-data-store"))
    monkeypatch.setattr(statistics, "_render_dashboard", lambda *_args, **_kwargs: dashboard)

    returned = callback(
        {"status": "ok", "query_token": "q1"}, [], [], "es", 0, {"query_token": "q1"}
    )

    assert len(returned) == 32
    assert returned[7] is None
    assert returned[10] is None
    assert returned[27][0]["value"] == 0
    assert returned[27][1]["value"] is None
    assert returned[31] == {"query_token": "q1", "status": "ready"}
    assert to_json(returned)


def test_component_mapping_failure_finishes_in_error_state_instead_of_http_500(
    monkeypatch,
) -> None:
    app = Dash("statistics-callback-error-boundary", suppress_callback_exceptions=True)
    statistics.register_statistics_callbacks(app)
    callback = _callback(app, "render_statistics")
    monkeypatch.setattr(statistics, "ctx", SimpleNamespace(triggered_id="stats-data-store"))
    monkeypatch.setattr(statistics, "_render_dashboard", lambda *_args, **_kwargs: [None] * 33)
    monkeypatch.setattr(
        statistics,
        "_dashboard_component_outputs",
        lambda _outputs: (_ for _ in ()).throw(ValueError("invalid-output")),
    )

    # The callback boundary logs the traceback and returns a terminal ERROR state.
    returned = callback(
        {"status": "ok", "query_token": "q2"}, [], [], "es", 0, {"query_token": "q2"}
    )

    assert len(returned) == 32
    assert all(value is no_update for value in returned[:31])
    assert returned[31] == {"query_token": "q2", "status": "error"}


def test_map_country_selection_ignores_missing_click_data() -> None:
    result = statistics._next_country_selection(
        "stats-map-graph", click_data=None, data=None, current=[]
    )

    assert result is no_update


def test_map_country_selection_toggles_repeated_clicks() -> None:
    spain_click = {"points": [{"customdata": ["ES", "42 %"]}]}

    selected = statistics._next_country_selection(
        "stats-map-graph", click_data=spain_click, data=None, current=[]
    )
    deselected = statistics._next_country_selection(
        "stats-map-graph", click_data=spain_click, data=None, current=selected
    )

    assert selected == ["ES"]
    assert deselected == []


def test_map_country_selection_supports_multiple_countries_and_clear() -> None:
    france_click = {"points": [{"customdata": ["FR"]}]}

    selected = statistics._next_country_selection(
        "stats-map-graph", click_data=france_click, data=None, current=["ES"]
    )
    cleared = statistics._next_country_selection(
        "stats-clear-countries", click_data=None, data=None, current=selected
    )

    assert selected == ["ES", "FR"]
    assert cleared == []


def test_ranking_pagination_updates_only_ranking_outputs(monkeypatch) -> None:
    # Arrange
    ranking_figure = object()
    average_figure = object()
    monkeypatch.setattr(
        statistics, "build_comparative_ranking_chart", lambda *_args, **_kwargs: ranking_figure
    )
    monkeypatch.setattr(
        statistics, "build_eu_average_comparison_chart", lambda *_args, **_kwargs: average_figure
    )
    monkeypatch.setattr(statistics, "_ranking_graph_style", lambda _figure: {"display": "block"})
    monkeypatch.setattr(statistics, "_prepare_dashboard_exports", lambda *_args, **_kwargs: None)

    # Act
    outputs = statistics._render_ranking_dashboard_update(_result(), ["ES"], "es", 0)

    # Assert
    assert len(outputs) == 33
    assert outputs[8] is ranking_figure
    assert outputs[9] is average_figure
    assert "is-hidden" not in outputs[10]
    assert outputs[28] == {"display": "block"}
    assert all(
        output is no_update for index, output in enumerate(outputs) if index not in {8, 9, 10, 28}
    )


def test_temporal_selector_updates_only_temporal_outputs(monkeypatch) -> None:
    # Arrange
    temporal_figure = object()
    monkeypatch.setattr(
        statistics, "build_temporal_evolution_chart", lambda *_args, **_kwargs: temporal_figure
    )
    monkeypatch.setattr(statistics, "_prepare_dashboard_exports", lambda *_args, **_kwargs: None)

    # Act
    outputs = statistics._render_temporal_dashboard_update(_result(), ["ES"], "es", ["ES"])

    # Assert
    assert len(outputs) == 33
    assert outputs[6] is temporal_figure
    assert "stats-temporal-wrapper" in outputs[7]
    assert all(output is no_update for index, output in enumerate(outputs) if index not in {6, 7})


def test_browser_payload_drops_server_only_fra_intermediates() -> None:
    payload = statistics._browser_statistics_payload(
        {
            "status": "ok",
            "source": "FRA",
            "data": [{"large": "intermediate"}],
            "detail_data": [{"answer": "Yes"}],
            "ranking": [{"iso": "ES", "value": 42}],
            "metrics": {"mean": 42},
            "response_details_diagnostics": {"records_loaded": 1},
        }
    )

    assert "data" not in payload
    assert "metrics" not in payload
    assert "response_details_diagnostics" not in payload
    assert payload["detail_data"] == [{"answer": "Yes"}]


def test_dashboard_render_cache_is_bounded_to_an_exact_query_identity(monkeypatch) -> None:
    class Cache:
        app = object()

        def __init__(self) -> None:
            self.values: dict[str, Any] = {}
            self.calculations = 0

        def get_or_compute(self, key, factory, *, timeout):
            assert timeout == statistics.STATISTICS_DASHBOARD_CACHE_SECONDS
            if key not in self.values:
                self.calculations += 1
                self.values[key] = factory()
            return self.values[key]

    local_cache = Cache()
    renders: list[tuple[str, tuple[str, ...]]] = []
    monkeypatch.setattr(statistics, "cache", local_cache)
    monkeypatch.setattr(
        statistics,
        "_render_dashboard_uncached",
        lambda _result, selected, language, **_kwargs: (
            renders.append((language, tuple(selected))) or tuple(range(33))
        ),
    )
    result = {**_result(), "query_token": "survey:2023:indicator"}

    first = statistics._render_dashboard(result, [], "es")
    second = statistics._render_dashboard(result, [], "es")
    statistics._render_dashboard(result, ["ES"], "es")

    assert first == second
    assert local_cache.calculations == 2
    assert renders == [("es", ()), ("es", ("ES",))]
