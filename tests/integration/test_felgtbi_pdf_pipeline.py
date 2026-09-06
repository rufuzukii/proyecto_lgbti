from __future__ import annotations

import hashlib
import weakref
from copy import deepcopy
from typing import Any

import fitz
import pytest

from app.modules.imports.felgtbi import batch as felgtbi_batch
from app.modules.imports.felgtbi import importer, mongo
from app.modules.imports.felgtbi.pipeline import parse_felgtbi_pdf_bytes


@pytest.mark.parametrize("encoding_fails", [False, True])
def test_figure_resources_are_released_before_storage_even_if_encoding_fails(
    monkeypatch, encoding_fails
) -> None:
    pdf = fitz.open()
    documents = []
    expected = []
    for index in range(3):
        page = pdf.new_page(width=120, height=90)
        page.draw_rect(page.rect, fill=(index / 3, 0.2, 0.4))
        documents.append(
            {
                "year": 2026,
                "code": f"figure-{index}",
                "page": index + 1,
                "figure": {"caption": f"Figure {index}"},
                "visual_context": {"page": index + 1, "bbox": [0, 0, 120, 90]},
            }
        )
        pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
        expected.append(importer._pixmap_image_bytes(pixmap)[0])
        del pixmap
    pdf_bytes = pdf.tobytes()
    pdf.close()
    fitz.TOOLS.store_shrink(100)
    released = []
    pixmap_refs = []
    uploads = []
    original_render = fitz.Page.get_pixmap
    original_release = fitz.TOOLS.store_shrink

    def render(page, **kwargs):
        pixmap = original_render(page, **kwargs)
        pixmap_refs.append(weakref.ref(pixmap))
        return pixmap

    def release(percent):
        released.append(percent)
        return original_release(percent)

    def upload(**kwargs):
        assert all(reference() is None for reference in pixmap_refs)
        assert released and released[-1] == 100
        image = kwargs["image_bytes"]
        assert image == expected[len(uploads)]
        assert kwargs["checksum"] == hashlib.sha256(image).hexdigest()
        uploads.append(kwargs)
        return {"status": "reused", "storage_path": kwargs["storage_path"]}

    monkeypatch.setattr(fitz.Page, "get_pixmap", render)
    monkeypatch.setattr(fitz.TOOLS, "store_shrink", release)
    monkeypatch.setattr(importer, "_upload_figure_to_supabase", upload)
    if encoding_fails:

        def fail_encoding(_pixmap):
            raise OSError("controlled encoding failure")

        monkeypatch.setattr(importer, "_pixmap_image_bytes", fail_encoding)
        with pytest.raises(OSError, match="controlled encoding failure"):
            importer._attach_page_assets(pdf_bytes, "controlled.pdf", documents)
        assert released == [100]
        assert uploads == []
    else:
        result = importer._attach_page_assets(pdf_bytes, "controlled.pdf", documents)
        assert result["reused"] == 3
        assert len(uploads) == 3
        assert all(document["figure"]["checksum"] for document in documents)


class RecordingCollection:
    def __init__(self) -> None:
        self.deleted: list[dict[str, Any]] = []
        self.updates: list[tuple[dict[str, Any], dict[str, Any]]] = []
        self.documents: list[dict[str, Any]] = []

    def delete_many(self, query):
        self.deleted.append(query)
        self.documents = [
            doc for doc in self.documents if not all(doc.get(k) == v for k, v in query.items())
        ]

    def update_one(self, query, update, *, upsert=False):
        assert upsert is True
        self.updates.append((query, update))
        document = next(
            (doc for doc in self.documents if all(doc.get(k) == v for k, v in query.items())),
            None,
        )
        if document is None:
            document = {**query, **update.get("$setOnInsert", {})}
            self.documents.append(document)
        document.update(update.get("$set", {}))
        for key in update.get("$unset", {}):
            document.pop(key, None)


@pytest.mark.parametrize("old_id", [None, "old-pdf-hash", "new-pdf-hash"])
def test_reimport_replaces_old_report_content_without_touching_other_reports(
    monkeypatch, old_id
) -> None:
    collection = RecordingCollection()
    original = {
        "source": "felgtbi_estado_lgtbi",
        "source_document_id": old_id,
        "original_filename": "estado-odio-2026.pdf",
        "year": 2026,
        "code": "old-section",
        "question": "Orientacion sexual",
        "paragraphs": ["Los resultados se muestran en laEl estudio analiza los datos"],
    }
    untouched = [
        {**original, "original_filename": "otro-informe.pdf"},
        {**original, "year": 2025},
        {**original, "source": "other-source"},
    ]
    # Other reports have their own IDs; legacy entries can lack one altogether.
    for index, document in enumerate(untouched):
        document["source_document_id"] = f"other-{index}"
    collection.documents = deepcopy([original, {**original, "code": "obsolete"}, *untouched])
    monkeypatch.setattr(mongo, "get_mongo_collection", lambda _: collection)
    corrected = {
        **original,
        "source_document_id": "new-pdf-hash",
        "code": "corrected-section",
        "paragraphs": ["Los resultados se muestran en la Figura 1. El estudio analiza los datos"],
    }

    for _ in range(2):
        assert mongo.insert_indicator_felgtbi_json([corrected]) == 1
        assert len(collection.documents) == 4
        assert all(document in collection.documents for document in untouched)
        imported = next(doc for doc in collection.documents if doc["code"] == "corrected-section")
        assert imported["paragraphs"] == corrected["paragraphs"]
        assert not any(doc["code"] == "obsolete" for doc in collection.documents)


def test_felgtbi_approval_persists_narrative_and_figures_without_fra_catalog(monkeypatch) -> None:
    from app.modules.imports.fra import indicators
    from app.web.application import _insert_approved_import

    collection = RecordingCollection()
    monkeypatch.setattr(mongo, "get_mongo_collection", lambda _: collection)
    monkeypatch.setattr(
        indicators, "postgres_connection", lambda **_: pytest.fail("FELGTBI sent to FRA catalog")
    )
    narrative = {
        "source": "felgtbi_estado_lgtbi",
        "year": 2026,
        "code": "narrative",
        "question": "Contexto del informe",
        "paragraphs": ["Texto del informe"],
    }
    figure = {
        **narrative,
        "code": "figure",
        "question": "Distribucion",
        "answers": [{"country": "Spain", "answer": "Total", "percentage": 0}],
        "figure": {"storage_path": "2026/report/figure.webp"},
    }

    assert _insert_approved_import([narrative, figure], original_filename="report.pdf") == "felgtbi"
    assert len(collection.documents) == 2
    assert collection.documents[0]["paragraphs"] == narrative["paragraphs"]
    assert "answers" not in collection.documents[0]
    assert collection.documents[1]["answers"][0]["percentage"] == 0
    assert collection.documents[1]["figure"]["storage_path"] == "2026/report/figure.webp"


def test_pdf_extraction_storage_identity_and_mongo_persistence(monkeypatch) -> None:
    # Arrange
    pdf = fitz.open()
    page = pdf.new_page(width=595, height=842)
    page.insert_text((85, 90), "Estado LGTBI+ 2026", fontsize=14)
    page.insert_text((85, 130), "Dimension del odio", fontsize=12)
    page.insert_text(
        (85, 170), "El 54% de las personas LGTBI+ declara haber sufrido odio.", fontsize=10
    )
    pdf_bytes = pdf.tobytes()
    pdf.close()
    collection = RecordingCollection()
    monkeypatch.setattr(
        importer,
        "_upload_figure_to_supabase",
        lambda **_kwargs: {"status": "uploaded", "storage_path": "2026/report/figure.webp"},
    )
    monkeypatch.setattr(mongo, "get_mongo_collection", lambda _name: collection)

    # Act
    documents = parse_felgtbi_pdf_bytes(pdf_bytes, file_name="estado-odio-2026.pdf")
    inserted = mongo.insert_indicator_felgtbi_json(
        documents, original_filename="estado-odio-2026.pdf"
    )

    # Assert
    assert inserted == len(documents) == 1
    assert documents[0]["year"] == 2026
    assert documents[0]["source_document_id"].startswith("felgtbi_pdf_")
    assert collection.deleted == [
        {
            "source": "felgtbi_estado_lgtbi",
            "source_document_id": documents[0]["source_document_id"],
        },
        {
            "source": "felgtbi_estado_lgtbi",
            "year": 2026,
            "original_filename": "estado-odio-2026.pdf",
        },
    ]
    assert collection.updates[0][1]["$set"]["import_status"] == "processed"


def test_directory_batch_continues_after_failure_and_publishes_complete_reports(
    monkeypatch,
    tmp_path,
) -> None:
    # Arrange
    report_directory = tmp_path / "2026"
    report_directory.mkdir()
    pdf = fitz.open()
    page = pdf.new_page(width=595, height=842)
    page.insert_text((85, 90), "Estado del odio", fontsize=18)
    page.insert_text((85, 130), "Agresiones físicas", fontsize=14)
    page.insert_text((85, 170), "Figura 1. Agresiones físicas", fontsize=10)
    page.draw_rect(fitz.Rect(100, 210, 490, 430), fill=(0.7, 0.2, 0.4))
    page.insert_text(
        (85, 470),
        "El 18,5% de las personas encuestadas declara haber sufrido discriminación.",
        fontsize=9,
    )
    (report_directory / "estado-odio-2026.pdf").write_bytes(pdf.tobytes())
    pdf.close()
    (report_directory / "corrupto.pdf").write_bytes(b"not-a-pdf")
    published: list[dict[str, Any]] = []
    monkeypatch.setattr(
        importer,
        "_upload_figure_to_supabase",
        lambda **kwargs: {
            "status": "uploaded",
            "storage_path": kwargs["storage_path"],
            "mime_type": kwargs["mime_type"],
        },
    )

    def record_publish(documents, *, batch_size):
        assert batch_size == 25
        published.extend(documents)
        return len(documents)

    monkeypatch.setattr(felgtbi_batch, "replace_indicator_felgtbi_documents", record_publish)

    # Act
    report = felgtbi_batch.import_felgtbi_pdf_directory(
        tmp_path,
        require_storage=True,
        batch_size=25,
    )

    # Assert
    assert report["pdf_found"] == 2
    assert report["pdf_imported"] == 1
    assert report["pdf_rejected"] == 1
    assert report["documents_persisted"] == len(published) == 1
    figure = published[0]["figure"]
    assert figure["storage_path"].endswith(".webp")
    assert figure["mime_type"] == "image/webp"
    assert len(figure["checksum"]) == 64
    assert not {"asset_url", "public_url", "signed_url"}.intersection(figure)
