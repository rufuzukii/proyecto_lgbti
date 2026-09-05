from __future__ import annotations

import json
import re
import unicodedata
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, cast

import psycopg
from psycopg.rows import dict_row

from app.infrastructure.postgres import postgres_connection
from app.shared.data.fra_validation import (
    has_valid_fra_statistic_answer,
    is_valid_fra_category,
)

# Reserved for reviewed methodological mappings. Exact code and exact normalized
# question/category matching do not need entries here.
FRA_INDICATOR_EQUIVALENCE_MAP: dict[tuple[int, str], str] = {}


@dataclass(frozen=True, slots=True)
class IndicatorResolution:
    question_code: str
    canonical_id: str
    action: str
    reason: str
    question: str
    category: str


def upsert_indicators_from_json(file_json: dict[str, Any] | list[Any]) -> int:
    resolved, _resolutions = resolve_and_upsert_indicators_from_json(file_json)
    return len(_normalize_documents(resolved))


def resolve_and_upsert_indicators_from_json(
    file_json: dict[str, Any] | list[Any],
) -> tuple[dict[str, Any] | list[dict[str, Any]], list[IndicatorResolution]]:
    """Resolve canonical indicators through the official relational catalog.

    Matching is deliberately conservative: exact canonical code, an explicit
    reviewed mapping, or one unambiguous normalized question/category match.
    """
    documents = _normalize_documents(file_json)
    resolved_documents = [deepcopy(document) for document in documents]
    resolutions: list[IndicatorResolution] = []
    catalog_documents = _consolidate_catalog_documents(documents)
    with postgres_connection(row_factory=cast(Any, dict_row)) as conn:
        for document in catalog_documents:
            resolution = _resolve_indicator(conn, document)
            resolutions.append(resolution)
            prepared = _resolved_document(document, resolution)
            _upsert_indicator(
                conn,
                prepared,
                preserve_existing=resolution.action == "reused",
            )
        conn.commit()

    by_question_code = {item.question_code: item for item in resolutions}
    for document in resolved_documents:
        question_code = _question_code(document)
        resolution = by_question_code.get(question_code)
        if resolution is not None:
            document.update(
                {
                    "question_code": question_code,
                    "indicator_id": resolution.canonical_id,
                    "canonical_indicator": resolution.canonical_id,
                    "code": resolution.canonical_id,
                }
            )
    if isinstance(file_json, dict) and file_json.get("code"):
        return resolved_documents[0], resolutions
    return resolved_documents, resolutions


def _resolve_indicator(conn: psycopg.Connection, document: dict[str, Any]) -> IndicatorResolution:
    question_code = _question_code(document)
    question = str(document.get("question") or "").strip()
    category = _resolve_category(document)
    survey_year = _survey_year(document.get("survey_year"))
    if not question_code or not question or survey_year is None:
        raise ValueError("invalid_indicator_payload")

    exact_code = _catalog_row_by_code(conn, question_code)
    if exact_code and _same_indicator(exact_code, question=question, category=category):
        return IndicatorResolution(
            question_code, question_code, "reused", "canonical_code", question, category
        )

    mapped_code = FRA_INDICATOR_EQUIVALENCE_MAP.get((survey_year, question_code))
    if mapped_code:
        mapped = _catalog_row_by_code(conn, mapped_code)
        if mapped and _same_indicator(mapped, question=question, category=category):
            return IndicatorResolution(
                question_code,
                mapped_code,
                "reused",
                "explicit_mapping",
                question,
                category,
            )

    semantic_matches = _catalog_rows_by_question(conn, question, category)
    safe_matches = [
        row
        for row in semantic_matches
        if _same_indicator(row, question=question, category=category)
    ]
    if len(safe_matches) == 1:
        return IndicatorResolution(
            question_code,
            str(safe_matches[0]["code"]),
            "reused",
            "exact_normalized_question_category",
            question,
            category,
        )

    canonical_id = question_code
    reason = "new_question_code"
    if exact_code is not None:
        canonical_id = f"fra_{survey_year}_{_safe_code(question_code)}"
        reason = "question_code_collision"
    existing_canonical = _catalog_row_by_code(conn, canonical_id)
    action = "reused" if existing_canonical else "created"
    if existing_canonical:
        reason = "canonical_code"
    return IndicatorResolution(question_code, canonical_id, action, reason, question, category)


def _catalog_row_by_code(conn: psycopg.Connection, code: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT i.code, i.question, c.name AS category
        FROM public.indicators i
        JOIN public.categories c ON c.id = i.category_id
        WHERE i.code = %s
        """,
        (code,),
    ).fetchone()
    return cast(dict[str, Any] | None, row)


def _catalog_rows_by_question(
    conn: psycopg.Connection, question: str, category: str
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT i.code, i.question, c.name AS category
        FROM public.indicators i
        JOIN public.categories c ON c.id = i.category_id
        WHERE lower(trim(i.question)) = lower(trim(%s))
          AND lower(trim(c.name)) = lower(trim(%s))
        ORDER BY i.code
        LIMIT 2
        """,
        (question, category),
    ).fetchall()
    return cast(list[dict[str, Any]], rows)


def _same_indicator(row: dict[str, Any], *, question: str, category: str) -> bool:
    return _safe_text(row.get("question")) == _safe_text(question) and _safe_text(
        row.get("category")
    ) == _safe_text(category)


def _safe_text(value: Any) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return " ".join(normalized.split())


def _safe_code(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]+", "_", value).strip("_") or "indicator"


def _survey_year(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except TypeError, ValueError:
        return None


def _question_code(document: dict[str, Any]) -> str:
    return str(document.get("question_code") or document.get("code") or "").strip()


def _resolved_document(document: dict[str, Any], resolution: IndicatorResolution) -> dict[str, Any]:
    return {
        **document,
        "question_code": resolution.question_code,
        "indicator_id": resolution.canonical_id,
        "canonical_indicator": resolution.canonical_id,
        "code": resolution.canonical_id,
    }


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


def _upsert_indicator(
    conn: psycopg.Connection,
    document: dict[str, Any],
    *,
    preserve_existing: bool = False,
) -> None:
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
    if preserve_existing:
        conn.execute(
            """
            UPDATE public.indicators
            SET answer_type = %s
            WHERE code = %s
            """,
            (_serialize_answer_types(merged_answer_types), code),
        )
        return

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
