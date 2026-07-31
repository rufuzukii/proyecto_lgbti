from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import Any, cast

import psycopg
from email_validator import EmailNotValidError, validate_email
from psycopg.errors import UniqueViolation
from psycopg.rows import dict_row
from werkzeug.security import check_password_hash, generate_password_hash

from app.config import get_postgres_connect_timeout, get_postgres_dsn
from app.users.schemas import (
    MAX_PASSWORD_LENGTH,
    MIN_PASSWORD_LENGTH,
    UserRead,
    UserRegister,
    UserRole,
    UserType,
)


class UserStorageError(RuntimeError):
    """Raised when the configured users table cannot support secure auth."""


_DUMMY_PASSWORD_HASH = generate_password_hash("not-a-real-account-password")


@dataclass
class UserRecord:
    id: str
    username: str | None
    email: str
    role: UserRole
    organization: str | None
    password_hash: str | None
    user_type: UserType | None = None

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


def get_user(user_id: str) -> UserRead | None:
    record = get_user_record(user_id)
    if record is None:
        return None
    return _record_to_user_read(record)


def get_user_record(user_id: str) -> UserRecord | None:
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


def get_user_record_by_email(email: str) -> UserRecord | None:
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

    username = _normalize_user_text(payload.name)
    if len(username) < 2 or len(username) > 80:
        raise ValueError("invalid_username")
    assigned_role = role if role == UserRole.ADMIN else UserRole.COMMON
    organization = _normalize_optional_text(payload.organization)
    if organization and len(organization) > 120:
        raise ValueError("invalid_organization")
    password_hash = generate_password_hash(payload.password.get_secret_value())

    try:
        with _connect() as conn:
            row = conn.execute(
                """
                insert into public.users (username, email, role, organization, password_hash)
                values (%s, %s, %s, %s, %s)
                returning id::text, username, email, role, organization
                """,
                (
                    username,
                    normalized_email,
                    assigned_role.value,
                    organization,
                    password_hash,
                ),
            ).fetchone()
            conn.commit()
    except UniqueViolation as exc:
        raise ValueError("email_exists") from exc

    return _row_to_user_read(row)


def authenticate_user(email: str, password: str) -> UserRecord | None:
    if not email or not password or len(password) > MAX_PASSWORD_LENGTH:
        return None
    record = get_user_record_by_email(email)
    password_hash = (
        record.password_hash
        if record is not None and record.password_hash
        else _DUMMY_PASSWORD_HASH
    )
    password_matches = check_password_hash(password_hash, password)
    if record is None or not record.password_hash or not password_matches:
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

    clean_username = _normalize_user_text(username)
    normalized_email = _normalize_email(email)
    clean_new_password = new_password or ""

    if len(clean_username) < 2 or len(clean_username) > 80:
        raise ValueError("invalid_username")
    if not normalized_email or len(normalized_email) > 254:
        raise ValueError("invalid_email")
    if clean_new_password and not (
        MIN_PASSWORD_LENGTH <= len(clean_new_password) <= MAX_PASSWORD_LENGTH
    ):
        raise ValueError("weak_password")

    next_hash = (
        generate_password_hash(clean_new_password) if clean_new_password else record.password_hash
    )

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
    clean_username = _normalize_user_text(username)
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
        row_factory=cast(Any, dict_row),
        connect_timeout=get_postgres_connect_timeout(),
    )


def _postgres_dsn() -> str:
    return get_postgres_dsn()


def _normalize_email(email: str | None) -> str:
    if not isinstance(email, str):
        return ""
    try:
        return validate_email(
            email.strip(),
            check_deliverability=False,
        ).normalized.casefold()
    except EmailNotValidError:
        return ""


def _normalize_optional_text(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    clean_value = _normalize_user_text(value)
    return clean_value or None


def _normalize_user_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).strip()
    return "".join(
        character
        for character in normalized
        if unicodedata.category(character) not in {"Cc", "Cf", "Cs"}
    ).strip()


def _row_to_user_record(row: Any) -> UserRecord:
    row = cast(dict[str, Any], row)
    return UserRecord(
        id=row["id"],
        username=row.get("username"),
        email=row["email"],
        role=_parse_role(row.get("role")),
        organization=row.get("organization"),
        password_hash=row.get("password_hash"),
    )


def _row_to_user_read(row: Any) -> UserRead:
    row = cast(dict[str, Any], row)
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
    clean_value = str(value or "").strip().casefold()
    if clean_value not in {UserRole.ADMIN.value, UserRole.COMMON.value}:
        raise ValueError("invalid_role")
    return UserRole(clean_value)
