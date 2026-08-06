from __future__ import annotations

import os
from pathlib import Path


class PdfValidationError(ValueError):
    """A PDF payload failed a cheap validation performed before extraction."""


def validate_felgtbi_pdf(pdf_bytes: bytes, file_name: str) -> None:
    """Validate filename, size and signature without parsing or retaining the file."""
    if Path(file_name).suffix.casefold() != ".pdf":
        raise PdfValidationError("unsupported_file_type")
    if not pdf_bytes:
        raise PdfValidationError("empty_file")
    maximum_bytes = max(1, int(os.getenv("UPLOAD_MAX_FILE_MB", "20"))) * 1024 * 1024
    if len(pdf_bytes) > maximum_bytes:
        raise PdfValidationError("file_too_large")
    if not pdf_bytes.lstrip().startswith(b"%PDF-"):
        raise PdfValidationError("invalid_pdf_signature")
