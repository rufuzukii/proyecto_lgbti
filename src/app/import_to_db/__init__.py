from .fra_importer import (
    convert_fra_csv_files,
    generate_fra_json,
    parse_answer_survey_csv,
    parse_answer_survey_csv_text,
)
from .rainbow_importer import (
    convert_rainbow_csv_files,
    generate_rainbow_json,
    parse_rainbow_map_csv,
    parse_rainbow_map_csv_text,
)


def register_failed_import(*args, **kwargs):
    from .import_log import register_failed_import as _register_failed_import

    return _register_failed_import(*args, **kwargs)


def register_pending_import(*args, **kwargs):
    from .import_log import register_pending_import as _register_pending_import

    return _register_pending_import(*args, **kwargs)

__all__ = [
    "convert_fra_csv_files",
    "generate_fra_json",
    "parse_answer_survey_csv",
    "parse_answer_survey_csv_text",
    "convert_rainbow_csv_files",
    "generate_rainbow_json",
    "parse_rainbow_map_csv",
    "parse_rainbow_map_csv_text",
    "register_failed_import",
    "register_pending_import",
]
