from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any

import json
from dotenv import load_dotenv
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Json

PENDING_STATUS = "pending"
JsonPayload = dict[str, Any] | list[Any]


@dataclass(frozen=True)
class PendingImportLog:
    id: str
    user_id: str | None
    user_label: str
    file_name: str
    file_json: JsonPayload
    created_at: str | None = None

# Coge la variable del enntorno .env
load_dotenv(override=True)


def _clean_dsn(value: str) -> str:
    value = value.strip().strip('"').strip("'")
    prefix = "DATABASE_URL="
    return value[len(prefix) :] if value.startswith(prefix) else value


def _resolve_postgres_dsn() -> str:
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        raise RuntimeError("DATABASE_URL must be set to connect to PostgreSQL.")
    return _clean_dsn(dsn)


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

    with psycopg.connect(dsn) as conn:
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
            l.created_at::text AS created_at
        FROM import_logs l
        LEFT JOIN public.users u ON u.id = l.user_id
        WHERE l.status = %s AND l.file_json IS NOT NULL
        ORDER BY user_label ASC, l.created_at DESC NULLS LAST, l.file_name ASC
    """
    with psycopg.connect(_resolve_postgres_dsn(), row_factory=dict_row) as conn:
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
    with psycopg.connect(_resolve_postgres_dsn(), row_factory=dict_row) as conn:
        row = conn.execute(query, (import_id, PENDING_STATUS)).fetchone()
    return _row_to_pending_import_log(row) if row else None


def delete_import_log(import_id: str) -> None:
    with psycopg.connect(_resolve_postgres_dsn()) as conn:
        result = conn.execute("DELETE FROM import_logs WHERE id = %s::uuid", (import_id,))
        conn.commit()
    if result.rowcount == 0:
        raise ValueError("import_not_found")


def _row_to_pending_import_log(row: dict[str, Any]) -> PendingImportLog:
    return PendingImportLog(
        id=row["id"],
        user_id=row.get("user_id"),
        user_label=row.get("user_label") or "Unknown user",
        file_name=row["file_name"],
        file_json=_normalize_json_payload(row["file_json"]),
        created_at=row.get("created_at"),
    )


def test_connection() -> dict[str, Any]:
    dsn = _resolve_postgres_dsn()
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT 1")
            result = cursor.fetchone()
    return {"ok": result is not None}
