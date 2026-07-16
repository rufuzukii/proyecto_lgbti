from pathlib import Path
import sys

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from app.analytics.statistics_geodata import merge_statistics_with_geodata
from app.analytics.statistics_charts import build_europe_choropleth, normalize_percentage
from app.analytics.statistics_models import FraStatisticsQuery, IlgaStatisticsQuery, validate_fra_query
from app.analytics.statistics_normalizers import normalize_country_code, normalize_filter_value
from app.analytics.statistics_service import (
    aggregate_fra_data,
    build_fra_filter_value_options,
    classify_external_data_error,
    filter_fra_dataframe,
    filter_ilga_dataframe,
    fra_document_to_dataframe,
    ilga_document_to_dataframe,
)
from app.dash.pages.statistics import (
    DATA_TYPE_OPTIONS,
    _control_group,
    _data_type_selector_class,
    _effective_query_mode,
)


def test_normalizes_country_codes_and_filter_values() -> None:
    assert normalize_country_code("UK") == "GB"
    assert normalize_country_code("", "Czechia") == "CZ"
    assert normalize_country_code("", "Kosovo") == "XK"
    assert normalize_filter_value("Rairly open") == "Fairly open"
    assert normalize_filter_value("Heterosexual/Straighy") == "Heterosexual/Straight"
    assert normalize_filter_value("Not limited al all") == "Not limited at all"


def test_statistics_data_type_options_keep_internal_source_values() -> None:
    assert DATA_TYPE_OPTIONS == [
        {"label": "Sociodemográficos", "value": "fra"},
        {"label": "Legales", "value": "ilga"},
    ]


def test_data_type_selector_class_marks_active_source() -> None:
    assert _data_type_selector_class("fra").endswith("stats-data-type-control--fra")
    assert _data_type_selector_class("ilga").endswith("stats-data-type-control--ilga")


def test_fra_query_rejects_two_group_a_filters_represented_as_group_b() -> None:
    query = FraStatisticsQuery(
        filter_a_name="Age",
        filter_a_value="18-24",
        filter_b_name="Education",
        filter_b_value="Tertiary education",
    )

    result = validate_fra_query(query)

    assert not result.ok
    assert "grupo B" in result.message


def test_fra_dataframe_keeps_one_filter_a_and_one_filter_b() -> None:
    document = {
        "code": "D1",
        "category": "Discrimination",
        "specific_category": "Work",
        "question": "Felt discriminated",
        "answers": [
            {
                "country": "Spain",
                "country_code": "ES",
                "answer": "Yes",
                "percentage": 21.0,
                "date": "2023",
                "filters": [
                    {"type": "Age", "value": "18-24"},
                    {"type": "Gender Expression", "value": "Trans women"},
                ],
            }
        ],
    }

    dataframe = fra_document_to_dataframe(document)

    assert dataframe.iloc[0]["filter_a"] == "18-24"
    assert dataframe.iloc[0]["filter_b"] == "Trans women"
    assert dataframe.iloc[0]["year"] == 2023


def test_fra_dataframe_accepts_string_percentages() -> None:
    document = {
        "answers": [
            {
                "country": "Spain",
                "country_code": "ES",
                "answer": "Yes",
                "percentage": "67,5%",
                "date": "2023",
                "filters": [],
            }
        ],
    }

    dataframe = fra_document_to_dataframe(document)

    assert dataframe.iloc[0]["percentage"] == 67.5


def test_filter_value_options_show_normalized_label_but_keep_raw_value() -> None:
    document = {
        "answers": [
            {
                "country": "Spain",
                "country_code": "ES",
                "answer": "Yes",
                "percentage": 21.0,
                "filters": [{"type": "Openness about being LGBTIQ", "value": "Rairly open"}],
            }
        ],
    }

    options = build_fra_filter_value_options(document, "Openness about being LGBTIQ")

    assert options == [{"label": "Fairly open", "value": "Rairly open"}]


def test_classifies_fra_no_data_payload_without_exposing_500() -> None:
    payload = {
        "error": ["500 - Internal server error"],
        "message": ["Error in getFilteredIndicatorEnrichedData(req): No data for this query.\n"],
    }

    assert classify_external_data_error(payload) == "empty"


def test_aggregate_fra_data_rejects_summing_percentages() -> None:
    dataframe = pd.DataFrame(
        [
            {"country": "Spain", "percentage": 20.0},
            {"country": "Spain", "percentage": 30.0},
        ]
    )

    with pytest.raises(ValueError, match="cannot_sum_percentages"):
        aggregate_fra_data(dataframe, ["country"], "percentage", "sum")


def test_aggregate_fra_data_computes_mean() -> None:
    dataframe = pd.DataFrame(
        [
            {"country": "Spain", "percentage": 20.0},
            {"country": "Spain", "percentage": 30.0},
        ]
    )

    result = aggregate_fra_data(dataframe, ["country"], "percentage", "mean")

    assert result.iloc[0]["percentage"] == 25.0


def test_effective_query_mode_follows_country_selection() -> None:
    assert _effective_query_mode("all", []) == "all"
    assert _effective_query_mode("all", ["ES"]) == "one"
    assert _effective_query_mode("all", ["ES", "PT"]) == "compare"


def test_normalize_percentage_handles_strings_and_invalid_values() -> None:
    assert normalize_percentage("78%") == 78.0
    assert normalize_percentage("67,5") == 67.5
    assert normalize_percentage(None) is None
    assert normalize_percentage("not-a-number") is None


def test_europe_choropleth_uses_iso3_locations_and_normalizes_ratio_values() -> None:
    figure = build_europe_choropleth(
        [
            {"country": "Spain", "iso": "ES", "value": "0,78"},
            {"country": "Portugal", "iso": "PT", "value": "0.61"},
        ],
        source="FRA",
    )
    trace = figure.data[0]

    assert trace.locationmode == "ISO-3"
    assert list(trace.locations) == ["ESP", "PRT"]
    assert list(trace.z) == [78.0, 61.0]
    assert trace.zmin == 61.0
    assert trace.zmax == 78.0


def test_ilga_filter_applies_countries_even_when_mode_is_all() -> None:
    dataframe = pd.DataFrame(
        [
            {"country": "Spain", "iso": "ES", "category": "Ranking total", "criterion": "", "ranking": 77.0},
            {"country": "Portugal", "iso": "PT", "category": "Ranking total", "criterion": "", "ranking": 68.0},
        ]
    )
    query = IlgaStatisticsQuery(countries=["ES"], mode="all", category="Ranking total")

    filtered = filter_ilga_dataframe(dataframe, query)

    assert filtered["country"].tolist() == ["Spain"]


def test_fra_filter_applies_countries_even_when_mode_is_all() -> None:
    dataframe = pd.DataFrame(
        [
            {
                "country": "Spain",
                "iso": "ES",
                "answer": "Yes",
                "percentage": 20.0,
                "filters": {"All": "All"},
                "year": 2023,
            },
            {
                "country": "Portugal",
                "iso": "PT",
                "answer": "Yes",
                "percentage": 30.0,
                "filters": {"All": "All"},
                "year": 2023,
            },
        ]
    )
    query = FraStatisticsQuery(countries=["PT"], mode="all", answer="Yes")

    filtered = filter_fra_dataframe(dataframe, query)

    assert filtered["country"].tolist() == ["Portugal"]


def test_ilga_dataframe_preserves_partial_criteria_values() -> None:
    document = {
        "year": 2026,
        "countries": [
            {
                "country": "Spain",
                "country_code": "ES",
                "ranking": 77.97,
                "criteria": [
                    {
                        "category": "Equality & non-discrimination",
                        "indicator": "Constitutional protection",
                        "weight": 1.0,
                        "value": 0.05882352941,
                    }
                ],
            }
        ],
    }

    dataframe = ilga_document_to_dataframe(document)
    criterion_row = dataframe[dataframe["criterion"] == "Constitutional protection"].iloc[0]

    assert criterion_row["criterion_value"] == 0.05882352941


def test_merge_statistics_with_geodata_flags_missing_geometry_and_duplicates() -> None:
    gpd = pytest.importorskip("geopandas")
    from shapely.geometry import Point

    geodata = gpd.GeoDataFrame(
        [{"iso": "ES", "geometry": Point(0, 0)}],
        geometry="geometry",
        crs="EPSG:4326",
    )
    stats = pd.DataFrame(
        [
            {"iso": "ES", "value": 10.0},
            {"iso": "ES", "value": 11.0},
            {"iso": "XK", "value": 12.0},
        ]
    )

    merged = merge_statistics_with_geodata(geodata, stats, "iso", "iso")

    assert merged.iloc[0]["has_statistics"]
    assert merged.attrs["missing_geometry_iso"] == ["XK"]
    assert merged.attrs["duplicated_statistics_iso"] == ["ES"]


def test_statistics_control_group_omits_empty_id() -> None:
    component = _control_group("Tipo de datos", [])

    assert "id" not in component.to_plotly_json()["props"]
