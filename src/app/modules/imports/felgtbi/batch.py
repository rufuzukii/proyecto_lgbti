from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from app.modules.imports.felgtbi.mongo import replace_indicator_felgtbi_documents
from app.modules.imports.felgtbi.pipeline import parse_felgtbi_pdf_bytes
from app.modules.imports.felgtbi.validation import validate_felgtbi_pdf

logger = logging.getLogger(__name__)
YEAR_PATTERN = re.compile(r"(?<!\d)(20\d{2})(?!\d)")


def import_felgtbi_pdf_directory(
    directory: Path | str,
    *,
    require_storage: bool = True,
    batch_size: int = 200,
) -> dict[str, Any]:
    """Process every PDF independently and atomically publish all successful reports."""
    root = Path(directory)
    pdf_paths = sorted(path for path in root.rglob("*.pdf") if path.is_file())
    if not pdf_paths:
        raise ValueError("felgtbi_pdf_directory_empty")

    all_documents: list[dict[str, Any]] = []
    reports: list[dict[str, Any]] = []
    for path in pdf_paths:
        report: dict[str, Any] = {
            "pdf": path.name,
            "path": str(path),
            "status": "rejected",
            "errors": [],
        }
        try:
            pdf_bytes = path.read_bytes()
            validate_felgtbi_pdf(pdf_bytes, path.name)
            year = _path_year(path)
            documents = parse_felgtbi_pdf_bytes(
                pdf_bytes,
                file_name=path.name,
                year=year,
                require_storage=require_storage,
                upload_id=f"batch-{path.stem[:40]}",
            )
            if not documents:
                raise ValueError("invalid_felgtbi_pdf")
            all_documents.extend(documents)
            report.update(_document_report(documents))
            report["status"] = "imported"
        except Exception as exc:
            logger.exception("felgtbi_batch_pdf_failed file=%s", path.name)
            report["errors"] = [f"{type(exc).__name__}: {exc}"]
        reports.append(report)

    if not all_documents:
        raise RuntimeError("felgtbi_batch_without_valid_documents")
    persisted = replace_indicator_felgtbi_documents(all_documents, batch_size=batch_size)
    return {
        "pdf_found": len(pdf_paths),
        "pdf_imported": sum(report["status"] == "imported" for report in reports),
        "pdf_rejected": sum(report["status"] != "imported" for report in reports),
        "documents_persisted": persisted,
        "years": sorted(
            {int(document["year"]) for document in all_documents if document.get("year")},
            reverse=True,
        ),
        "reports": reports,
    }


def _path_year(path: Path) -> int | None:
    for value in (path.parent.name, path.name):
        match = YEAR_PATTERN.search(value)
        if match:
            return int(match.group(1))
    return None


def _document_report(documents: list[dict[str, Any]]) -> dict[str, Any]:
    sections = {
        str(document.get("section_title") or "").strip()
        for document in documents
        if str(document.get("section_title") or "").strip()
    }
    figures = [
        document.get("figure") for document in documents if isinstance(document.get("figure"), dict)
    ]
    stored = [figure for figure in figures if str((figure or {}).get("storage_path") or "").strip()]
    discarded: dict[str, int] = {}
    for document in documents:
        extraction = document.get("extraction")
        reasons = (
            extraction.get("semantic_cleanup_reasons") if isinstance(extraction, dict) else None
        )
        if not isinstance(reasons, dict):
            continue
        for reason, count in reasons.items():
            key = str(reason or "unknown")
            discarded[key] = discarded.get(key, 0) + int(count or 0)
    return {
        "year": int(documents[0].get("year") or 0),
        "title": str(documents[0].get("report_title") or ""),
        "sections": len(sections),
        "indicators": len(documents),
        "figures": len(figures),
        "figures_stored": len(stored),
        "discarded": discarded,
        "errors": [],
    }
