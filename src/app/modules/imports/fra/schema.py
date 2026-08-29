from __future__ import annotations

import csv
import hashlib
import logging
import math
import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass, field
from io import StringIO
from pathlib import Path
from typing import Any, Literal, cast

import pandas as pd

from app.shared.data.fra_validation import (
    FRA_FOOTNOTE_MOJIBAKE,
    FRA_FOOTNOTE_SYMBOLS,
    fra_metadata_key,
    is_fra_footnote_symbol,
    is_valid_fra_category,
)
from app.shared.data.normalization import normalize_header

logger = logging.getLogger(__name__)

FRA_SOURCE_NAME = "EU LGBTIQ+ Survey (FRA)"
FRA_SOURCE_TYPE = "EU_SURVEY"
FRA_MIN_SURVEY_YEAR = 1990
FRA_MAX_SURVEY_YEAR = 2100

FraCsvVersion = Literal["legacy_long", "current_wide"]
PercentageScale = Literal["percentage_points", "proportion"]

MISSING_PERCENTAGE_VALUES = frozenset({"", "null", "none", "n/a", "na", ":", "-", "..", "‡", "¹"})
HTML_PREFIXES = ("<html", "<!doctype html", "<?xml")
FRA_DUPLICATE_COLUMN_SUFFIX = "__fra_duplicate_"

NORMALIZED_FRA_COLUMNS = (
    "source",
    "source_type",
    "category",
    "specific_category",
    "question",
    "indicator_id",
    "country_name",
    "country_code",
    "country_scope",
    "response",
    "percentage",
    "raw_percentage",
    "survey_year",
    "date",
    "filter_a_type",
    "filter_a_value",
    "filter_b_type",
    "filter_b_value",
    "filters",
    "notes",
    "hyperlink",
    "schema_version",
)

FILTER_TYPE_TO_KEY = {
    "age": "age_group",
    "age group": "age_group",
    "edad": "age_group",
    "belonging to a minority group": "minority_group",
    "minority group": "minority_group",
    "minority": "minority_group",
    "education": "education",
    "education level": "education",
    "openness about being lgbtiq": "openness",
    "openness": "openness",
    "employment status": "employment_status",
    "employment": "employment_status",
    "place of residence": "place_of_residence",
    "residence": "place_of_residence",
    "activity limitation": "activity_limitation",
    "disability": "activity_limitation",
    "making ends meet": "making_ends_meet",
    "sexual orientation": "sexual_orientation",
    "orientation": "sexual_orientation",
    "so": "sexual_orientation",
    "gender expression": "gender_expression",
    "gender identity": "gender_expression",
    "ge": "gender_expression",
    "gi": "gender_expression",
    "sex characteristics": "sex_characteristics",
    "sex characteristic": "sex_characteristics",
    "sc": "sex_characteristics",
}


def _fra_response_comparison_key(value: Any) -> str:
    """Compare response labels while tolerating harmless punctuation loss in FRA exports."""
    normalized = unicodedata.normalize("NFKD", normalize_header(value)).casefold()
    return "".join(character for character in normalized if character.isalnum())

FILTER_KEY_TO_LABEL = {
    "age_group": "Age",
    "minority_group": "Belonging to a minority group",
    "education": "Education",
    "openness": "Openness about being LGBTIQ+",
    "employment_status": "Employment status",
    "place_of_residence": "Place of residence",
    "activity_limitation": "Activity limitation",
    "making_ends_meet": "Making ends meet",
    "sexual_orientation": "Sexual Orientation",
    "gender_expression": "Gender Expression",
    "sex_characteristics": "Sex Characteristics",
}

FILTER_GROUP_A_KEYS = frozenset(
    {
        "age_group",
        "minority_group",
        "education",
        "openness",
        "employment_status",
        "place_of_residence",
        "activity_limitation",
        "making_ends_meet",
    }
)
FILTER_GROUP_B_KEYS = frozenset({"sexual_orientation", "gender_expression", "sex_characteristics"})

COLUMN_ALIASES = {
    "country": "country",
    "country_name": "country",
    "location": "country",
    "pais": "country",
    "territory": "country",
    "country_code": "country_code",
    # Survey II calls this field CountryCode although its values are names.
    "countrycode": "country",
    "iso": "country_code",
    "iso2": "country_code",
    "topic": "topic",
    "tema": "topic",
    "category": "category",
    "categoria": "category",
    "question": "question",
    "question_label": "question",
    "pregunta": "question",
    "indicator": "question",
    "indicador": "question",
    "answer": "answer",
    "response": "answer",
    "respuesta": "answer",
    "value": "percentage",
    "valor": "percentage",
    "percentage": "percentage",
    "percent": "percentage",
    "porcentaje": "percentage",
    "proportion": "proportion",
    "share": "proportion",
    "ratio": "proportion",
    "notes": "notes",
    "note": "notes",
    "notas": "notes",
    "nota": "notes",
    "source": "source",
    "fuente": "source",
    "question_code": "indicator_id",
    "questioncode": "indicator_id",
    "indicator_code": "indicator_id",
    "indicator_id": "indicator_id",
    "external_code": "indicator_id",
    "codigo_pregunta": "indicator_id",
    "codigo": "indicator_id",
    "date": "date",
    "fecha": "date",
    "year": "year",
    "ano": "year",
    "anio": "year",
    "hyperlink": "hyperlink",
    "link": "hyperlink",
    "url": "hyperlink",
}

RESERVED_CURRENT_COLUMNS = frozenset(
    {
        "topic",
        "question",
        "question_code",
        "location",
        "country",
        "comment",
        "comments",
        "unit",
        "year",
        "notes",
        "note",
        "source",
        "date",
        "filters",
        "hyperlink",
    }
)
COUNTRY_NAME_CODES = {
    "albania": "AL",
    "austria": "AT",
    "belgium": "BE",
    "bulgaria": "BG",
    "croatia": "HR",
    "cyprus": "CY",
    "czechia": "CZ",
    "czech republic": "CZ",
    "denmark": "DK",
    "estonia": "EE",
    "finland": "FI",
    "france": "FR",
    "germany": "DE",
    "greece": "GR",
    "hungary": "HU",
    "ireland": "IE",
    "italy": "IT",
    "latvia": "LV",
    "lithuania": "LT",
    "luxembourg": "LU",
    "malta": "MT",
    "netherlands": "NL",
    "north macedonia": "MK",
    "poland": "PL",
    "portugal": "PT",
    "romania": "RO",
    "serbia": "RS",
    "slovakia": "SK",
    "slovenia": "SI",
    "spain": "ES",
    "espana": "ES",
    "sweden": "SE",
    "united kingdom": "GB",
    "eu 28": "EU28",
    "eu-28": "EU28",
}
COUNTRY_CODE_ALIASES = {"EL": "GR", "UK": "GB"}


class FraCsvError(ValueError):
    """Base class for CSV validation failures safe to expose in the UI."""


class UnsupportedFraCsvSchemaError(FraCsvError):
    pass


class InvalidFraCsvError(FraCsvError):
    pass


class FraMetadataMismatchError(FraCsvError):
    pass


class FraDuplicateConflictError(FraCsvError):
    pass


@dataclass(frozen=True)
class FraCsvSchema:
    version: FraCsvVersion
    delimiter: str
    original_columns: tuple[str, ...]
    country_name_column: str
    country_code_column: str | None
    topic_column: str | None
    question_column: str
    indicator_column: str | None
    response_column: str | None
    percentage_columns: tuple[str, ...]
    year_column: str | None
    percentage_scale: PercentageScale
    metadata_layout: str
    header_row: int = 0


@dataclass(frozen=True)
class FraCsvMetadata:
    source: str = FRA_SOURCE_NAME
    survey_year: int | None = None
    downloaded_at: str = ""
    indicator_id: str = ""
    hyperlink: str = ""
    response: str = ""
    filters: dict[str, str] = field(default_factory=dict)
    note: str = ""
    disclaimer: str = ""
    footnotes: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "date": self.downloaded_at,
            "filters": dict(self.filters),
            "question_code": self.indicator_id,
            "source": self.source,
            "hyperlink": self.hyperlink,
            "note": self.note,
            "disclaimer": self.disclaimer,
            "footnotes": dict(self.footnotes),
            "survey_year": self.survey_year,
        }


def decode_fra_csv_bytes(payload: bytes) -> str:
    if not payload:
        raise InvalidFraCsvError("empty_fra_csv")
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return ensure_fra_csv_text(payload.decode(encoding))
        except UnicodeDecodeError:
            continue
    raise InvalidFraCsvError("unsupported_fra_csv_encoding")


def ensure_fra_csv_text(csv_text: str) -> str:
    if not csv_text or not csv_text.strip():
        raise InvalidFraCsvError("empty_fra_csv")
    if csv_text.lstrip().casefold().startswith(HTML_PREFIXES):
        raise InvalidFraCsvError("html_instead_of_fra_csv")
    return csv_text


def read_fra_csv_text(csv_text: str) -> tuple[pd.DataFrame, FraCsvSchema]:
    ensure_fra_csv_text(csv_text)
    delimiter = _detect_delimiter(csv_text)
    try:
        rows = list(csv.reader(StringIO(csv_text), delimiter=delimiter))
    except csv.Error as exc:
        raise InvalidFraCsvError("malformed_fra_csv") from exc
    header_row = find_fra_header_row(rows)
    dataframe = _dataframe_from_fra_rows(rows, header_row=header_row)
    dataframe.attrs["fra_preamble_rows"] = rows[:header_row]
    dataframe.attrs["fra_header_row"] = header_row
    schema = detect_fra_csv_schema(dataframe, delimiter=delimiter)
    logger.info(
        "fra_header_row_detected",
        extra={
            "header_row": header_row,
            "delimiter": delimiter,
            "columns": list(schema.original_columns),
            "schema_version": schema.version,
        },
    )
    return dataframe, schema


def find_fra_header_row(rows: list[list[str]]) -> int:
    best_index: int | None = None
    best_score = 0
    for index, row in enumerate(rows):
        score = _fra_header_score(row)
        if score > best_score:
            best_index = index
            best_score = score
    if best_index is None:
        raise UnsupportedFraCsvSchemaError("fra_csv_header_not_detected")
    return best_index


def detect_fra_csv_schema(
    dataframe: pd.DataFrame,
    *,
    delimiter: str = ",",
) -> FraCsvSchema:
    if dataframe is None or len(dataframe.columns) == 0:
        raise InvalidFraCsvError("empty_fra_csv")
    original_columns = tuple(str(column) for column in dataframe.columns)
    normalized_to_original = {normalize_header(column): column for column in original_columns}
    normalized = set(normalized_to_original)
    current_required = {"topic", "question", "question_code", "location", "country"}
    if current_required.issubset(normalized):
        answer_columns = _detect_current_answer_columns(dataframe, normalized_to_original)
        if not answer_columns:
            raise UnsupportedFraCsvSchemaError("fra_current_schema_without_answer_columns")
        return FraCsvSchema(
            version="current_wide",
            delimiter=delimiter,
            original_columns=original_columns,
            country_name_column=normalized_to_original["location"],
            country_code_column=normalized_to_original["country"],
            topic_column=normalized_to_original["topic"],
            question_column=normalized_to_original["question"],
            indicator_column=normalized_to_original["question_code"],
            response_column=None,
            percentage_columns=answer_columns,
            year_column=normalized_to_original.get("year"),
            percentage_scale="percentage_points",
            metadata_layout="fra_footer_rows",
            header_row=int(dataframe.attrs.get("fra_header_row") or 0),
        )

    canonical = {
        COLUMN_ALIASES.get(normalized_name, normalized_name): original
        for normalized_name, original in normalized_to_original.items()
    }
    if {"country", "question"}.issubset(canonical) and (
        {"answer", "percentage"}.issubset(canonical) or {"answer", "proportion"}.issubset(canonical)
    ):
        percentage_key = "proportion" if "proportion" in canonical else "percentage"
        return FraCsvSchema(
            version="legacy_long",
            delimiter=delimiter,
            original_columns=original_columns,
            country_name_column=canonical["country"],
            country_code_column=canonical.get("country_code"),
            topic_column=canonical.get("topic"),
            question_column=canonical["question"],
            indicator_column=canonical.get("indicator_id"),
            response_column=canonical["answer"],
            percentage_columns=(canonical[percentage_key],),
            year_column=canonical.get("year"),
            percentage_scale=(
                "proportion" if percentage_key == "proportion" else "percentage_points"
            ),
            metadata_layout="rows",
            header_row=int(dataframe.attrs.get("fra_header_row") or 0),
        )
    raise UnsupportedFraCsvSchemaError("unsupported_fra_csv_schema:" + ",".join(original_columns))


def normalize_fra_csv(
    dataframe: pd.DataFrame,
    schema: FraCsvSchema,
    *,
    path_filters: Mapping[str, str] | None = None,
    file_name: Path | str | None = None,
    survey_year: int | None = None,
) -> pd.DataFrame:
    if schema.version == "current_wide":
        normalized = normalize_current_fra_csv(
            dataframe,
            schema=schema,
            path_filters=path_filters,
            file_name=file_name,
        )
    elif schema.version == "legacy_long":
        normalized = normalize_legacy_fra_csv(
            dataframe,
            schema=schema,
            path_filters=path_filters,
            file_name=file_name,
            preserve_question_slashes=survey_year == 2019,
        )
    else:
        raise UnsupportedFraCsvSchemaError(f"unsupported_fra_csv_schema:{schema.version}")
    metadata = dict(normalized.attrs.get("fra_metadata") or {})
    validated = validate_normalized_fra(normalized)
    validated.attrs["fra_metadata"] = metadata
    _log_fra_import_summary(dataframe, schema, validated)
    return validated


def normalize_current_fra_csv(
    dataframe: pd.DataFrame,
    schema: FraCsvSchema | None = None,
    *,
    path_filters: Mapping[str, str] | None = None,
    file_name: Path | str | None = None,
) -> pd.DataFrame:
    current_schema = schema or detect_fra_csv_schema(dataframe)
    if current_schema.version != "current_wide":
        raise UnsupportedFraCsvSchemaError("expected_current_fra_csv")
    metadata = extract_fra_csv_metadata(dataframe, current_schema, file_name=file_name)
    filters = metadata.filters or _canonical_filter_dict(path_filters or {})
    filter_scope = _split_filter_scope(filters)
    rows: list[dict[str, Any]] = []
    for record in dataframe.to_dict(orient="records"):
        label = _clean(record.get(current_schema.topic_column or ""))
        if fra_metadata_key(label) or is_fra_footnote_symbol(label):
            continue
        indicator_id = _clean(record.get(current_schema.indicator_column or ""))
        country_name = _clean(record.get(current_schema.country_name_column))
        question_text = _clean(record.get(current_schema.question_column))
        if not indicator_id or not country_name or not question_text:
            continue
        country_code = normalize_country_code(
            record.get(current_schema.country_code_column or ""), country_name
        )
        topic = _clean(record.get(current_schema.topic_column or "")) or "Uncategorized"
        if not is_valid_fra_category(topic):
            continue
        specific_category, question = split_fra_question(question_text, fallback_category=topic)
        for percentage_column in current_schema.percentage_columns:
            response = _fra_column_label(percentage_column)
            if normalize_header(response) == "value":
                response = "Mean"
            if (
                metadata.response
                and len(current_schema.percentage_columns) == 1
                and _fra_response_comparison_key(metadata.response)
                != _fra_response_comparison_key(response)
            ):
                raise FraMetadataMismatchError(
                    f"fra_answer_metadata_mismatch:header={response}:metadata={metadata.response}"
                )
            raw_percentage = _clean(record.get(percentage_column))
            percentage = parse_fra_percentage(raw_percentage, scale=current_schema.percentage_scale)
            if is_fra_footnote_symbol(response):
                continue
            rows.append(
                _normalized_row(
                    source=metadata.source,
                    category=topic,
                    specific_category=specific_category,
                    question=question,
                    indicator_id=indicator_id,
                    country_name=country_name,
                    country_code=country_code,
                    response=response,
                    percentage=percentage,
                    raw_percentage=raw_percentage,
                    survey_year=metadata.survey_year,
                    date=metadata.downloaded_at,
                    filters=filters,
                    filter_scope=filter_scope,
                    notes=_note_for_percentage(raw_percentage, metadata),
                    hyperlink=metadata.hyperlink,
                    schema_version=current_schema.version,
                )
            )
    normalized = _normalized_dataframe(rows)
    normalized.attrs["fra_metadata"] = metadata.to_dict()
    return normalized


def normalize_legacy_fra_csv(
    dataframe: pd.DataFrame,
    schema: FraCsvSchema | None = None,
    *,
    path_filters: Mapping[str, str] | None = None,
    file_name: Path | str | None = None,
    preserve_question_slashes: bool = False,
) -> pd.DataFrame:
    legacy_schema = schema or detect_fra_csv_schema(dataframe)
    if legacy_schema.version != "legacy_long":
        raise UnsupportedFraCsvSchemaError("expected_legacy_fra_csv")
    metadata = extract_fra_csv_metadata(dataframe, legacy_schema, file_name=file_name)
    original_to_canonical = {
        original: COLUMN_ALIASES.get(normalize_header(original), normalize_header(original))
        for original in legacy_schema.original_columns
    }
    fallback_filters = _canonical_filter_dict(path_filters or {})
    rows: list[dict[str, Any]] = []
    for raw_record in cast(list[dict[str, Any]], dataframe.to_dict(orient="records")):
        record = {
            canonical: _clean(raw_record.get(original))
            for original, canonical in original_to_canonical.items()
        }
        if _is_metadata_record(record) or _is_footnote_record(record):
            continue
        country_name = record.get("country", "")
        question_text = record.get("question", "")
        response = record.get("answer", "")
        if not country_name or not question_text or not response:
            continue
        filters = dict(fallback_filters)
        filters.update(_legacy_record_filters(record, raw_record, original_to_canonical))
        filter_scope = _split_filter_scope(filters)
        topic = record.get("topic") or record.get("category") or "Uncategorized"
        if not is_valid_fra_category(topic):
            continue
        specific_category, question = split_fra_question(
            question_text,
            fallback_category=record.get("category") or topic,
            split_slash=not preserve_question_slashes,
        )
        indicator_id = (
            record.get("indicator_id") or metadata.indicator_id or build_fra_question_code(question)
        )
        raw_percentage = record.get("proportion") or record.get("percentage", "")
        percentage = parse_fra_percentage(raw_percentage, scale=legacy_schema.percentage_scale)
        if is_fra_footnote_symbol(response):
            continue
        rows.append(
            _normalized_row(
                source=record.get("source") or metadata.source,
                category=topic,
                specific_category=specific_category,
                question=question,
                indicator_id=indicator_id,
                country_name=country_name,
                country_code=normalize_country_code(record.get("country_code"), country_name),
                response=response,
                percentage=percentage,
                raw_percentage=raw_percentage,
                survey_year=(
                    metadata.survey_year
                    or extract_fra_survey_year(record.get("year") or record.get("date"))
                ),
                date=record.get("date") or metadata.downloaded_at,
                filters=filters,
                filter_scope=filter_scope,
                notes=record.get("notes", ""),
                hyperlink=record.get("hyperlink") or metadata.hyperlink,
                schema_version=legacy_schema.version,
            )
        )
    normalized = _normalized_dataframe(rows)
    normalized.attrs["fra_metadata"] = metadata.to_dict()
    return normalized


def extract_fra_csv_metadata(
    dataframe: pd.DataFrame,
    schema: FraCsvSchema,
    *,
    file_name: Path | str | None = None,
) -> FraCsvMetadata:
    source = FRA_SOURCE_NAME
    source_year: int | None = None
    metadata_year: int | None = None
    downloaded_at = ""
    indicator_id = ""
    hyperlink = ""
    response = ""
    filters: dict[str, str] = {}
    note = ""
    disclaimer = ""
    footnotes: dict[str, str] = {}
    if dataframe.empty and len(dataframe.columns) == 0:
        return FraCsvMetadata()

    if schema.version == "current_wide":
        label_column = schema.topic_column or schema.country_name_column
        value_column = schema.question_column
    else:
        label_column = schema.country_name_column
        value_column = schema.topic_column or schema.question_column

    metadata_pairs = [
        (_clean(row[0]) if row else "", _clean(row[1]) if len(row) > 1 else "")
        for row in dataframe.attrs.get("fra_preamble_rows", [])
    ]
    records = dataframe.to_dict(orient="records")
    metadata_pairs.extend(
        (
            _clean(record.get(label_column)),
            _clean(record.get(value_column)),
        )
        for record in records
    )
    metadata_pairs.extend(
        (nonempty[0], "")
        for record in records
        if len(nonempty := [_clean(value) for value in record.values() if _clean(value)]) == 1
    )

    for raw_label, raw_value in metadata_pairs:
        label = normalize_header(raw_label.rstrip(":"))
        if not raw_label:
            continue
        if not raw_value and _is_unlabeled_fra_source(raw_label):
            source = raw_label
            source_year = extract_fra_survey_year(raw_label) or source_year
        elif label in {"filters", "filtros"}:
            response, filters = parse_fra_filter_metadata(raw_value)
        elif label in {"source", "fuente", "source_of_data"}:
            if raw_value and raw_value.casefold() != "placeholder":
                source = raw_value
            source_year = extract_fra_survey_year(raw_value) or source_year
        elif label in {"survey_year", "survey year", "ano_encuesta", "anio_encuesta"}:
            metadata_year = extract_fra_survey_year(raw_value) or metadata_year
        elif label in {"date", "fecha", "last_update"}:
            downloaded_at = raw_value
        elif label in {"question_code", "codigo_pregunta", "indicator_code", "code"}:
            indicator_id = raw_value
        elif label in {"hyperlink", "link", "url", "hyperlink_to_the_variable"}:
            hyperlink = raw_value
        elif label in {"note", "nota"}:
            note = raw_value
        elif label == "general_disclaimer_of_the_fra_website":
            disclaimer = raw_value
        elif _looks_like_footnote_label(raw_label) and raw_value:
            footnotes[raw_label.strip()] = raw_value
        elif not raw_value:
            raw_filter_type, separator, raw_filter_value = raw_label.partition(":")
            filter_key = FILTER_TYPE_TO_KEY.get(_filter_type_key(raw_filter_type))
            if separator and filter_key and raw_filter_value.strip().casefold() != "all":
                filters[filter_key] = raw_filter_value.strip()
    explicit_year = _explicit_fra_year(dataframe, schema.year_column)
    filename_year = extract_fra_survey_year(Path(file_name).stem) if file_name else None
    return FraCsvMetadata(
        source=source,
        survey_year=source_year or explicit_year or metadata_year or filename_year,
        downloaded_at=downloaded_at,
        indicator_id=indicator_id,
        hyperlink=hyperlink,
        response=response,
        filters=filters,
        note=note,
        disclaimer=disclaimer,
        footnotes=footnotes,
    )


def parse_fra_filter_metadata(value: str) -> tuple[str, dict[str, str]]:
    response = ""
    filters: dict[str, str] = {}
    for part in re.split(r"\s*[;|]\s*", str(value or "").strip()):
        if not part:
            continue
        key, separator, raw_value = part.partition(":")
        if not separator:
            key, separator, raw_value = part.partition("=")
        if not separator:
            continue
        clean_value = raw_value.strip()
        key_normalized = _filter_type_key(key)
        if key_normalized == "answer":
            response = clean_value
            continue
        canonical_key = FILTER_TYPE_TO_KEY.get(key_normalized)
        if canonical_key and clean_value.casefold() != "all":
            filters[canonical_key] = clean_value
    return response, filters


def parse_fra_percentage(
    value: Any,
    *,
    scale: PercentageScale,
) -> float | int | None:
    if isinstance(value, bool):
        raise InvalidFraCsvError("invalid_fra_percentage:boolean")
    text = _clean(value).replace("\u00a0", " ")
    if text.casefold() in MISSING_PERCENTAGE_VALUES:
        return None
    numeric_text, _footnote = _split_percentage_footnote(text)
    cleaned = numeric_text.replace(" ", "")
    had_percent_sign = cleaned.endswith("%")
    cleaned = cleaned.removesuffix("%").replace(",", ".")
    try:
        number = float(cleaned)
    except ValueError as exc:
        if _looks_like_footnote_label(text):
            return None
        raise InvalidFraCsvError(f"invalid_fra_percentage:{text}") from exc
    if not math.isfinite(number):
        raise InvalidFraCsvError(f"invalid_fra_percentage:{text}")
    if scale == "proportion" and not had_percent_sign:
        if not 0 <= number <= 1:
            raise InvalidFraCsvError(f"fra_proportion_out_of_range:{text}")
        number *= 100
    if not 0 <= number <= 100:
        raise InvalidFraCsvError(f"fra_percentage_out_of_range:{text}")
    return int(number) if number.is_integer() else number


def _split_percentage_footnote(value: str) -> tuple[str, str]:
    """Separate FRA significance markers appended to an otherwise numeric value."""
    clean = str(value or "").strip()
    if not clean:
        return clean, ""
    had_percent_sign = clean.endswith("%")
    body = clean.removesuffix("%").rstrip()
    for suffix_length in range(1, min(4, len(body) - 1) + 1):
        suffix = body[-suffix_length:]
        prefix = body[:-suffix_length].rstrip()
        if prefix and suffix in FRA_FOOTNOTE_SYMBOLS | FRA_FOOTNOTE_MOJIBAKE:
            return f"{prefix}{'%' if had_percent_sign else ''}", suffix
    return clean, ""


def validate_normalized_fra(dataframe: pd.DataFrame) -> pd.DataFrame:
    if dataframe.empty:
        raise InvalidFraCsvError("fra_csv_without_data_rows")
    missing_columns = [
        column for column in NORMALIZED_FRA_COLUMNS if column not in dataframe.columns
    ]
    if missing_columns:
        raise InvalidFraCsvError("fra_normalization_missing_columns:" + ",".join(missing_columns))
    for column in ("category", "question", "indicator_id", "country_name", "response"):
        if dataframe[column].astype(str).str.strip().eq("").any():
            raise InvalidFraCsvError(f"fra_normalization_missing_value:{column}")
    if not dataframe["category"].map(is_valid_fra_category).all():
        raise InvalidFraCsvError("fra_normalization_invalid_category")
    numeric = dataframe["percentage"].dropna().map(float)
    if ((numeric < 0) | (numeric > 100)).any():
        raise InvalidFraCsvError("fra_percentage_out_of_range")

    identity = [
        "source",
        "survey_year",
        "indicator_id",
        "question",
        "country_code",
        "country_name",
        "response",
        "filter_a_type",
        "filter_a_value",
        "filter_b_type",
        "filter_b_value",
    ]
    conflict_groups = dataframe.groupby(identity, dropna=False)["percentage"].nunique(dropna=False)
    if (conflict_groups > 1).any():
        raise FraDuplicateConflictError("fra_conflicting_duplicate_rows")
    return dataframe.drop_duplicates(subset=identity, keep="first").reset_index(drop=True)


def validate_fra_filter_scope(
    dataframe: pd.DataFrame,
    *,
    expected_filter_a_type: str,
    expected_filter_a_value: str,
    expected_filter_b_type: str,
    expected_filter_b_value: str,
) -> None:
    expected = tuple(
        _display_filter(filter_type, filter_value)
        for filter_type, filter_value in (
            (expected_filter_a_type, expected_filter_a_value),
            (expected_filter_b_type, expected_filter_b_value),
        )
    )
    expected_scope = (*expected[0], *expected[1])
    detected = {
        tuple(
            str(value)
            for value in (
                row.filter_a_type,
                row.filter_a_value,
                row.filter_b_type,
                row.filter_b_value,
            )
        )
        for row in dataframe[["filter_a_type", "filter_a_value", "filter_b_type", "filter_b_value"]]
        .drop_duplicates()
        .itertuples(index=False)
    }
    if {tuple(map(str.casefold, item)) for item in detected} != {
        tuple(map(str.casefold, expected_scope))
    }:
        raise FraMetadataMismatchError(
            f"fra_metadata_mismatch:expected={expected_scope}:detected={sorted(detected)}"
        )


def filename_declares_all_all(file_name: Path | str | None) -> bool:
    if not file_name:
        return False
    path = Path(file_name)
    stem = normalize_header(path.stem)
    if stem in {"no_filters", "no_filter"}:
        parents = [normalize_header(part) for part in path.parts[-3:-1]]
        return len(parents) == 2 and parents == ["all", "all"]
    return stem.endswith("_all_all") or "_all_all_" in f"_{stem}_"


def split_fra_question(
    question: str,
    *,
    fallback_category: str,
    split_slash: bool = True,
) -> tuple[str, str]:
    clean = _clean(question)
    category = _clean(fallback_category) or "Uncategorized"
    if ">" in clean:
        left, right = clean.split(">", 1)
        category = left.strip() or category
        clean = right.strip() or clean
    if split_slash and "/" in clean:
        left, right = clean.split("/", 1)
        category = left.strip() or category
        clean = right.strip() or clean
    return category, clean


def build_fra_question_code(question: str) -> str:
    seed = normalize_header(question) or "unknown_question"
    digest = hashlib.sha1(seed.encode("utf-8"), usedforsecurity=False).hexdigest()[:12]
    return f"fra_{digest}"


def normalize_country_code(value: Any, country_name: Any | None = None) -> str:
    code = _clean(value).upper()
    code = COUNTRY_CODE_ALIASES.get(code, code)
    if re.fullmatch(r"[A-Z]{2}|EU\d{2}|TOTAL", code):
        return code
    return COUNTRY_NAME_CODES.get(_filter_type_key(country_name), "")


def _normalized_row(
    *,
    source: str,
    category: str,
    specific_category: str,
    question: str,
    indicator_id: str,
    country_name: str,
    country_code: str,
    response: str,
    percentage: float | None,
    raw_percentage: str,
    survey_year: int | None,
    date: str,
    filters: Mapping[str, str],
    filter_scope: tuple[str, str, str, str],
    notes: str,
    hyperlink: str,
    schema_version: str,
) -> dict[str, Any]:
    filter_a_type, filter_a_value, filter_b_type, filter_b_value = filter_scope
    return {
        "source": source or FRA_SOURCE_NAME,
        "source_type": FRA_SOURCE_TYPE,
        "category": category,
        "specific_category": specific_category,
        "question": question,
        "indicator_id": indicator_id,
        "country_name": country_name,
        "country_code": country_code,
        "country_scope": "aggregate" if country_code.startswith("EU") else "country",
        "response": response,
        "percentage": percentage,
        "raw_percentage": raw_percentage,
        "survey_year": survey_year,
        "date": date,
        "filter_a_type": filter_a_type,
        "filter_a_value": filter_a_value,
        "filter_b_type": filter_b_type,
        "filter_b_value": filter_b_value,
        "filters": dict(filters),
        "notes": notes,
        "hyperlink": hyperlink,
        "schema_version": schema_version,
    }


def _normalized_dataframe(rows: list[dict[str, Any]]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=NORMALIZED_FRA_COLUMNS)


def _split_filter_scope(filters: Mapping[str, str]) -> tuple[str, str, str, str]:
    canonical = _canonical_filter_dict(filters)
    group_a = [(key, value) for key, value in canonical.items() if key in FILTER_GROUP_A_KEYS]
    group_b = [(key, value) for key, value in canonical.items() if key in FILTER_GROUP_B_KEYS]
    if len(group_a) > 1 or len(group_b) > 1:
        raise InvalidFraCsvError("fra_csv_contains_multiple_filters_in_same_group")
    if group_a:
        a_key, a_value = group_a[0]
        a_type = FILTER_KEY_TO_LABEL[a_key]
    else:
        a_type, a_value = "All", "All"
    if group_b:
        b_key, b_value = group_b[0]
        b_type = FILTER_KEY_TO_LABEL[b_key]
    else:
        b_type, b_value = "All", "All"
    return a_type, a_value, b_type, b_value


def _display_filter(filter_type: Any, filter_value: Any) -> tuple[str, str]:
    clean_type = _clean(filter_type)
    clean_value = _clean(filter_value)
    if (
        not clean_type
        or not clean_value
        or clean_type.casefold() == "all"
        or clean_value.casefold() == "all"
    ):
        return "All", "All"
    return clean_type, clean_value


def _canonical_filter_dict(filters: Mapping[str, str]) -> dict[str, str]:
    output: dict[str, str] = {}
    for raw_key, raw_value in filters.items():
        value = _clean(raw_value)
        if not value or value.casefold() == "all":
            continue
        key = FILTER_TYPE_TO_KEY.get(_filter_type_key(raw_key), normalize_header(str(raw_key)))
        if key in FILTER_KEY_TO_LABEL:
            output[key] = value
    return output


def _legacy_record_filters(
    record: Mapping[str, str],
    raw_record: Mapping[str, Any],
    original_to_canonical: Mapping[str, str],
) -> dict[str, str]:
    filters: dict[str, str] = {}
    for original, raw_value in raw_record.items():
        value = _clean(raw_value)
        if not value:
            continue
        normalized_original = normalize_header(str(original))
        canonical = original_to_canonical.get(str(original), normalized_original)
        if normalized_original in {
            "filter",
            "filters",
            "filter1",
            "filter2",
            "filter3",
            "filter_1",
            "filter_2",
            "filter_3",
            "filtro",
            "filtros",
            "filtro1",
            "filtro2",
            "filtro3",
        }:
            _response, parsed = parse_fra_filter_metadata(value)
            filters.update(parsed)
            continue
        if canonical in {
            "country",
            "country_code",
            "topic",
            "category",
            "question",
            "answer",
            "percentage",
            "proportion",
            "notes",
            "source",
            "indicator_id",
            "date",
            "year",
            "hyperlink",
        }:
            continue
        filter_key = FILTER_TYPE_TO_KEY.get(_filter_type_key(original))
        if filter_key:
            filters[filter_key] = value
    return filters


def _is_metadata_record(record: Mapping[str, str]) -> bool:
    labels = (record.get("country", ""), record.get("topic", ""), record.get("category", ""))
    return any(fra_metadata_key(label) for label in labels)


def _is_footnote_record(record: Mapping[str, str]) -> bool:
    country = record.get("country", "").strip()
    return bool(
        country
        and not record.get("answer")
        and not record.get("percentage")
        and not normalize_country_code("", country)
    )


def _note_for_percentage(raw_percentage: str, metadata: FraCsvMetadata) -> str:
    _numeric_text, footnote = _split_percentage_footnote(raw_percentage)
    if footnote:
        return metadata.footnotes.get(footnote, metadata.note)
    if parse_fra_percentage(raw_percentage, scale="percentage_points") is not None:
        return ""
    return metadata.footnotes.get(raw_percentage.strip(), metadata.note)


def extract_fra_survey_year(source_text: object) -> int | None:
    """Return one unambiguous, plausible four-digit FRA survey year."""
    matches = {
        int(match)
        for match in re.findall(r"(?<!\d)(?:19|20|21)\d{2}(?!\d)", _clean(source_text))
        if FRA_MIN_SURVEY_YEAR <= int(match) <= FRA_MAX_SURVEY_YEAR
    }
    return next(iter(matches)) if len(matches) == 1 else None


def _explicit_fra_year(dataframe: pd.DataFrame, year_column: str | None) -> int | None:
    if not year_column or year_column not in dataframe.columns:
        return None
    years = {
        year
        for value in dataframe[year_column].tolist()
        if (year := extract_fra_survey_year(value)) is not None
    }
    return next(iter(years)) if len(years) == 1 else None


def _looks_like_footnote_label(value: str) -> bool:
    return is_fra_footnote_symbol(value)


def _is_unlabeled_fra_source(value: str) -> bool:
    normalized = normalize_header(value)
    return normalized.startswith("eu_lgbtiq_survey") and extract_fra_survey_year(value) is not None


def _filter_type_key(value: Any) -> str:
    ascii_text = (
        unicodedata.normalize("NFKD", _clean(value))
        .encode("ascii", "ignore")
        .decode("ascii")
        .casefold()
        .replace("_", " ")
    )
    return " ".join(ascii_text.split())


def _clean(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _detect_current_answer_columns(
    dataframe: pd.DataFrame,
    normalized_to_original: Mapping[str, str],
) -> tuple[str, ...]:
    candidates: list[str] = []
    topic_column = normalized_to_original["topic"]
    for normalized, original in normalized_to_original.items():
        if normalized in RESERVED_CURRENT_COLUMNS:
            continue
        values = (
            dataframe.loc[
                ~dataframe[topic_column].astype(str).str.strip().str.endswith(":"), original
            ]
            .astype(str)
            .str.strip()
        )
        meaningful = [
            value for value in values if value.casefold() not in MISSING_PERCENTAGE_VALUES
        ]
        if meaningful and all(
            _percentage_looks_valid(value, scale="percentage_points") for value in meaningful
        ):
            candidates.append(original)
    return tuple(candidates)


def _percentage_looks_valid(value: Any, *, scale: PercentageScale) -> bool:
    try:
        parse_fra_percentage(value, scale=scale)
    except InvalidFraCsvError:
        return False
    return True


def _detect_delimiter(csv_text: str) -> str:
    candidates: list[tuple[int, int, str]] = []
    for delimiter in (",", ";", "\t", "|"):
        try:
            rows = list(csv.reader(StringIO(csv_text), delimiter=delimiter))
            header_row = find_fra_header_row(rows)
        except csv.Error, UnsupportedFraCsvSchemaError:
            continue
        candidates.append(
            (
                _fra_header_score(rows[header_row]),
                len(rows[header_row]),
                delimiter,
            )
        )
    if candidates:
        return max(candidates, key=lambda item: (item[0], item[1]))[2]

    sample = "\n".join(csv_text.splitlines()[:25])
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error as exc:
        counts = {delimiter: sample.count(delimiter) for delimiter in (",", ";", "\t", "|")}
        delimiter, count = max(counts.items(), key=lambda item: item[1])
        if count:
            return delimiter
        raise UnsupportedFraCsvSchemaError("fra_csv_delimiter_not_detected") from exc


def _fra_header_score(row: list[str]) -> int:
    normalized = {normalize_header(value) for value in row if str(value).strip()}
    current_required = {"topic", "question", "question_code", "location", "country"}
    if current_required.issubset(normalized):
        return 100 + len(normalized)

    canonical = {COLUMN_ALIASES.get(value, value) for value in normalized}
    if {"country", "question", "answer"}.issubset(canonical) and (
        "percentage" in canonical or "proportion" in canonical
    ):
        return 80 + len(canonical)
    return 0


def _dataframe_from_fra_rows(rows: list[list[str]], *, header_row: int) -> pd.DataFrame:
    if header_row >= len(rows):
        raise InvalidFraCsvError("fra_csv_header_out_of_range")
    columns = [str(value).lstrip("\ufeff").strip() for value in rows[header_row]]
    if not columns or any(not column for column in columns):
        raise UnsupportedFraCsvSchemaError("fra_csv_header_contains_empty_columns")
    normalized_columns = [normalize_header(column) for column in columns]
    protected_duplicates = {"topic", "question", "question_code", "location", "country"}
    repeated = {
        column for column in normalized_columns if normalized_columns.count(column) > 1
    }
    if repeated & protected_duplicates:
        raise UnsupportedFraCsvSchemaError("fra_csv_header_contains_duplicate_columns")
    unique_columns: list[str] = []
    occurrences: dict[str, int] = {}
    for column, normalized in zip(columns, normalized_columns, strict=True):
        occurrence = occurrences.get(normalized, 0) + 1
        occurrences[normalized] = occurrence
        unique_columns.append(
            column if occurrence == 1 else f"{column}{FRA_DUPLICATE_COLUMN_SUFFIX}{occurrence}"
        )
    columns = unique_columns

    records: list[list[str]] = []
    for row in rows[header_row + 1 :]:
        values = [str(value) for value in row]
        if len(values) > len(columns):
            if any(value.strip() for value in values[len(columns) :]):
                raise InvalidFraCsvError("fra_csv_row_has_extra_columns")
            values = values[: len(columns)]
        records.append(values + [""] * (len(columns) - len(values)))
    return pd.DataFrame(records, columns=columns, dtype=str)


def _fra_column_label(column: str) -> str:
    return str(column).split(FRA_DUPLICATE_COLUMN_SUFFIX, 1)[0].strip()


def _log_fra_import_summary(
    dataframe: pd.DataFrame,
    schema: FraCsvSchema,
    normalized: pd.DataFrame,
) -> None:
    preamble = list(dataframe.attrs.get("fra_preamble_rows") or [])
    metadata_rows = 0
    footnote_rows = 0
    valid_source_rows = 0
    metadata_keys: set[str] = set()
    footnote_symbols: set[str] = set()

    for row in preamble:
        label = _clean(row[0]) if row else ""
        key = fra_metadata_key(label)
        if key:
            metadata_rows += 1
            metadata_keys.add(key)
        elif is_fra_footnote_symbol(label):
            footnote_rows += 1
            footnote_symbols.add(label)

    label_column = schema.topic_column or schema.country_name_column
    for record in dataframe.to_dict(orient="records"):
        label = _clean(record.get(label_column))
        key = fra_metadata_key(label)
        if key:
            metadata_rows += 1
            metadata_keys.add(key)
            continue
        if is_fra_footnote_symbol(label):
            footnote_rows += 1
            footnote_symbols.add(label)
            continue
        if _fra_record_has_statistic_shape(cast(Mapping[str, Any], record), schema):
            valid_source_rows += 1

    rows_read = len(preamble) + len(dataframe)
    skipped_rows = max(0, rows_read - metadata_rows - footnote_rows - valid_source_rows)
    logger.debug(
        "fra_auxiliary_rows_detected",
        extra={
            "metadata_keys": sorted(metadata_keys),
            "footnote_symbols": sorted(footnote_symbols),
        },
    )
    logger.info(
        "fra_import_summary",
        extra={
            "rows_read": rows_read,
            "rows_valid": len(normalized),
            "source_data_rows": valid_source_rows,
            "metadata_rows": metadata_rows,
            "footnote_rows": footnote_rows,
            "skipped_rows": skipped_rows,
            "header_row": schema.header_row,
            "schema_version": schema.version,
        },
    )


def _fra_record_has_statistic_shape(
    record: Mapping[str, Any],
    schema: FraCsvSchema,
) -> bool:
    category = _clean(record.get(schema.topic_column or "")) or _clean(record.get("category"))
    country = _clean(record.get(schema.country_name_column))
    question = _clean(record.get(schema.question_column))
    indicator = _clean(record.get(schema.indicator_column or ""))
    if not country or not question or not is_valid_fra_category(category):
        return False
    if schema.version == "current_wide" and not indicator:
        return False
    return any(
        _percentage_looks_valid(record.get(column), scale=schema.percentage_scale)
        and parse_fra_percentage(record.get(column), scale=schema.percentage_scale) is not None
        for column in schema.percentage_columns
    )
