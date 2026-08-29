from __future__ import annotations

import statistics
import time
from pathlib import Path

from app.shared.data import geography_service
from app.shared.data.geography_service import (
    clear_geography_caches,
    europe_bounds,
    europe_centroids,
    europe_geojson,
    europe_view_bounds,
    load_europe_geodataframe,
    prepare_europe_map_data,
)


def test_europe_geometry_is_loaded_once_with_canonical_iso_codes() -> None:
    # Arrange
    clear_geography_caches()

    # Act
    first = load_europe_geodataframe()
    second = load_europe_geodataframe()

    # Assert
    assert first is second
    assert len(first) == 49
    assert first["country_code"].is_unique
    assert {"ES", "FR", "XK", "TR"}.issubset(first["country_code"])
    assert first.geometry.is_valid.all()
    assert not first.geometry.is_empty.any()
    assert first.total_bounds[0] >= -32
    assert first.total_bounds[2] <= 65


def test_geopandas_merge_keeps_countries_without_statistics_as_missing() -> None:
    # Arrange
    ranking = [
        {"country": "Spain", "iso": "ES", "value": 63.5},
        {"country": "France", "iso": "FRA", "value": None},
    ]

    # Act
    prepared = prepare_europe_map_data(ranking)
    rows = {row["country_code"]: row for row in prepared.rows}

    # Assert
    assert len(rows) == 49
    assert rows["ES"]["value"] == 63.5
    assert rows["FR"]["value"] is None
    assert rows["PT"]["value"] is None
    assert prepared.unmatched_codes == ()


def test_geography_metadata_and_geojson_are_cached_and_complete() -> None:
    # Arrange
    clear_geography_caches()

    # Act
    first_geojson = europe_geojson()
    second_geojson = europe_geojson()
    centroids = europe_centroids()
    bounds = europe_bounds()

    # Assert
    assert first_geojson is second_geojson
    assert len(first_geojson["features"]) == 49
    assert len(centroids) == 49
    assert bounds[0] < bounds[2]
    assert bounds[1] < bounds[3]
    path = Path("src/app/shared/data/resources/europe_countries.geojson")
    assert path.stat().st_size < 250_000
    assert all("country_code" in feature["properties"] for feature in first_geojson["features"])


def test_selected_country_bounds_gently_focus_and_reset_to_europe() -> None:
    europe = europe_view_bounds()
    spain = europe_view_bounds(["ES"])
    multiple = europe_view_bounds(["ES", "FR", "DE"])

    assert europe == europe_bounds()
    assert spain[2] - spain[0] < europe[2] - europe[0]
    assert spain[3] - spain[1] < europe[3] - europe[1]
    assert multiple[2] - multiple[0] < europe[2] - europe[0]
    assert europe_view_bounds([]) == europe


def test_warm_country_merge_has_a_non_fragile_performance_budget() -> None:
    # Arrange
    ranking = [
        {"country": f"Country {index}", "iso": code, "value": float(index)}
        for index, code in enumerate(("ES", "FR", "PT", "DE", "IT"), start=1)
    ]
    prepare_europe_map_data(ranking)

    # Act
    durations = []
    for _ in range(5):
        started_at = time.perf_counter()
        prepare_europe_map_data(ranking)
        durations.append((time.perf_counter() - started_at) * 1000)

    # Assert
    assert statistics.median(durations) < 500


def test_map_merge_does_not_load_geopandas_when_no_centroids_are_needed(monkeypatch) -> None:
    clear_geography_caches()
    monkeypatch.setattr(
        geography_service,
        "load_europe_geodataframe",
        lambda: (_ for _ in ()).throw(AssertionError("unexpected GeoPandas load")),
    )

    prepared = prepare_europe_map_data([{"country": "Spain", "iso": "ES", "value": 5}])

    assert len(prepared.rows) == 49
    assert next(row for row in prepared.rows if row["country_code"] == "ES")["value"] == 5
