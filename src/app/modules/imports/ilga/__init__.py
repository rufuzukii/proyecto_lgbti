from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .importer import (
        ILGA_DATASET_CODE,
        IlgaValidationError,
        extract_ilga_year,
        parse_ilga_csv,
        parse_ilga_csv_text,
        parse_ilga_json,
        parse_ilga_json_text,
    )
    from .mongo import INDICATOR_ILGA_COLLECTION, insert_indicator_ilga_json


_LAZY_EXPORTS = {
    "ILGA_DATASET_CODE": ("app.modules.imports.ilga.importer", "ILGA_DATASET_CODE"),
    "IlgaValidationError": ("app.modules.imports.ilga.importer", "IlgaValidationError"),
    "extract_ilga_year": ("app.modules.imports.ilga.importer", "extract_ilga_year"),
    "parse_ilga_csv": ("app.modules.imports.ilga.importer", "parse_ilga_csv"),
    "parse_ilga_csv_text": ("app.modules.imports.ilga.importer", "parse_ilga_csv_text"),
    "parse_ilga_json": ("app.modules.imports.ilga.importer", "parse_ilga_json"),
    "parse_ilga_json_text": ("app.modules.imports.ilga.importer", "parse_ilga_json_text"),
    "INDICATOR_ILGA_COLLECTION": (
        "app.modules.imports.ilga.mongo",
        "INDICATOR_ILGA_COLLECTION",
    ),
    "insert_indicator_ilga_json": (
        "app.modules.imports.ilga.mongo",
        "insert_indicator_ilga_json",
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
    "ILGA_DATASET_CODE",
    "INDICATOR_ILGA_COLLECTION",
    "IlgaValidationError",
    "extract_ilga_year",
    "insert_indicator_ilga_json",
    "parse_ilga_csv",
    "parse_ilga_csv_text",
    "parse_ilga_json",
    "parse_ilga_json_text",
]
