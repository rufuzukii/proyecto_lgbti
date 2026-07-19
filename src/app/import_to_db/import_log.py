from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import json
from dotenv import load_dotenv
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Json

from app.config import get_postgres_connect_timeout, get_postgres_dsn

PENDING_STATUS = "pending"
JsonPayload = dict[str, Any] | list[Any]


@dataclass(frozen=True)
class PendingImportLog:
    id: str
    user_id: str | None
    user_label: str
    file_name: str
    file_json: JsonPayload | None
    created_at: str | None = None
    record_count: int = 0

# Load local .env values without replacing variables already provided by the process.
load_dotenv()


def _resolve_postgres_dsn() -> str:
    return get_postgres_dsn()


def insert_import_log(
    file_name: str,
    status: str,
    *,
    file_json: Json | None = None,
    user_id: str | None = None,
    source_id: str | None = None,
    records_inserted: int = 0,
    error_message: str | None = None,
) -> None:
    dsn = _resolve_postgres_dsn()
    query = (
        "INSERT INTO import_logs (user_id, source_id, file_name, file_json, status, records_inserted, error_message) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s)"
    )

    with psycopg.connect(dsn, connect_timeout=get_postgres_connect_timeout()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                query,
                (
                    user_id,
                    source_id,
                    file_name,
                    file_json,
                    status,
                    records_inserted,
                    error_message,
                ),
            )
        conn.commit()


def _parse_json_payload(file_json: str | dict | list) -> Json:
    if isinstance(file_json, (dict, list)):
        return Json(file_json)
    return Json(json.loads(file_json))


def _normalize_json_payload(file_json: str | dict | list) -> JsonPayload:
    if isinstance(file_json, (dict, list)):
        return file_json
    return json.loads(file_json)


def register_pending_import(
    file_name: str,
    *,
    file_json: str | dict | list,
    user_id: str | None = None,
    source_id: str | None = None,
) -> None:
    insert_import_log(
        file_name=file_name,
        status=PENDING_STATUS,
        file_json=_parse_json_payload(file_json),
        user_id=user_id,
        source_id=source_id,
    )


def register_failed_import(
    file_name: str,
    error_message: str,
    *,
    user_id: str | None = None,
    source_id: str | None = None,
) -> None:
    insert_import_log(
        file_name=file_name,
        status="failed",
        file_json=None,
        user_id=user_id,
        source_id=source_id,
        error_message=error_message,
    )


def list_pending_import_logs() -> list[PendingImportLog]:
    query = """
        SELECT
            l.id::text AS id,
            l.user_id::text AS user_id,
            COALESCE(NULLIF(u.username, ''), NULLIF(u.email, ''), 'Unknown user') AS user_label,
            l.file_name,
            l.file_json,
            CASE
                WHEN jsonb_typeof(l.file_json::jsonb) = 'array'
                    THEN jsonb_array_length(l.file_json::jsonb)
                WHEN jsonb_typeof(l.file_json::jsonb) = 'object'
                    AND jsonb_typeof((l.file_json::jsonb)->'questions') = 'array'
                    THEN jsonb_array_length((l.file_json::jsonb)->'questions')
                WHEN jsonb_typeof(l.file_json::jsonb) = 'object'
                    THEN 1
                ELSE 0
            END AS record_count,
            l.created_at::text AS created_at
        FROM import_logs l
        LEFT JOIN public.users u ON u.id = l.user_id
        WHERE l.status = %s AND l.file_json IS NOT NULL
        ORDER BY user_label ASC, l.created_at DESC NULLS LAST, l.file_name ASC
    """
    with psycopg.connect(
        _resolve_postgres_dsn(),
        row_factory=dict_row,
        connect_timeout=get_postgres_connect_timeout(),
    ) as conn:
        rows = conn.execute(query, (PENDING_STATUS,)).fetchall()
    return [_row_to_pending_import_log(row) for row in rows]


def get_pending_import_log(import_id: str) -> PendingImportLog | None:
    query = """
        SELECT
            l.id::text AS id,
            l.user_id::text AS user_id,
            COALESCE(NULLIF(u.username, ''), NULLIF(u.email, ''), 'Unknown user') AS user_label,
            l.file_name,
            l.file_json,
            l.created_at::text AS created_at
        FROM import_logs l
        LEFT JOIN public.users u ON u.id = l.user_id
        WHERE l.id = %s::uuid AND l.status = %s AND l.file_json IS NOT NULL
    """
    with psycopg.connect(
        _resolve_postgres_dsn(),
        row_factory=dict_row,
        connect_timeout=get_postgres_connect_timeout(),
    ) as conn:
        row = conn.execute(query, (import_id, PENDING_STATUS)).fetchone()
    return _row_to_pending_import_log(row) if row else None


def delete_import_log(import_id: str) -> None:
    with psycopg.connect(
        _resolve_postgres_dsn(),
        connect_timeout=get_postgres_connect_timeout(),
    ) as conn:
        result = conn.execute("DELETE FROM import_logs WHERE id = %s::uuid", (import_id,))
        conn.commit()
    if result.rowcount == 0:
        raise ValueError("import_not_found")


def _row_to_pending_import_log(row: dict[str, Any]) -> PendingImportLog:
    file_json = row.get("file_json")
    return PendingImportLog(
        id=row["id"],
        user_id=row.get("user_id"),
        user_label=row.get("user_label") or "Unknown user",
        file_name=row["file_name"],
        file_json=_normalize_json_payload(file_json) if file_json is not None else None,
        created_at=row.get("created_at"),
        record_count=int(row.get("record_count") or 0),
    )


def test_connection() -> dict[str, Any]:
    dsn = _resolve_postgres_dsn()
    with psycopg.connect(dsn, connect_timeout=get_postgres_connect_timeout()) as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT 1")
            result = cursor.fetchone()
    return {"ok": result is not None}
