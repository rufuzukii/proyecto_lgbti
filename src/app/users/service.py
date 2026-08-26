from __future__ import annotations

import logging
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from typing import Any, cast

import psycopg
from email_validator import EmailNotValidError, validate_email
from psycopg.errors import UniqueViolation
from psycopg.rows import dict_row
from werkzeug.security import check_password_hash, generate_password_hash

from app.config import get_postgres_connect_timeout, get_postgres_dsn
from app.taxonomy import canonical_taxonomy_value
from app.users.account_security import (
    AccountSecurityState,
    AccountSecurityStorageError,
    get_account_security,
    get_account_security_many,
    increment_session_version,
    initialize_new_account,
    mark_admin_validated,
    record_security_event,
)
from app.users.audit import record_user_admin_event
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
logger = logging.getLogger(__name__)
ADMIN_ROSTER_LOCK_ID = 1_981_060_117


@dataclass
class UserRecord:
    id: str
    username: str | None
    email: str
    role: UserRole
    organization: str | None
    password_hash: str | None
    user_type: UserType | None = None
    active: bool = True
    admin_validated: bool = False
    validated_at: datetime | None = None
    validated_by: str | None = None
    session_version: int = 0

    @property
    def display_name(self) -> str:
        return self.username or self.email


@dataclass(frozen=True, slots=True)
class UserPage:
    users: list[UserRead]
    page: int
    page_size: int
    total: int
    page_count: int


def list_users() -> list[UserRead]:
    with _connect() as conn:
        rows = conn.execute(
            """
            select id::text, username, email, organization, user_type
            from public.users
            order by created_at desc nulls last, email asc
            """
        ).fetchall()
    return _rows_to_user_reads(rows)


def list_users_page(
    *,
    search: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> UserPage:
    clean_search = _normalize_user_text(search or "")[:120]
    clean_page_size = min(100, max(1, page_size))
    pattern = f"%{_escape_like(clean_search)}%"
    with _connect() as conn:
        count_row = conn.execute(
            """
            select count(*) as total
            from public.users
            where (%s = '' or username ilike %s escape '\\' or email ilike %s escape '\\'
                   or coalesce(organization, '') ilike %s escape '\\')
            """,
            (clean_search, pattern, pattern, pattern),
        ).fetchone()
        count_values = cast(dict[str, Any], count_row or {})
        total = int(count_values.get("total") or 0)
        page_count = max(1, (total + clean_page_size - 1) // clean_page_size)
        clean_page = min(max(1, page), page_count)
        rows = conn.execute(
            """
            select id::text, username, email, organization, user_type
            from public.users
            where (%s = '' or username ilike %s escape '\\' or email ilike %s escape '\\'
                   or coalesce(organization, '') ilike %s escape '\\')
            order by created_at desc nulls last, email asc
            limit %s offset %s
            """,
            (
                clean_search,
                pattern,
                pattern,
                pattern,
                clean_page_size,
                (clean_page - 1) * clean_page_size,
            ),
        ).fetchall()
    return UserPage(
        users=_rows_to_user_reads(rows),
        page=clean_page,
        page_size=clean_page_size,
        total=total,
        page_count=page_count,
    )


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
            select id::text, username, email, organization, password_hash, user_type
            from public.users
            where id = %s::uuid
            """,
            (user_id,),
        ).fetchone()
    if row is None:
        return None
    values = cast(dict[str, Any], row)
    return _row_to_user_record(values, _account_state(str(values["id"])))


def get_user_record_by_email(email: str) -> UserRecord | None:
    normalized = _normalize_email(email)
    if not normalized:
        return None
    with _connect() as conn:
        row = conn.execute(
            """
            select id::text, username, email, organization, password_hash, user_type
            from public.users
            where lower(email) = %s
            """,
            (normalized,),
        ).fetchone()
    if row is None:
        return None
    values = cast(dict[str, Any], row)
    return _row_to_user_record(values, _account_state(str(values["id"])))


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
                insert into public.users
                    (username, email, user_type, organization, password_hash)
                values (%s, %s, %s, %s, %s)
                returning id::text, username, email, organization, user_type
                """,
                (
                    username,
                    normalized_email,
                    (
                        UserType.ADMIN.value
                        if assigned_role == UserRole.ADMIN
                        else UserType.COMUN.value
                    ),
                    organization,
                    password_hash,
                ),
            ).fetchone()
            if row is None:
                raise UserStorageError("user_creation_failed")
            row_values = cast(dict[str, Any], row)
            new_account_state = initialize_new_account(str(row_values["id"]))
            conn.commit()
    except UniqueViolation as exc:
        raise ValueError("email_exists") from exc
    except AccountSecurityStorageError as exc:
        raise UserStorageError("account_security_unavailable") from exc

    return _row_to_user_read(row_values, new_account_state)


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
    if not record.active:
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
                returning id::text, username, email, organization, password_hash, user_type
                """,
                (clean_username, normalized_email, next_hash, user_id),
            ).fetchone()
            conn.commit()
    except UniqueViolation as exc:
        raise ValueError("email_exists") from exc

    if row is None:
        raise ValueError("user_not_found")
    email_changed = normalized_email != record.email.casefold()
    security_changed = email_changed or bool(clean_new_password)
    if security_changed:
        try:
            increment_session_version(user_id)
            _record_security_event_safely(
                user_id,
                "email_changed" if email_changed else "password_changed",
            )
        except AccountSecurityStorageError as exc:
            raise UserStorageError("account_security_unavailable") from exc
    return _row_to_user_record(row, _account_state(user_id))


def update_user_as_admin(
    *,
    user_id: str,
    username: str,
    email: str,
    role: str,
    organization: str | None,
    actor_user_id: str,
    expected_version: str | None = None,
) -> UserRecord:
    if not actor_user_id:
        raise ValueError("actor_required")
    if user_id == actor_user_id:
        raise ValueError("self_manage")
    clean_username = _normalize_user_text(username)
    normalized_email = _normalize_email(email)
    clean_organization = _normalize_optional_text(organization)
    parsed_user_type = _parse_admin_user_type(role)

    if len(clean_username) < 2 or len(clean_username) > 80:
        raise ValueError("invalid_username")
    if not normalized_email or len(normalized_email) > 254:
        raise ValueError("invalid_email")
    if clean_organization and len(clean_organization) > 120:
        raise ValueError("invalid_organization")

    try:
        with _connect() as conn:
            conn.execute("select pg_advisory_xact_lock(%s)", (ADMIN_ROSTER_LOCK_ID,))
            current = conn.execute(
                """
                select id::text, username, email, organization, password_hash, user_type
                from public.users
                where id = %s::uuid
                for update
                """,
                (user_id,),
            ).fetchone()
            if current is None:
                raise ValueError("user_not_found")
            current_values = cast(dict[str, Any], current)
            if expected_version and expected_version != _user_version(current_values):
                raise ValueError("concurrent_update")
            if (
                _parse_user_type(current_values.get("user_type")) == UserType.ADMIN
                and parsed_user_type != UserType.ADMIN
            ):
                admin_count_row = conn.execute(
                    "select count(*) as total from public.users where lower(user_type) = %s",
                    (UserType.ADMIN.value,),
                ).fetchone()
                admin_count = cast(dict[str, Any], admin_count_row or {})
                if int(admin_count.get("total") or 0) <= 1:
                    raise ValueError("last_admin")
            row = conn.execute(
                """
                update public.users
                set username = %s, email = %s, user_type = %s, organization = %s
                where id = %s::uuid
                returning id::text, username, email, organization, password_hash, user_type
                """,
                (
                    clean_username,
                    normalized_email,
                    parsed_user_type.value,
                    clean_organization,
                    user_id,
                ),
            ).fetchone()
            conn.commit()
    except UniqueViolation as exc:
        raise ValueError("email_exists") from exc

    if row is None:
        raise ValueError("user_not_found")
    updated = _row_to_user_record(row, _account_state(user_id))
    _record_admin_event_safely(
        actor_user_id=actor_user_id,
        target_user_id=user_id,
        action="user_updated",
        before=current_values,
        after=cast(dict[str, Any], row),
    )
    return updated


def validate_user_as_admin(*, user_id: str, actor_user_id: str) -> UserRead:
    if not actor_user_id:
        raise ValueError("actor_required")
    if user_id == actor_user_id:
        raise ValueError("self_manage")
    record = get_user_record(user_id)
    if record is None:
        raise ValueError("user_not_found")
    try:
        state = mark_admin_validated(user_id, actor_user_id)
    except AccountSecurityStorageError as exc:
        raise UserStorageError("account_security_unavailable") from exc
    _record_admin_event_safely(
        actor_user_id=actor_user_id,
        target_user_id=user_id,
        action="account_validated",
        before={"admin_validated": record.admin_validated},
        after={"admin_validated": state.admin_validated},
    )
    return _row_to_user_read(
        {
            "id": record.id,
            "username": record.username,
            "email": record.email,
            "organization": record.organization,
            "user_type": record.user_type.value if record.user_type else None,
        },
        state,
    )


def delete_user_as_admin(*, user_id: str, actor_user_id: str) -> None:
    """Run the same cross-store erasure policy from the separate admin flow."""

    if not actor_user_id or actor_user_id == user_id:
        raise ValueError("self_delete")
    from app.privacy.service import AccountDeletionError, delete_user_account_as_admin

    try:
        delete_user_account_as_admin(user_id=user_id, actor_user_id=actor_user_id)
    except AccountDeletionError as exc:
        raise ValueError(exc.code) from exc


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


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _user_version(row: Any) -> str:
    values = cast(dict[str, Any], row)
    canonical = "\x1f".join(
        str(values.get(key) or "")
        for key in ("id", "username", "email", "organization", "user_type")
    )
    return sha256(canonical.encode("utf-8")).hexdigest()[:24]


def _record_admin_event_safely(**event: Any) -> None:
    try:
        record_user_admin_event(**event)
    except Exception:
        logger.exception("user_admin_audit_write_failed")


def _record_security_event_safely(user_id: str, action: str) -> None:
    try:
        record_security_event(user_id, action)
    except AccountSecurityStorageError:
        logger.exception("user_security_audit_write_failed")


def _row_to_user_record(
    row: Any,
    state: AccountSecurityState | None = None,
) -> UserRecord:
    row = cast(dict[str, Any], row)
    return UserRecord(
        id=row["id"],
        username=row.get("username"),
        email=row["email"],
        role=_role_from_user_type(row.get("user_type")),
        organization=row.get("organization"),
        password_hash=row.get("password_hash"),
        user_type=_parse_user_type(row.get("user_type")),
        active=state.active if state is not None else True,
        admin_validated=state.admin_validated if state is not None else False,
        validated_at=state.validated_at if state is not None else None,
        validated_by=state.validated_by if state is not None else None,
        session_version=state.session_version if state is not None else 0,
    )


def _row_to_user_read(
    row: Any,
    state: AccountSecurityState | None = None,
) -> UserRead:
    row = cast(dict[str, Any], row)
    username = row.get("username")
    return UserRead(
        id=row["id"],
        username=username,
        name=username,
        email=row.get("email"),
        role=_role_from_user_type(row.get("user_type")),
        organization=row.get("organization") or "No organization",
        user_type=_parse_user_type(row.get("user_type")),
        version=_user_version(row),
        active=state.active if state is not None else True,
        admin_validated=state.admin_validated if state is not None else False,
        validated_at=state.validated_at if state is not None else None,
        validated_by=state.validated_by if state is not None else None,
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
        version=_user_version(
            {
                "id": record.id,
                "username": record.username,
                "email": record.email,
                "organization": record.organization,
                "user_type": record.user_type.value if record.user_type else None,
            }
        ),
        active=record.active,
        admin_validated=record.admin_validated,
        validated_at=record.validated_at,
        validated_by=record.validated_by,
        session_version=record.session_version,
    )


def _rows_to_user_reads(rows: Any) -> list[UserRead]:
    values = [cast(dict[str, Any], row) for row in rows]
    try:
        states = get_account_security_many([str(row["id"]) for row in values])
    except AccountSecurityStorageError as exc:
        raise UserStorageError("account_security_unavailable") from exc
    return [_row_to_user_read(row, states.get(str(row["id"]))) for row in values]


def _account_state(user_id: str) -> AccountSecurityState:
    try:
        return get_account_security(user_id)
    except AccountSecurityStorageError as exc:
        raise UserStorageError("account_security_unavailable") from exc


def _role_from_user_type(value: str | None) -> UserRole:
    return UserRole.ADMIN if _parse_user_type(value) == UserType.ADMIN else UserRole.COMMON


def _parse_admin_user_type(value: str | None) -> UserType:
    clean_value = canonical_taxonomy_value("role", value)
    try:
        return UserType(clean_value)
    except ValueError as exc:
        raise ValueError("invalid_role") from exc


def _parse_user_type(value: str | None) -> UserType | None:
    clean_value = canonical_taxonomy_value("role", value)
    try:
        return UserType(clean_value)
    except ValueError:
        return None
