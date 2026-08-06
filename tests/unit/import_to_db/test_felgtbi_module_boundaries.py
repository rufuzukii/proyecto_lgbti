from __future__ import annotations

import pytest

from app.import_to_db.felgtbi.document_identity import (
    attach_source_document_metadata,
    build_pdf_source_document_id,
)
from app.import_to_db.felgtbi.models import PdfExtractionError
from app.import_to_db.felgtbi.pipeline import parse_felgtbi_pdf_bytes
from app.import_to_db.felgtbi.storage import figure_storage_path
from app.import_to_db.felgtbi.validation import PdfValidationError, validate_felgtbi_pdf


def test_pdf_validation_rejects_wrong_extension_signature_and_size(monkeypatch) -> None:
    # Arrange
    monkeypatch.setenv("UPLOAD_MAX_FILE_MB", "1")

    # Act / Assert
    with pytest.raises(PdfValidationError, match="unsupported_file_type"):
        validate_felgtbi_pdf(b"%PDF-1.4", "report.csv")
    with pytest.raises(PdfValidationError, match="invalid_pdf_signature"):
        validate_felgtbi_pdf(b"not-pdf", "report.pdf")
    with pytest.raises(PdfValidationError, match="file_too_large"):
        validate_felgtbi_pdf(b"%PDF-" + b"x" * (1024 * 1024), "report.pdf")


def test_pipeline_stops_before_extraction_when_pdf_is_invalid() -> None:
    with pytest.raises(PdfExtractionError, match="invalid_pdf_signature"):
        parse_felgtbi_pdf_bytes(b"not-pdf", file_name="report.pdf")


def test_document_identity_is_stable_and_metadata_is_non_destructive() -> None:
    # Arrange
    documents = [{"source_document_id": "assigned", "import_status": "reviewed"}]

    # Act
    first = build_pdf_source_document_id(b"%PDF-1.4", "folder/report.pdf")
    second = build_pdf_source_document_id(b"%PDF-1.4", "report.pdf")
    attach_source_document_metadata(
        documents,
        file_name="folder/report.pdf",
        source_document_id="replacement",
    )

    # Assert
    assert first == second
    assert documents == [
        {
            "source_document_id": "assigned",
            "import_status": "reviewed",
            "original_filename": "report.pdf",
        }
    ]


def test_figure_storage_path_keeps_only_canonical_storage_path_data() -> None:
    document = {
        "year": 2026,
        "report_title": "Estado LGTBI+",
        "section_title": "Agresiones físicas",
        "figure_number": "3.1",
    }

    result = figure_storage_path(document, "report.pdf")

    assert result == "2026/estado-lgtbi/agresiones-fisicas/figura-3-1.webp"
