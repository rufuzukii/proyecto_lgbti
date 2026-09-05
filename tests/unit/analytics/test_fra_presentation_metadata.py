from __future__ import annotations

from typing import Any, cast

from app.modules.statistics.figures import (
    FRA_NO_DATA_COLOR,
    FRA_OUTSIDE_SCOPE_COLOR,
    build_europe_choropleth,
    build_response_country_comparison_chart,
)
from app.modules.statistics.service import build_fra_control_payload
from app.shared.data.fra_metadata import (
    FraCountryState,
    FraResponseType,
    classify_fra_country_state,
    detect_fra_response_type,
    fra_survey_participant_codes,
    order_fra_responses,
)
from app.shared.data.geography_service import europe_country_catalog, prepare_europe_map_data

RANKED_RESPONSES = ["Not Selected", "3rd", "1st", "2nd"]


def test_fra_2023_scope_is_edition_specific_and_contains_30_countries() -> None:
    participants = fra_survey_participant_codes(2023)

    assert participants is not None
    assert len(participants) == 30
    assert {"ES", "AL", "MK", "RS"}.issubset(participants)
    assert {"GB", "NO", "CH"}.isdisjoint(participants)
    survey_ii = fra_survey_participant_codes(2019)
    assert survey_ii is not None
    assert len(survey_ii) == 30
    assert {"ES", "GB", "MK", "RS"}.issubset(survey_ii)


def test_fra_country_state_does_not_infer_scope_from_value_presence() -> None:
    assert classify_fra_country_state("ES", True, survey_year=2023) is FraCountryState.HAS_DATA
    assert classify_fra_country_state("ES", False, survey_year=2023) is FraCountryState.NO_DATA
    assert (
        classify_fra_country_state("GB", True, survey_year=2023)
        is FraCountryState.OUTSIDE_SURVEY_SCOPE
    )
    assert classify_fra_country_state("GB", True, survey_year=2019) is FraCountryState.HAS_DATA


def test_geography_merge_keeps_value_and_scope_as_separate_fields() -> None:
    prepared = prepare_europe_map_data(
        [
            {"country": "Spain", "iso": "ES", "value": 0},
            {"country": "United Kingdom", "iso": "GB", "value": 42},
        ],
        fra_survey_year=2023,
    )
    rows = {row["country_code"]: row for row in prepared.rows}

    assert rows["ES"]["value"] == 0
    assert rows["ES"]["survey_state"] == "has_data"
    assert rows["FR"]["value"] is None
    assert rows["FR"]["survey_state"] == "no_data"
    assert rows["GB"]["value"] == 42
    assert rows["GB"]["survey_state"] == "outside_survey_scope"


def test_fra_map_distinguishes_zero_missing_and_outside_scope_with_hover_and_legend() -> None:
    figure = build_europe_choropleth(
        [
            {"country": "Spain", "iso": "ES", "value": 0},
            {"country": "France", "iso": "FR", "value": None},
        ],
        source="FRA",
        survey_year=2023,
        language="en",
    )
    choropleth = cast(Any, figure.data[0])
    values = dict(zip(choropleth.locations, choropleth.z, strict=True))
    hovers = dict(zip(choropleth.locations, choropleth.hovertext, strict=True))

    assert values["ES"] == 0
    assert values["FR"] == -1
    assert values["GB"] == -2
    assert "Value: 0%" in hovers["ES"]
    assert "No data is available for this selection." in hovers["FR"]
    assert "not part of the European Union" in hovers["GB"]
    assert "Value:" not in hovers["GB"]
    legend = {cast(Any, trace).name: cast(Any, trace).marker.color for trace in figure.data[2:]}
    assert legend["No data"] == FRA_NO_DATA_COLOR
    assert legend["Outside the scope of the FRA survey"] == FRA_OUTSIDE_SCOPE_COLOR


def test_every_european_country_has_one_fra_2023_visual_state() -> None:
    prepared = prepare_europe_map_data([], fra_survey_year=2023)
    states = {row["survey_state"] for row in prepared.rows}
    outside = {
        row["country_code"]
        for row in prepared.rows
        if row["survey_state"] == "outside_survey_scope"
    }

    assert len(prepared.rows) == len(europe_country_catalog()) == 49
    assert states == {"no_data", "outside_survey_scope"}
    assert {"GB", "NO", "CH", "TR", "XK"}.issubset(outside)


def test_ranked_reason_detection_uses_response_set_not_only_title() -> None:
    assert (
        detect_fra_response_type(RANKED_RESPONSES, question="insufficient income")
        is FraResponseType.RANKED_REASON
    )
    assert detect_fra_response_type(["Yes", "No"]) is FraResponseType.STANDARD
    assert order_fra_responses(RANKED_RESPONSES) == ["1st", "2nd", "3rd", "Not Selected"]


def test_ranked_reason_control_payload_preserves_values_and_semantic_order() -> None:
    payload = build_fra_control_payload(
        {
            "question": "insufficient income",
            "specific_category": "Reason for housing difficulties - financial problems",
            "answers": [
                {"answer": answer, "country": "Spain", "filters": []} for answer in RANKED_RESPONSES
            ],
        }
    )

    assert payload["response_type"] == "ranked_reason"
    assert payload["response_help"] == "fra_ranked_reason_help"
    assert [option["value"] for option in payload["answers"]] == [
        "1st",
        "2nd",
        "3rd",
        "Not Selected",
    ]


def test_ranked_reason_chart_keeps_canonical_english_categories_without_numeric_scoring() -> None:
    rows = [
        {
            "country": "Spain",
            "iso": "ES",
            "answer": answer,
            "percentage": value,
            "year": 2023,
            "source": "FRA",
        }
        for answer, value in zip(RANKED_RESPONSES, [55, 10, 20, 15], strict=True)
    ]

    figure = build_response_country_comparison_chart(rows, language="es")

    trace = cast(Any, figure.data[0])
    assert list(trace.x) == [
        "1st",
        "2nd",
        "3rd",
        "Not Selected",
    ]
    assert list(trace.y) == [20.0, 15.0, 10.0, 55.0]
