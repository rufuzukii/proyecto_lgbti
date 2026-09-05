from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Self, cast

import pytest

from app.core.errors import DatabaseUnavailableError
from app.shared.data import repository


class _Result:
    def __init__(self, *, rows=None, row=None) -> None:
        self.rows = rows or []
        self.row = row

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.row


class _Postgres:
    def __init__(self, result: _Result | None = None, error: Exception | None = None) -> None:
        self.result = result or _Result()
        self.error = error

    def __enter__(self) -> Self:
        if self.error:
            raise self.error
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, *_args, **_kwargs):
        return self.result


class _Cursor(list):
    def sort(self, *_args, **_kwargs):
        return self


class _Collection:
    def __init__(self) -> None:
        self.distinct_values: list[Any] = []
        self.aggregate_rows: list[dict[str, Any]] = []
        self.find_rows: list[dict[str, Any]] = []
        self.find_one_row: dict[str, Any] | None = None
        self.error: Exception | None = None
        self.calls: list[tuple[str, Any]] = []
        self.matched_count = 1

    def _raise(self):
        if self.error:
            raise self.error

    def distinct(self, field, query):
        self._raise()
        self.calls.append(("distinct", (field, query)))
        return self.distinct_values

    def aggregate(self, pipeline, **kwargs):
        self._raise()
        self.calls.append(("aggregate", (pipeline, kwargs)))
        return iter(self.aggregate_rows)

    def find(self, query, projection, **kwargs):
        self._raise()
        self.calls.append(("find", (query, projection, kwargs)))
        return _Cursor(self.find_rows)

    def find_one(self, query, projection, **kwargs):
        self._raise()
        self.calls.append(("find_one", (query, projection, kwargs)))
        return self.find_one_row

    def update_one(self, query, update, **kwargs):
        self._raise()
        self.calls.append(("update_one", (query, update, kwargs)))
        return SimpleNamespace(matched_count=self.matched_count)


def test_postgres_catalogs_map_valid_rows_and_fail_closed(monkeypatch) -> None:
    rows = [
        {"name": "Employment"},
        {"name": ""},
    ]
    monkeypatch.setattr(
        repository, "postgres_connection", lambda **_kwargs: _Postgres(_Result(rows=rows))
    )
    assert repository.get_categories.uncached() == ["Employment"]

    indicator_rows = [
        {"code": "E1", "category": "Employment", "specific_category": "Work", "question": "Safe?"},
        {"code": "X", "category": "Source:", "specific_category": "", "question": "Ignore"},
    ]
    monkeypatch.setattr(
        repository,
        "postgres_connection",
        lambda **_kwargs: _Postgres(_Result(rows=indicator_rows)),
    )
    indicators = repository.get_fra_indicators.uncached()
    assert [(item.code, item.label) for item in indicators] == [("E1", "Employment · Work · Safe?")]

    monkeypatch.setattr(
        repository,
        "postgres_connection",
        lambda **_kwargs: _Postgres(error=RuntimeError("offline")),
    )
    assert repository.get_categories.uncached() == []
    assert repository.get_fra_indicators.uncached() == []


def test_fra_category_catalog_builds_query_and_maps_rows(monkeypatch) -> None:
    collection = _Collection()
    collection.aggregate_rows = [
        {"code": "E2", "category": "Employment", "specific_category": None, "question": "Q"},
        {"code": "", "category": "Employment", "question": "ignored"},
    ]
    monkeypatch.setattr(repository, "_mongo_collection", lambda _name: collection)

    assert repository.get_fra_mongo_indicators_by_category.uncached("", 2023) == []
    indicators = repository.get_fra_mongo_indicators_by_category.uncached(" Employment ", 2023)

    assert [item.code for item in indicators] == ["E2"]
    match = collection.calls[0][1][0][0]["$match"]
    assert match["category"] == "Employment"
    assert match["survey_year"] == 2023
    collection.error = RuntimeError("mongo offline")
    assert repository.get_fra_mongo_indicators_by_category.uncached("Employment", 2023) == []


def test_fra_answers_merge_documents_and_keep_real_zero(monkeypatch) -> None:
    collection = _Collection()
    collection.find_rows = [
        {
            "code": "E1",
            "category": "Employment",
            "survey_year": 2023,
            "answers": [{"country": "Spain", "answer": "Yes", "percentage": 0.0}, None],
        },
        {"code": "E1", "answers": [{"country": "France", "answer": "Yes", "percentage": 50}]},
    ]
    monkeypatch.setattr(repository, "_mongo_collection", lambda _name: collection)

    assert repository.get_fra_indicator_answers.__wrapped__("", None, 2023) is None
    document = repository.get_fra_indicator_answers.__wrapped__(" E1 ", "Employment", 2023)

    assert document is not None
    assert [answer["percentage"] for answer in document["answers"]] == [0.0, 50]
    query = collection.calls[0][1][0]
    assert query == {"code": "E1", "category": "Employment", "survey_year": 2023}
    collection.find_rows = []
    assert repository.get_fra_indicator_answers.__wrapped__("E1") is None
    collection.error = RuntimeError("offline")
    assert repository.get_fra_indicator_answers.__wrapped__("E1") is None


def test_fra_control_catalog_maps_answer_specific_filters(monkeypatch) -> None:
    collection = _Collection()
    collection.aggregate_rows = [
        {
            "category": "Employment",
            "question": "Question",
            "answers": ["No", "Yes"],
            "filters": [],
            "answer_filters": [
                {"answer": "Yes", "type": "Age", "value": "18-24"},
                {"answer": "", "type": "Age", "value": "25-39"},
                "bad",
            ],
        }
    ]
    monkeypatch.setattr(repository, "_mongo_collection", lambda _name: collection)

    result = repository.get_fra_indicator_control_document.__wrapped__("E1", None, 2023)

    assert result is not None
    assert result["answers"] == [
        {"answer": "Yes", "country": "catalog", "filters": [{"type": "Age", "value": "18-24"}]}
    ]
    assert result["global_answers"] == []
    collection.aggregate_rows = []
    assert repository.get_fra_indicator_control_document.__wrapped__("E1") is None
    collection.error = RuntimeError("offline")
    assert repository.get_fra_indicator_control_document.__wrapped__("E1") is None


def test_fra_multi_document_query_deduplicates_codes_and_ignores_malformed_rows(
    monkeypatch,
) -> None:
    collection = _Collection()
    collection.find_rows = [
        {"code": "A", "question": "One", "answers": [{"percentage": 0}, "bad"]},
        {"code": "A", "answers": [{"percentage": 25}]},
        {"code": "", "answers": []},
    ]
    monkeypatch.setattr(repository, "_mongo_collection", lambda _name: collection)

    assert repository.get_fra_indicator_documents.__wrapped__(("",)) == []
    result = repository.get_fra_indicator_documents.__wrapped__(("A", "A", "B"), 2023)

    assert [item["code"] for item in result] == ["A"]
    assert [answer["percentage"] for answer in result[0]["answers"]] == [0, 25]
    assert collection.calls[0][1][0] == {"code": {"$in": ["A", "B"]}, "survey_year": 2023}
    collection.error = RuntimeError("offline")
    assert repository.get_fra_indicator_documents.__wrapped__(("A",), 2023) == []


def test_fra_years_normalize_ranges_duplicates_and_errors(monkeypatch) -> None:
    collection = _Collection()
    collection.distinct_values = [2023, "2019", 2023, "bad", 1989, 2101, None]
    monkeypatch.setattr(repository, "_mongo_collection", lambda _name: collection)

    assert repository.get_fra_years.uncached(" E1 ") == [2023, 2019]
    assert all(call[1][1] == {"code": "E1"} for call in collection.calls)
    collection.error = RuntimeError("offline")
    assert repository.get_fra_years.uncached() == []


def test_ilga_criteria_catalog_ignores_malformed_and_deduplicates(monkeypatch) -> None:
    document = {
        "countries": [
            {
                "criteria": [
                    {"category": "Family", "indicator": "Marriage", "weight": 2},
                    {"category": "Family", "indicator": "Marriage", "weight": 9},
                    {"category": "", "indicator": "No category"},
                    "bad",
                ]
            },
            {"criteria": "bad"},
            "bad",
        ]
    }
    monkeypatch.setattr(repository, "get_ilga_document_by_year", lambda _year: document)

    assert repository.get_ilga_criteria_categories_by_year.uncached(2026) == ["Family"]
    criteria = repository.get_ilga_criteria_by_year.uncached(2026, "Family")
    assert criteria == [
        {"category": "Family", "indicator": "Marriage", "weight": 2, "description": ""}
    ]
    monkeypatch.setattr(repository, "get_ilga_document_by_year", lambda _year: None)
    assert repository.get_ilga_criteria_categories_by_year.uncached() == []
    assert repository.get_ilga_criteria_by_year.uncached() == []


def test_ilga_storage_catalogs_map_years_latest_and_failures(monkeypatch) -> None:
    collection = _Collection()
    collection.distinct_values = [2026, "2025", "bad"]
    collection.find_one_row = {"dataset": "ilga_rainbow_map", "year": 2026, "countries": []}
    monkeypatch.setattr(repository, "_mongo_collection", lambda _name: collection)

    assert repository.get_ilga_years.uncached() == [2026, 2025]
    assert repository.get_ilga_document_by_year.uncached("bad") == collection.find_one_row
    assert repository.get_ilga_document_by_year.uncached(2026) == collection.find_one_row
    assert repository.get_latest_ilga_document.uncached() == collection.find_one_row
    collection.error = RuntimeError("offline")
    assert repository.get_ilga_years.uncached() == []
    assert repository.get_ilga_document_by_year.uncached(2026) is None
    with pytest.raises(DatabaseUnavailableError):
        repository.get_ilga_document_by_year.uncached(2026, raise_on_error=True)
    assert repository.get_latest_ilga_document.uncached() is None


def test_ilga_overall_rows_flatten_countries_and_preserve_zero_scores() -> None:
    collection = _Collection()
    collection.find_rows = [
        {
            "_id": "doc-1",
            "year": 2025,
            "normalization": "percentage",
            "countries": [
                {"country_code": "ES", "country": "Spain", "ranking": 0},
                "bad",
            ],
        }
    ]

    rows = repository._get_ilga_overall_score_rows(collection)

    assert rows[0]["ranking"] == 0
    assert rows[0]["country_code"] == "ES"
    assert rows[0]["criteria"] == []


def test_country_status_repository_preserves_requested_order_and_latest(monkeypatch) -> None:
    collection = _Collection()
    collection.find_rows = [
        {"country_code": "ES", "year": 2026},
        {"country_code": "ES", "year": 2025},
        {"country_code": "PT", "year": 2024},
        {"country_code": "", "year": 2026},
    ]
    monkeypatch.setattr(repository, "_mongo_collection", lambda _name: collection)

    assert repository.get_country_lgbti_status_records.uncached(()) == []
    rows = repository.get_country_lgbti_status_records.uncached((" pt ", "ES", "PT", ""), 2026)
    assert [(row["country_code"], row["year"]) for row in rows] == [("PT", 2024), ("ES", 2026)]
    assert collection.calls[0][1][0]["year"] == {"$lte": 2026}

    collection.find_one_row = {"country_code": "ES", "year": 2026, "active": False}
    assert repository.get_country_lgbti_status_record("", 2026) is None
    assert repository.get_country_lgbti_status_record("ES", cast(Any, "bad")) is None
    assert (
        repository.get_country_lgbti_status_record(" es ", 2026, active_only=True)
        == collection.find_one_row
    )
    assert collection.calls[-1][1][0]["active"] is True


def test_country_status_repository_writes_and_propagates_storage_errors(monkeypatch) -> None:
    collection = _Collection()
    monkeypatch.setattr(repository, "_mongo_collection", lambda _name: collection)

    with pytest.raises(ValueError, match="invalid_country_lgbti_status_year"):
        repository.upsert_country_lgbti_status_record({"country_code": "ES"})
    repository.upsert_country_lgbti_status_record({"country_code": " es ", "year": 2026})
    assert repository.deactivate_country_lgbti_status_record(" es ", 2026) is True
    collection.matched_count = 0
    assert repository.deactivate_country_lgbti_status_record("ES", 2026) is False
    collection.error = RuntimeError("offline")
    with pytest.raises(RuntimeError, match="offline"):
        repository.upsert_country_lgbti_status_record({"country_code": "ES", "year": 2026})
    with pytest.raises(RuntimeError, match="offline"):
        repository.deactivate_country_lgbti_status_record("ES", 2026)


def test_spain_collection_discovery_filters_technical_names_and_localizes(monkeypatch) -> None:
    class Database:
        def list_collection_names(self):
            return ["Indicator_felgtbi", "felgtbi_reports", "tmp_cache", "indicator_fra", ""]

    class Client:
        def __getitem__(self, _name):
            return Database()

    monkeypatch.setattr(repository, "_mongo_client_and_database", lambda: (Client(), "db"))
    monkeypatch.setattr(
        repository,
        "_collection_has_spain_interface_documents",
        lambda name: name in {"Indicator_felgtbi", "felgtbi_reports"},
    )

    collections = repository.get_spain_available_collections.uncached()
    monkeypatch.setattr(repository, "get_spain_available_collections", lambda: collections)

    assert [item.name for item in collections] == ["Indicator_felgtbi", "felgtbi_reports"]
    assert repository.get_spain_collection_options("en")[0]["label"] == "LGBTIQ+ status in Spain"
    assert repository.get_spain_collection_options("xx")[0]["label"] == "Estado LGBTIQ+ en España"


def test_spain_document_grouping_filters_invalid_rows_and_deduplicates_labels() -> None:
    valid = {
        "source_document_id": "report-1",
        "original_filename": "reports/estado-lgtbi+-2026.pdf",
        "year": "2026",
        "report_title": "Estado LGTBI+ 2026",
        "report_type": "general",
        "import_status": "processed",
        "code": "section-1",
        "question": "Resultados",
    }
    rows = [
        valid,
        {**valid, "code": "section-2"},
        {**valid, "source_document_id": "report-2", "year": 2025},
        {**valid, "source_document_id": "blocked", "status": "failed"},
        {**valid, "source_document_id": "image", "original_filename": "image.png"},
        {**valid, "source_document_id": "empty", "code": ""},
        "bad",
    ]

    documents = repository._group_spain_documents(rows, repository.DEFAULT_FELGTBI_COLLECTION)
    documents = repository._deduplicate_spain_document_labels(documents)

    assert len(documents) == 2
    assert documents[0].section_count == 2
    assert {document.label.rsplit(" - ", 1)[-1] for document in documents} == {"2025", "2026"}


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ([{"percentage": 0}], 0.0),
        ([{"value": 2.5}], 2.5),
        (["bad", {"percentage": None}], None),
        (None, None),
    ],
)
def test_first_percentage_preserves_zero_and_rejects_non_numeric(value, expected) -> None:
    assert repository._first_percentage(value) == expected


def test_felgtbi_years_normalize_values_and_fail_closed(monkeypatch) -> None:
    collection = _Collection()
    collection.distinct_values = [2026, "2025", "bad", None, 2026]
    monkeypatch.setattr(repository, "_resolve_spain_collection_name", lambda _name: "")
    assert repository.get_felgtbi_years.uncached() == []

    monkeypatch.setattr(
        repository, "_resolve_spain_collection_name", lambda _name: "Indicator_felgtbi"
    )
    monkeypatch.setattr(repository, "_mongo_collection", lambda _name: collection)
    assert repository.get_felgtbi_years.uncached() == [2026, 2025]
    collection.error = RuntimeError("offline")
    assert repository.get_felgtbi_years.uncached() == []


def test_felgtbi_document_catalog_validates_year_and_builds_options(monkeypatch) -> None:
    collection = _Collection()
    collection.find_rows = [
        {
            "source_document_id": "report-1",
            "original_filename": "report.pdf",
            "year": 2026,
            "report_title": "Report",
            "report_type": "general",
            "code": "section-1",
            "question": "Results",
        }
    ]
    monkeypatch.setattr(
        repository, "_resolve_spain_collection_name", lambda _name: "Indicator_felgtbi"
    )
    monkeypatch.setattr(repository, "_mongo_collection", lambda _name: collection)

    assert repository.get_felgtbi_documents.uncached(None, "bad") == []
    get_documents_uncached = repository.get_felgtbi_documents.uncached
    documents = get_documents_uncached(None, "2026")
    monkeypatch.setattr(repository, "get_felgtbi_documents", lambda *_args: documents)

    assert documents[0].id == "document:report-1"
    assert documents[0].section_count == 1
    assert repository.get_felgtbi_document_options()[0] == {
        "label": "Report",
        "value": "document:report-1",
        "title": "Report",
    }
    collection.error = RuntimeError("offline")
    assert get_documents_uncached() == []


def test_felgtbi_document_years_and_navigation_validate_document_and_year(monkeypatch) -> None:
    document = repository.FelgtbiDocument(
        id="document:report-1",
        label="Report",
        original_filename="report.pdf",
        year=2026,
        report_title="Report",
        report_type="general",
        section_count=1,
        filter_fields=(("source_document_id", "report-1"),),
    )
    collection = _Collection()
    collection.distinct_values = [2026, "2025", "bad", 2026]
    collection.find_rows = [
        {
            "code": "section-1",
            "year": 2026,
            "category": "Social",
            "question": "Results",
            "description": "Description",
            "report_title": "Report",
            "answers": [{"percentage": 0}],
        },
        {"code": "", "year": 2026, "question": "Invalid"},
    ]
    monkeypatch.setattr(
        repository, "_resolve_spain_collection_name", lambda _name: "Indicator_felgtbi"
    )
    monkeypatch.setattr(repository, "_resolve_felgtbi_document", lambda *_args: document)
    monkeypatch.setattr(repository, "_mongo_collection", lambda _name: collection)

    assert repository.get_felgtbi_document_years.uncached("report-1") == [2026, 2025]
    assert repository.get_felgtbi_indicators_by_document.uncached("report-1", "bad") == []
    indicators = repository.get_felgtbi_indicators_by_document.uncached("report-1", 2026)
    assert [(item.code, item.value, item.label) for item in indicators] == [
        ("section-1", 0.0, "2026 - Report - Description")
    ]
    collection.error = RuntimeError("offline")
    assert repository.get_felgtbi_document_years.uncached("report-1") == []
    assert repository.get_felgtbi_indicators_by_document.uncached("report-1") == []


def test_felgtbi_section_cache_short_circuits_invalid_and_cached_requests(monkeypatch) -> None:
    monkeypatch.setattr(repository, "_resolve_spain_collection_name", lambda _name: "")
    assert repository.get_felgtbi_indicator_answers("section-1") is None
    monkeypatch.setattr(
        repository, "_resolve_spain_collection_name", lambda _name: "Indicator_felgtbi"
    )
    assert repository.get_felgtbi_indicator_answers("") is None

    cached = {"code": "section-1", "answers": [{"percentage": 0}]}
    monkeypatch.setattr(repository.cache, "get", lambda _key: cached)
    monkeypatch.setattr(
        repository.cache,
        "get_or_compute",
        lambda *_args, **_kwargs: pytest.fail("cache hit must avoid computation"),
    )
    assert repository.get_felgtbi_indicator_answers("section-1") is cached


def test_spain_collection_resolution_and_document_lookup(monkeypatch) -> None:
    collections = [
        repository.SpainCollection("custom_spain", "Custom", "Custom"),
        repository.SpainCollection("Indicator_felgtbi", "Default", "Default"),
    ]
    monkeypatch.setattr(repository, "get_spain_available_collections", lambda: collections)
    assert repository._resolve_spain_collection_name("custom_spain") == "custom_spain"
    assert repository._resolve_spain_collection_name("missing") == "Indicator_felgtbi"

    direct = repository._resolve_felgtbi_document("document:source-1", "Indicator_felgtbi")
    assert direct is not None and direct.filter_fields == (("source_document_id", "source-1"),)
    assert repository._resolve_felgtbi_document("document:", "Indicator_felgtbi") is None

    expected = repository.FelgtbiDocument(
        "legacy:one", "One", "one.pdf", 2026, "One", "general", 1, (("year", 2026),)
    )
    monkeypatch.setattr(repository, "get_felgtbi_documents", lambda _name: [expected])
    assert repository._resolve_felgtbi_document("legacy:one", "custom") is expected
    assert repository._resolve_felgtbi_document("missing", "custom") is None


def test_spain_document_identity_supports_nested_filename_object_and_digest_fallbacks() -> None:
    nested = {
        "metadata": {"original_filename": "folder/report.pdf"},
        "year": "2026",
        "report_title": "Report",
        "report_type": "general",
    }
    document_id, fields = repository._spain_document_identity(nested, "custom")
    assert document_id.startswith("legacy:")
    assert fields[0] == ("metadata.original_filename", "folder/report.pdf")
    assert ("year", 2026) in fields

    object_id, object_fields = repository._spain_document_identity({"_id": 42}, "custom")
    assert object_id == "legacy-object:42"
    assert object_fields == (("_id", 42),)

    digest_id, empty_fields = repository._spain_document_identity({}, "custom")
    assert digest_id.startswith("legacy:") and empty_fields == ()


@pytest.mark.parametrize(
    ("row", "expected"),
    [
        ({"description": "A sufficiently useful narrative sentence."}, True),
        ({"content_html": "<p>Content</p>"}, True),
        ({"paragraphs": ["Narrative"]}, True),
        ({"paragraphs_before_figure": ["Before"]}, True),
        ({"paragraphs_after_figure": ["After"]}, True),
        ({"figure_caption": "Figure 1"}, True),
        ({"sample_size": "n=100"}, True),
        ({"figure": {"note": "Source note"}}, True),
        ({"visual_context": {"methodology": "Survey"}}, True),
        ({"figure": {"storage_path": "reports/chart.webp"}}, True),
        ({"answers": [{"percentage": 0}]}, True),
        ({"data_points": [{"value": 0}]}, True),
        ({"figure": {"storage_path": "https://unsafe.test/chart.webp"}}, False),
        ({"question": "Same", "description": "Same"}, False),
    ],
)
def test_spain_section_validation_distinguishes_real_content(row, expected: bool) -> None:
    assert repository._has_valid_spain_section(row) is expected


@pytest.mark.parametrize(
    ("name", "technical"),
    [
        ("", True),
        ("indicator_fra", True),
        ("system.profile", True),
        ("felgtbi_backup", True),
        ("felgtbi_reports", False),
    ],
)
def test_spain_collection_names_filter_technical_sources(name: str, technical: bool) -> None:
    assert repository._is_technical_collection_name(name) is technical


def test_spain_collection_probe_uses_extended_country_fields_only_for_matching_names(
    monkeypatch,
) -> None:
    collection = _Collection()
    collection.find_one_row = {"code": "one"}
    monkeypatch.setattr(repository, "_mongo_collection", lambda _name: collection)

    assert repository._collection_has_spain_interface_documents("felgtbi_reports") is True
    query = collection.calls[-1][1][0]
    assert {"answers.country_code": "ES"} in query["$or"]

    assert repository._collection_has_spain_interface_documents("custom") is True
    query = collection.calls[-1][1][0]
    assert {"answers.country_code": "ES"} not in query["$or"]
    collection.error = RuntimeError("offline")
    assert repository._collection_has_spain_interface_documents("custom") is False


def test_collection_labels_are_readable_in_both_languages() -> None:
    assert repository._readable_collection_label("", language="es") == "Fuente de datos"
    assert repository._readable_collection_label("", language="en") == "Data source"
    assert repository._readable_collection_label(
        "felgtbi_discrimination_reports", language="es"
    ) == ("FELGTBI - Informes de discriminación")
    assert repository._readable_collection_label("felgtbi_lgtbi_spain_2026", language="en") == (
        "FELGTBI Spain 2026"
    )
    assert repository._display_name_from_pdf_filename(r"C:\reports\Estado LGTBI+ 2026.pdf") == (
        "Estado LGBTIQ+ 2026"
    )
