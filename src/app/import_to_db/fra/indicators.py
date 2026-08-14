from __future__ import annotations

import json
from typing import Any, cast

import psycopg
from psycopg.rows import dict_row

from app.import_to_db.fra.validation import (
    has_valid_fra_statistic_answer,
    is_valid_fra_category,
)
from app.postgres import postgres_connection


def upsert_indicators_from_json(file_json: dict[str, Any] | list[Any]) -> int:
    documents = _normalize_documents(file_json)
    catalog_documents = _consolidate_catalog_documents(documents)
    with postgres_connection(row_factory=cast(Any, dict_row)) as conn:
        for document in catalog_documents:
            _upsert_indicator(conn, document)
        conn.commit()
    return len(documents)


def _consolidate_catalog_documents(
    documents: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Apply one catalog upsert per code while retaining every response label."""
    consolidated: dict[str, dict[str, Any]] = {}
    for document in documents:
        code = str(document.get("code") or "").strip()
        if not code:
            continue
        current = consolidated.get(code)
        answers = [answer for answer in document.get("answers", []) if isinstance(answer, dict)]
        if current is None:
            consolidated[code] = {**document, "answers": list(answers)}
            continue
        combined_answers = [*current.get("answers", []), *answers]
        current.update(document)
        current["answers"] = combined_answers
    return list(consolidated.values())


def _upsert_indicator(conn: psycopg.Connection, document: dict[str, Any]) -> None:
    indicator = _indicator_payload(document)
    code = (document.get("code") or indicator.get("code") or "").strip()
    question = (indicator.get("question") or "").strip()
    category = _resolve_category(indicator)
    specific_category = _resolve_specific_category(indicator)
    if (
        not code
        or not question
        or not is_valid_fra_category(category)
        or not has_valid_fra_statistic_answer(indicator)
    ):
        raise ValueError("invalid_indicator_payload")

    category_id = _get_or_create_category(conn, category)
    next_answer_types = _extract_answer_types(document)
    row = conn.execute(
        """
        SELECT answer_type
        FROM public.indicators
        WHERE code = %s
        """,
        (code,),
    ).fetchone()

    if row is None:
        conn.execute(
            """
            INSERT INTO public.indicators (category_id, code, question, definition, answer_type, specific_category)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                category_id,
                code,
                question,
                indicator.get("definition"),
                _serialize_answer_types(next_answer_types),
                specific_category,
            ),
        )
        return

    row = cast(dict[str, Any], row)
    merged_answer_types = _merge_answer_types(row.get("answer_type"), next_answer_types)
    conn.execute(
        """
        UPDATE public.indicators
        SET category_id = %s,
            question = %s,
            definition = COALESCE(%s, definition),
            answer_type = %s,
            specific_category = %s
        WHERE code = %s
        """,
        (
            category_id,
            question,
            indicator.get("definition"),
            _serialize_answer_types(merged_answer_types),
            specific_category,
            code,
        ),
    )


def _get_or_create_category(conn: psycopg.Connection, name: str) -> str:
    row = conn.execute(
        """
        INSERT INTO public.categories (name)
        VALUES (%s)
        ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name
        RETURNING id::text
        """,
        (name,),
    ).fetchone()
    if row is None:
        raise RuntimeError("category_upsert_failed")
    row = cast(dict[str, Any], row)
    return row["id"]


def _extract_answer_types(document: dict[str, Any]) -> list[str]:
    values: list[str] = []

    for question in _question_entries(document):
        for answer in question.get("answers", []):
            if not isinstance(answer, dict):
                continue
            value = answer.get("answer")
            if value is None:
                continue
            clean_value = str(value).strip()
            if clean_value and clean_value not in values:
                values.append(clean_value)
    values = [value for index, value in enumerate(values) if value and value not in values[:index]]
    return values


def _merge_answer_types(existing: str | None, new_values: list[str]) -> list[str]:
    merged = _parse_answer_type(existing)
    for value in new_values:
        if value not in merged:
            merged.append(value)
    return merged


def _parse_answer_type(value: str | None) -> list[str]:
    if not value:
        return []
    clean_value = value.strip()
    try:
        parsed = json.loads(clean_value)
    except json.JSONDecodeError:
        parsed = [part.strip() for part in clean_value.split(",")]
    if not isinstance(parsed, list):
        return [str(parsed)]
    return [str(item).strip() for item in parsed if str(item).strip()]


def _serialize_answer_types(values: list[str]) -> str:
    return json.dumps(values, ensure_ascii=False)


def _normalize_documents(file_json: dict[str, Any] | list[Any]) -> list[dict[str, Any]]:
    if (
        isinstance(file_json, dict)
        and file_json.get("code")
        and isinstance(file_json.get("answers"), list)
    ):
        return [file_json]
    if isinstance(file_json, dict) and isinstance(file_json.get("questions"), list):
        questions = file_json["questions"]
        if not all(isinstance(item, dict) for item in questions):
            raise ValueError("invalid_indicator_payload")
        return questions
    if isinstance(file_json, dict):
        return [file_json]
    if not isinstance(file_json, list) or not file_json:
        raise ValueError("invalid_indicator_payload")
    if not all(isinstance(item, dict) for item in file_json):
        raise ValueError("invalid_indicator_payload")
    return file_json


def _resolve_category(document: dict[str, Any]) -> str:
    if document.get("specific_category"):
        value = document.get("category") or document.get("topic")
    else:
        value = document.get("topic") or document.get("category")
    return (value or "Uncategorized").strip()


def _resolve_specific_category(document: dict[str, Any]) -> str | None:
    value = document.get("specific_category")
    if not value and document.get("topic") and document.get("category"):
        value = document.get("category")
    clean_value = str(value or "").strip()
    return clean_value or None


def _indicator_payload(document: dict[str, Any]) -> dict[str, Any]:
    questions = document.get("questions")
    if (
        not document.get("question")
        and isinstance(questions, list)
        and questions
        and isinstance(questions[0], dict)
    ):
        return questions[0]
    return document


def _question_entries(document: dict[str, Any]) -> list[dict[str, Any]]:
    questions = document.get("questions")
    if (
        not document.get("answers")
        and isinstance(questions, list)
        and all(isinstance(item, dict) for item in questions)
    ):
        return questions
    return [document]
