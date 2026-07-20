from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .felgtbi import (
        parse_felgtbi_pdf,
        parse_felgtbi_pdf_bytes,
        parse_felgtbi_text_pages,
        discover_felgtbi_pdfs,
        parse_felgtbi_pdf_links,
    )
    from .fra import (
        build_fra_questions_payload,
        count_fra_questions,
        convert_fra_csv_files,
        generate_fra_json,
        generate_fra_questions_json,
        parse_answer_survey_csv,
        parse_answer_survey_csv_text,
        parse_fra_csv,
        parse_fra_csv_text,
    )
    from .ilga import (
        extract_ilga_year,
        generate_ilga_json,
        parse_ilga_csv,
        parse_ilga_csv_text,
        parse_ilga_json_text,
    )


_LAZY_EXPORTS = {
    "parse_felgtbi_pdf": ("app.import_to_db.felgtbi", "parse_felgtbi_pdf"),
    "parse_felgtbi_pdf_bytes": ("app.import_to_db.felgtbi", "parse_felgtbi_pdf_bytes"),
    "parse_felgtbi_text_pages": ("app.import_to_db.felgtbi", "parse_felgtbi_text_pages"),
    "discover_felgtbi_pdfs": ("app.import_to_db.felgtbi", "discover_felgtbi_pdfs"),
    "parse_felgtbi_pdf_links": ("app.import_to_db.felgtbi", "parse_felgtbi_pdf_links"),
    "build_fra_questions_payload": ("app.import_to_db.fra", "build_fra_questions_payload"),
    "count_fra_questions": ("app.import_to_db.fra", "count_fra_questions"),
    "convert_fra_csv_files": ("app.import_to_db.fra", "convert_fra_csv_files"),
    "generate_fra_json": ("app.import_to_db.fra", "generate_fra_json"),
    "generate_fra_questions_json": ("app.import_to_db.fra", "generate_fra_questions_json"),
    "parse_answer_survey_csv": ("app.import_to_db.fra", "parse_answer_survey_csv"),
    "parse_answer_survey_csv_text": ("app.import_to_db.fra", "parse_answer_survey_csv_text"),
    "parse_fra_csv": ("app.import_to_db.fra", "parse_fra_csv"),
    "parse_fra_csv_text": ("app.import_to_db.fra", "parse_fra_csv_text"),
    "extract_ilga_year": ("app.import_to_db.ilga", "extract_ilga_year"),
    "generate_ilga_json": ("app.import_to_db.ilga", "generate_ilga_json"),
    "parse_ilga_csv": ("app.import_to_db.ilga", "parse_ilga_csv"),
    "parse_ilga_csv_text": ("app.import_to_db.ilga", "parse_ilga_csv_text"),
    "parse_ilga_json_text": ("app.import_to_db.ilga", "parse_ilga_json_text"),
}


def register_failed_import(*args, **kwargs):
    from .import_log import register_failed_import as _register_failed_import

    return _register_failed_import(*args, **kwargs)


def register_pending_import(*args, **kwargs):
    from .import_log import register_pending_import as _register_pending_import

    return _register_pending_import(*args, **kwargs)


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
    "parse_felgtbi_pdf",
    "parse_felgtbi_pdf_bytes",
    "parse_felgtbi_text_pages",
    "discover_felgtbi_pdfs",
    "parse_felgtbi_pdf_links",
    "build_fra_questions_payload",
    "count_fra_questions",
    "convert_fra_csv_files",
    "generate_fra_json",
    "generate_fra_questions_json",
    "parse_answer_survey_csv",
    "parse_answer_survey_csv_text",
    "parse_fra_csv",
    "parse_fra_csv_text",
    "extract_ilga_year",
    "generate_ilga_json",
    "parse_ilga_csv",
    "parse_ilga_csv_text",
    "parse_ilga_json_text",
    "register_failed_import",
    "register_pending_import",
]
