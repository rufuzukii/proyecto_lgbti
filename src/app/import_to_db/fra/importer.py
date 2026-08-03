from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from io import StringIO
from pathlib import Path
from typing import Any, cast

import pandas as pd
from pandas.errors import EmptyDataError

from app.import_to_db.fra.schema import (
    FraCsvSchema,
    filename_declares_all_all,
    normalize_fra_csv,
    read_fra_csv_text,
    validate_fra_filter_scope,
)
from app.import_to_db.fra.validation import (
    fra_metadata_key,
    is_fra_footnote_symbol,
    is_valid_fra_category,
)
from app.import_to_db.utils import normalize_header, parse_float

FRA_SOURCE_NAME = "EU LGBTIQ+ Survey III (FRA 2023)"
FRA_SOURCE_TYPE = "EU_SURVEY"

COLUMN_ALIASES: dict[str, str] = {
    "country": "country",
    "country_name": "country",
    "pais": "country",
    "territory": "country",
    "topic": "topic",
    "tema": "topic",
    "categoria": "category",
    "category": "category",
    "question": "question",
    "pregunta": "question",
    "indicator": "question",
    "indicador": "question",
    "answer": "answer",
    "respuesta": "answer",
    "value": "percentage",
    "valor": "percentage",
    "percentage": "percentage",
    "percent": "percentage",
    "porcentaje": "percentage",
    "notes": "notes",
    "notas": "notes",
    "nota": "notes",
    "note": "notes",
    "source": "source",
    "fuente": "source",
    "question_code": "external_code",
    "questioncode": "external_code",
    "indicator_code": "external_code",
    "external_code": "external_code",
    "codigo_pregunta": "external_code",
    "codigo": "external_code",
    "date": "date",
    "fecha": "date",
    "year": "year",
    "ano": "year",
    "anio": "year",
    "hyperlink": "hyperlink",
    "link": "hyperlink",
    "url": "hyperlink",
}

FILTER_KEY_ALIASES: dict[str, str] = {
    "age": "age_group",
    "age_group": "age_group",
    "edad": "age_group",
    "ge": "gender_expression",
    "gender": "gender_expression",
    "gender_expression": "gender_expression",
    "genderexpression": "gender_expression",
    "gender_identity": "gender_identity",
    "sex": "sex_characteristics",
    "sc": "sex_characteristics",
    "sex_characteristics": "sex_characteristics",
    "sex_characteristic": "sex_characteristics",
    "so": "sexual_orientation",
    "sexual_orientation": "sexual_orientation",
    "orientation": "sexual_orientation",
    "activity_limitation": "activity_limitation",
    "disability": "activity_limitation",
    "making_ends_meet": "making_ends_meet",
    "place_of_residence": "place_of_residence",
    "residence": "place_of_residence",
    "employment_status": "employment_status",
    "employment": "employment_status",
    "belonging_to_a_minority_group": "minority_group",
    "minority": "minority_group",
    "minority_group": "minority_group",
    "education": "education",
    "education_level": "education",
    "openness_about_being_lgbtiq": "openness",
    "openness": "openness",
}

PATH_FILTER_PREFIXES: dict[str, str] = {
    "age": "age_group",
    "ge": "gender_expression",
    "gi": "gender_identity",
    "sc": "sex_characteristics",
    "so": "sexual_orientation",
    "al": "activity_limitation",
    "me": "making_ends_meet",
    "pr": "place_of_residence",
    "es": "employment_status",
    "mg": "minority_group",
    "op": "openness",
}

RESERVED_FIELDS: set[str] = {
    "country",
    "topic",
    "category",
    "question",
    "answer",
    "percentage",
    "notes",
    "source",
    "external_code",
    "date",
    "year",
    "hyperlink",
}

EXPLICIT_FILTER_FIELDS: set[str] = {
    "filter",
    "filters",
    "filtro",
    "filtros",
    "filtro1",
    "filtro2",
    "filtro3",
    "filter1",
    "filter2",
    "filter3",
    "filter_1",
    "filter_2",
    "filter_3",
}

COUNTRY_CODES: dict[str, str] = {
    "albania": "AL",
    "andorra": "AD",
    "austria": "AT",
    "belarus": "BY",
    "belgium": "BE",
    "bosnia_and_herzegovina": "BA",
    "bulgaria": "BG",
    "croatia": "HR",
    "cyprus": "CY",
    "czech_republic": "CZ",
    "czechia": "CZ",
    "denmark": "DK",
    "estonia": "EE",
    "faroe_islands": "FO",
    "finland": "FI",
    "france": "FR",
    "germany": "DE",
    "gibraltar": "GI",
    "greece": "GR",
    "guernsey": "GG",
    "holy_see": "VA",
    "hungary": "HU",
    "iceland": "IS",
    "ireland": "IE",
    "isle_of_man": "IM",
    "italy": "IT",
    "jersey": "JE",
    "kosovo": "XK",
    "latvia": "LV",
    "liechtenstein": "LI",
    "lithuania": "LT",
    "luxembourg": "LU",
    "malta": "MT",
    "moldova": "MD",
    "monaco": "MC",
    "montenegro": "ME",
    "netherlands": "NL",
    "north_macedonia": "MK",
    "norway": "NO",
    "poland": "PL",
    "portugal": "PT",
    "romania": "RO",
    "russia": "RU",
    "san_marino": "SM",
    "serbia": "RS",
    "slovakia": "SK",
    "slovenia": "SI",
    "spain": "ES",
    "sweden": "SE",
    "switzerland": "CH",
    "turkey": "TR",
    "turkiye": "TR",
    "tuerkiye": "TR",
    "uk": "GB",
    "united_kingdom": "GB",
}

ENCODINGS: tuple[str, ...] = ("utf-8-sig", "utf-8", "cp1252", "latin-1")


@dataclass(frozen=True)
class FraPathContext:
    category: str = ""
    topic: str = ""
    question: str = ""
    answer: str = ""
    filters: dict[str, str] = field(default_factory=dict)
    file_name: str = ""


@dataclass(frozen=True)
class IndicatorQuestionParts:
    category: str
    specific_category: str
    topic: str
    question: str
    raw_question: str


def _parse_answer_survey_rows(
    raw_rows: Iterable[Mapping[str, str | None]],
    *,
    path_context: FraPathContext | None = None,
) -> list[dict]:
    context = path_context or FraPathContext()
    rows = []
    for raw_row in raw_rows:
        normalized = normalize_row(raw_row)
        rows.append((normalized, remap_row(normalized)))
    file_metadata = extract_file_metadata(row for _, row in rows)
    documents: dict[tuple[str, str, str, str, str, str], dict[str, Any]] = {}

    for normalized, row in rows:
        if is_metadata_or_note_row(row):
            continue

        raw_topic = row.get("topic") or context.topic
        raw_question = row.get("question") or context.question
        if not raw_topic or not raw_question:
            continue

        raw_category = row.get("category") or raw_topic or context.category
        question_parts = split_indicator_question(
            raw_question,
            fallback_category=raw_category,
            fallback_topic=raw_topic,
        )
        category = question_parts.category
        if not is_valid_fra_category(category):
            continue
        specific_category = question_parts.specific_category
        topic = question_parts.topic
        question = question_parts.question
        source = row.get("source") or file_metadata.get("source") or FRA_SOURCE_NAME
        external_code = row.get("external_code") or file_metadata.get("external_code")
        external_code = external_code or build_indicator_code(
            source=source,
            category=category,
            topic=topic,
            question=question,
        )
        code = external_code or build_question_code(question)

        key = (source, category, specific_category, topic, question, external_code)
        if key not in documents:
            documents[key] = {
                "source": source,
                "source_type": FRA_SOURCE_TYPE,
                "category": category,
                "specific_category": specific_category,
                "topic": topic,
                "question": question,
                "code": code,
                "external_code": external_code,
                "question_path": split_question_path(question_parts.raw_question),
                "metadata": {
                    "schema_version": 1,
                    "file_name": context.file_name,
                    "requires_review": True,
                    **file_metadata,
                },
                "answers": [],
            }

        answer_entry = build_answer_entry(row, normalized, context, file_metadata)
        documents[key]["answers"].append(answer_entry)
        if row.get("hyperlink") and not documents[key]["metadata"].get("hyperlink"):
            documents[key]["metadata"]["hyperlink"] = row["hyperlink"]

    for document in documents.values():
        document["validation"] = validate_fra_document(document)
        document["hyperlink"] = document["metadata"].get("hyperlink", "")

    return list(documents.values())


def parse_answer_survey_csv(file_path: Path | str, *, root: Path | str | None = None) -> list[dict]:
    path = Path(file_path)
    csv_text = read_text_with_fallback(path)
    context = build_path_context(path, Path(root) if root else None)
    return parse_answer_survey_csv_text(csv_text, file_name=path, path_context=context)


def parse_answer_survey_csv_text(
    csv_text: str,
    *,
    file_name: Path | str | None = None,
    path_context: FraPathContext | None = None,
) -> list[dict]:
    context = path_context or (
        build_path_context(Path(file_name), None) if file_name else FraPathContext()
    )
    dataframe, schema = read_fra_csv_text(csv_text)
    normalized = normalize_fra_csv(
        dataframe,
        schema,
        path_filters=context.filters,
    )
    if filename_declares_all_all(file_name):
        validate_fra_filter_scope(
            normalized,
            expected_filter_a_type="All",
            expected_filter_a_value="All",
            expected_filter_b_type="All",
            expected_filter_b_value="All",
        )
    return _parse_normalized_fra_dataframe(normalized, schema=schema, context=context)


def _parse_normalized_fra_dataframe(
    dataframe: pd.DataFrame,
    *,
    schema: FraCsvSchema,
    context: FraPathContext,
) -> list[dict]:
    documents: dict[tuple[str, str, str, str, str, str], dict[str, Any]] = {}
    fra_metadata = dict(dataframe.attrs.get("fra_metadata") or {})
    for row in dataframe.to_dict(orient="records"):
        source = str(row.get("source") or FRA_SOURCE_NAME)
        category = str(row.get("category") or context.category or "Uncategorized")
        specific_category = str(row.get("specific_category") or category)
        topic = category
        question = str(row.get("question") or "")
        external_code = str(row.get("indicator_id") or build_question_code(question))
        key = (source, category, specific_category, topic, question, external_code)
        if key not in documents:
            documents[key] = {
                "source": source,
                "source_type": FRA_SOURCE_TYPE,
                "category": category,
                "specific_category": specific_category,
                "topic": topic,
                "question": question,
                "code": external_code,
                "external_code": external_code,
                "question_path": [specific_category, question],
                "metadata": {
                    "schema_version": 2,
                    "fra_csv_schema": schema.version,
                    "file_name": context.file_name,
                    "requires_review": False,
                    **fra_metadata,
                },
                "answers": [],
            }

        filters = row.get("filters")
        answer_entry = {
            "country": str(row.get("country_name") or ""),
            "country_code": str(row.get("country_code") or ""),
            "country_scope": str(row.get("country_scope") or "country"),
            "answer": str(row.get("response") or context.answer),
            "percentage": row.get("percentage"),
            "raw_percentage": str(row.get("raw_percentage") or ""),
            "notes": str(row.get("notes") or ""),
            "note_text": str(row.get("notes") or ""),
            "date": str(row.get("date") or ""),
            "filters": dict(filters) if isinstance(filters, Mapping) else {},
        }
        documents[key]["answers"].append(answer_entry)
        hyperlink = str(row.get("hyperlink") or "")
        if hyperlink and not documents[key]["metadata"].get("hyperlink"):
            documents[key]["metadata"]["hyperlink"] = hyperlink

    for document in documents.values():
        document["validation"] = validate_fra_document(document)
        document["hyperlink"] = document["metadata"].get("hyperlink", "")
    return list(documents.values())


def read_csv_rows(csv_text: str) -> list[dict[str, str]]:
    try:
        dataframe = pd.read_csv(
            StringIO(csv_text),
            sep=None,
            engine="python",
            dtype=str,
            keep_default_na=False,
            na_filter=False,
        )
    except EmptyDataError:
        return []
    return cast(list[dict[str, str]], dataframe.to_dict(orient="records"))


def read_text_with_fallback(file_path: Path) -> str:
    last_error: UnicodeDecodeError | None = None
    for encoding in ENCODINGS:
        try:
            return file_path.read_text(encoding=encoding)
        except UnicodeDecodeError as exc:
            last_error = exc
    if last_error is not None:
        raise last_error
    return file_path.read_text()


def normalize_row(raw_row: Mapping[str, str | None]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for key, value in raw_row.items():
        if key is None:
            continue
        normalized[normalize_header(str(key))] = value.strip() if value is not None else ""
    return normalized


def remap_row(normalized_row: dict[str, str]) -> dict[str, str]:
    remapped: dict[str, str] = {}
    for key, value in normalized_row.items():
        canonical = COLUMN_ALIASES.get(key, key)
        remapped[canonical] = value
    return remapped


def build_answer_entry(
    row: dict[str, str],
    normalized_row: dict[str, str],
    context: FraPathContext,
    file_metadata: dict[str, str],
) -> dict:
    country = row.get("country", "")
    country_code = resolve_country_code(country)
    filters = dict(context.filters)
    filters.update(build_filters(row, normalized_row))

    return {
        "country": country,
        "country_code": country_code,
        "country_scope": resolve_country_scope(country),
        "answer": row.get("answer") or context.answer,
        "percentage": parse_float(row.get("percentage")),
        "raw_percentage": row.get("percentage", ""),
        "notes": row.get("notes", ""),
        "note_text": resolve_note_text(row.get("notes", ""), file_metadata),
        "date": row.get("date") or file_metadata.get("date", ""),
        "filters": filters,
    }


def build_filters(remapped_row: dict[str, str], normalized_row: dict[str, str]) -> dict[str, str]:
    filters: dict[str, str] = {}

    for key, value in remapped_row.items():
        if key in RESERVED_FIELDS or key in EXPLICIT_FILTER_FIELDS:
            continue
        if not value:
            continue
        filter_key = FILTER_KEY_ALIASES.get(key, key)
        filters[filter_key] = value

    for key in EXPLICIT_FILTER_FIELDS:
        raw_value = normalized_row.get(key, "")
        if not raw_value:
            continue
        filter_key, filter_value = parse_filter_field(raw_value, fallback=key)
        filter_key = FILTER_KEY_ALIASES.get(filter_key, filter_key)
        filters[filter_key] = filter_value

    return filters


def parse_filter_field(value: str, fallback: str) -> tuple[str, str]:
    if ":" in value:
        key, val = value.split(":", 1)
        return normalize_header(key), val.strip()
    if "=" in value:
        key, val = value.split("=", 1)
        return normalize_header(key), val.strip()
    return normalize_header(fallback), value.strip()


def extract_file_metadata(rows: Iterable[dict[str, str]]) -> dict[str, str]:
    metadata: dict[str, Any] = {}
    footnotes: dict[str, str] = {}
    label_map = {
        "source": "source",
        "fuente": "source",
        "date": "date",
        "fecha": "date",
        "question_code": "external_code",
        "codigo_pregunta": "external_code",
        "indicator_code": "external_code",
        "hyperlink": "hyperlink",
        "link": "hyperlink",
        "url": "hyperlink",
        "note": "global_note",
        "nota": "global_note",
        "general_disclaimer_of_the_fra_website": "fra_disclaimer_url",
    }

    for row in rows:
        raw_label, value = _metadata_label_and_value(row)
        label = normalize_header(raw_label.rstrip(":"))
        if not value:
            continue
        metadata_key = label_map.get(label)
        if metadata_key:
            metadata[metadata_key] = value
        elif is_footnote_label(row):
            footnotes[row["country"].strip()] = value

    if footnotes:
        metadata["footnotes"] = footnotes
    return metadata


def is_metadata_or_note_row(row: dict[str, str]) -> bool:
    raw_label, _value = _metadata_label_and_value(row)
    if fra_metadata_key(raw_label):
        return True
    return is_footnote_label(row)


def is_footnote_label(row: dict[str, str]) -> bool:
    raw_label, _value = _metadata_label_and_value(row)
    if is_fra_footnote_symbol(raw_label):
        return True
    country = row.get("country", "").strip()
    if not country:
        return False
    has_data_shape = bool(row.get("question") or row.get("answer") or row.get("percentage"))
    if has_data_shape:
        return False
    if resolve_country_code(country):
        return False
    return bool(row.get("topic"))


def _metadata_label_and_value(row: Mapping[str, str]) -> tuple[str, str]:
    country_label = str(row.get("country") or "").strip()
    if country_label:
        return country_label, str(row.get("topic") or row.get("question") or "").strip()
    topic_label = str(row.get("topic") or row.get("category") or "").strip()
    return topic_label, str(row.get("question") or "").strip()


def resolve_note_text(note: str, file_metadata: dict[str, str]) -> str:
    footnotes = file_metadata.get("footnotes")
    if not note or not isinstance(footnotes, dict):
        return ""
    return footnotes.get(note.strip(), "")


def build_path_context(file_path: Path, root: Path | None) -> FraPathContext:
    file_name = file_path.name
    try:
        relative = file_path.relative_to(root) if root else Path(file_name)
    except ValueError:
        relative = Path(file_name)

    parts = list(relative.with_suffix("").parts)
    if root and root.name and is_meaningful_path_part(root.name):
        parts.insert(0, root.name)

    clean_parts = [part.strip() for part in parts if part and part.strip()]
    filters = extract_filters_from_path(clean_parts)

    category = clean_parts[0] if len(clean_parts) >= 1 else ""
    question = clean_parts[1] if len(clean_parts) >= 2 else ""
    answer = clean_parts[2] if len(clean_parts) >= 3 else ""

    return FraPathContext(
        category=category,
        topic=category,
        question=question,
        answer=answer,
        filters=filters,
        file_name=file_name,
    )


def is_meaningful_path_part(value: str) -> bool:
    ignored = {"data", "datos", "downloads", "imports", "csv", "fra"}
    return normalize_header(value) not in ignored


def extract_filters_from_path(parts: list[str]) -> dict[str, str]:
    filters: dict[str, str] = {}
    filter_parts = parts[3:] if len(parts) > 3 else []
    index = 0
    while index < len(filter_parts):
        current = filter_parts[index]
        normalized = normalize_header(current)

        if index + 1 < len(filter_parts):
            canonical = FILTER_KEY_ALIASES.get(normalized)
            if canonical:
                filters[canonical] = filter_parts[index + 1]
                index += 2
                continue

        prefixed = parse_prefixed_filter(current)
        if prefixed:
            key, value = prefixed
            filters[key] = value
        index += 1

    return filters


def parse_prefixed_filter(value: str) -> tuple[str, str] | None:
    if "-" not in value:
        return None
    prefix, raw_filter_value = value.split("-", 1)
    normalized_prefix = normalize_header(prefix)
    filter_key = PATH_FILTER_PREFIXES.get(normalized_prefix)
    if not filter_key or not raw_filter_value.strip():
        return None
    return filter_key, raw_filter_value.strip()


def build_indicator_code(*, source: str, category: str, topic: str, question: str) -> str:
    return build_question_code(question)


def split_indicator_question(
    raw_question: str,
    *,
    fallback_category: str,
    fallback_topic: str,
) -> IndicatorQuestionParts:
    clean_question = raw_question.strip()
    category = fallback_topic.strip() or fallback_category.strip() or "Uncategorized"
    specific_category = fallback_category.strip() or category
    topic = category
    question = clean_question

    if ">" in clean_question:
        left, right = clean_question.split(">", 1)
        if left.strip():
            specific_category = left.strip()
        question = right.strip()

    if "/" in question:
        left, right = question.split("/", 1)
        if left.strip():
            specific_category = left.strip()
        if right.strip():
            question = right.strip()

    return IndicatorQuestionParts(
        category=category,
        specific_category=specific_category,
        topic=topic,
        question=question,
        raw_question=clean_question,
    )


def build_question_code(question: str) -> str:
    seed = "|".join(part for part in [normalize_header(question)] if part) or "unknown_question"
    digest = hashlib.sha1(seed.encode("utf-8"), usedforsecurity=False).hexdigest()[:12]
    return f"fra_{digest}"


def split_question_path(question: str) -> list[str]:
    return [part.strip() for part in question.split(">") if part.strip()]


def resolve_country_code(country: str) -> str | None:
    normalized = normalize_header(country)
    if not normalized:
        return None
    if normalized.startswith("eu") and normalized[2:].isdigit():
        return normalized.upper()
    return COUNTRY_CODES.get(normalized)


def resolve_country_scope(country: str) -> str:
    normalized = normalize_header(country)
    if normalized.startswith("eu") and normalized[2:].isdigit():
        return "aggregate"
    return "country"


def validate_fra_document(document: dict) -> dict:
    warnings: list[str] = []
    if not document.get("code"):
        warnings.append("missing_code")
    if not document.get("answers"):
        warnings.append("empty_answers")

    missing_country_code = sorted(
        {
            answer["country"]
            for answer in document.get("answers", [])
            if answer.get("country") and not answer.get("country_code")
        }
    )
    if missing_country_code:
        warnings.append(f"unknown_country_code:{','.join(missing_country_code)}")

    missing_percentage_count = sum(
        1
        for answer in document.get("answers", [])
        if answer.get("raw_percentage") and answer.get("percentage") is None
    )
    if missing_percentage_count:
        warnings.append(f"invalid_percentage:{missing_percentage_count}")

    return {
        "status": "review_required" if warnings else "ready",
        "warnings": warnings,
    }


def convert_fra_csv_files(file_paths: Iterable[Path | str]) -> list[tuple[Path, list[dict]]]:
    results: list[tuple[Path, list[dict]]] = []
    for file_path in file_paths:
        path = Path(file_path)
        results.append((path, parse_answer_survey_csv(path)))
    return results


def generate_fra_json(discrimination_dir: str) -> list[tuple[Path, list[dict]]]:
    base_dir = Path(discrimination_dir)
    csv_paths = sorted(base_dir.rglob("*.csv"))
    if not csv_paths:
        return []

    results: list[tuple[Path, list[dict]]] = []
    for csv_path in csv_paths:
        results.append((csv_path, parse_answer_survey_csv(csv_path, root=base_dir)))
    return results
