from __future__ import annotations

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


def test_map_selection_patch_does_not_resend_geojson() -> None:
    # Arrange
    figure = go.Figure(
        [
            go.Choropleth(
                geojson={"type": "FeatureCollection", "features": []},
                locations=["ES"],
                z=[1],
            ),
            go.Scattergeo(lat=[40.0], lon=[-3.0], text=["España"], customdata=[["ES"]]),
        ]
    )

    # Act
    payload = statistics._map_selection_patch(figure).to_plotly_json()

    # Assert
    locations = [operation["location"] for operation in payload["operations"]]
    assert locations == [
        ["data", 1, "lat"],
        ["data", 1, "lon"],
        ["data", 1, "text"],
        ["data", 1, "customdata"],
    ]
    assert "geojson" not in str(payload)


def test_map_data_patch_updates_values_without_resending_static_geometry() -> None:
    # Arrange
    geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"country_code": "ES"},
                "geometry": {"type": "Polygon", "coordinates": []},
            }
        ],
    }
    figure = go.Figure(
        [
            go.Choropleth(
                geojson=geojson,
                featureidkey="properties.country_code",
                locations=["ES"],
                z=[72],
            ),
            go.Scattergeo(lat=[], lon=[], text=[], customdata=[]),
        ]
    )

    # Act
    payload = statistics._map_data_patch(figure).to_plotly_json()

    # Assert
    assert statistics._map_contains_static_geojson({"data": [{"geojson": geojson}]})
    assert any(operation["location"] == ["data", 0, "z"] for operation in payload["operations"])
    assert "geojson" not in str(payload)


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
    assert outputs[9] is average_figure
    assert outputs[24] == {"display": "block"}
    assert all(
        output is no_update for index, output in enumerate(outputs) if index not in {7, 9, 24}
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
