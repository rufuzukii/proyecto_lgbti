from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .importer import (
        FELGTBI_SOURCE_CODE,
        parse_felgtbi_text_pages,
    )
    from .mongo import INDICATOR_FELGTBI_COLLECTION, insert_indicator_felgtbi_json
    from .pipeline import parse_felgtbi_pdf, parse_felgtbi_pdf_bytes
    from .scraper import discover_felgtbi_pdfs, parse_felgtbi_pdf_links


_LAZY_EXPORTS = {
    "FELGTBI_SOURCE_CODE": ("app.import_to_db.felgtbi.importer", "FELGTBI_SOURCE_CODE"),
    "parse_felgtbi_pdf": ("app.import_to_db.felgtbi.pipeline", "parse_felgtbi_pdf"),
    "parse_felgtbi_pdf_bytes": (
        "app.import_to_db.felgtbi.pipeline",
        "parse_felgtbi_pdf_bytes",
    ),
    "parse_felgtbi_text_pages": (
        "app.import_to_db.felgtbi.importer",
        "parse_felgtbi_text_pages",
    ),
    "INDICATOR_FELGTBI_COLLECTION": (
        "app.import_to_db.felgtbi.mongo",
        "INDICATOR_FELGTBI_COLLECTION",
    ),
    "insert_indicator_felgtbi_json": (
        "app.import_to_db.felgtbi.mongo",
        "insert_indicator_felgtbi_json",
    ),
    "discover_felgtbi_pdfs": (
        "app.import_to_db.felgtbi.scraper",
        "discover_felgtbi_pdfs",
    ),
    "parse_felgtbi_pdf_links": (
        "app.import_to_db.felgtbi.scraper",
        "parse_felgtbi_pdf_links",
    ),
}


def __getattr__(name: str) -> Any:
    try:
        module_name, attribute_name = _LAZY_EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc

    from importlib import import_module

    value = getattr(import_module(module_name), attribute_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted([*globals(), *_LAZY_EXPORTS])


__all__ = [
    "FELGTBI_SOURCE_CODE",
    "INDICATOR_FELGTBI_COLLECTION",
    "discover_felgtbi_pdfs",
    "insert_indicator_felgtbi_json",
    "parse_felgtbi_pdf",
    "parse_felgtbi_pdf_bytes",
    "parse_felgtbi_pdf_links",
    "parse_felgtbi_text_pages",
]
