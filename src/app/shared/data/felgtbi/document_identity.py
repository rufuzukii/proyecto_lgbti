from __future__ import annotations

import hashlib
import re
import unicodedata
from pathlib import Path

_TECHNICAL_FILENAME_TOKEN = re.compile(
    r"\b(?:final|revisado|version|versi[oó]n|v\d+|felgtbi?|lgrbi|informe)\b",
    re.IGNORECASE,
)
_TRAILING_YEAR = re.compile(r"(?:^|\s)[_-]?(?:20)?\d{2}(?:\s|$)")
_DASHES = "-\u2013\u2014"
_TRAILING_INDICATOR_VALUE = re.compile(
    r"\s*(?:[-\u2013\u2014·|:]\s*)?"
    r"(?:\d{1,3}(?:[.,]\d{1,2})?\s*%|\d{1,3}[.,]\d{1,2})\s*$"
)
_LEADING_REPORT_PREFIX = re.compile(
    r"^\s*(?:informe|estado\s+lgtbi\+?\s*\d{2,4})\s*[-\u2013\u2014·|:]\s*",
    re.IGNORECASE,
)


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


def clean_felgtbi_document_label(file_name: str, report_title: str = "") -> str:
    """Devuelve una etiqueta legible del informe sin cambiar su identidad persistente."""
    title = " ".join(str(report_title or "").split()).strip(f" ._{_DASHES}")
    if title and not _is_generic_report_title(title):
        return title

    stem = Path(safe_original_filename(file_name)).stem
    stem = unicodedata.normalize("NFC", stem).replace("_", " ").replace("-", " ")
    stem = _TECHNICAL_FILENAME_TOKEN.sub(" ", stem)
    stem = _TRAILING_YEAR.sub(" ", stem)
    stem = re.sub(r"\s+", " ", stem).strip(f" ._{_DASHES}")
    return stem[:1].upper() + stem[1:] if stem else "Informe FELGTBI+"


def clean_felgtbi_indicator_label(label: str, document_title: str = "") -> str:
    """Limpia solo la etiqueta visible y conserva los códigos canónicos."""
    clean = " ".join(str(label or "").split()).strip()
    title = " ".join(str(document_title or "").split()).strip()
    if title:
        clean = re.sub(
            rf"^\s*{re.escape(title)}\s*(?:[-\u2013\u2014·|:]\s*)?",
            "",
            clean,
            flags=re.IGNORECASE,
        )
    clean = _LEADING_REPORT_PREFIX.sub("", clean)
    clean = _TRAILING_INDICATOR_VALUE.sub("", clean)
    clean = re.sub(r"\s*(?:[-\u2013\u2014·|:]\s*)+$", "", clean)
    clean = re.sub(r"\s{2,}", " ", clean).strip(f" ._{_DASHES}·|:")
    return clean or "Indicador FELGTBI+"


def _is_generic_report_title(value: str) -> bool:
    normalized = unicodedata.normalize("NFKD", value)
    normalized = normalized.encode("ascii", "ignore").decode("ascii").casefold()
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized).strip()
    return bool(
        re.fullmatch(r"(?:i\s+)?informe(?:\s+felgtbi?)?(?:\s+20\d{2})?", normalized)
        or re.fullmatch(r"estado\s+lgtbi(?:q)?(?:\s+20\d{2})?", normalized)
    )


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
