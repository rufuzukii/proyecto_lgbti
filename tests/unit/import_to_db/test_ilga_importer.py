from unittest.mock import MagicMock, patch

from app.import_to_db.ilga import parse_ilga_csv_text, parse_ilga_json_text
from app.import_to_db.ilga.mongo import insert_indicator_ilga_json


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


def test_ilga_mongo_upserts_indicator_ilga_by_year() -> None:
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
    with patch("app.import_to_db.ilga.mongo.get_mongo_collection", return_value=collection):
        insert_indicator_ilga_json(payload)

    query, update = collection.update_one.call_args.args[:2]
    assert query == {"dataset": "ilga_rainbow_map", "year": 2026}
    assert update["$setOnInsert"]["countries"] == payload["countries"]
    assert type(update["$setOnInsert"]["_id"]).__name__ == "ObjectId"
    assert "$set" not in update


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
    with patch("app.import_to_db.ilga.mongo.get_mongo_collection", return_value=collection):
        insert_indicator_ilga_json(payload)

    query, update = collection.update_one.call_args.args[:2]
    assert query == {"dataset": "ilga_rainbow_map", "year": 2025}
    assert update["$setOnInsert"]["countries"] == [
        {
            "country": "Malta",
            "ranking": 89.0,
            "criteria": None,
            "country_code": "MT",
        }
    ]
