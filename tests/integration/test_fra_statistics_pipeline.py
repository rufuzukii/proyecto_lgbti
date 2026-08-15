from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace
from typing import Any, cast

from flask import Flask

from app.analytics import repository
from app.analytics.geography_service import prepare_europe_map_data
from app.analytics.statistics_charts import build_europe_choropleth
from app.analytics.statistics_models import FraStatisticsQuery
from app.analytics.statistics_service import get_fra_statistics
from app.cache import init_cache
from app.import_to_db.fra import mongo as fra_mongo
from app.import_to_db.fra import parse_fra_csv_text


class InMemoryFraCollection:
    def __init__(self) -> None:
        self.documents: list[dict[str, Any]] = []
        self.find_calls = 0

    def update_one(self, query, update, *, upsert=False):
        document = next(
            (
                item
                for item in self.documents
                if all(
                    item.get(key) == value
                    for key, value in query.items()
                    if key != "answers.identity_key"
                )
            ),
            None,
        )
        identity_condition = query.get("answers.identity_key")
        if document is not None and isinstance(identity_condition, dict):
            excluded = set(identity_condition.get("$nin", []))
            if any(answer.get("identity_key") in excluded for answer in document.get("answers", [])):
                document = None
        if document is None and upsert:
            document = dict(query)
            self.documents.append(document)
        if document is None:
            return SimpleNamespace(matched_count=0)
        if isinstance(update, list):
            set_stage = update[0]["$set"]
            for key, expression in set_stage.items():
                if key == "answers":
                    continue
                document[key] = deepcopy(expression["$literal"])
            incoming = set_stage["answers"]["$let"]["vars"]["incoming"]["$literal"]
            answers = document.setdefault("answers", [])
            for answer in incoming:
                existing_index = next(
                    (
                        index
                        for index, existing in enumerate(answers)
                        if existing.get("identity_key") == answer.get("identity_key")
                    ),
                    None,
                )
                if existing_index is None:
                    answers.append(deepcopy(answer))
                else:
                    answers[existing_index] = deepcopy(answer)
            return SimpleNamespace(matched_count=1)
        document.update(deepcopy(update.get("$set", {})))
        incoming_answers = [
            *update.get("$addToSet", {}).get("answers", {}).get("$each", []),
            *update.get("$push", {}).get("answers", {}).get("$each", []),
        ]
        for answer in incoming_answers:
            if answer not in document.setdefault("answers", []):
                document["answers"].append(deepcopy(answer))
        return SimpleNamespace(matched_count=1)

    def bulk_write(self, operations, *, ordered=False):
        assert ordered is False
        for operation in operations:
            self.update_one(operation._filter, operation._doc, upsert=operation._upsert)
        return SimpleNamespace()

    def find(self, query, _projection):
        self.find_calls += 1
        return [
            deepcopy(document)
            for document in self.documents
            if all(document.get(key) == value for key, value in query.items())
        ]

    def distinct(self, field, _query):
        return list({document.get(field) for document in self.documents})

    def aggregate(self, pipeline, **_kwargs):
        query = pipeline[0].get("$match", {})
        rows = [
            document
            for document in self.documents
            if all(
                document.get(key) == value
                for key, value in query.items()
                if key in {"category", "survey_year", "code"} and not isinstance(value, dict)
            )
        ]
        if any("$group" in stage and isinstance(stage["$group"].get("_id"), dict) for stage in pipeline):
            unique = {}
            for document in rows:
                key = (
                    document.get("code"),
                    document.get("category"),
                    document.get("specific_category"),
                    document.get("question"),
                )
                unique[key] = {
                    "code": key[0],
                    "category": key[1],
                    "specific_category": key[2],
                    "question": key[3],
                }
            return list(unique.values())
        return []


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


def _social_attitudes_csv() -> str:
    return '''country,topic,question,answer,percentage,question_code
Spain,Social attitudes and government response,Government response > Effectiveness of government,Yes,42.5,D5
France,Social attitudes and government response,Government response > Effectiveness of government,Yes,38,D5
Source:,"EU LGBTIQ Survey III, 2023",,,,
'''


def _ranked_reason_csv() -> str:
    return '''country,topic,question,answer,percentage,question_code
Spain,Living openly as LGBTIQ,Reason for housing difficulties > sexual orientation,1st,12,G22_A
Spain,Living openly as LGBTIQ,Reason for housing difficulties > sexual orientation,2nd,8,G22_A
Spain,Living openly as LGBTIQ,Reason for housing difficulties > sexual orientation,3rd,5,G22_A
Spain,Living openly as LGBTIQ,Reason for housing difficulties > sexual orientation,Not Selected,75,G22_A
France,Living openly as LGBTIQ,Reason for housing difficulties > sexual orientation,1st,10,G22_A
France,Living openly as LGBTIQ,Reason for housing difficulties > sexual orientation,2nd,9,G22_A
France,Living openly as LGBTIQ,Reason for housing difficulties > sexual orientation,3rd,6,G22_A
France,Living openly as LGBTIQ,Reason for housing difficulties > sexual orientation,Not Selected,75,G22_A
Source:,"EU LGBTIQ Survey III, 2023",,,,
'''


def _education_bathroom_csv() -> str:
    return '''country,topic,question,answer,Gender Expression,percentage,question_code
Spain,Education,Problems when going to bathroom and changing rooms at school,Always,Cisgender men,12,C9_E
Spain,Education,Problems when going to bathroom and changing rooms at school,Never,,50,C9_E
Spain,Education,Problems when going to bathroom and changing rooms at school,Often,,20,C9_E
Spain,Education,Problems when going to bathroom and changing rooms at school,Rarely,,18,C9_E
Source:,"EU LGBTIQ Survey III, 2023",,,,,
'''


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


def test_reimport_updates_same_natural_answer_without_duplication(monkeypatch) -> None:
    collection = InMemoryFraCollection()
    monkeypatch.setattr(fra_mongo, "get_mongo_collection", lambda _name: collection)

    fra_mongo.insert_indicator_fra_json(parse_fra_csv_text(_csv(62), file_name="fra.csv"))
    fra_mongo.insert_indicator_fra_json(parse_fra_csv_text(_csv(70), file_name="fra.csv"))

    answers = collection.documents[0]["answers"]
    spain = [answer for answer in answers if answer["country_code"] == "ES"]
    assert len(spain) == 1
    assert spain[0]["percentage"] == 70


def test_query_cache_geopandas_and_map_pipeline_reuses_database_result(monkeypatch) -> None:
    # Arrange
    collection = InMemoryFraCollection()
    monkeypatch.setattr(fra_mongo, "get_mongo_collection", lambda _name: collection)
    monkeypatch.setattr(repository, "_mongo_collection", lambda _name: collection)
    app = Flask("fra-map-integration")
    init_cache(app)
    fra_mongo.insert_indicator_fra_json(parse_fra_csv_text(_csv(), file_name="fra.csv"))

    # Act
    with app.app_context():
        first = get_fra_statistics(_query())
        calls_after_first_query = collection.find_calls
        second = get_fra_statistics(_query())
        geography = prepare_europe_map_data(second["ranking"])
        figure = build_europe_choropleth(second["ranking"], source="fra")

    # Assert
    assert first == second
    assert collection.find_calls == calls_after_first_query
    assert len(geography.rows) == 49
    map_trace = cast(Any, figure.data[0])
    assert len(map_trace.locations) == 49
    assert map_trace.geojson == geography.geojson


def test_social_attitudes_csv_to_mongo_catalog_and_statistics(monkeypatch) -> None:
    collection = InMemoryFraCollection()
    monkeypatch.setattr(fra_mongo, "get_mongo_collection", lambda _name: collection)
    monkeypatch.setattr(repository, "_mongo_collection", lambda _name: collection)
    app = Flask("fra-social-attitudes-integration")
    init_cache(app)

    payload = parse_fra_csv_text(_social_attitudes_csv(), file_name="social-attitudes.csv")
    fra_mongo.insert_indicator_fra_json(payload)

    with app.app_context():
        categories = repository.get_fra_categories(2023)
        indicators = repository.get_fra_mongo_indicators_by_category(
            "Social attitudes and government response", 2023
        )
        result = get_fra_statistics(
            FraStatisticsQuery(
                year=2023,
                category="Social attitudes and government response",
                question_code="D5",
                answer="Yes",
                filter_a_name="All",
                filter_a_value="All",
                filter_b_name="All",
                filter_b_value="All",
            )
        )

    assert "Social attitudes and government response" in categories
    assert [(item.code, item.question) for item in indicators] == [
        ("D5", "Effectiveness of government")
    ]
    assert result["status"] == "ok"
    assert [(row["iso"], row["value"]) for row in result["ranking"]] == [
        ("ES", 42.5),
        ("FR", 38.0),
    ]


def test_ranked_reason_csv_to_mongo_statistics_preserves_categorical_responses(
    monkeypatch,
) -> None:
    collection = InMemoryFraCollection()
    monkeypatch.setattr(fra_mongo, "get_mongo_collection", lambda _name: collection)
    monkeypatch.setattr(repository, "_mongo_collection", lambda _name: collection)
    app = Flask("fra-ranked-reason-integration")
    init_cache(app)

    payload = parse_fra_csv_text(_ranked_reason_csv(), file_name="ranked-reason.csv")
    fra_mongo.insert_indicator_fra_json(payload)
    with app.app_context():
        result = get_fra_statistics(
            FraStatisticsQuery(
                year=2023,
                category="Living openly as LGBTIQ",
                question_code="G22_A",
                answer="1st",
                filter_a_name="All",
                filter_a_value="All",
                filter_b_name="All",
                filter_b_value="All",
            )
        )

    stored_answers = {answer["answer"] for document in collection.documents for answer in document["answers"]}
    assert stored_answers == {"1st", "2nd", "3rd", "Not Selected"}
    assert result["status"] == "ok"
    assert result["response_type"] == "ranked_reason"
    assert [(row["iso"], row["value"]) for row in result["ranking"]] == [
        ("ES", 12.0),
        ("FR", 10.0),
    ]


def test_education_bathroom_all_all_ignores_answers_only_published_for_a_segment(
    monkeypatch,
) -> None:
    collection = InMemoryFraCollection()
    monkeypatch.setattr(fra_mongo, "get_mongo_collection", lambda _name: collection)
    monkeypatch.setattr(repository, "_mongo_collection", lambda _name: collection)
    app = Flask("fra-education-all-all-integration")
    init_cache(app)
    payload = parse_fra_csv_text(_education_bathroom_csv(), file_name="education.csv")
    fra_mongo.insert_indicator_fra_json(payload)

    with app.app_context():
        result = get_fra_statistics(
            FraStatisticsQuery(
                year=2023,
                category="Education",
                question_code="C9_E",
                answer=None,
                filter_a_name="All",
                filter_a_value="All",
                filter_b_name="All",
                filter_b_value="All",
            )
        )

    assert result["status"] == "ok"
    assert result["answer"] == "Often"
    assert [(row["iso"], row["value"]) for row in result["ranking"]] == [("ES", 20.0)]
