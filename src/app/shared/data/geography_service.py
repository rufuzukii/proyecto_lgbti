from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from functools import lru_cache
from importlib.resources import files
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import pandas as pd
from shapely.geometry import Point

from app.shared.data.fra_metadata import classify_fra_country_state
from app.shared.data.geography import ISO2_TO_ISO3
from app.shared.data.normalization import normalize_country_code

if TYPE_CHECKING:
    import geopandas as gpd

logger = logging.getLogger(__name__)

REQUIRED_GEOGRAPHY_COLUMNS = {"country_code", "iso3", "name_en", "geometry"}


@dataclass(frozen=True)
class EuropeMapData:
    rows: list[dict[str, Any]]
    geojson: dict[str, Any]
    merge_ms: float
    unmatched_codes: tuple[str, ...]


def _geometry_path() -> Path:
    return Path(str(files("app.shared.data").joinpath("resources/europe_countries.geojson")))


@lru_cache(maxsize=1)
def load_europe_geodataframe() -> gpd.GeoDataFrame:
    """Load and validate the canonical Europe geometry once in each process."""
    import geopandas as gpd

    started_at = time.perf_counter()
    dataframe = gpd.read_file(_geometry_path())
    missing = REQUIRED_GEOGRAPHY_COLUMNS.difference(dataframe.columns)
    if missing:
        raise ValueError(f"Europe geometry is missing columns: {sorted(missing)}")
    dataframe = dataframe[list(REQUIRED_GEOGRAPHY_COLUMNS)].copy()
    dataframe["country_code"] = dataframe["country_code"].astype(str).str.strip().str.upper()
    dataframe["iso3"] = dataframe["iso3"].astype(str).str.strip().str.upper()
    if dataframe["country_code"].duplicated().any():
        raise ValueError("Europe geometry contains duplicated country codes")
    if dataframe.geometry.is_empty.any() or not dataframe.geometry.is_valid.all():
        raise ValueError("Europe geometry contains empty or invalid geometries")
    logger.info(
        "europe_geometry_loaded countries=%d bytes=%d load_ms=%.2f",
        len(dataframe),
        _geometry_path().stat().st_size,
        (time.perf_counter() - started_at) * 1000,
    )
    return dataframe


@lru_cache(maxsize=1)
def europe_geojson() -> dict[str, Any]:
    """Return the static, optimized GeoJSON without serializing it per callback."""
    return json.loads(_geometry_path().read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def europe_country_catalog() -> tuple[dict[str, str], ...]:
    """Return lightweight static country metadata without loading GeoPandas.

    The choropleth only needs geometry in GeoJSON form.  Keeping the country
    catalogue separate avoids reading and merging a GeoDataFrame on the first
    statistics request; GeoPandas remains lazy for centroid-only interactions.
    """
    rows: list[dict[str, str]] = []
    for feature in europe_geojson().get("features", []):
        properties = feature.get("properties") if isinstance(feature, dict) else None
        if not isinstance(properties, dict):
            continue
        country_code = str(properties.get("country_code") or "").strip().upper()
        iso3 = str(properties.get("iso3") or "").strip().upper()
        name_en = str(properties.get("name_en") or "").strip()
        if not country_code or not iso3 or not name_en:
            raise ValueError("Europe GeoJSON contains incomplete country metadata")
        rows.append({"country_code": country_code, "iso3": iso3, "name_en": name_en})
    if len(rows) != len({row["country_code"] for row in rows}):
        raise ValueError("Europe GeoJSON contains duplicated country codes")
    return tuple(rows)


@lru_cache(maxsize=1)
def europe_bounds() -> tuple[float, float, float, float]:
    minimum_x, minimum_y, maximum_x, maximum_y = load_europe_geodataframe().total_bounds
    return float(minimum_x), float(minimum_y), float(maximum_x), float(maximum_y)


def europe_view_bounds(
    selected_country_codes: tuple[str, ...] | list[str] | None = None,
) -> tuple[float, float, float, float]:
    """Return the European extent, gently focused on selected countries."""
    base = europe_bounds()
    selected = {
        normalize_country_code(code) or str(code or "").strip().upper()
        for code in (selected_country_codes or [])
        if str(code or "").strip()
    }
    if not selected:
        return base

    frame = load_europe_geodataframe()
    focus = frame[frame["country_code"].isin(selected)]
    if focus.empty:
        return base
    minimum_x, minimum_y, maximum_x, maximum_y = map(float, focus.total_bounds)
    width = max(maximum_x - minimum_x, 1.0)
    height = max(maximum_y - minimum_y, 1.0)
    padded = (
        minimum_x - width * 0.22,
        minimum_y - height * 0.22,
        maximum_x + width * 0.22,
        maximum_y + height * 0.22,
    )
    focus_weight = 0.42 if len(focus) == 1 else 0.36
    blended = tuple(
        base_value + (focus_value - base_value) * focus_weight
        for base_value, focus_value in zip(base, padded, strict=True)
    )
    return cast(tuple[float, float, float, float], blended)


@lru_cache(maxsize=1)
def europe_centroids() -> dict[str, tuple[float, float]]:
    """Calculate stable in-country marker points once in a projected CRS."""
    frame = load_europe_geodataframe()
    projected = frame.to_crs("EPSG:3035")
    points = projected.geometry.representative_point().to_crs("EPSG:4326")
    return {
        str(country_code): (
            float(cast(Point, point).y),
            float(cast(Point, point).x),
        )
        for country_code, point in zip(frame["country_code"], points, strict=True)
    }


def prepare_europe_map_data(
    ranking_rows: list[dict[str, Any]],
    *,
    fra_survey_year: int | None = None,
) -> EuropeMapData:
    """Left-join statistics onto every canonical European country using ISO codes."""
    started_at = time.perf_counter()
    iso3_to_iso2 = {iso3: iso2 for iso2, iso3 in ISO2_TO_ISO3.items()}
    statistics_by_code: dict[str, dict[str, Any]] = {}
    requested_codes: set[str] = set()
    for raw_row in ranking_rows:
        if not isinstance(raw_row, dict):
            continue
        country = str(raw_row.get("country") or "").strip()
        code = normalize_country_code(raw_row.get("iso") or raw_row.get("country_code"), country)
        code = iso3_to_iso2.get(code, code)
        if not code:
            continue
        requested_codes.add(code)
        if code in ISO2_TO_ISO3:
            statistics_by_code[code] = {
                "country": country,
                "value": raw_row.get("value"),
            }
    unmatched_codes = tuple(sorted(requested_codes.difference(ISO2_TO_ISO3)))
    rows: list[dict[str, Any]] = []
    for country in europe_country_catalog():
        statistics = statistics_by_code.get(country["country_code"], {})
        value = statistics.get("value")
        if pd.isna(value):
            value = None
        survey_state = classify_fra_country_state(
            country["country_code"],
            value is not None,
            survey_year=fra_survey_year,
        )
        rows.append(
            {
                **country,
                "country": statistics.get("country") or country["name_en"],
                "value": value,
                "survey_state": survey_state.value,
            }
        )
    merge_ms = (time.perf_counter() - started_at) * 1000
    with_data = sum(row["value"] is not None for row in rows)
    logger.info(
        "geodata_merge_completed countries=%d with_data=%d without_data=%d merge_ms=%.2f",
        len(rows),
        with_data,
        len(rows) - with_data,
        merge_ms,
    )
    return EuropeMapData(
        rows=rows,
        geojson=europe_geojson(),
        merge_ms=merge_ms,
        unmatched_codes=unmatched_codes,
    )


def clear_geography_caches() -> None:
    load_europe_geodataframe.cache_clear()
    europe_geojson.cache_clear()
    europe_country_catalog.cache_clear()
    europe_bounds.cache_clear()
    europe_centroids.cache_clear()
