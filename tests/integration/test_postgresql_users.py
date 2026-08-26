from __future__ import annotations

import psycopg
import pytest

from app.config import get_postgres_connect_timeout, get_postgres_dsn
from app.users import service
from app.users.account_security import AccountSecurityState
from app.users.schemas import UserType


def test_postgresql_users_schema_and_service_are_compatible(monkeypatch) -> None:
    # Arrange
    try:
        connection = psycopg.connect(
            get_postgres_dsn(), connect_timeout=get_postgres_connect_timeout()
        )
    except (psycopg.Error, ValueError) as exc:
        pytest.skip(f"PostgreSQL temporal/no local no disponible: {type(exc).__name__}")
    monkeypatch.setattr(
        service,
        "get_account_security_many",
        lambda user_ids: {
            user_id: AccountSecurityState(
                user_id=user_id,
                active=True,
                admin_validated=False,
                validated_at=None,
                validated_by=None,
                session_version=0,
            )
            for user_id in user_ids
        },
    )

    # Act
    try:
        columns = connection.execute(
            """
            select column_name, is_nullable, column_default
            from information_schema.columns
            where table_schema = 'public' and table_name = 'users'
            """
        ).fetchall()
        users = service.list_users_page(page=1, page_size=5)
        role_rows = connection.execute("select distinct lower(user_type) from public.users").fetchall()
    finally:
        connection.close()

    # Assert
    schema = {row[0]: (row[1], row[2]) for row in columns}
    assert "user_type" in schema
    assert schema["user_type"][0] == "NO"
    assert users.page == 1
    valid_roles = {role.value for role in UserType}
    assert {row[0] for row in role_rows if row[0]} <= valid_roles
