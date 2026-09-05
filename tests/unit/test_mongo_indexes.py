from __future__ import annotations

from typing import Any

from pymongo import ASCENDING, IndexModel

from app.infrastructure import mongo_indexes


class FakeCollection:
    def __init__(self, indexes: list[dict[str, Any]]) -> None:
        self.indexes = indexes
        self.created: list[IndexModel] = []
        self.dropped: list[str] = []

    def list_indexes(self) -> list[dict[str, Any]]:
        return self.indexes

    def create_indexes(self, indexes: list[IndexModel]) -> list[str]:
        self.created.extend(indexes)
        for index in indexes:
            self.indexes.append(dict(index.document))
        return [str(index.document.get("name")) for index in indexes]

    def aggregate(self, _pipeline):
        return []

    def drop_index(self, name: str) -> None:
        self.dropped.append(name)
        self.indexes = [index for index in self.indexes if index.get("name") != name]


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
    collection = FakeCollection(
        [{"name": "country_code_1_year_1", "key": {"country_code": 1, "year": 1}}]
    )
    monkeypatch.setattr(mongo_indexes, "get_mongo_collection", lambda _name: collection)

    mongo_indexes._ensure_collection_indexes(
        "country_lgbti_status",
        [
            IndexModel(
                [("country_code", ASCENDING), ("year", ASCENDING)],
                unique=True,
                name="country_year_unique",
            )
        ],
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
    monkeypatch.setattr(mongo_indexes, "_drop_obsolete_indexes", lambda *_args: None)
    mongo_indexes.initialize_mongo_indexes.cache_clear()


def test_fra_unique_identity_includes_value_bucket(monkeypatch) -> None:
    captured: dict[str, list[IndexModel]] = {}
    monkeypatch.setattr(
        mongo_indexes,
        "_ensure_collection_indexes",
        lambda name, indexes: captured.setdefault(name, list(indexes)),
    )
    monkeypatch.setattr(mongo_indexes, "_drop_obsolete_indexes", lambda *_args: None)
    monkeypatch.setattr(mongo_indexes, "migrate_account_security_schema", lambda: None)
    monkeypatch.setattr(mongo_indexes, "spain_report_collection_names", lambda: set())

    mongo_indexes.ensure_fra_indexes()

    unique = next(
        index
        for index in captured["Indicator_fra"]
        if index.document.get("name") == "fra_question_year_bucket_unique"
    )
    assert list(unique.document["key"].items())[-2:] == [
        ("survey_year", 1),
        ("value_bucket", 1),
    ]
    assert unique.document.get("unique") is True

    mongo_indexes.initialize_mongo_indexes()

    fra_indexes = captured["Indicator_fra"]
    category_index = next(
        index
        for index in fra_indexes
        if index.document.get("name") == "fra_category_year_question_code"
    )
    assert list(category_index.document["key"].items()) == [
        ("category", 1),
        ("survey_year", -1),
        ("specific_category", 1),
        ("question", 1),
        ("code", 1),
    ]
    docente_indexes = captured["didactica_docente_games"]
    assert "didactica_progress" not in captured
    assert {index.document.get("name") for index in docente_indexes} == {
        "docente_game_id_unique",
        "docente_game_public_id_unique",
        "docente_games_by_owner",
        "docente_games_by_type",
    }
    owner_index = next(
        index for index in docente_indexes if index.document.get("name") == "docente_games_by_owner"
    )
    assert list(owner_index.document["key"].items()) == [
        ("owner_user_id", 1),
        ("updated_at", -1),
    ]
    ilga_index = captured["Indicator_ilga"][0]
    assert ilga_index.document.get("unique") is True
    mongo_indexes.initialize_mongo_indexes.cache_clear()


def test_removes_only_explicitly_obsolete_indexes(monkeypatch) -> None:
    collection = FakeCollection(
        [
            {"name": "_id_", "key": {"_id": 1}},
            {
                "name": "fra_category_question_code_year",
                "key": {"category": 1, "question": 1, "code": 1, "survey_year": -1},
            },
            {"name": "fra_category_year_question_code", "key": {"category": 1}},
        ]
    )
    monkeypatch.setattr(mongo_indexes, "get_mongo_collection", lambda _name: collection)

    mongo_indexes._drop_obsolete_indexes("Indicator_fra", {"fra_category_question_code_year"})

    assert collection.dropped == ["fra_category_question_code_year"]
    assert any(index["name"] == "fra_category_year_question_code" for index in collection.indexes)


def test_ilga_index_upgrade_checks_duplicates_before_replacing_non_unique(monkeypatch) -> None:
    collection = FakeCollection(
        [
            {"name": "_id_", "key": {"_id": 1}},
            {"name": "dataset_1_year_-1", "key": {"dataset": 1, "year": -1}},
        ]
    )
    monkeypatch.setattr(mongo_indexes, "get_mongo_collection", lambda _name: collection)

    mongo_indexes.ensure_ilga_unique_index()

    assert collection.dropped == ["dataset_1_year_-1"]
    created = collection.created[0].document
    assert created["key"] == {"dataset": 1, "year": -1}
    assert created["unique"] is True


def test_felgtbi_indexes_match_catalog_navigation_and_indicator_queries() -> None:
    # Arrange / Act
    indexes = {
        str(index.document["name"]): list(index.document["key"].items())
        for index in mongo_indexes.felgtbi_index_models()
    }

    # Assert
    assert indexes == {
        "felgtbi_year_documents": [
            ("source", 1),
            ("year", -1),
            ("source_document_id", 1),
        ],
        "felgtbi_document_navigation": [
            ("source", 1),
            ("source_document_id", 1),
            ("page", 1),
            ("code", 1),
        ],
        "felgtbi_document_indicator": [
            ("source", 1),
            ("source_document_id", 1),
            ("code", 1),
        ],
    }
