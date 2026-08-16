from __future__ import annotations

import json
from collections.abc import Iterable
from copy import deepcopy
from pathlib import Path
from typing import Any

from bson import ObjectId

from app.fra_surveys import default_fra_survey, get_fra_survey_by_year
from app.import_to_db.fra.importer import (
    parse_answer_survey_csv,
    parse_answer_survey_csv_text,
)

JsonPayload = dict[str, Any] | list[dict[str, Any]]
FRA_DATASET_CODE = default_fra_survey().dataset_code

FILTER_LABELS: dict[str, str] = {
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

FILTER_PRIORITY: tuple[str, ...] = (
    "age_group",
    "minority_group",
    "education",
    "openness",
    "employment_status",
    "place_of_residence",
    "activity_limitation",
    "making_ends_meet",
    "sexual_orientation",
    "gender_expression",
    "sex_characteristics",
)


def parse_fra_csv(
    file_path: Path | str,
    *,
    root: Path | str | None = None,
    survey_year: int | None = None,
) -> JsonPayload:
    path = Path(file_path)
    documents = parse_answer_survey_csv(path, root=root, survey_year=survey_year)
    return build_fra_questions_payload(documents, file_name=path.name)


def parse_fra_csv_text(
    csv_text: str,
    *,
    file_name: Path | str | None = None,
    survey_year: int | None = None,
) -> JsonPayload:
    documents = parse_answer_survey_csv_text(
        csv_text, file_name=file_name, survey_year=survey_year
    )
    return build_fra_questions_payload(
        documents,
        file_name=Path(file_name).name if file_name else "",
    )


def build_fra_questions_payload(
    documents: Iterable[dict[str, Any]],
    *,
    file_name: str = "",
) -> JsonPayload:
    question_documents_by_identity: dict[tuple[str, str, str, str, int | None], dict[str, Any]] = {}

    for document in documents:
        code = _question_code(document)
        if not code:
            continue

        identity = _question_identity(document, code)
        question_document = question_documents_by_identity.get(identity)
        if question_document is None:
            question_document = _build_question_document(document, code)
            question_documents_by_identity[identity] = question_document

        for answer in document.get("answers", []):
            if isinstance(answer, dict):
                _append_unique(
                    question_document["answers"],
                    _build_answer(answer, survey_year=question_document.get("survey_year")),
                )

    question_documents = list(question_documents_by_identity.values())
    if len(question_documents) == 1:
        return question_documents[0]
    return question_documents


def count_fra_questions(payload: Any) -> int:
    if isinstance(payload, list):
        return len(payload)
    return 1 if isinstance(payload, dict) else 0


def _build_question_document(document: dict[str, Any], code: str) -> dict[str, Any]:
    specific_category = _specific_category(document)
    question_text = str(document.get("question") or "").strip()
    survey_year = _document_survey_year(document)
    survey = get_fra_survey_by_year(survey_year)

    output = {
        "id": str(ObjectId()),
        "code": code,
        "dataset": survey.dataset_code if survey else FRA_DATASET_CODE,
        "record_type": "statistic",
        "source": str(document.get("source") or "").strip(),
        "category": _category(document),
        "specific_category": specific_category,
        "question": question_text,
        "survey_year": survey_year,
        "survey_id": survey.survey_id if survey else "",
        "indicator_id": code,
        "question_code": str(document.get("external_code") or code).strip(),
        "answers": [],
    }
    metadata = document.get("metadata")
    if isinstance(metadata, dict) and metadata:
        output["metadata"] = deepcopy(metadata)
    return output


def _build_answer(answer: dict[str, Any], *, survey_year: int | None) -> dict[str, Any]:
    return {
        "country": answer.get("country") or "",
        "country_code": answer.get("country_code") or "",
        "answer": answer.get("answer") or "",
        "percentage": answer.get("percentage"),
        "date": answer.get("date") or "",
        "survey_year": answer.get("survey_year") or survey_year,
        "filters": _build_filters(answer.get("filters")),
    }


def _build_filters(filters: Any) -> list[dict[str, str]]:
    if not isinstance(filters, dict):
        return [{"type": "All", "value": "All"}]

    output: list[dict[str, str]] = []
    for key in FILTER_PRIORITY:
        value = str(filters.get(key) or "").strip()
        if value:
            output.append({"type": FILTER_LABELS[key], "value": value})

    return output or [{"type": "All", "value": "All"}]


def _question_code(document: dict[str, Any]) -> str:
    return str(
        document.get("code") or document.get("external_code") or document.get("id") or ""
    ).strip()


def _question_identity(
    document: dict[str, Any], code: str
) -> tuple[str, str, str, str, int | None]:
    return (
        code,
        _category(document),
        _specific_category(document),
        str(document.get("question") or "").strip(),
        _document_survey_year(document),
    )


def _document_survey_year(document: dict[str, Any]) -> int | None:
    value = document.get("survey_year")
    metadata = document.get("metadata")
    if value is None and isinstance(metadata, dict):
        value = metadata.get("survey_year")
    if isinstance(value, bool):
        return None
    try:
        year = int(str(value))
    except TypeError, ValueError:
        return None
    return year if 1990 <= year <= 2100 else None


def _category(document: dict[str, Any]) -> str:
    return str(document.get("category") or document.get("topic") or "Uncategorized").strip()


def _specific_category(document: dict[str, Any]) -> str:
    return str(
        document.get("specific_category")
        or document.get("category")
        or document.get("topic")
        or "Uncategorized"
    ).strip()


def _append_unique(items: list[Any], item: Any) -> None:
    marker = json.dumps(item, ensure_ascii=False, sort_keys=True)
    for existing in items:
        if json.dumps(existing, ensure_ascii=False, sort_keys=True) == marker:
            return
    items.append(item)
