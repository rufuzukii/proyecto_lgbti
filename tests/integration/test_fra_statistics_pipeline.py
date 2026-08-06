from __future__ import annotations

from copy import deepcopy
from typing import Any

from flask import Flask

from app.analytics import repository
from app.analytics.statistics_models import FraStatisticsQuery
from app.analytics.statistics_service import get_fra_statistics
from app.cache import init_cache
from app.import_to_db.fra import mongo as fra_mongo
from app.import_to_db.fra import parse_fra_csv_text


class InMemoryFraCollection:
    def __init__(self) -> None:
        self.documents: list[dict[str, Any]] = []

    def update_one(self, query, update, *, upsert=False):
        document = next(
            (item for item in self.documents if all(item.get(key) == value for key, value in query.items())),
            None,
        )
        if document is None and upsert:
            document = dict(query)
            self.documents.append(document)
        assert document is not None
        document.update(deepcopy(update.get("$set", {})))
        for answer in update.get("$addToSet", {}).get("answers", {}).get("$each", []):
            if answer not in document.setdefault("answers", []):
                document["answers"].append(deepcopy(answer))

    def find(self, query, _projection):
        return [
            deepcopy(document)
            for document in self.documents
            if all(document.get(key) == value for key, value in query.items())
        ]

    def distinct(self, field, _query):
        return list({document.get(field) for document in self.documents})


def _csv(value_spain: int = 62) -> str:
    return f'''country,topic,question,answer,percentage,question_code
Spain,Discrimination,Work > Felt discriminated at work,Yes,{value_spain},D1
France,Discrimination,Work > Felt discriminated at work,Yes,48,D1
Source:,"EU LGBTIQ Survey III, 2023",,,,
'''


def _query() -> FraStatisticsQuery:
    return FraStatisticsQuery(
        year=2023,
        category="Discrimination",
        question_code="D1",
        answer="Yes",
        filter_a_name="All",
        filter_a_value="All",
        filter_b_name="All",
        filter_b_value="All",
    )


def test_fra_import_normalization_persistence_and_statistics_query(monkeypatch) -> None:
    # Arrange
    collection = InMemoryFraCollection()
    monkeypatch.setattr(fra_mongo, "get_mongo_collection", lambda _name: collection)
    monkeypatch.setattr(repository, "_mongo_collection", lambda _name: collection)
    app = Flask("fra-integration")
    init_cache(app)

    # Act
    payload = parse_fra_csv_text(_csv(), file_name="fra-survey.csv")
    inserted = fra_mongo.insert_indicator_fra_json(payload)
    with app.app_context():
        result = get_fra_statistics(_query())

    # Assert
    assert inserted == 1
    assert collection.documents[0]["survey_year"] == 2023
    assert result["status"] == "ok"
    assert [(row["iso"], row["value"]) for row in result["ranking"]] == [
        ("ES", 62.0),
        ("FR", 48.0),
    ]


def test_statistics_cache_is_invalidated_after_the_persisted_data_changes(monkeypatch) -> None:
    # Arrange
    collection = InMemoryFraCollection()
    monkeypatch.setattr(fra_mongo, "get_mongo_collection", lambda _name: collection)
    monkeypatch.setattr(repository, "_mongo_collection", lambda _name: collection)
    app = Flask("fra-cache-integration")
    init_cache(app)
    fra_mongo.insert_indicator_fra_json(parse_fra_csv_text(_csv(), file_name="fra.csv"))

    # Act
    with app.app_context():
        before = get_fra_statistics(_query())
        collection.documents[0]["answers"][0]["percentage"] = 70.0
        cached = get_fra_statistics(_query())
        repository.invalidate_analytics_cache()
        refreshed = get_fra_statistics(_query())

    # Assert
    assert before["ranking"][0]["value"] == 62.0
    assert cached["ranking"][0]["value"] == 62.0
    assert refreshed["ranking"][0]["value"] == 70.0
