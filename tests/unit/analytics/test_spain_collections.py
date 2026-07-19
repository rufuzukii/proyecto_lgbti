from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from app.analytics import repository
from app.dash.pages.spain import (
    _resolve_topic_selection,
    _selected_option_index,
    _spain_document_view_state,
    _spain_visualization_shell,
)


class FakeDatabase:
    def __init__(
        self,
        names: list[str] | None = None,
        error: Exception | None = None,
        documents_by_name: dict[str, dict | None] | None = None,
    ) -> None:
        self._names = names or []
        self._error = error
        self._documents_by_name = documents_by_name or {}

    def list_collection_names(self) -> list[str]:
        if self._error is not None:
            raise self._error
        return self._names

    def __getitem__(self, name: str):
        return FakeCollection(self._documents_by_name.get(name))


class FakeCollection:
    def __init__(self, document: dict | None = None) -> None:
        self._document = document

    def find_one(self, *_args, **_kwargs):
        return self._document


class QueryableCollection:
    def __init__(self, rows: list[dict]) -> None:
        self.rows = rows

    def create_index(self, *_args, **_kwargs) -> None:
        return None

    def find(self, query: dict | None = None, *_args, **_kwargs):
        query = query or {}
        return [row for row in self.rows if _matches_query(row, query)]

    def distinct(self, field: str, query: dict | None = None):
        values = []
        for row in self.find(query):
            value = _nested_value(row, field)
            if value not in values:
                values.append(value)
        return values

    def find_one(self, query: dict | None = None, *_args, **_kwargs):
        rows = self.find(query)
        return rows[0] if rows else None


class FakeClient:
    def __init__(self, database: FakeDatabase) -> None:
        self._database = database

    def __getitem__(self, _name: str) -> FakeDatabase:
        return self._database


def _uncached_collections():
    return getattr(
        repository.get_spain_available_collections,
        "uncached",
        repository.get_spain_available_collections,
    )()


def _component_ids(component) -> list[str]:
    if isinstance(component, (list, tuple)):
        ids: list[str] = []
        for child in component:
            ids.extend(_component_ids(child))
        return ids

    component_id = getattr(component, "id", None)
    ids = [component_id] if isinstance(component_id, str) else []
    children = getattr(component, "children", None)
    if children is not None:
        ids.extend(_component_ids(children))
    return ids


def _matches_query(row: dict, query: dict) -> bool:
    for key, expected in query.items():
        value = _nested_value(row, key)
        if isinstance(expected, dict):
            if "$exists" in expected:
                exists = value is not None
                if bool(expected["$exists"]) != exists:
                    return False
            if "$nin" in expected and value in expected["$nin"]:
                return False
            continue
        if value != expected:
            return False
    return True


def _nested_value(row: dict, field_path: str):
    current = row
    for part in field_path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _valid_spain_row(**overrides) -> dict:
    row = {
        "source": "felgtbi_estado_lgtbi",
        "code": "S1",
        "year": 2026,
        "category": "Categoría nueva",
        "specific_category": "Sección",
        "question": "Pregunta con resultado",
        "description": "Texto interpretativo suficiente para mostrar esta sección.",
        "answers": [{"percentage": 42.0}],
    }
    row.update(overrides)
    return row


def test_spain_collections_are_discovered_from_mongo_and_filter_technical_names(monkeypatch) -> None:
    valid_document = {
        "code": "S1",
        "category": "Discriminación",
        "year": 2026,
        "source": "felgtbi_estado_lgtbi",
    }
    database = FakeDatabase(
        [
            "Indicator_felgtbi",
            "felgtbi_discrimination_reports",
            "felgtbi-special.reports_2026",
            "felgtbi_empty",
            "system.profile",
            "_felgtbi_tmp",
            "tmp_felgtbi_upload",
            "audit_felgtbi",
            "schema_migrations",
            "country_lgbti_status",
            "Indicator_fra",
        ],
        documents_by_name={
            "Indicator_felgtbi": valid_document,
            "felgtbi_discrimination_reports": valid_document,
            "felgtbi-special.reports_2026": valid_document,
            "Indicator_fra": valid_document,
        },
    )
    monkeypatch.setattr(repository, "_mongo_client_and_database", lambda: (FakeClient(database), "db"))

    collections = _uncached_collections()

    assert [collection.name for collection in collections] == [
        "Indicator_felgtbi",
        "felgtbi_discrimination_reports",
        "felgtbi-special.reports_2026",
    ]


def test_spain_collection_options_keep_exact_mongo_value(monkeypatch) -> None:
    monkeypatch.setattr(
        repository,
        "get_spain_available_collections",
        lambda: [
            repository.SpainCollection(
                name="felgtbi_discrimination_reports",
                label_es="FELGTBI - Informes de discriminación",
                label_en="FELGTBI - Discrimination reports",
            )
        ],
    )

    options = repository.get_spain_collection_options()
    english_options = repository.get_spain_collection_options(language="en")

    assert options == [
        {
            "label": "FELGTBI - Informes de discriminación",
            "value": "felgtbi_discrimination_reports",
        }
    ]
    assert english_options == [
        {
            "label": "FELGTBI - Discrimination reports",
            "value": "felgtbi_discrimination_reports",
        }
    ]


def test_spain_collections_include_names_with_spain_documents(monkeypatch) -> None:
    database = FakeDatabase(
        ["custom_source_2026", "unrelated_dataset", "Indicator_fra"],
        documents_by_name={
            "custom_source_2026": {
                "code": "S1",
                "category": "Discriminación",
                "year": 2026,
                "country_code": "ES",
            },
            "unrelated_dataset": None,
            "Indicator_fra": {
                "code": "D1",
                "category": "Discrimination",
                "year": 2023,
                "country_code": "ES",
            },
        },
    )
    monkeypatch.setattr(repository, "_mongo_client_and_database", lambda: (FakeClient(database), "db"))

    collections = _uncached_collections()

    assert [collection.name for collection in collections] == ["custom_source_2026"]


def test_spain_collection_labels_fall_back_to_readable_names() -> None:
    label_es = repository._spain_collection_label("felgtbi-hate_crime.reports_2026", language="es")
    label_en = repository._spain_collection_label("felgtbi-hate_crime.reports_2026", language="en")

    assert "FELGTBI" in label_es
    assert "Hate" in label_es
    assert "2026" in label_es
    assert "FELGTBI" in label_en
    assert "Reports" in label_en


def test_spain_collections_return_empty_list_when_mongo_is_unavailable(monkeypatch, caplog) -> None:
    database = FakeDatabase(error=RuntimeError("mongo unavailable"))
    monkeypatch.setattr(repository, "_mongo_client_and_database", lambda: (FakeClient(database), "db"))

    collections = _uncached_collections()

    assert collections == []
    assert "spain_collections_read_failed" in caplog.text


def test_felgtbi_queries_use_selected_collection(monkeypatch) -> None:
    called: dict[str, str] = {}

    class FakeCollection:
        def create_index(self, *_args, **_kwargs) -> None:
            return None

        def distinct(self, field: str, query: dict) -> list[str]:
            called["field"] = field
            called["query"] = repr(query)
            return ["2026"]

    monkeypatch.setattr(
        repository,
        "get_spain_available_collections",
        lambda: [
            repository.SpainCollection(
                name="felgtbi_discrimination_reports",
                label_es="FELGTBI - Informes de discriminación",
                label_en="FELGTBI - Discrimination reports",
            )
        ],
    )
    monkeypatch.setattr(repository, "_mongo_collection", lambda name: called.setdefault("collection", name) and FakeCollection())
    repository._ensure_spain_collection_indexes.cache_clear()

    years = repository.get_felgtbi_years.uncached(
        "Discriminación",
        "felgtbi_discrimination_reports",
    )

    assert years == [2026]
    assert called["collection"] == "felgtbi_discrimination_reports"
    assert called["field"] == "year"
    assert "source" not in called["query"]


def test_spain_document_options_are_generated_from_original_pdf_names(monkeypatch) -> None:
    rows = [
        _valid_spain_row(code="known", original_filename="Informe_delitos_odio_2024.pdf"),
        _valid_spain_row(code="upper", original_filename="Estado LGTBI+ 2025.PDF", year=2025),
        _valid_spain_row(code="path", original_filename="/uploads/spain/informe.final.2025.pdf", year=2025),
        _valid_spain_row(code="accent", original_filename="Informe áéíóú 2026.pdf"),
        _valid_spain_row(code="legacy", source_file="/uploads/legacy/Legacy_File.pdf"),
        _valid_spain_row(code="pending", original_filename="Pendiente.pdf", import_status="pending"),
        _valid_spain_row(code="error", original_filename="Error.pdf", status="error"),
        _valid_spain_row(code="csv", original_filename="NoPdf.csv"),
    ]
    monkeypatch.setattr(
        repository,
        "get_spain_available_collections",
        lambda: [
            repository.SpainCollection(
                name="Indicator_felgtbi",
                label_es="Estado LGBTIQ+ en España",
                label_en="LGBTIQ+ status in Spain",
            )
        ],
    )
    monkeypatch.setattr(repository, "_mongo_collection", lambda _name: QueryableCollection(rows))
    repository._ensure_spain_collection_indexes.cache_clear()

    documents = repository.get_felgtbi_documents.uncached("Indicator_felgtbi")

    labels = {document.label for document in documents}
    assert "Informe_delitos_odio_2024" in labels
    assert "Estado LGBTIQ+ 2025" in labels
    assert "informe.final.2025" in labels
    assert "Informe áéíóú 2026" in labels
    assert "Legacy_File" in labels
    assert "Pendiente" not in labels
    assert "Error" not in labels
    assert "NoPdf" not in labels
    assert len({document.id for document in documents}) == len(documents)


def test_spain_document_options_disambiguate_duplicate_file_names(monkeypatch) -> None:
    rows = [
        _valid_spain_row(
            code="first",
            original_filename="Informe anual.pdf",
            source_document_id="doc-2024",
            year=2024,
        ),
        _valid_spain_row(
            code="second",
            original_filename="Informe anual.pdf",
            source_document_id="doc-2025",
            year=2025,
        ),
    ]
    monkeypatch.setattr(
        repository,
        "get_spain_available_collections",
        lambda: [
            repository.SpainCollection(
                name="Indicator_felgtbi",
                label_es="Estado LGBTIQ+ en España",
                label_en="LGBTIQ+ status in Spain",
            )
        ],
    )
    monkeypatch.setattr(repository, "_mongo_collection", lambda _name: QueryableCollection(rows))
    repository._ensure_spain_collection_indexes.cache_clear()

    documents = repository.get_felgtbi_documents.uncached("Indicator_felgtbi")

    assert [document.label for document in documents] == [
        "Informe anual - 2025",
        "Informe anual - 2024",
    ]
    assert [document.id for document in documents] == [
        "document:doc-2025",
        "document:doc-2024",
    ]


def test_felgtbi_indicators_by_document_does_not_filter_new_categories(monkeypatch) -> None:
    rows = [
        _valid_spain_row(
            code="new-category",
            original_filename="Nueva categoría.pdf",
            source_document_id="new-doc",
            category="Categoría totalmente nueva",
        ),
        _valid_spain_row(
            code="other-doc",
            original_filename="Otro.pdf",
            source_document_id="other-doc",
            category="Categoría conocida",
        ),
    ]
    document = repository.FelgtbiDocument(
        id="document:new-doc",
        label="Nueva categoría",
        original_filename="Nueva categoría.pdf",
        year=2026,
        report_title="Nueva categoría",
        report_type="estado_lgtbi",
        section_count=1,
        filter_fields=(("source_document_id", "new-doc"),),
    )
    monkeypatch.setattr(
        repository,
        "get_spain_available_collections",
        lambda: [
            repository.SpainCollection(
                name="Indicator_felgtbi",
                label_es="Estado LGBTIQ+ en España",
                label_en="LGBTIQ+ status in Spain",
            )
        ],
    )
    monkeypatch.setattr(repository, "get_felgtbi_documents", lambda _collection_name=None: [document])
    monkeypatch.setattr(repository, "_mongo_collection", lambda _name: QueryableCollection(rows))
    repository._ensure_spain_collection_indexes.cache_clear()

    indicators = repository.get_felgtbi_indicators_by_document.uncached(
        "document:new-doc",
        2026,
        "Indicator_felgtbi",
    )

    assert [indicator.code for indicator in indicators] == ["new-category"]
    assert indicators[0].category == "Categoría totalmente nueva"


def test_felgtbi_indicator_answers_filters_by_document_id(monkeypatch) -> None:
    rows = [
        _valid_spain_row(
            code="same-section",
            original_filename="Primer informe.pdf",
            source_document_id="doc-a",
            question="Pregunta del primer documento",
        ),
        _valid_spain_row(
            code="same-section",
            original_filename="Segundo informe.pdf",
            source_document_id="doc-b",
            question="Pregunta del segundo documento",
        ),
    ]
    documents = [
        repository.FelgtbiDocument(
            id="document:doc-a",
            label="Primer informe",
            original_filename="Primer informe.pdf",
            year=2026,
            report_title="Primer informe",
            report_type="estado_lgtbi",
            section_count=1,
            filter_fields=(("source_document_id", "doc-a"),),
        ),
        repository.FelgtbiDocument(
            id="document:doc-b",
            label="Segundo informe",
            original_filename="Segundo informe.pdf",
            year=2026,
            report_title="Segundo informe",
            report_type="estado_lgtbi",
            section_count=1,
            filter_fields=(("source_document_id", "doc-b"),),
        ),
    ]
    monkeypatch.setattr(
        repository,
        "get_spain_available_collections",
        lambda: [
            repository.SpainCollection(
                name="Indicator_felgtbi",
                label_es="Estado LGBTIQ+ en España",
                label_en="LGBTIQ+ status in Spain",
            )
        ],
    )
    monkeypatch.setattr(repository, "get_felgtbi_documents", lambda _collection_name=None: documents)
    monkeypatch.setattr(repository, "_mongo_collection", lambda _name: QueryableCollection(rows))
    repository._ensure_spain_collection_indexes.cache_clear()

    result = repository.get_felgtbi_indicator_answers.uncached(
        "same-section",
        "Indicator_felgtbi",
        document_id="document:doc-b",
    )

    assert result is not None
    assert result["source_document_id"] == "doc-b"
    assert result["original_filename"] == "Segundo informe.pdf"
    assert result["question"] == "Pregunta del segundo documento"


def test_felgtbi_importer_attaches_original_filename_and_document_id() -> None:
    from app.import_to_db.felgtbi.importer import _attach_source_document_metadata

    documents = [{"code": "one"}, {"code": "two", "original_filename": "Already.pdf"}]

    _attach_source_document_metadata(
        documents,
        file_name="/unsafe/path/Estado LGTBI+ 2025.PDF",
        source_document_id="felgtbi_pdf_test",
    )

    assert documents[0]["original_filename"] == "Estado LGTBI+ 2025.PDF"
    assert documents[1]["original_filename"] == "Already.pdf"
    assert {document["source_document_id"] for document in documents} == {"felgtbi_pdf_test"}
    assert {document["import_status"] for document in documents} == {"processed"}


def test_felgtbi_mongo_prepare_backfills_original_filename_from_pending_file() -> None:
    from app.import_to_db.felgtbi.mongo import _prepare_indicator_document

    prepared = _prepare_indicator_document(
        {
            "source": "felgtbi_estado_lgtbi",
            "code": "felgtbi_test",
            "year": "2026",
            "report_title": "Informe test",
            "report_type": "estado_lgtbi",
            "question": "Pregunta",
            "description": "Descripción suficiente",
            "answers": [{"percentage": 75}],
        },
        original_filename="/uploads/spain/informe.final.2026.PDF",
    )

    assert prepared["original_filename"] == "informe.final.2026.PDF"
    assert prepared["source_document_id"].startswith("felgtbi_pdf_")
    assert prepared["import_status"] == "processed"


def test_felgtbi_replacement_scope_prefers_source_document_id() -> None:
    from app.import_to_db.felgtbi.mongo import _report_replacement_scopes

    scopes = _report_replacement_scopes(
        [
            {
                "source": "felgtbi_estado_lgtbi",
                "source_document_id": "doc-a",
                "original_filename": "Informe anual.pdf",
                "year": 2026,
                "report_title": "Informe anual",
                "report_type": "estado_lgtbi",
            },
            {
                "source": "felgtbi_estado_lgtbi",
                "source_document_id": "doc-b",
                "original_filename": "Informe anual.pdf",
                "year": 2026,
                "report_title": "Informe anual",
                "report_type": "estado_lgtbi",
            },
        ]
    )

    assert scopes == [
        {"source": "felgtbi_estado_lgtbi", "source_document_id": "doc-a"},
        {"source": "felgtbi_estado_lgtbi", "source_document_id": "doc-b"},
    ]


def test_felgtbi_indicator_filter_includes_source_document_id() -> None:
    from app.import_to_db.felgtbi.mongo import _indicator_filter

    query = _indicator_filter(
        {
            "source": "felgtbi_estado_lgtbi",
            "source_document_id": "doc-a",
            "original_filename": "Informe anual.pdf",
            "code": "same-section",
            "year": 2026,
        }
    )

    assert query == {
        "source": "felgtbi_estado_lgtbi",
        "source_document_id": "doc-a",
        "code": "same-section",
        "year": 2026,
    }


def test_felgtbi_indicators_exclude_chart_only_sections(monkeypatch) -> None:
    rows = [
        {
            "code": "chart_only",
            "year": 2026,
            "category": "Discriminación",
            "question": "Solo porcentaje",
            "answers": [{"percentage": 42.0}],
        },
        {
            "code": "chart_with_information",
            "year": 2026,
            "category": "Discriminación",
            "question": "Con información",
            "description": "Texto interpretativo suficiente para explicar la sección.",
            "answers": [{"percentage": 64.0}],
        },
        {
            "code": "chart_with_image",
            "year": 2026,
            "category": "Discriminación",
            "question": "Con imagen",
            "answers": [{"percentage": 50.0}],
            "figure": {"image_url": "https://example.test/chart.png"},
        },
        {
            "code": "information_without_chart",
            "year": 2026,
            "category": "Discriminación",
            "question": "Sin gráfica",
            "description": "Texto interpretativo suficiente para explicar la sección.",
        },
    ]

    class IndicatorCollection:
        def create_index(self, *_args, **_kwargs) -> None:
            return None

        def find(self, *_args, **_kwargs):
            return rows

    monkeypatch.setattr(
        repository,
        "get_spain_available_collections",
        lambda: [
            repository.SpainCollection(
                name="Indicator_felgtbi",
                label_es="Estado LGBTIQ+ en España",
                label_en="LGBTIQ+ status in Spain",
            )
        ],
    )
    monkeypatch.setattr(repository, "_mongo_collection", lambda _name: IndicatorCollection())
    repository._ensure_spain_collection_indexes.cache_clear()

    indicators = repository.get_felgtbi_indicators_by_category.uncached(
        "Discriminación",
        2026,
        "Indicator_felgtbi",
    )

    assert [indicator.code for indicator in indicators] == [
        "chart_with_information",
        "chart_with_image",
    ]


def test_spain_topic_navigation_resolves_previous_next_and_removed_selection() -> None:
    options = [
        {"label": "Uno", "value": "one"},
        {"label": "Dos", "value": "two"},
        {"label": "Tres", "value": "three"},
    ]

    assert _resolve_topic_selection(options, "two", trigger_id="spain-topic-prev") == ("one", "ok")
    assert _resolve_topic_selection(options, "two", trigger_id="spain-topic-next") == ("three", "ok")
    assert _resolve_topic_selection(options, "missing", trigger_id="spain-category-select") == ("one", "removed")
    assert _selected_option_index(options, "three") == 2
    assert _selected_option_index(options, "missing") == -1


def test_spain_visualization_shell_keeps_stable_slot_ids() -> None:
    ids = _component_ids(_spain_visualization_shell())

    for expected_id in [
        "spain-content-empty",
        "spain-report-content",
        "spain-section-image",
        "spain-section-graph",
        "spain-detail-content",
    ]:
        assert ids.count(expected_id) == 1


def test_spain_document_view_state_switches_slots_without_replacing_shell() -> None:
    graph_state = _spain_document_view_state(
        {
            "answers": [{"answer": "Total", "percentage": 61.0}],
            "description": "Visible context.",
        }
    )
    report_state = _spain_document_view_state(
        {
            "content_html": "<p>Report content</p>",
            "answers": [{"answer": "Total", "percentage": 61.0}],
        }
    )

    assert graph_state[1] == "spain-content-slot is-hidden"
    assert graph_state[8] == "spain-section-graph spain-content-slot"
    assert report_state[3] == "spain-content-slot"
    assert report_state[8] == "spain-section-graph spain-content-slot is-hidden"
