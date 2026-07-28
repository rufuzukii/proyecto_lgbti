from __future__ import annotations

from typing import Any

from pymongo import ASCENDING, IndexModel

from app import mongo_indexes


class FakeCollection:
    def __init__(self, indexes: list[dict[str, Any]]) -> None:
        self.indexes = indexes
        self.created: list[IndexModel] = []

    def list_indexes(self) -> list[dict[str, Any]]:
        return self.indexes

    def create_indexes(self, indexes: list[IndexModel]) -> list[str]:
        self.created.extend(indexes)
        for index in indexes:
            self.indexes.append(dict(index.document))
        return [str(index.document.get("name")) for index in indexes]


def test_reuses_equivalent_index_with_a_different_name(monkeypatch) -> None:
    collection = FakeCollection([{"name": "code_1", "key": {"code": 1}, "v": 2}])
    monkeypatch.setattr(mongo_indexes, "get_mongo_collection", lambda _name: collection)

    mongo_indexes._ensure_collection_indexes(
        "Indicator_fra",
        [IndexModel([("code", ASCENDING)], name="fra_code")],
    )

    assert collection.created == []


def test_creates_index_when_its_key_does_not_exist(monkeypatch) -> None:
    collection = FakeCollection([{"name": "_id_", "key": {"_id": 1}, "v": 2}])
    monkeypatch.setattr(mongo_indexes, "get_mongo_collection", lambda _name: collection)

    mongo_indexes._ensure_collection_indexes(
        "Indicator_fra",
        [IndexModel([("code", ASCENDING)], name="fra_code")],
    )

    assert [index.document.get("name") for index in collection.created] == ["fra_code"]


def test_does_not_replace_an_incompatible_existing_index(monkeypatch, caplog) -> None:
    collection = FakeCollection([{"name": "country_code_1_year_1", "key": {"country_code": 1, "year": 1}}])
    monkeypatch.setattr(mongo_indexes, "get_mongo_collection", lambda _name: collection)

    mongo_indexes._ensure_collection_indexes(
        "country_lgbti_status",
        [IndexModel([("country_code", ASCENDING), ("year", ASCENDING)], unique=True, name="country_year_unique")],
    )

    assert collection.created == []
    assert "mongo_index_definition_conflict" in caplog.text


def test_fra_category_selector_uses_a_covered_compound_index(monkeypatch) -> None:
    captured: dict[str, list[IndexModel]] = {}
    monkeypatch.setattr(
        mongo_indexes,
        "_ensure_collection_indexes",
        lambda name, indexes: captured.setdefault(name, list(indexes)),
    )
    monkeypatch.setattr(mongo_indexes, "spain_report_collection_names", lambda: set())
    mongo_indexes.initialize_mongo_indexes.cache_clear()

    mongo_indexes.initialize_mongo_indexes()

    fra_indexes = captured["Indicator_fra"]
    category_index = next(
        index
        for index in fra_indexes
        if index.document.get("name") == "fra_category_question_code"
    )
    assert list(category_index.document["key"].items()) == [
        ("category", 1),
        ("specific_category", 1),
        ("question", 1),
        ("code", 1),
    ]
    mongo_indexes.initialize_mongo_indexes.cache_clear()
