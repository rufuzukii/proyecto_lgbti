import json
from unittest.mock import MagicMock, patch

import pytest

from app.modules.imports.ilga import IlgaValidationError, parse_ilga_csv_text, parse_ilga_json_text
from app.modules.imports.ilga.mongo import insert_indicator_ilga_json


def test_ilga_csv_creates_one_document_grouped_by_year() -> None:
    csv_text = """,,RANKING,Equality & non-discrimination,Family
,,,Employment (sexual orientation),Marriage equality
,,,"1,10%","3,75%"
AT,Austria,"54,98",1,1
ES,Spain,"77,97",1,1
"""

    payload = parse_ilga_csv_text(
        csv_text,
        file_name="rainbow-map-2026-1.csv",
    )

    assert payload["dataset"] == "ilga_rainbow_map"
    assert payload["year"] == 2026
    assert len(payload["id"]) == 24
    assert len(payload["countries"]) == 2
    assert payload["countries"][0]["ranking"] == 54.98
    assert payload["countries"][0]["criteria"][0] == {
        "category": "Equality & non-discrimination",
        "indicator": "Employment (sexual orientation)",
        "weight": 1.1,
        "value": 1.0,
    }


def test_ilga_mongo_bulk_inserts_without_upsert() -> None:
    payload = {
        "id": "665f1f3f9b9f7a2f4b7a0b11",
        "dataset": "ilga_rainbow_map",
        "year": 2026,
        "countries": [
            {
                "country_code": "AT",
                "country": "Austria",
                "ranking": 54.98,
                "criteria": [],
            }
        ],
    }
    collection = MagicMock()
    collection.find.return_value = []
    collection.bulk_write.return_value.inserted_count = 1
    with patch("app.modules.imports.ilga.mongo.get_mongo_collection", return_value=collection):
        inserted = insert_indicator_ilga_json(payload)

    assert inserted == 1
    operations = collection.bulk_write.call_args.args[0]
    document = operations[0]._doc
    assert document["countries"] == payload["countries"]
    assert type(document["_id"]).__name__ == "ObjectId"
    assert collection.update_one.call_count == 0


def test_ilga_json_with_global_criteria_is_normalized_to_ranking() -> None:
    json_text = """
{
  "year": 2025,
  "dataset": "ilga_rainbow_map",
  "countries": [
    { "country": "Malta", "criteria": 89, "country_code": "MT" },
    { "country": "Belgium", "ranking": 85, "criteria": null, "country_code": "BE" }
  ]
}
"""

    payload = parse_ilga_json_text(json_text)

    assert isinstance(payload, dict)
    assert payload["dataset"] == "ilga_rainbow_map"
    assert payload["year"] == 2025
    assert payload["countries"][0] == {
        "country": "Malta",
        "ranking": 89.0,
        "criteria": None,
        "country_code": "MT",
    }
    assert payload["countries"][1] == {
        "country": "Belgium",
        "ranking": 85.0,
        "criteria": None,
        "country_code": "BE",
    }
    assert payload["normalization"] == {"applied": False}


def test_ilga_mongo_accepts_legacy_global_json_shape() -> None:
    payload = {
        "id": "665f1f3f9b9f7a2f4b7a0b11",
        "dataset": "ilga_rainbow_map",
        "year": 2025,
        "countries": [
            {
                "country": "Malta",
                "criteria": 89,
                "country_code": "MT",
            }
        ],
    }
    collection = MagicMock()
    collection.find.return_value = []
    collection.bulk_write.return_value.inserted_count = 1
    with patch("app.modules.imports.ilga.mongo.get_mongo_collection", return_value=collection):
        insert_indicator_ilga_json(payload)

    document = collection.bulk_write.call_args.args[0][0]._doc
    assert document["countries"] == [
        {
            "country": "Malta",
            "ranking": 89.0,
            "criteria": None,
            "country_code": "MT",
        }
    ]


@pytest.mark.parametrize(
    ("mutation", "expected_error"),
    [
        (lambda payload: payload.pop("year"), "missing_year"),
        (lambda payload: payload.update(dataset="other"), "invalid_dataset"),
        (
            lambda payload: payload["countries"].append(dict(payload["countries"][0])),
            "duplicate_country_codes:ES",
        ),
        (
            lambda payload: payload["countries"][0].update(country_code="ZZ"),
            "invalid_country_code:ZZ",
        ),
        (
            lambda payload: payload["countries"][0].update(criteria="79.17"),
            "invalid_criteria",
        ),
    ],
)
def test_ilga_json_rejects_invalid_historical_payloads(mutation, expected_error) -> None:
    payload = {
        "year": 2011,
        "dataset": "ilga_rainbow_map",
        "countries": [{"country": "Spain", "country_code": "ES", "criteria": 79.17}],
    }
    mutation(payload)

    with pytest.raises(IlgaValidationError) as exc_info:
        parse_ilga_json_text(json.dumps(payload), file_name="rainbow-map-2011.json")

    assert any(error.endswith(expected_error) for error in exc_info.value.errors)


def test_ilga_json_rejects_filename_year_mismatch() -> None:
    payload = {
        "year": 2012,
        "dataset": "ilga_rainbow_map",
        "countries": [{"country": "Spain", "country_code": "ES", "criteria": 70}],
    }

    with pytest.raises(IlgaValidationError) as exc_info:
        parse_ilga_json_text(json.dumps(payload), file_name="rainbow-map-2011.json")

    assert "filename_year_mismatch:2011" in exc_info.value.errors


@pytest.mark.parametrize(
    ("year", "original_min", "original_max", "score"),
    [(2011, -7, 17, 79.17), (2012, -12, 30, 71.43)],
)
def test_legacy_scales_keep_json_score_and_add_annual_metadata(
    year: int,
    original_min: int,
    original_max: int,
    score: float,
) -> None:
    payload = parse_ilga_json_text(
        json.dumps(
            {
                "year": year,
                "dataset": "ilga_rainbow_map",
                "countries": [
                    {"country": "Spain", "country_code": "ES", "criteria": score}
                ],
            }
        ),
        file_name=f"rainbow-map-{year}.json",
    )

    assert isinstance(payload, dict)
    assert payload["countries"][0]["ranking"] == score
    assert payload["normalization"] == {
        "applied": True,
        "method": "linear_min_max",
        "original_min": original_min,
        "original_max": original_max,
        "target_min": 0,
        "target_max": 100,
    }


def test_repeated_ilga_import_is_skipped_without_writes() -> None:
    payload = {
        "dataset": "ilga_rainbow_map",
        "year": 2025,
        "countries": [{"country": "Spain", "country_code": "ES", "criteria": 78}],
    }
    first_collection = MagicMock()
    first_collection.find.return_value = []
    first_collection.bulk_write.return_value.inserted_count = 1
    with patch(
        "app.modules.imports.ilga.mongo.get_mongo_collection",
        return_value=first_collection,
    ):
        assert insert_indicator_ilga_json(payload) == 1
    stored_document = first_collection.bulk_write.call_args.args[0][0]._doc

    second_collection = MagicMock()
    second_collection.find.return_value = [stored_document]
    with patch(
        "app.modules.imports.ilga.mongo.get_mongo_collection",
        return_value=second_collection,
    ):
        assert insert_indicator_ilga_json(payload) == 0

    second_collection.bulk_write.assert_not_called()
    second_collection.update_one.assert_not_called()
