from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Self

import pytest

from app.users import service


@dataclass
class _Result:
    row: dict[str, Any] | None = None
    rows: list[dict[str, Any]] | None = None
    rowcount: int = 1

    def fetchone(self) -> dict[str, Any] | None:
        return self.row

    def fetchall(self) -> list[dict[str, Any]]:
        return self.rows or []


class _Connection:
    def __init__(self, handler: Any) -> None:
        self.handler = handler
        self.calls: list[tuple[str, tuple[Any, ...] | None]] = []
        self.committed = False

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, query: str, params: tuple[Any, ...] | None = None) -> _Result:
        self.calls.append((query, params))
        return self.handler(query, params)

    def commit(self) -> None:
        self.committed = True


def _user_row(*, user_type: str = "admin") -> dict[str, Any]:
    return {
        "id": "00000000-0000-0000-0000-000000000001",
        "username": "Admin",
        "email": "admin@example.com",
        "organization": "RainbowLens",
        "password_hash": "hash",
        "user_type": user_type,
    }


def test_last_administrator_cannot_be_demoted(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange
    current = _user_row()

    def handler(query: str, _params: tuple[Any, ...] | None) -> _Result:
        if "for update" in query.casefold():
            return _Result(row=current)
        if "count(*)" in query.casefold():
            return _Result(row={"total": 1})
        return _Result()

    connection = _Connection(handler)
    monkeypatch.setattr(service, "_connect", lambda: connection)

    # Act / Assert
    with pytest.raises(ValueError, match="last_admin"):
        service.update_user_as_admin(
            user_id=current["id"],
            username="Admin",
            email="admin@example.com",
            role="comun",
            organization="RainbowLens",
            actor_user_id="00000000-0000-0000-0000-000000000099",
            expected_version=service._user_version(current),
        )
    assert connection.committed is False


def test_concurrent_admin_edit_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange
    current = _user_row(user_type="docente")
    connection = _Connection(
        lambda query, _params: _Result(row=current)
        if "for update" in query.casefold()
        else _Result()
    )
    monkeypatch.setattr(service, "_connect", lambda: connection)

    # Act / Assert
    with pytest.raises(ValueError, match="concurrent_update"):
        service.update_user_as_admin(
            user_id=current["id"],
            username="Changed",
            email="changed@example.com",
            role="docente",
            organization=None,
            actor_user_id="00000000-0000-0000-0000-000000000002",
            expected_version="stale-version",
        )


def test_admin_cannot_delete_their_own_account() -> None:
    # Arrange
    user_id = "00000000-0000-0000-0000-000000000001"

    # Act / Assert
    with pytest.raises(ValueError, match="self_delete"):
        service.delete_user_as_admin(user_id=user_id, actor_user_id=user_id)


def test_user_page_uses_one_count_and_one_paged_query(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange
    rows = [_user_row(user_type="comun")]

    def handler(query: str, _params: tuple[Any, ...] | None) -> _Result:
        return _Result(row={"total": 49}) if "count(*)" in query.casefold() else _Result(rows=rows)

    connection = _Connection(handler)
    monkeypatch.setattr(service, "_connect", lambda: connection)
    monkeypatch.setattr(
        service,
        "get_account_security_many",
        lambda user_ids: {
            user_id: service.AccountSecurityState(user_id, True, True, 0)
            for user_id in user_ids
        },
    )

    # Act
    page = service.list_users_page(search="admin", page=3, page_size=20)

    # Assert
    assert (page.page, page.page_count, page.total) == (3, 3, 49)
    assert len(page.users) == 1
    assert len(connection.calls) == 2
    query_params = connection.calls[1][1]
    assert query_params is not None
    assert query_params[-2:] == (20, 40)


def test_like_search_escapes_wildcards() -> None:
    assert service._escape_like("50%_team\\") == "50\\%\\_team\\\\"


def test_admin_cannot_modify_their_own_account_from_user_management() -> None:
    user_id = "00000000-0000-0000-0000-000000000001"

    with pytest.raises(ValueError, match="self_manage"):
        service.update_user_as_admin(
            user_id=user_id,
            username="Admin",
            email="admin@example.com",
            role="admin",
            organization="RainbowLens",
            actor_user_id=user_id,
        )
