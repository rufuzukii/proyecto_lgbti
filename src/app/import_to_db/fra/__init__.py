from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .importer import (
        convert_fra_csv_files,
        generate_fra_json,
        parse_answer_survey_csv,
        parse_answer_survey_csv_text,
    )
    from .indicators import upsert_indicators_from_json
    from .mongo import INDICATOR_FRA_COLLECTION, insert_indicator_fra_json
    from .payload import (
        build_fra_questions_payload,
        count_fra_questions,
        generate_fra_questions_json,
        parse_fra_csv,
        parse_fra_csv_text,
    )


_LAZY_EXPORTS = {
    "convert_fra_csv_files": ("app.import_to_db.fra.importer", "convert_fra_csv_files"),
    "generate_fra_json": ("app.import_to_db.fra.importer", "generate_fra_json"),
    "parse_answer_survey_csv": ("app.import_to_db.fra.importer", "parse_answer_survey_csv"),
    "parse_answer_survey_csv_text": (
        "app.import_to_db.fra.importer",
        "parse_answer_survey_csv_text",
    ),
    "build_fra_questions_payload": (
        "app.import_to_db.fra.payload",
        "build_fra_questions_payload",
    ),
    "count_fra_questions": ("app.import_to_db.fra.payload", "count_fra_questions"),
    "generate_fra_questions_json": (
        "app.import_to_db.fra.payload",
        "generate_fra_questions_json",
    ),
    "parse_fra_csv": ("app.import_to_db.fra.payload", "parse_fra_csv"),
    "parse_fra_csv_text": ("app.import_to_db.fra.payload", "parse_fra_csv_text"),
    "INDICATOR_FRA_COLLECTION": ("app.import_to_db.fra.mongo", "INDICATOR_FRA_COLLECTION"),
    "insert_indicator_fra_json": ("app.import_to_db.fra.mongo", "insert_indicator_fra_json"),
    "upsert_indicators_from_json": (
        "app.import_to_db.fra.indicators",
        "upsert_indicators_from_json",
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


__all__ = list(_LAZY_EXPORTS)
