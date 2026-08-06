from __future__ import annotations

from pathlib import Path

from app.import_to_db.felgtbi.models import PdfExtractionError
from app.import_to_db.felgtbi.validation import PdfValidationError, validate_felgtbi_pdf


def parse_felgtbi_pdf(file_path: Path | str, *, year: int | None = None) -> list[dict]:
    """Read a PDF once and pass its bounded payload to the import pipeline."""
    path = Path(file_path)
    return parse_felgtbi_pdf_bytes(path.read_bytes(), file_name=path.name, year=year)


def parse_felgtbi_pdf_bytes(
    pdf_bytes: bytes,
    *,
    file_name: str = "felgtbi.pdf",
    year: int | None = None,
    require_storage: bool = False,
    upload_id: str = "",
) -> list[dict]:
    """Validate input and coordinate the existing phase-oriented extractor."""
    try:
        validate_felgtbi_pdf(pdf_bytes, file_name)
    except PdfValidationError as exc:
        raise PdfExtractionError(str(exc)) from exc

    # Local import keeps the coordinator independent from extraction details
    # and prevents an import cycle while importer.py retains compatibility exports.
    from app.import_to_db.felgtbi.importer import _run_felgtbi_pdf_pipeline

    return _run_felgtbi_pdf_pipeline(
        pdf_bytes,
        file_name=file_name,
        year=year,
        require_storage=require_storage,
        upload_id=upload_id,
    )
