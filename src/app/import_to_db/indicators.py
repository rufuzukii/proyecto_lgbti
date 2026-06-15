from __future__ import annotations

import json
from typing import Any

import psycopg
from psycopg.rows import dict_row

from app.import_to_db.import_log import _resolve_postgres_dsn


def upsert_indicators_from_json(file_json: dict[str, Any] | list[Any]) -> int:
    documents = _normalize_documents(file_json)
    with psycopg.connect(_resolve_postgres_dsn(), row_factory=dict_row) as conn:
        for document in documents:
            _upsert_indicator(conn, document)
        conn.commit()
    return len(documents)


def _upsert_indicator(conn: psycopg.Connection, document: dict[str, Any]) -> None:
    code = (document.get("code") or document.get("external_code") or "").strip()
    question = (document.get("question") or "").strip()
    category = (document.get("category") or document.get("topic") or "Uncategorized").strip()
    topic = (document.get("topic") or "").strip() or None
    if not code or not question:
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
            INSERT INTO public.indicators (category_id, code, question, definition, answer_type, topic)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                category_id,
                code,
                question,
                document.get("definition"),
                _serialize_answer_types(next_answer_types),
                topic,
            ),
        )
        return

    merged_answer_types = _merge_answer_types(row.get("answer_type"), next_answer_types)
    conn.execute(
        """
        UPDATE public.indicators
        SET category_id = %s,
            question = %s,
            definition = COALESCE(%s, definition),
            answer_type = %s,
            topic = %s
        WHERE code = %s
        """,
        (
            category_id,
            question,
            document.get("definition"),
            _serialize_answer_types(merged_answer_types),
            topic,
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
    return row["id"]


def _extract_answer_types(document: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for answer in document.get("answers", []):
        if not isinstance(answer, dict):
            continue
        value = answer.get("answer")
        if value is None:
            continue
        clean_value = str(value).strip()
        if clean_value and clean_value not in values:
            values.append(clean_value)
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
    if isinstance(file_json, dict):
        return [file_json]
    if not isinstance(file_json, list) or not file_json:
        raise ValueError("invalid_indicator_payload")
    if not all(isinstance(item, dict) for item in file_json):
        raise ValueError("invalid_indicator_payload")
    return file_json
