from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Self

import pytest

from app.modules.imports import import_log


class _Cursor:
    def __init__(self, connection: _Connection) -> None:
        self.connection = connection

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, query: str, params: tuple[Any, ...]) -> None:
        self.connection.calls.append((query, params))


class _Connection:
    def __init__(self, *, rows=None, row=None, rowcount: int = 1) -> None:
        self.rows = rows or []
        self.row = row
        self.rowcount = rowcount
        self.calls: list[tuple[str, tuple[Any, ...]]] = []
        self.committed = False

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def cursor(self) -> _Cursor:
        return _Cursor(self)

    def execute(self, query: str, params: tuple[Any, ...]):
        self.calls.append((query, params))
        return SimpleNamespace(
            fetchall=lambda: self.rows,
            fetchone=lambda: self.row,
            rowcount=self.rowcount,
        )

    def commit(self) -> None:
        self.committed = True


def test_import_log_registration_maps_success_and_failure_payloads(monkeypatch) -> None:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(import_log, "insert_import_log", lambda *args, **kwargs: calls.append({"args": args, **kwargs}))

    import_log.register_pending_import(
        "fra.json", file_json='{"questions": []}', user_id="user-1", source_id="fra"
    )
    import_log.register_failed_import(
        "fra.json", "invalid", user_id="user-1", source_id="fra"
    )

    assert calls[0]["status"] == "pending"
    assert calls[0]["file_json"].obj == {"questions": []}
    assert calls[1]["status"] == "failed"
    assert calls[1]["file_json"] is None
    assert calls[1]["error_message"] == "invalid"
    with pytest.raises(ValueError):
        import_log._parse_json_payload("not-json")


def test_insert_import_log_executes_parameterized_query_and_commits(monkeypatch) -> None:
    connection = _Connection()
    monkeypatch.setattr(import_log, "postgres_connection", lambda **_kwargs: connection)

    import_log.insert_import_log("data.json", "processed", records_inserted=4)

    assert connection.committed is True
    assert connection.calls[0][1] == (None, None, "data.json", None, "processed", 4, None)


def test_pending_import_queries_map_json_and_missing_rows(monkeypatch) -> None:
    rows = [
        {
            "id": "log-1",
            "user_id": None,
            "user_label": "",
            "file_name": "one.json",
            "file_json": '{"questions": [1]}',
            "created_at": None,
            "record_count": "1",
        },
        {
            "id": "log-2",
            "user_id": "user-2",
            "user_label": "User",
            "file_name": "two.json",
            "file_json": [1, 2],
            "record_count": 2,
        },
    ]
    connection = _Connection(rows=rows, row=rows[0])
    monkeypatch.setattr(import_log, "postgres_connection", lambda **_kwargs: connection)

    pending = import_log.list_pending_import_logs()
    found = import_log.get_pending_import_log("log-1")
    connection.row = None
    missing = import_log.get_pending_import_log("missing")

    assert [item.record_count for item in pending] == [1, 2]
    assert pending[0].user_label == "Unknown user"
    assert pending[0].file_json == {"questions": [1]}
    assert found is not None and found.id == "log-1"
    assert missing is None


@pytest.mark.parametrize("rowcount", [0, 1])
def test_delete_import_log_commits_and_reports_missing(monkeypatch, rowcount: int) -> None:
    connection = _Connection(rowcount=rowcount)
    monkeypatch.setattr(import_log, "postgres_connection", lambda **_kwargs: connection)

    if rowcount:
        import_log.delete_import_log("log-1")
    else:
        with pytest.raises(ValueError, match="import_not_found"):
            import_log.delete_import_log("log-1")

    assert connection.committed is True
