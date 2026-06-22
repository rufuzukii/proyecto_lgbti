from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import psycopg
from psycopg.rows import dict_row
from psycopg.errors import UniqueViolation
from werkzeug.security import check_password_hash, generate_password_hash

from app.config import get_postgres_connect_timeout, get_postgres_dsn
from app.users.schemas import UserRead, UserRegister, UserRole, UserType


class UserStorageError(RuntimeError):
    """Raised when the configured users table cannot support secure auth."""


@dataclass
class UserRecord:
    id: str
    username: Optional[str]
    email: str
    role: UserRole
    organization: Optional[str]
    password_hash: Optional[str]
    user_type: Optional[UserType] = None

    @property
    def display_name(self) -> str:
        return self.username or self.email


def list_users() -> list[UserRead]:
    with _connect() as conn:
        rows = conn.execute(
            """
            select id::text, username, email, role, organization
            from public.users
            order by created_at desc nulls last, email asc
            """
        ).fetchall()
    return [_row_to_user_read(row) for row in rows]


def get_user(user_id: str) -> Optional[UserRead]:
    record = get_user_record(user_id)
    if record is None:
        return None
    return _record_to_user_read(record)


def get_user_record(user_id: str) -> Optional[UserRecord]:
    if not user_id:
        return None
    with _connect() as conn:
        row = conn.execute(
            """
            select id::text, username, email, role, organization, password_hash
            from public.users
            where id = %s::uuid
            """,
            (user_id,),
        ).fetchone()
    return _row_to_user_record(row) if row else None


def get_user_record_by_email(email: str) -> Optional[UserRecord]:
    normalized = _normalize_email(email)
    if not normalized:
        return None
    with _connect() as conn:
        row = conn.execute(
            """
            select id::text, username, email, role, organization, password_hash
            from public.users
            where lower(email) = %s
            """,
            (normalized,),
        ).fetchone()
    return _row_to_user_record(row) if row else None


def create_user(payload: UserRegister, *, role: UserRole = UserRole.COMMON) -> UserRead:
    normalized_email = _normalize_email(payload.email)
    if not normalized_email:
        raise ValueError("invalid_email")

    assigned_role = role if role == UserRole.ADMIN else UserRole.COMMON
    organization = _normalize_optional_text(payload.organization)
    password_hash = generate_password_hash(payload.password)

    try:
        with _connect() as conn:
            row = conn.execute(
                """
                insert into public.users (username, email, role, organization, password_hash)
                values (%s, %s, %s, %s, %s)
                returning id::text, username, email, role, organization
                """,
                (payload.name.strip(), normalized_email, assigned_role.value, organization, password_hash),
            ).fetchone()
            conn.commit()
    except UniqueViolation as exc:
        raise ValueError("email_exists") from exc

    return _row_to_user_read(row)


def authenticate_user(email: str, password: str) -> Optional[UserRecord]:
    if not email or not password:
        return None
    record = get_user_record_by_email(email)
    if record is None or not record.password_hash:
        return None
    if not check_password_hash(record.password_hash, password):
        return None
    return record


def update_user_profile(
    *,
    user_id: str,
    username: str,
    email: str,
    current_password: str,
    new_password: str | None = None,
) -> UserRecord:
    record = get_user_record(user_id)
    if record is None:
        raise ValueError("user_not_found")
    if not record.password_hash or not check_password_hash(record.password_hash, current_password):
        raise ValueError("invalid_current_password")

    clean_username = username.strip()
    normalized_email = _normalize_email(email)
    clean_new_password = (new_password or "").strip()

    if len(clean_username) < 2 or len(clean_username) > 80:
        raise ValueError("invalid_username")
    if not normalized_email or len(normalized_email) > 254:
        raise ValueError("invalid_email")
    if clean_new_password and (len(clean_new_password) < 8 or len(clean_new_password) > 32):
        raise ValueError("weak_password")

    next_hash = generate_password_hash(clean_new_password) if clean_new_password else record.password_hash

    try:
        with _connect() as conn:
            row = conn.execute(
                """
                update public.users
                set username = %s,
                    email = %s,
                    password_hash = %s
                where id = %s::uuid
                returning id::text, username, email, role, organization, password_hash
                """,
                (clean_username, normalized_email, next_hash, user_id),
            ).fetchone()
            conn.commit()
    except UniqueViolation as exc:
        raise ValueError("email_exists") from exc

    if row is None:
        raise ValueError("user_not_found")
    return _row_to_user_record(row)


def update_user_as_admin(
    *,
    user_id: str,
    username: str,
    email: str,
    role: str,
    organization: str | None,
) -> UserRecord:
    clean_username = username.strip()
    normalized_email = _normalize_email(email)
    clean_organization = _normalize_optional_text(organization)
    parsed_role = _parse_admin_role(role)

    if len(clean_username) < 2 or len(clean_username) > 80:
        raise ValueError("invalid_username")
    if not normalized_email or len(normalized_email) > 254:
        raise ValueError("invalid_email")
    if clean_organization and len(clean_organization) > 120:
        raise ValueError("invalid_organization")

    try:
        with _connect() as conn:
            row = conn.execute(
                """
                update public.users
                set username = %s,
                    email = %s,
                    role = %s,
                    organization = %s
                where id = %s::uuid
                returning id::text, username, email, role, organization, password_hash
                """,
                (
                    clean_username,
                    normalized_email,
                    parsed_role.value,
                    clean_organization,
                    user_id,
                ),
            ).fetchone()
            conn.commit()
    except UniqueViolation as exc:
        raise ValueError("email_exists") from exc

    if row is None:
        raise ValueError("user_not_found")
    return _row_to_user_record(row)


def delete_user_as_admin(*, user_id: str) -> None:
    with _connect() as conn:
        result = conn.execute(
            "delete from public.users where id = %s::uuid",
            (user_id,),
        )
        conn.commit()

    if result.rowcount == 0:
        raise ValueError("user_not_found")


def _connect() -> psycopg.Connection:
    return psycopg.connect(
        _postgres_dsn(),
        row_factory=dict_row,
        connect_timeout=get_postgres_connect_timeout(),
    )


def _postgres_dsn() -> str:
    return get_postgres_dsn()


def _normalize_email(email: str | None) -> str:
    return email.strip().lower() if isinstance(email, str) else ""


def _normalize_optional_text(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    clean_value = value.strip()
    return clean_value or None


def _row_to_user_record(row: dict) -> UserRecord:
    return UserRecord(
        id=row["id"],
        username=row.get("username"),
        email=row["email"],
        role=_parse_role(row.get("role")),
        organization=row.get("organization"),
        password_hash=row.get("password_hash"),
    )


def _row_to_user_read(row: dict) -> UserRead:
    username = row.get("username")
    return UserRead(
        id=row["id"],
        username=username,
        name=username,
        email=row.get("email"),
        role=_parse_role(row.get("role")),
        organization=row.get("organization") or "No organization",
        user_type=None,
    )


def _record_to_user_read(record: UserRecord) -> UserRead:
    return UserRead(
        id=record.id,
        username=record.username,
        name=record.username,
        email=record.email,
        role=record.role,
        organization=record.organization or "No organization",
        user_type=record.user_type,
    )


def _parse_role(value: str | None) -> UserRole:
    if value in {"comun", "user"}:
        return UserRole.COMMON
    if value in {role.value for role in UserRole}:
        return UserRole(value)
    return UserRole.COMMON


def _parse_admin_role(value: str | None) -> UserRole:
    parsed_role = _parse_role(value)
    if parsed_role not in {UserRole.ADMIN, UserRole.COMMON}:
        raise ValueError("invalid_role")
    return parsed_role
