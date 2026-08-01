from __future__ import annotations

from typing import Any, cast
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from app.import_to_db.fra import parse_fra_csv_text
from app.import_to_db.fra.mongo import insert_indicator_fra_json
from app.import_to_db.fra.schema import (
    FraDuplicateConflictError,
    FraMetadataMismatchError,
    InvalidFraCsvError,
    UnsupportedFraCsvSchemaError,
    detect_fra_csv_schema,
    normalize_fra_csv,
    parse_fra_percentage,
    read_fra_csv_text,
)

CURRENT_CSV = '''topic,question,question_code,Location,country,Yes
Discrimination,Discrimination in areas of life > Felt discriminated,D1_1,Spain,ES,42
Discrimination,Discrimination in areas of life > Felt discriminated,D1_1,Greece,EL,"42,5 %"
,,,,,
‡,small sample size,,,,
¹,not available due to small sample size,,,,
Note:,Population note,,,,
Filters:,Answer: Yes,,,,
Source:,"EU LGBTIQ Survey III, 2023",,,,
Date:,2026-08-01,,,,
Question Code:,D1_1,,,,
Hyperlink:,https://fra.example/export,,,,
'''


def payload_dict(payload: Any) -> dict[str, Any]:
    assert isinstance(payload, dict)
    return cast(dict[str, Any], payload)


def test_detects_and_normalizes_current_wide_fra_csv() -> None:
    dataframe, schema = read_fra_csv_text(CURRENT_CSV)
    assert schema.version == "current_wide"
    assert schema.country_name_column == "Location"
    assert schema.country_code_column == "country"
    assert schema.percentage_columns == ("Yes",)

    normalized = normalize_fra_csv(dataframe, schema)
    assert normalized["country_code"].tolist() == ["ES", "GR"]
    assert normalized["percentage"].tolist() == [42, 42.5]
    assert normalized["year"].tolist() == [2023, 2023]
    assert set(normalized["response"]) == {"Yes"}
    assert set(normalized["filter_a_value"]) == {"All"}
    assert set(normalized["filter_b_value"]) == {"All"}


def test_detect_function_accepts_a_dataframe_directly() -> None:
    dataframe = pd.DataFrame(
        [{"topic": "T", "question": "Q", "question_code": "I", "Location": "Spain", "country": "ES", "Yes": "42"}]
    )
    assert detect_fra_csv_schema(dataframe).version == "current_wide"


def test_current_wide_supports_multiple_answer_columns() -> None:
    csv_text = """topic,question,question_code,Location,country,Yes,No
Discrimination,Area > Question,D1_1,Spain,ES,42,58
Filters:,All respondents,,,,,
Source:,"EU LGBTIQ Survey III, 2023",,,,,
"""
    dataframe, schema = read_fra_csv_text(csv_text)
    normalized = normalize_fra_csv(dataframe, schema)
    assert normalized[["response", "percentage"]].to_dict("records") == [
        {"response": "Yes", "percentage": 42},
        {"response": "No", "percentage": 58},
    ]


def test_added_metadata_columns_are_not_answers() -> None:
    csv_text = """Comment,unit,country,Yes,Location,question_code,question,topic
weighted,percentage,ES,42,Spain,D1_1,Area > Question,Discrimination
"""
    dataframe, schema = read_fra_csv_text(csv_text)
    assert schema.percentage_columns == ("Yes",)
    normalized = normalize_fra_csv(dataframe, schema)
    assert normalized.iloc[0]["percentage"] == 42


@pytest.mark.parametrize(
    ("metadata", "expected_a", "expected_b"),
    [
        ("Answer: Yes", "All", "All"),
        ("Answer: Yes; Age: 18-24", "18-24", "All"),
        ("Answer: Yes; Sexual Orientation: Lesbian", "All", "Lesbian"),
        (
            "Answer: Yes; Age: 18-24; Sex Characteristics: Endosex",
            "18-24",
            "Endosex",
        ),
    ],
)
def test_current_filter_combinations(
    metadata: str, expected_a: str, expected_b: str
) -> None:
    dataframe, schema = read_fra_csv_text(
        CURRENT_CSV.replace("Answer: Yes", metadata)
    )
    row = normalize_fra_csv(dataframe, schema).iloc[0]
    assert row["filter_a_value"] == expected_a
    assert row["filter_b_value"] == expected_b


def test_all_all_filename_rejects_explicit_endosex_metadata() -> None:
    inconsistent = CURRENT_CSV.replace(
        "Answer: Yes", "Answer: Yes; Sex Characteristics: Endosex"
    )
    with pytest.raises(FraMetadataMismatchError, match="fra_metadata_mismatch"):
        parse_fra_csv_text(inconsistent, file_name="d1-1_yes_2023_all_all.csv")


def test_all_all_and_explicit_endosex_reach_expected_payload_filters() -> None:
    all_payload = payload_dict(
        parse_fra_csv_text(CURRENT_CSV, file_name="d1-1_yes_2023_all_all.csv")
    )
    assert all_payload["answers"][0]["filters"] == [{"type": "All", "value": "All"}]

    endosex_csv = CURRENT_CSV.replace(
        "Answer: Yes", "Answer: Yes; Sex Characteristics: Endosex"
    )
    endosex_payload = payload_dict(
        parse_fra_csv_text(endosex_csv, file_name="d1-1_yes_2023_sc-endosex.csv")
    )
    assert endosex_payload["answers"][0]["filters"] == [
        {"type": "Sex Characteristics", "value": "Endosex"}
    ]


def test_legacy_semicolon_csv_and_decimal_comma_remain_supported() -> None:
    csv_text = '''country;topic;question;answer;Age;Sexual Orientation;percentage;question_code
España;Discrimination;Area > Pregunta;Yes;18-24;Lesbian;"42,5 %";D1_1
'''
    dataframe, schema = read_fra_csv_text(csv_text)
    assert schema.version == "legacy_long"
    row = normalize_fra_csv(dataframe, schema).iloc[0]
    assert row["country_code"] == "ES"
    assert row["percentage"] == 42.5
    assert row["filter_a_value"] == "18-24"
    assert row["filter_b_value"] == "Lesbian"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("42", 42),
        ("42.0", 42),
        ("42,5", 42.5),
        ("42.5", 42.5),
        ("42,5 %", 42.5),
        ("42.5%", 42.5),
        ("null", None),
        ("N/A", None),
        (":", None),
    ],
)
def test_percentage_points_variants(value: str, expected: float | None) -> None:
    assert parse_fra_percentage(value, scale="percentage_points") == expected


def test_proportion_scale_is_schema_specific() -> None:
    assert parse_fra_percentage("0.425", scale="percentage_points") == 0.425
    assert parse_fra_percentage("0.425", scale="proportion") == 42.5
    with pytest.raises(InvalidFraCsvError, match="proportion_out_of_range"):
        parse_fra_percentage("1.1", scale="proportion")


@pytest.mark.parametrize("csv_text", ["", "   ", "<html><body>Error</body></html>"])
def test_empty_and_html_payloads_are_rejected(csv_text: str) -> None:
    with pytest.raises(InvalidFraCsvError):
        read_fra_csv_text(csv_text)


def test_unknown_column_set_is_rejected_with_actionable_error() -> None:
    with pytest.raises(UnsupportedFraCsvSchemaError, match="unsupported_fra_csv_schema"):
        detect_fra_csv_schema(pd.DataFrame([{"foo": "bar", "answer": "Yes"}]))


def test_exact_duplicate_is_idempotent_but_conflicting_duplicate_is_rejected() -> None:
    duplicate = CURRENT_CSV.replace(
        "Discrimination,Discrimination in areas of life > Felt discriminated,D1_1,Greece",
        "Discrimination,Discrimination in areas of life > Felt discriminated,D1_1,Spain,ES,42\n"
        "Discrimination,Discrimination in areas of life > Felt discriminated,D1_1,Greece",
    )
    dataframe, schema = read_fra_csv_text(duplicate)
    assert len(normalize_fra_csv(dataframe, schema)) == 2

    conflict = duplicate.replace("Spain,ES,42\nDiscrimination", "Spain,ES,43\nDiscrimination", 1)
    with pytest.raises(FraDuplicateConflictError, match="fra_conflicting_duplicate_rows"):
        dataframe, schema = read_fra_csv_text(conflict)
        normalize_fra_csv(dataframe, schema)


def test_repeated_persistence_uses_set_semantics_for_answer_batches() -> None:
    payload = payload_dict(parse_fra_csv_text(CURRENT_CSV, file_name="fra.csv"))
    collection = MagicMock()
    with patch("app.import_to_db.fra.mongo.get_mongo_collection", return_value=collection):
        insert_indicator_fra_json(payload)
        insert_indicator_fra_json(payload)
    assert collection.update_one.call_count == 2
    for call in collection.update_one.call_args_list:
        update = call.args[1]
        assert "$addToSet" in update
        assert "$each" in update["$addToSet"]["answers"]
