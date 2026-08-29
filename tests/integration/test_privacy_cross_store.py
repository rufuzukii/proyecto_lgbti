from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Self

import pytest

from app.modules.account.privacy import service

USER_ID = "7bf1c278-4ad4-4cf3-a70d-9769590c5099"


@dataclass
class _Result:
    row: dict[str, Any] | None = None
    rowcount: int = 0

    def fetchone(self) -> dict[str, Any] | None:
        return self.row


class _Connection:
    def __init__(self) -> None:
        self.queries: list[str] = []
        self.committed = False

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, query: str, _params: object = None) -> _Result:
        clean = " ".join(query.split()).casefold()
        self.queries.append(clean)
        if "select user_type" in clean:
            return _Result(row={"user_type": "comun"})
        if "delete from public.import_logs" in clean:
            return _Result(rowcount=2)
        if "delete from public.users" in clean:
            return _Result(rowcount=1)
        return _Result()

    def commit(self) -> None:
        self.committed = True


def test_postgres_deletion_removes_private_imports_and_user_in_one_transaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    connection = _Connection()
    monkeypatch.setattr(service, "postgres_connection", lambda **_kwargs: connection)

    # Act
    result = service._delete_postgres_account(USER_ID)

    # Assert
    assert result == {"import_logs": 2, "user_profile": 1}
    assert connection.committed is True
    assert next(i for i, query in enumerate(connection.queries) if "import_logs" in query) < next(
        i for i, query in enumerate(connection.queries) if "delete from public.users" in query
    )


def test_mongo_deletion_removes_private_content_and_account_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    deleted_queries: dict[str, list[dict[str, str]]] = {}

    class _Collection:
        def __init__(self, name: str) -> None:
            self.name = name

        def delete_many(self, query: dict[str, str]):
            deleted_queries.setdefault(self.name, []).append(query)
            return SimpleNamespace(deleted_count=1)

    monkeypatch.setattr(service, "get_mongo_collection", lambda name: _Collection(name))

    # Act
    content = service._delete_private_mongo_data(USER_ID)
    security = service._delete_security_state(USER_ID)

    # Assert
    assert content == {"teacher_games": 1}
    assert security == {"account_security": 1}
    assert deleted_queries[service.GAMES_COLLECTION] == [
        {"$or": [{"owner_user_id": USER_ID}, {"owner_id": USER_ID}]}
    ]
    assert deleted_queries[service.ACCOUNT_COLLECTION] == [{"user_id": USER_ID}]


def test_supabase_stage_is_explicitly_idempotent_when_no_personal_objects_exist() -> None:
    # Supabase contains public FELGTBI+ figures only in the current application.
    assert service._delete_personal_supabase_objects(USER_ID) == 0
    assert service._delete_personal_supabase_objects(USER_ID) == 0
