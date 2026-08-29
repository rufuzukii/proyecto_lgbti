from __future__ import annotations

import pytest

from app.modules.imports.felgtbi.models import PdfExtractionError
from app.modules.imports.felgtbi.pipeline import parse_felgtbi_pdf_bytes
from app.modules.imports.felgtbi.storage import figure_storage_path
from app.modules.imports.felgtbi.validation import PdfValidationError, validate_felgtbi_pdf
from app.shared.data.felgtbi.document_identity import (
    attach_source_document_metadata,
    build_pdf_source_document_id,
    clean_felgtbi_document_label,
    clean_felgtbi_indicator_label,
)


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

    assert result.startswith("2026/estado-lgtbi/agresiones-fisicas/figura-3-1-")
    assert result.endswith(".webp")


@pytest.mark.parametrize(
    ("raw_label", "document_title", "expected"),
    [
        (
            "Estado del odio - ¿Podría decirme cuál es su orientación sexual? - 9,60",
            "Estado del odio",
            "¿Podría decirme cuál es su orientación sexual?",
        ),
        (
            "Estado LGTBI+ 2025 - Discriminación en el trabajo - 18,5%",
            "Estado LGTBI+ 2025",
            "Discriminación en el trabajo",
        ),
        (
            "¿Has sufrido discriminación en los últimos 12 meses?",
            "Estado del odio",
            "¿Has sufrido discriminación en los últimos 12 meses?",
        ),
    ],
)
def test_indicator_label_cleanup_changes_only_display_text(
    raw_label: str,
    document_title: str,
    expected: str,
) -> None:
    # Arrange / Act
    cleaned = clean_felgtbi_indicator_label(raw_label, document_title)

    # Assert
    assert cleaned == expected


def test_document_label_prefers_pdf_title_and_cleans_technical_filename() -> None:
    # Arrange / Act
    official = clean_felgtbi_document_label(
        "1b845c_FINAL_2025.pdf",
        "20 años de matrimonio igualitario",
    )
    fallback = clean_felgtbi_document_label(
        "Informe-socio-economico_estado-lgrbi-2025_FINAL.pdf"
    )

    # Assert
    assert official == "20 años de matrimonio igualitario"
    assert fallback == "Socio economico estado"
