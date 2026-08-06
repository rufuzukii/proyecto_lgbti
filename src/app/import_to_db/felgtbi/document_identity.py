from __future__ import annotations

import hashlib


def build_pdf_source_document_id(pdf_bytes: bytes, file_name: str) -> str:
    digest = hashlib.sha1(usedforsecurity=False)
    digest.update(safe_original_filename(file_name).encode("utf-8", errors="ignore"))
    digest.update(pdf_bytes)
    return f"felgtbi_pdf_{digest.hexdigest()[:16]}"


def build_metadata_source_document_id(file_name: str, year: int, report_title: str) -> str:
    seed = f"{safe_original_filename(file_name)}|{year}|{report_title}"
    digest = hashlib.sha1(seed.encode("utf-8", errors="ignore"), usedforsecurity=False).hexdigest()
    return f"felgtbi_pdf_{digest[:16]}"


def safe_original_filename(file_name: str) -> str:
    clean_name = str(file_name or "felgtbi.pdf").replace("\\", "/").rstrip("/")
    clean_name = clean_name.rsplit("/", 1)[-1].strip()
    return clean_name or "felgtbi.pdf"


def attach_source_document_metadata(
    documents: list[dict],
    *,
    file_name: str,
    source_document_id: str,
    overwrite_document_id: bool = False,
) -> None:
    original_filename = safe_original_filename(file_name)
    for document in documents:
        if not isinstance(document, dict):
            continue
        document["original_filename"] = str(document.get("original_filename") or original_filename)
        if overwrite_document_id or not document.get("source_document_id"):
            document["source_document_id"] = source_document_id
        document["import_status"] = str(document.get("import_status") or "processed")
