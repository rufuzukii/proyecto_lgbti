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
    "build_fra_questions_payload",
    "count_fra_questions",
    "generate_fra_questions_json",
    "parse_fra_csv",
    "parse_fra_csv_text",
    "extract_ilga_year",
    "generate_ilga_json",
    "parse_ilga_csv",
    "parse_ilga_csv_text",
    "register_failed_import",
    "register_pending_import",
]
