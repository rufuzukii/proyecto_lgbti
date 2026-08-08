from __future__ import annotations

from typing import Any

import fitz

from app.import_to_db.felgtbi import batch as felgtbi_batch
from app.import_to_db.felgtbi import importer, mongo
from app.import_to_db.felgtbi.pipeline import parse_felgtbi_pdf_bytes


class RecordingCollection:
    def __init__(self) -> None:
        self.deleted: list[dict[str, Any]] = []
        self.updates: list[tuple[dict[str, Any], dict[str, Any]]] = []

    def delete_many(self, query):
        self.deleted.append(query)

    def update_one(self, query, update, *, upsert=False):
        assert upsert is True
        self.updates.append((query, update))


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
        {"source": "felgtbi_estado_lgtbi", "source_document_id": documents[0]["source_document_id"]}
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
