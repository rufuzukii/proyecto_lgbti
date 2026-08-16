from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from app.fra_surveys import get_fra_survey_by_year
from app.import_to_db.fra.schema import (
    FraCsvSchema,
    filename_declares_all_all,
    normalize_fra_csv,
    read_fra_csv_text,
    validate_fra_filter_scope,
)
from app.import_to_db.utils import normalize_header

FRA_SOURCE_NAME = "EU LGBTIQ+ Survey (FRA)"
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



def parse_answer_survey_csv(
    file_path: Path | str,
    *,
    root: Path | str | None = None,
    survey_year: int | None = None,
) -> list[dict]:
    path = Path(file_path)
    csv_text = read_text_with_fallback(path)
    context = build_path_context(path, Path(root) if root else None)
    return parse_answer_survey_csv_text(
        csv_text,
        file_name=path,
        path_context=context,
        survey_year=survey_year,
    )


def parse_answer_survey_csv_text(
    csv_text: str,
    *,
    file_name: Path | str | None = None,
    path_context: FraPathContext | None = None,
    survey_year: int | None = None,
) -> list[dict]:
    context = path_context or (
        build_path_context(Path(file_name), None) if file_name else FraPathContext()
    )
    dataframe, schema = read_fra_csv_text(csv_text)
    normalized = normalize_fra_csv(
        dataframe,
        schema,
        path_filters=context.filters,
        file_name=file_name,
        survey_year=survey_year,
    )
    survey = get_fra_survey_by_year(survey_year) if survey_year is not None else None
    if survey_year is not None and survey is None:
        raise ValueError("unsupported_fra_survey_year")
    if survey is not None and schema.version not in survey.csv_versions:
        raise ValueError(
            f"fra_survey_schema_mismatch:year={survey.year}:schema={schema.version}"
        )
    detected_years = {
        int(value)
        for value in normalized["survey_year"].dropna().tolist()
        if str(value).strip()
    }
    if survey_year is not None and detected_years and detected_years != {int(survey_year)}:
        raise ValueError(
            f"fra_survey_year_mismatch:expected={survey_year}:detected={sorted(detected_years)}"
        )
    if survey_year is not None:
        normalized["survey_year"] = int(survey_year)
        metadata = dict(normalized.attrs.get("fra_metadata") or {})
        metadata.update(
            {
                "survey_year": int(survey_year),
                "survey_id": survey.survey_id if survey else "",
                "survey_year_source": (
                    "csv_metadata" if detected_years else "explicit_survey_configuration"
                ),
            }
        )
        normalized.attrs["fra_metadata"] = metadata

    path_category = _path_category(context.category)
    if path_category:
        category_missing = normalized["category"].astype(str).str.strip().isin(
            {"", "Uncategorized"}
        )
        specific_category_missing = normalized["specific_category"].astype(str).str.strip().isin(
            {"", "Uncategorized"}
        )
        normalized.loc[category_missing, "category"] = path_category
        normalized.loc[specific_category_missing, "specific_category"] = path_category
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
    documents: dict[tuple[str, str, str, str, str, str, int | None], dict[str, Any]] = {}
    fra_metadata = dict(dataframe.attrs.get("fra_metadata") or {})
    for row in dataframe.to_dict(orient="records"):
        source = str(row.get("source") or FRA_SOURCE_NAME)
        category = str(row.get("category") or context.category or "Uncategorized")
        specific_category = str(row.get("specific_category") or category)
        topic = category
        question = str(row.get("question") or "")
        external_code = str(row.get("indicator_id") or build_question_code(question))
        survey_year = row.get("survey_year")
        key = (source, category, specific_category, topic, question, external_code, survey_year)
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
                "survey_year": survey_year,
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
        percentage = row.get("percentage")
        if percentage is None or pd.isna(percentage):
            percentage = None
        answer_entry = {
            "country": str(row.get("country_name") or ""),
            "country_code": str(row.get("country_code") or ""),
            "country_scope": str(row.get("country_scope") or "country"),
            "answer": str(row.get("response") or context.answer),
            "percentage": percentage,
            "raw_percentage": str(row.get("raw_percentage") or ""),
            "notes": str(row.get("notes") or ""),
            "note_text": str(row.get("notes") or ""),
            "date": str(row.get("date") or ""),
            "survey_year": survey_year,
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












def build_path_context(file_path: Path, root: Path | None) -> FraPathContext:
    file_name = file_path.name
    try:
        relative = file_path.relative_to(root) if root else Path(file_name)
    except ValueError:
        relative = Path(file_name)

    parts = list(relative.with_suffix("").parts)
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


def _path_category(value: str) -> str:
    """Remove the FRA explorer's display-only question count suffix."""
    return re.sub(r"\s*\(\d+\)\s*$", "", str(value or "")).strip()


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




def build_question_code(question: str) -> str:
    seed = "|".join(part for part in [normalize_header(question)] if part) or "unknown_question"
    digest = hashlib.sha1(seed.encode("utf-8"), usedforsecurity=False).hexdigest()[:12]
    return f"fra_{digest}"





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
