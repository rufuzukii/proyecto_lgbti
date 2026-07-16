from __future__ import annotations

from typing import Any

import pandas as pd

from app.analytics.statistics_normalizers import normalize_country_code


def merge_statistics_with_geodata(
    geodataframe: Any,
    dataframe: pd.DataFrame,
    geo_iso_column: str,
    data_iso_column: str,
) -> Any:
    if geo_iso_column not in geodataframe.columns:
        raise ValueError("invalid_geo_iso_column")
    if data_iso_column not in dataframe.columns:
        raise ValueError("invalid_data_iso_column")

    geodata = geodataframe.copy()
    data = dataframe.copy()
    geodata["_stats_iso"] = geodata[geo_iso_column].apply(normalize_country_code)
    data["_stats_iso"] = data[data_iso_column].apply(normalize_country_code)

    duplicated = sorted(data.loc[data["_stats_iso"].duplicated(), "_stats_iso"].dropna().unique())
    if duplicated:
        data = data.drop_duplicates("_stats_iso", keep="first")

    merged = geodata.merge(data, on="_stats_iso", how="left", suffixes=("", "_stat"))
    merged["has_statistics"] = merged[data_iso_column].notna() if data_iso_column in merged else False
    merged.attrs["missing_geometry_iso"] = sorted(
        set(data["_stats_iso"].dropna()).difference(set(geodata["_stats_iso"].dropna()))
    )
    merged.attrs["duplicated_statistics_iso"] = duplicated
    return merged.drop(columns=["_stats_iso"])
