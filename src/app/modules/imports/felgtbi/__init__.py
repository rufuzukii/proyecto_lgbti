from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .batch import import_felgtbi_pdf_directory
    from .importer import (
        FELGTBI_SOURCE_CODE,
        parse_felgtbi_text_pages,
    )
    from .mongo import (
        INDICATOR_FELGTBI_COLLECTION,
        insert_indicator_felgtbi_json,
        replace_indicator_felgtbi_documents,
    )
    from .pipeline import parse_felgtbi_pdf, parse_felgtbi_pdf_bytes
    from .scraper import discover_felgtbi_pdfs, parse_felgtbi_pdf_links


_LAZY_EXPORTS = {
    "import_felgtbi_pdf_directory": (
        "app.modules.imports.felgtbi.batch",
        "import_felgtbi_pdf_directory",
    ),
    "FELGTBI_SOURCE_CODE": ("app.modules.imports.felgtbi.importer", "FELGTBI_SOURCE_CODE"),
    "parse_felgtbi_pdf": ("app.modules.imports.felgtbi.pipeline", "parse_felgtbi_pdf"),
    "parse_felgtbi_pdf_bytes": (
        "app.modules.imports.felgtbi.pipeline",
        "parse_felgtbi_pdf_bytes",
    ),
    "parse_felgtbi_text_pages": (
        "app.modules.imports.felgtbi.importer",
        "parse_felgtbi_text_pages",
    ),
    "INDICATOR_FELGTBI_COLLECTION": (
        "app.modules.imports.felgtbi.mongo",
        "INDICATOR_FELGTBI_COLLECTION",
    ),
    "insert_indicator_felgtbi_json": (
        "app.modules.imports.felgtbi.mongo",
        "insert_indicator_felgtbi_json",
    ),
    "replace_indicator_felgtbi_documents": (
        "app.modules.imports.felgtbi.mongo",
        "replace_indicator_felgtbi_documents",
    ),
    "discover_felgtbi_pdfs": (
        "app.modules.imports.felgtbi.scraper",
        "discover_felgtbi_pdfs",
    ),
    "parse_felgtbi_pdf_links": (
        "app.modules.imports.felgtbi.scraper",
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
    "import_felgtbi_pdf_directory",
    "insert_indicator_felgtbi_json",
    "parse_felgtbi_pdf",
    "parse_felgtbi_pdf_bytes",
    "parse_felgtbi_pdf_links",
    "parse_felgtbi_text_pages",
    "replace_indicator_felgtbi_documents",
]
