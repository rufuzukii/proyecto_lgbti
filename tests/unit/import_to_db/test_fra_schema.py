from __future__ import annotations

from typing import Any, cast
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from app.modules.imports.fra import parse_fra_csv_text
from app.modules.imports.fra.mongo import insert_indicator_fra_json
from app.modules.imports.fra.schema import (
    FraDuplicateConflictError,
    FraMetadataMismatchError,
    InvalidFraCsvError,
    UnsupportedFraCsvSchemaError,
    detect_fra_csv_schema,
    extract_fra_survey_year,
    find_fra_header_row,
    normalize_fra_csv,
    parse_fra_percentage,
    read_fra_csv_text,
)
from app.shared.data.fra_validation import is_valid_fra_category

CURRENT_CSV = """topic,question,question_code,Location,country,Yes
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
"""


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
    assert normalized["survey_year"].tolist() == [2023, 2023]
    assert set(normalized["response"]) == {"Yes"}
    assert set(normalized["filter_a_value"]) == {"All"}
    assert set(normalized["filter_b_value"]) == {"All"}


def test_detect_function_accepts_a_dataframe_directly() -> None:
    dataframe = pd.DataFrame(
        [
            {
                "topic": "T",
                "question": "Q",
                "question_code": "I",
                "Location": "Spain",
                "country": "ES",
                "Yes": "42",
            }
        ]
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
def test_current_filter_combinations(metadata: str, expected_a: str, expected_b: str) -> None:
    dataframe, schema = read_fra_csv_text(CURRENT_CSV.replace("Answer: Yes", metadata))
    row = normalize_fra_csv(dataframe, schema).iloc[0]
    assert row["filter_a_value"] == expected_a
    assert row["filter_b_value"] == expected_b


def test_current_response_metadata_tolerates_lost_punctuation() -> None:
    header = "By healthcare personnel (e.g. a nurse)"
    csv_text = CURRENT_CSV.replace("Yes", header).replace(
        f"Answer: {header}", "Answer: By healthcare personnel (e.ga nurse)"
    )
    payload = payload_dict(parse_fra_csv_text(csv_text))
    assert payload["answers"][0]["answer"] == header


def test_current_response_metadata_still_rejects_different_answer() -> None:
    inconsistent = CURRENT_CSV.replace("Answer: Yes", "Answer: No")
    with pytest.raises(FraMetadataMismatchError, match="fra_answer_metadata_mismatch"):
        parse_fra_csv_text(inconsistent)


def test_unlabeled_fra_source_footer_supplies_survey_year() -> None:
    csv_text = """Location,country,topic,question,question_code,value,notes
Spain,ES,Health and mental health,Mental health > Satisfaction with life,H1,6.7,
Place of residence: A village,,,,,,
\"EU LGBTIQ Survey III, 2023\",,,,,,
2026-08-12,,,,,,
"""
    payload = payload_dict(parse_fra_csv_text(csv_text, file_name="No-filters.csv"))
    assert payload["survey_year"] == 2023
    assert payload["answers"][0]["answer"] == "Mean"
    assert payload["answers"][0]["percentage"] == 6.7
    assert payload["answers"][0]["filters"] == [
        {"type": "Place of residence", "value": "A village"}
    ]


def test_all_all_filename_rejects_explicit_endosex_metadata() -> None:
    inconsistent = CURRENT_CSV.replace("Answer: Yes", "Answer: Yes; Sex Characteristics: Endosex")
    with pytest.raises(FraMetadataMismatchError, match="fra_metadata_mismatch"):
        parse_fra_csv_text(inconsistent, file_name="d1-1_yes_2023_all_all.csv")


def test_all_all_and_explicit_endosex_reach_expected_payload_filters() -> None:
    all_payload = payload_dict(
        parse_fra_csv_text(CURRENT_CSV, file_name="d1-1_yes_2023_all_all.csv")
    )
    assert all_payload["answers"][0]["filters"] == [{"type": "All", "value": "All"}]

    endosex_csv = CURRENT_CSV.replace("Answer: Yes", "Answer: Yes; Sex Characteristics: Endosex")
    endosex_payload = payload_dict(
        parse_fra_csv_text(endosex_csv, file_name="d1-1_yes_2023_sc-endosex.csv")
    )
    assert endosex_payload["answers"][0]["filters"] == [
        {"type": "Sex Characteristics", "value": "Endosex"}
    ]


def test_legacy_semicolon_csv_and_decimal_comma_remain_supported() -> None:
    csv_text = """country;topic;question;answer;Age;Sexual Orientation;percentage;question_code
España;Discrimination;Area > Pregunta;Yes;18-24;Lesbian;"42,5 %";D1_1
"""
    dataframe, schema = read_fra_csv_text(csv_text)
    assert schema.version == "legacy_long"
    row = normalize_fra_csv(dataframe, schema).iloc[0]
    assert row["country_code"] == "ES"
    assert row["percentage"] == 42.5
    assert row["filter_a_value"] == "18-24"
    assert row["filter_b_value"] == "Lesbian"
    assert row["survey_year"] is None


@pytest.mark.parametrize(
    ("source_text", "expected"),
    [
        ("EU LGBTIQ Survey III, 2023", 2023),
        ("EU LGBTIQ Survey III (2023)", 2023),
        ("Survey 2023", 2023),
        ("Survey III", None),
        ("", None),
        (None, None),
        ("Survey wave 3, edition 2023", 2023),
        ("Survey 2019-2023", None),
        ("Survey 1789", None),
        ("Survey 2201", None),
    ],
)
def test_extract_fra_survey_year(source_text: object, expected: int | None) -> None:
    assert extract_fra_survey_year(source_text) == expected


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


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("54\u2021", 54),
        ("42,5 \u2021", 42.5),
        ("42.5%\u2021", 42.5),
        ("\u0105", None),
    ],
)
def test_percentage_points_support_fra_footnote_suffixes(
    value: str, expected: float | None
) -> None:
    assert parse_fra_percentage(value, scale="percentage_points") == expected


def test_current_csv_preserves_null_percentages_and_numeric_footnotes() -> None:
    csv_text = """topic,question,question_code,Location,country,Place of residence,Yes
Families,Families > Raising children,G12,Austria,AT,A village,54\u2021
Families,Families > Raising children,G12,Bulgaria,BG,A village,\u0105
\u2021,small sample size,,,,,
\u0105,not available due to small sample size,,,,,
Filters:,Answer: Yes; Place of residence: A village,,,,,
Source:,"EU LGBTIQ Survey III, 2023",,,,,
"""

    payload = payload_dict(parse_fra_csv_text(csv_text, file_name="No-filters.csv"))

    assert [answer["percentage"] for answer in payload["answers"]] == [54, None]
    assert payload["survey_year"] == 2023
    assert payload["answers"][0]["filters"] == [
        {"type": "Place of residence", "value": "A village"}
    ]


def test_age_55_plus_column_is_a_filter_not_an_answer_column() -> None:
    csv_text = """topic,question,question_code,Location,country,Age,Yes
Families,Families > Question,G9,Spain,ES,55+,42
Filters:,Answer: Yes; Age: 55+,,,,
Source:,"EU LGBTIQ Survey III, 2023",,,,,
"""

    payload = payload_dict(parse_fra_csv_text(csv_text, file_name="No-filters.csv"))

    assert {answer["answer"] for answer in payload["answers"]} == {"Yes"}
    assert payload["answers"][0]["filters"] == [{"type": "Age", "value": "55+"}]


def test_duplicate_age_headers_keep_filter_and_answer_roles_separate() -> None:
    csv_text = """topic,question,question_code,Location,country,Age,Age
Discrimination,Area > Reasons,C2,Albania,AL,15-17,\u00b9
Discrimination,Area > Reasons,C2,Spain,ES,15-17,31
Filters:,Answer: Age; Age: 15-17,,,,
Source:,"EU LGBTIQ Survey III, 2023",,,,,
"""

    payload = payload_dict(parse_fra_csv_text(csv_text, file_name="No-filters.csv"))

    assert {answer["answer"] for answer in payload["answers"]} == {"Age"}
    assert [answer["percentage"] for answer in payload["answers"]] == [None, 31]
    assert payload["answers"][1]["filters"] == [{"type": "Age", "value": "15-17"}]


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


def test_repeated_persistence_uses_atomic_natural_key_replacement() -> None:
    payload = payload_dict(parse_fra_csv_text(CURRENT_CSV, file_name="fra.csv"))
    collection = MagicMock()
    with patch("app.modules.imports.fra.mongo.get_mongo_collection", return_value=collection):
        insert_indicator_fra_json(payload)
        insert_indicator_fra_json(payload)
    assert collection.update_one.call_count == 2
    for call in collection.update_one.call_args_list:
        answer_update = call.args[1][0]["$set"]["answers"]
        assert "$let" in answer_update
        incoming = answer_update["$let"]["vars"]["incoming"]["$literal"]
        assert all(answer.get("identity_key") for answer in incoming)


def test_current_csv_detects_header_after_leading_metadata_and_keeps_it_separate() -> None:
    csv_text = """Date:,2026-08-03,,,,
Filters:,Answer: Yes,,,,
Source:,"EU LGBTIQ Survey III, 2023",,,,
Question Code:,D1_1,,,,
Hyperlink:,https://fra.example/export,,,,
Note:,Weighted survey results,,,,
General Disclaimer of the FRA website:,https://fra.example/terms,,,,
¹,not available due to sample size,,,,
topic,question,question_code,Location,country,Yes
Discrimination,Area > Felt discriminated,D1_1,Spain,ES,42
‡,small sample size,,,,
"""

    dataframe, schema = read_fra_csv_text(csv_text)
    normalized = normalize_fra_csv(dataframe, schema)
    payload = payload_dict(parse_fra_csv_text(csv_text, file_name="fra-new.csv"))

    assert schema.header_row == 8
    assert normalized["category"].tolist() == ["Discrimination"]
    assert payload["category"] == "Discrimination"
    assert payload["record_type"] == "statistic"
    assert payload["metadata"]["date"] == "2026-08-03"
    assert payload["survey_year"] == 2023
    assert payload["metadata"]["question_code"] == "D1_1"
    assert payload["metadata"]["hyperlink"] == "https://fra.example/export"
    assert payload["metadata"]["note"] == "Weighted survey results"
    assert payload["metadata"]["disclaimer"] == "https://fra.example/terms"
    assert payload["metadata"]["footnotes"] == {
        "¹": "not available due to sample size",
        "‡": "small sample size",
    }


def test_legacy_csv_detects_header_after_variable_metadata_preamble() -> None:
    csv_text = """Source:;"EU LGBTIQ Survey III, 2023";;;;
Date:;2026-08-03;;;;
Note:;Legacy export;;;;
country;topic;question;answer;percentage;question_code
Spain;Discrimination;Area > Felt discriminated;Yes;42;D1_1
"""

    dataframe, schema = read_fra_csv_text(csv_text)
    normalized = normalize_fra_csv(dataframe, schema)

    assert schema.version == "legacy_long"
    assert schema.header_row == 3
    assert normalized["survey_year"].tolist() == [2023]
    assert normalized[["category", "country_code", "percentage"]].to_dict("records") == [
        {"category": "Discrimination", "country_code": "ES", "percentage": 42}
    ]


def test_find_header_row_rejects_metadata_only_csv() -> None:
    with pytest.raises(UnsupportedFraCsvSchemaError, match="header_not_detected"):
        find_fra_header_row([["Date:", "2026-08-03"], ["Source:", "FRA"]])


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        "   ",
        "Date:",
        "Filters:",
        "Source:",
        "Question Code:",
        "Hyperlink:",
        "Note:",
        "General Disclaimer of the FRA website:",
        "¹",
        "‡",
        "ą",
        "https://fra.example/category",
    ],
)
def test_invalid_fra_categories_are_rejected(value: object) -> None:
    assert not is_valid_fra_category(value)


@pytest.mark.parametrize(
    "value",
    [
        "Discrimination",
        "Health: access and outcomes",
        "A long valid category describing social attitudes and government response",
    ],
)
def test_real_categories_with_long_text_or_colons_remain_valid(value: str) -> None:
    assert is_valid_fra_category(value)


def test_import_logs_one_summary_instead_of_warning_per_metadata_row(caplog) -> None:
    caplog.set_level("INFO", logger="app.modules.imports.fra.schema")
    dataframe, schema = read_fra_csv_text(CURRENT_CSV)
    normalize_fra_csv(dataframe, schema)

    summaries = [record for record in caplog.records if record.message == "fra_import_summary"]
    assert len(summaries) == 1
    summary = summaries[0]
    assert summary.rows_valid == 2
    assert summary.metadata_rows >= 6
    assert summary.footnote_rows == 2
    assert summary.skipped_rows >= 1
