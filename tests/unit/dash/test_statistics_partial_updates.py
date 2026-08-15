from __future__ import annotations

from typing import Any

import plotly.graph_objects as go
from dash import no_update

from app.dash.pages import statistics


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
    outputs: list[Any] = [no_update] * 29
    figure = go.Figure(go.Scattergeo(locations=["ES"]))
    outputs[2] = figure

    converted = statistics._dashboard_component_outputs(outputs)

    assert converted[2] is figure
    assert converted[3] == {"width": "100%"}
    assert all(output is no_update for index, output in enumerate(converted) if index not in {2, 3})


def test_partial_dashboard_update_does_not_touch_the_stable_map() -> None:
    converted = statistics._dashboard_component_outputs([no_update] * 29)

    assert converted[2] is no_update
    assert converted[3] is no_update


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
    assert len(outputs) == 29
    assert outputs[7] is ranking_figure
    assert outputs[8] is average_figure
    assert "is-hidden" not in outputs[9]
    assert outputs[24] == {"display": "block"}
    assert all(
        output is no_update for index, output in enumerate(outputs) if index not in {7, 8, 9, 24}
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
    assert len(outputs) == 29
    assert outputs[5] is temporal_figure
    assert "stats-temporal-wrapper" in outputs[6]
    assert all(output is no_update for index, output in enumerate(outputs) if index not in {5, 6})


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
