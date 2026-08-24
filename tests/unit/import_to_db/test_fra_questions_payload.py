from typing import Any, cast
from unittest.mock import MagicMock, patch

from app.import_to_db.fra import parse_fra_csv_text
from app.import_to_db.fra.indicators import _consolidate_catalog_documents, _normalize_documents
from app.import_to_db.fra.mongo import (
    _prepare_indicator_document,
    insert_indicator_fra_json,
)


def _payload_dict(payload: Any) -> dict[str, Any]:
    assert isinstance(payload, dict)
    return cast(dict[str, Any], payload)


def _payload_list(payload: Any) -> list[dict[str, Any]]:
    assert isinstance(payload, list)
    return cast(list[dict[str, Any]], payload)


def test_fra_payload_groups_csv_by_question_code() -> None:
    csv_text = """country,topic,question,answer,Age,Gender Expression,percentage,notes
Spain,Discrimination,Discrimination in areas of life > Felt discriminated at work,Yes,18-24,Trans women,21,""
Source:,"EU LGBTIQ Survey III, 2023",,,,,,
Date:,2026-02-27,,,,,,
Question Code:,D1_3_2,,,,,,
Hyperlink:,http://example.test/fra,,,,,,
"""

    payload = _payload_dict(parse_fra_csv_text(csv_text, file_name="GE-Trans women.csv"))

    assert len(payload["id"]) == 24
    assert payload["code"] == "D1_3_2"
    assert payload["dataset"] == "eu_lgbtiq_survey_iii"
    assert "external_code" not in payload
    assert "questions" not in payload
    assert payload["category"] == "Discrimination"
    assert payload["specific_category"] == "Discrimination in areas of life"
    assert payload["question"] == "Felt discriminated at work"
    assert payload["survey_year"] == 2023
    assert payload["answers"][0] == {
        "country": "Spain",
        "country_code": "ES",
        "answer": "Yes",
        "percentage": 21.0,
        "date": "2026-02-27",
        "survey_year": 2023,
        "filters": [
            {"type": "Age", "value": "18-24"},
            {"type": "Gender Expression", "value": "Trans women"},
        ],
    }


def test_indicator_normalizer_accepts_grouped_fra_payload() -> None:
    payload = {
        "id": "665f1f3f9b9f7a2f4b7a0b11",
        "code": "D1_3_2",
        "dataset": "eu_lgbtiq_survey_iii",
        "category": "Discrimination",
        "specific_category": "Discrimination in areas of life",
        "question": "Felt discriminated at work",
        "answers": [
            {
                "country": "Spain",
                "country_code": "ES",
                "answer": "Yes",
                "percentage": 21.0,
                "filters": [
                    {"type": "Age", "value": "18-24"},
                    {"type": "Gender Expression", "value": "Trans women"},
                ],
            }
        ],
    }

    assert _normalize_documents(payload) == [payload]


def test_catalog_consolidates_repeated_code_without_losing_answers() -> None:
    documents = [
        {"code": "D1", "question": "Old", "answers": [{"answer": "Yes"}]},
        {"code": "D1", "question": "Current", "answers": [{"answer": "No"}]},
    ]

    consolidated = _consolidate_catalog_documents(documents)

    assert len(consolidated) == 1
    assert consolidated[0]["question"] == "Current"
    assert [answer["answer"] for answer in consolidated[0]["answers"]] == ["Yes", "No"]


def test_fra_question_split_uses_text_before_greater_than_as_specific_category() -> None:
    csv_text = """country,topic,question,answer,Age,Gender Expression,percentage,notes
Austria,Discrimination,Discrimination in areas of life > Felt discriminated in the 12 months before the survey in any of 8 areas of life,Yes,18-24,Trans women,74,""
Question Code:,D1_1,,,,,,
"""

    payload = _payload_dict(parse_fra_csv_text(csv_text, file_name="GE-Trans women.csv"))

    assert payload["specific_category"] == "Discrimination in areas of life"
    assert (
        payload["question"]
        == "Felt discriminated in the 12 months before the survey in any of 8 areas of life"
    )


def test_fra_payload_creates_different_documents_for_different_questions() -> None:
    csv_text = """country,topic,question,answer,percentage,notes,question_code
Austria,Discrimination,Discrimination in areas of life > Felt discriminated at work,Yes,36,"",D1_1
Austria,Education,Education > Experienced negative comments / conduct at school due to being LGBTIQ,Often,13,"",C9_C
"""

    payload = _payload_list(parse_fra_csv_text(csv_text, file_name="mixed.csv"))

    assert len(payload) == 2
    assert payload[0]["id"] != payload[1]["id"]
    assert {document["question"] for document in payload} == {
        "Felt discriminated at work",
        "conduct at school due to being LGBTIQ",
    }
    education = next(document for document in payload if document["code"] == "C9_C")
    assert education["specific_category"] == "Experienced negative comments"


def test_fra_payload_does_not_merge_different_questions_with_same_code() -> None:
    csv_text = """country,topic,question,answer,percentage,notes,question_code
Austria,Discrimination,Discrimination in areas of life > Felt discriminated at work,Yes,36,"",D1_1
Austria,Discrimination,Discrimination in areas of life > Felt discriminated in housing,Yes,22,"",D1_1
"""

    payload = _payload_list(parse_fra_csv_text(csv_text, file_name="same-code.csv"))

    assert len(payload) == 2
    assert payload[0]["code"] == "D1_1"
    assert payload[1]["code"] == "D1_1"
    assert payload[0]["id"] != payload[1]["id"]


def test_fra_payload_keeps_demographic_and_identity_filters() -> None:
    csv_text = """country,topic,question,answer,Age,Gender Expression,percentage,notes,question_code
Austria,Discrimination,Discrimination in areas of life > Felt discriminated at work,Yes,18-24,Trans women,36,"",D1_1
"""

    payload = _payload_dict(parse_fra_csv_text(csv_text, file_name="gender-expression.csv"))

    assert payload["answers"][0]["filters"] == [
        {"type": "Age", "value": "18-24"},
        {"type": "Gender Expression", "value": "Trans women"},
    ]


def test_mongo_preparation_converts_json_id_to_object_id() -> None:
    payload = {
        "id": "665f1f3f9b9f7a2f4b7a0b11",
        "code": "D1_1",
        "dataset": "eu_lgbtiq_survey_iii",
        "survey_year": 2023,
        "category": "Discrimination",
        "specific_category": "Discrimination in areas of life",
        "question": "Felt discriminated at work",
        "answers": [
            {
                "country": "Spain",
                "country_code": "ES",
                "answer": "Yes",
                "percentage": 21.0,
                "filters": [{"type": "All", "value": "All"}],
            }
        ],
    }

    prepared = _prepare_indicator_document(payload)

    assert type(prepared["_id"]).__name__ == "ObjectId"
    assert "id" not in prepared


def test_mongo_upsert_uses_atomic_answer_replacement_pipeline() -> None:
    payload = {
        "id": "665f1f3f9b9f7a2f4b7a0b11",
        "code": "D1_1",
        "dataset": "eu_lgbtiq_survey_iii",
        "survey_year": 2023,
        "category": "Discrimination",
        "specific_category": "Discrimination in areas of life",
        "question": "Felt discriminated at work",
        "answers": [
            {
                "country": "Spain",
                "country_code": "ES",
                "answer": "Yes",
                "percentage": 21.0,
                "filters": [
                    {"type": "Age", "value": "18-24"},
                    {"type": "Gender Expression", "value": "Trans women"},
                ],
            }
        ],
    }
    collection = MagicMock()
    with patch("app.import_to_db.fra.mongo.get_mongo_collection", return_value=collection):
        insert_indicator_fra_json(payload)

    update = collection.update_one.call_args.args[1]
    assert collection.update_one.call_args.args[0] == {
        "code": "D1_1",
        "category": "Discrimination",
        "specific_category": "Discrimination in areas of life",
        "question": "Felt discriminated at work",
        "survey_year": 2023,
        "value_bucket": collection.update_one.call_args.args[0]["value_bucket"],
    }
    assert isinstance(update, list)
    answer_update = update[0]["$set"]["answers"]
    assert "$let" in answer_update
    incoming = answer_update["$let"]["vars"]["incoming"]["$literal"]
    assert len(incoming) == 1
    assert incoming[0]["identity_key"]
    assert "survey_year" not in incoming[0]


def test_mongo_upsert_keeps_two_editions_of_the_same_indicator_separate() -> None:
    collection = MagicMock()
    requested_collections: list[str] = []
    payload = {
        "code": "D1_1",
        "dataset": "eu_lgbtiq_survey_iii",
        "category": "Discrimination",
        "specific_category": "Area",
        "question": "Question",
        "answers": [
            {
                "country": "Spain",
                "country_code": "ES",
                "answer": "Yes",
                "percentage": 42,
                "filters": [{"type": "All", "value": "All"}],
            }
        ],
    }
    with patch(
        "app.import_to_db.fra.mongo.get_mongo_collection",
        side_effect=lambda name: requested_collections.append(name) or collection,
    ):
        insert_indicator_fra_json({**payload, "survey_year": 2019})
        insert_indicator_fra_json({**payload, "survey_year": 2023})

    assert [call.args[0]["survey_year"] for call in collection.update_one.call_args_list] == [
        2019,
        2023,
    ]
    assert requested_collections == ["Indicator_fra_2019", "Indicator_fra"]
    datasets = [
        call.args[1][0]["$set"]["dataset"]["$literal"]
        for call in collection.update_one.call_args_list
    ]
    assert datasets == ["eu_lgbti_survey_ii", "eu_lgbtiq_survey_iii"]


def test_mongo_groups_same_question_files_into_one_atomic_operation() -> None:
    base = {
        "code": "D1_1",
        "dataset": "eu_lgbtiq_survey_iii",
        "survey_year": 2023,
        "category": "Discrimination",
        "specific_category": "Area",
        "question": "Question",
    }
    documents = [
        {
            **base,
            "answers": [
                {
                    "country": country,
                    "country_code": code,
                    "answer": "Yes",
                    "percentage": percentage,
                    "filters": [{"type": "All", "value": "All"}],
                }
            ],
        }
        for country, code, percentage in (("Spain", "ES", 42), ("France", "FR", 38))
    ]
    collection = MagicMock()
    with patch("app.import_to_db.fra.mongo.get_mongo_collection", return_value=collection):
        assert insert_indicator_fra_json(documents) == 2

    collection.update_one.assert_called_once()
    operation_filter, operation_update = collection.update_one.call_args.args
    incoming = [
        answer
        for answer in operation_update[0]["$set"]["answers"]["$let"]["vars"]["incoming"][
            "$literal"
        ]
    ]
    assert {answer["country_code"] for answer in incoming} == {"ES", "FR"}
    assert "value_bucket" in operation_filter
