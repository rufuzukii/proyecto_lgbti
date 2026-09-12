from __future__ import annotations

from pathlib import Path

from app.modules.imports.felgtbi.models import PdfExtractionError
from app.modules.imports.felgtbi.validation import PdfValidationError, validate_felgtbi_pdf


def parse_felgtbi_pdf(file_path: Path | str, *, year: int | None = None) -> list[dict]:
    """Lee el PDF una sola vez y entrega su contenido acotado al proceso de importación."""
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
    """Valida la entrada y coordina las fases de extracción existentes."""
    try:
        validate_felgtbi_pdf(pdf_bytes, file_name)
    except PdfValidationError as exc:
        raise PdfExtractionError(str(exc)) from exc

    # El import local desacopla el coordinador de la extracción y evita un ciclo
    # mientras importer.py mantiene sus exportaciones de compatibilidad.
    from app.modules.imports.felgtbi.importer import _run_felgtbi_pdf_pipeline

    return _run_felgtbi_pdf_pipeline(
        pdf_bytes,
        file_name=file_name,
        year=year,
        require_storage=require_storage,
        upload_id=upload_id,
    )
