from __future__ import annotations

from typing import Any

from flask import Flask

from app.analytics import repository
from app.cache import cache, init_cache


class _AggregateCollection:
    def __init__(self, result: dict[str, Any]) -> None:
        self.result = result
        self.pipeline: list[dict[str, Any]] | None = None

    def aggregate(self, pipeline: list[dict[str, Any]]):
        self.pipeline = pipeline
        return iter([self.result])


class _FindCollection:
    def __init__(self) -> None:
        self.query: dict[str, Any] | None = None
        self.projection: dict[str, int] | None = None

    def find(self, query: dict[str, Any], projection: dict[str, int]):
        self.query = query
        self.projection = projection
        return [
            {
                "code": "D1",
                "category": "Discrimination",
                "question": "Example",
                "survey_year": 2023,
                "answers": [],
            }
        ]


def test_fra_control_catalog_is_aggregated_in_mongodb(monkeypatch) -> None:
    # Arrange
    collection = _AggregateCollection(
        {
            "code": "D1_1",
            "category": "Discrimination",
            "answers": ["No", "Yes", "No"],
            "filters": [
                {"filter_name": "age", "filter_value": "18-24"},
                None,
            ],
        }
    )
    monkeypatch.setattr(repository, "_mongo_collection", lambda _name: collection)

    # Act
    document = repository.get_fra_indicator_control_document.__wrapped__(
        "D1_1", "Discrimination", 2023
    )

    # Assert
    assert document is not None
    assert [row["answer"] for row in document["answers"][:2]] == ["No", "Yes"]
    assert document["answers"][2]["filters"][0]["filter_name"] == "age"
    assert collection.pipeline is not None
    assert collection.pipeline[0] == {
        "$match": {
            "code": "D1_1",
            "category": "Discrimination",
            "survey_year": 2023,
        }
    }
    assert any("$project" in stage for stage in collection.pipeline)


def test_fra_indicator_query_is_scoped_by_year_and_uses_a_projection(monkeypatch) -> None:
    collection = _FindCollection()
    monkeypatch.setattr(repository, "_mongo_collection", lambda _name: collection)

    repository.get_fra_indicator_answers.__wrapped__("D1", "Discrimination", 2023)

    assert collection.query == {
        "code": "D1",
        "category": "Discrimination",
        "survey_year": 2023,
    }
    assert collection.projection is not None
    assert collection.projection["_id"] == 0
    assert set(collection.projection) == {
        "_id",
        "code",
        "category",
        "specific_category",
        "question",
        "survey_year",
        "answers",
    }


def test_source_invalidation_changes_generation_without_global_clear(
    monkeypatch,
) -> None:
    # Arrange
    application = Flask(__name__)
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setenv("APP_ENV", "development")
    init_cache(application)
    cache.set("unrelated", "preserved")
    deleted: list[Any] = []
    monkeypatch.setattr(cache, "delete_memoized", deleted.append)

    # Act
    repository.invalidate_analytics_cache("fra")

    # Assert
    assert repository.analytics_cache_generation("fra") == 1
    assert cache.get("unrelated") == "preserved"
    assert repository.get_fra_indicator_control_document in deleted
    assert repository.get_ilga_document_by_year not in deleted
