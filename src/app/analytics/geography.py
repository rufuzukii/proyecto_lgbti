from __future__ import annotations

from typing import Any

import geopandas as gpd
from shapely.geometry import Point


EUROPE_CENTROIDS: dict[str, tuple[float, float]] = {
    "AL": (41.15, 20.17),
    "AD": (42.51, 1.52),
    "AM": (40.07, 45.04),
    "AT": (47.52, 14.55),
    "AZ": (40.14, 47.58),
    "BY": (53.71, 27.95),
    "BE": (50.50, 4.47),
    "BA": (43.92, 17.68),
    "BG": (42.73, 25.49),
    "HR": (45.10, 15.20),
    "CY": (35.13, 33.43),
    "CZ": (49.82, 15.47),
    "DK": (56.26, 9.50),
    "EE": (58.60, 25.01),
    "FI": (61.92, 25.75),
    "FR": (46.23, 2.21),
    "GE": (42.32, 43.36),
    "DE": (51.17, 10.45),
    "GR": (39.07, 21.82),
    "HU": (47.16, 19.50),
    "IS": (64.96, -19.02),
    "IE": (53.14, -7.69),
    "IT": (41.87, 12.57),
    "XK": (42.60, 20.90),
    "LV": (56.88, 24.60),
    "LI": (47.17, 9.56),
    "LT": (55.17, 23.88),
    "LU": (49.82, 6.13),
    "MT": (35.94, 14.38),
    "MD": (47.41, 28.37),
    "MC": (43.74, 7.42),
    "ME": (42.71, 19.37),
    "NL": (52.13, 5.29),
    "MK": (41.61, 21.75),
    "NO": (60.47, 8.47),
    "PL": (51.92, 19.15),
    "PT": (39.40, -8.22),
    "RO": (45.94, 24.97),
    "RU": (61.52, 50.82),
    "SM": (43.94, 12.46),
    "RS": (44.02, 21.01),
    "SK": (48.67, 19.70),
    "SI": (46.15, 14.99),
    "ES": (40.46, -3.75),
    "SE": (60.13, 18.64),
    "CH": (46.82, 8.23),
    "TR": (38.96, 35.24),
    "UA": (48.38, 31.17),
    "GB": (55.38, -3.44),
}


def build_ilga_geodataframe(document: dict[str, Any] | None) -> gpd.GeoDataFrame:
    records: list[dict[str, Any]] = []
    if isinstance(document, dict):
        for country in document.get("countries", []):
            if not isinstance(country, dict):
                continue
            country_code = str(country.get("country_code") or "").strip()
            coordinates = EUROPE_CENTROIDS.get(country_code)
            ranking = country.get("ranking")
            if coordinates is None or not isinstance(ranking, (int, float)):
                continue
            latitude, longitude = coordinates
            records.append(
                {
                    "country_code": country_code,
                    "country": country.get("country") or country_code,
                    "ranking": float(ranking),
                    "latitude": latitude,
                    "longitude": longitude,
                    "geometry": Point(longitude, latitude),
                }
            )
    if not records:
        return gpd.GeoDataFrame(
            {
                "country_code": [],
                "country": [],
                "ranking": [],
                "latitude": [],
                "longitude": [],
                "geometry": [],
            },
            geometry="geometry",
            crs="EPSG:4326",
        )
    return gpd.GeoDataFrame(records, geometry="geometry", crs="EPSG:4326")
