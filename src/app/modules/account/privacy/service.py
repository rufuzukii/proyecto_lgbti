from __future__ import annotations

import hmac
import json
import logging
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any, cast

import psycopg
from email_validator import EmailNotValidError, validate_email
from psycopg.rows import dict_row
from pymongo.errors import PyMongoError
from werkzeug.security import check_password_hash

from app.core.config import get_app_config
from app.infrastructure.cache import cache
from app.infrastructure.mongo import get_mongo_collection
from app.infrastructure.postgres import postgres_connection
from app.modules.account.privacy.models import DeletionOutcome, PersonalDataInventory
from app.modules.account.privacy.policy import get_privacy_policy_config
from app.modules.account.users.account_security import (
    ACCOUNT_COLLECTION,
    SECURITY_AUDIT_COLLECTION,
    get_account_security_many,
)
from app.modules.account.users.audit import COLLECTION_NAME as ADMIN_AUDIT_COLLECTION
from app.modules.account.users.schemas import UserType
from app.modules.account.users.service import UserRecord, get_user_record
from app.modules.didactics.custom_game_service import COLLECTION_NAME as GAMES_COLLECTION

logger = logging.getLogger(__name__)
DELETION_COLLECTION = "user_deletion_requests"
EXPECTED_CONFIRMATIONS = {
    "es": "ELIMINAR MI CUENTA",
    "en": "DELETE MY ACCOUNT",
}


class AccountDeletionError(RuntimeError):
    """Código seguro de error para una eliminación rechazada o incompleta."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class PrivacyStorageError(RuntimeError):
    """No se ha podido inventariar con seguridad un almacén de datos personales necesario."""


def get_personal_data_inventory(user_id: str) -> PersonalDataInventory:
    if not user_id:
        raise ValueError("user_id_required")
    try:
        with postgres_connection(row_factory=cast(Any, dict_row)) as conn:
            row = conn.execute(
                """
                select
                    exists(select 1 from public.users where id = %s::uuid) as profile,
                    (select count(*) from public.import_logs where user_id = %s::uuid) as import_logs
                """,
                (user_id, user_id),
            ).fetchone()
        values = cast(dict[str, Any], row or {})
        account_security = get_mongo_collection(ACCOUNT_COLLECTION).count_documents(
            {"user_id": user_id}
        )
        teacher_games = get_mongo_collection(GAMES_COLLECTION).count_documents(
            _teacher_activity_owner_query(user_id)
        )
        security_audit = get_mongo_collection(SECURITY_AUDIT_COLLECTION).count_documents(
            {"user_id": user_id}
        )
        admin_audit = get_mongo_collection(ADMIN_AUDIT_COLLECTION).count_documents(
            {"$or": [{"actor_user_id": user_id}, {"target_user_id": user_id}]}
        )
    except (OSError, PyMongoError, RuntimeError, psycopg.Error, ValueError) as exc:
        raise PrivacyStorageError("personal_data_inventory_unavailable") from exc
    return PersonalDataInventory(
        profile=bool(values.get("profile")),
        account_security=account_security,
        teacher_games=teacher_games,
        import_logs=int(values.get("import_logs") or 0),
        security_audit_events=security_audit,
        admin_audit_events=admin_audit,
    )


def validate_deletion_confirmation(
    record: UserRecord,
    *,
    email: str,
    password: str,
    confirmation_checked: bool,
    confirmation_text: str,
    language: str,
) -> None:
    clean_language = "en" if language == "en" else "es"
    if not confirmation_checked:
        raise AccountDeletionError("confirmation_required")
    try:
        normalized_email = validate_email(email, check_deliverability=False).normalized.casefold()
    except EmailNotValidError as exc:
        raise AccountDeletionError("invalid_email") from exc
    # Los correos internacionales son válidos; la comparación segura requiere bytes.
    if not hmac.compare_digest(
        normalized_email.encode("utf-8"), record.email.casefold().encode("utf-8")
    ):
        raise AccountDeletionError("invalid_email")
    stored_hash = record.password_hash or ""
    if not stored_hash or not password or not check_password_hash(stored_hash, password):
        raise AccountDeletionError("invalid_password")
    expected = EXPECTED_CONFIRMATIONS[clean_language]
    if not hmac.compare_digest(confirmation_text.strip().encode("utf-8"), expected.encode("utf-8")):
        raise AccountDeletionError("invalid_confirmation_text")


def delete_user_account(
    *,
    user_id: str,
    email: str,
    password: str,
    confirmation_checked: bool,
    confirmation_text: str,
    language: str,
) -> DeletionOutcome:
    record = get_user_record(user_id)
    if record is None:
        return DeletionOutcome(status="already_deleted")
    validate_deletion_confirmation(
        record,
        email=email,
        password=password,
        confirmation_checked=confirmation_checked,
        confirmation_text=confirmation_text,
        language=language,
    )
    return _execute_account_deletion(record, actor_user_id=None)


def delete_user_account_as_admin(*, user_id: str, actor_user_id: str) -> DeletionOutcome:
    if not actor_user_id or actor_user_id == user_id:
        raise AccountDeletionError("self_delete")
    record = get_user_record(user_id)
    if record is None:
        return DeletionOutcome(status="already_deleted")
    return _execute_account_deletion(record, actor_user_id=actor_user_id)


def build_personal_data_export(user_id: str) -> dict[str, Any]:
    record = get_user_record(user_id)
    if record is None:
        raise AccountDeletionError("user_not_found")
    with postgres_connection(row_factory=cast(Any, dict_row)) as conn:
        profile = conn.execute(
            """
            select username, email, organization, user_type, created_at
            from public.users where id = %s::uuid
            """,
            (user_id,),
        ).fetchone()
        imports = conn.execute(
            """
            select file_name, status, records_inserted, created_at, file_json
            from public.import_logs where user_id = %s::uuid order by created_at
            """,
            (user_id,),
        ).fetchall()
    security = get_mongo_collection(ACCOUNT_COLLECTION).find_one(
        {"user_id": user_id},
        {"_id": 0, "user_id": 0, "session_version": 0},
    )
    games = list(
        get_mongo_collection(GAMES_COLLECTION).find(
            _teacher_activity_owner_query(user_id),
            {"_id": 0, "owner_id": 0, "owner_user_id": 0},
        )
    )
    return _json_safe(
        {
            "exported_at": datetime.now(UTC),
            "account": dict(profile or {}),
            "account_security": security or {},
            "teacher_games": games,
            "data_imports": [dict(item) for item in imports],
            "not_persisted_by_server": {
                "language_and_theme": "stored only in this browser",
                "generated_reports": "generated in memory and temporary files",
                "contact_attachments": "sent by email and not stored in the application databases",
            },
        }
    )


def personal_data_export_bytes(user_id: str) -> bytes:
    return json.dumps(
        build_personal_data_export(user_id),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ).encode("utf-8")


def _execute_account_deletion(
    record: UserRecord,
    *,
    actor_user_id: str | None,
) -> DeletionOutcome:
    inventory = get_personal_data_inventory(record.id)
    if not inventory.profile:
        return DeletionOutcome(status="already_deleted")
    _assert_not_last_admin(record)
    subject_ref = _subject_reference(record.id)
    _start_or_resume_job(record.id, inventory)
    deleted: dict[str, int] = {}
    anonymized: dict[str, int] = {}
    try:
        deleted.update(_delete_private_mongo_data(record.id))
        _mark_stage_safely(record.id, "private_mongo")

        deleted["supabase_objects"] = _delete_personal_supabase_objects(record.id)
        _mark_stage_safely(record.id, "supabase")

        deleted.update(_delete_security_state(record.id))
        _mark_stage_safely(record.id, "security")

        anonymized.update(_anonymize_audits(record.id, subject_ref))
        _mark_stage_safely(record.id, "audits")

        deleted.update(_delete_postgres_account(record.id))
        _mark_stage_safely(record.id, "postgres")

        _invalidate_user_cache()
        _mark_stage_safely(record.id, "cache")
    except AccountDeletionError:
        _record_job_failure(record.id, "validation")
        raise
    except Exception as exc:
        logger.exception("privacy_account_deletion_failed", extra={"stage_user": subject_ref})
        _record_job_failure(record.id, type(exc).__name__)
        raise AccountDeletionError("deletion_incomplete") from exc

    _complete_job(record.id, subject_ref)
    if actor_user_id:
        try:
            _record_admin_deletion(actor_user_id, subject_ref)
        except OSError, PyMongoError, RuntimeError, ValueError:
            logger.exception("privacy_admin_deletion_audit_failed")
    logger.info("privacy_account_deletion_completed", extra={"subject": subject_ref})
    return DeletionOutcome(
        status="completed",
        deleted=deleted,
        anonymized=anonymized,
        retained={
            "security_audits": (
                f"anonymized for up to {get_privacy_policy_config().audit_retention_days} days"
            ),
            "backups": "removed through the configured backup rotation",
            "contact_email": "subject to the configured mailbox retention policy",
            "hosting_logs": "subject to the contracted provider log-retention policy",
        },
    )


def _assert_not_last_admin(record: UserRecord) -> None:
    if record.user_type != UserType.ADMIN or not record.active:
        return
    with postgres_connection(row_factory=cast(Any, dict_row)) as conn:
        rows = conn.execute(
            "select id::text as id from public.users where lower(user_type) = %s",
            (UserType.ADMIN.value,),
        ).fetchall()
    admin_ids = [str(cast(dict[str, Any], row).get("id") or "") for row in rows]
    states = get_account_security_many(admin_ids)
    active_admins = sum(1 for user_id in admin_ids if states[user_id].active)
    if active_admins <= 1:
        raise AccountDeletionError("last_admin")


def _start_or_resume_job(user_id: str, inventory: PersonalDataInventory) -> None:
    now = datetime.now(UTC)
    get_mongo_collection(DELETION_COLLECTION).update_one(
        {"user_id": user_id},
        {
            "$set": {"status": "pending", "updated_at": now},
            "$setOnInsert": {
                "user_id": user_id,
                "created_at": now,
                "completed_stages": [],
                "inventory": inventory.to_safe_dict(),
            },
            "$inc": {"attempts": 1},
            "$unset": {"last_error": ""},
        },
        upsert=True,
    )


def _mark_stage(user_id: str, stage: str) -> None:
    get_mongo_collection(DELETION_COLLECTION).update_one(
        {"user_id": user_id},
        {
            "$addToSet": {"completed_stages": stage},
            "$set": {"updated_at": datetime.now(UTC)},
        },
    )


def _mark_stage_safely(user_id: str, stage: str) -> None:
    try:
        _mark_stage(user_id, stage)
    except OSError, PyMongoError, RuntimeError, ValueError:
        logger.warning("privacy_deletion_stage_record_failed", extra={"stage": stage})


def _record_job_failure(user_id: str, error_code: str) -> None:
    try:
        get_mongo_collection(DELETION_COLLECTION).update_one(
            {"user_id": user_id},
            {
                "$set": {
                    "status": "pending",
                    "last_error": str(error_code)[:80],
                    "updated_at": datetime.now(UTC),
                }
            },
        )
    except Exception:
        logger.exception("privacy_deletion_failure_record_failed")


def _complete_job(user_id: str, subject_ref: str) -> None:
    config = get_privacy_policy_config()
    now = datetime.now(UTC)
    try:
        get_mongo_collection(DELETION_COLLECTION).update_one(
            {"user_id": user_id},
            {
                "$set": {
                    "status": "completed",
                    "subject_ref": subject_ref,
                    "completed_at": now,
                    "updated_at": now,
                    "expires_at": now + timedelta(days=config.deletion_job_retention_days),
                },
                "$unset": {"user_id": "", "inventory": "", "last_error": ""},
            },
        )
    except Exception:
        logger.exception("privacy_deletion_completion_record_failed")


def _delete_private_mongo_data(user_id: str) -> dict[str, int]:
    games = get_mongo_collection(GAMES_COLLECTION).delete_many(
        _teacher_activity_owner_query(user_id)
    )
    return {
        "teacher_games": int(games.deleted_count),
    }


def _teacher_activity_owner_query(user_id: str) -> dict[str, Any]:
    """Incluye registros anteriores al esquema v2 y usa owner_user_id como referencia canónica."""
    return {"$or": [{"owner_user_id": user_id}, {"owner_id": user_id}]}


def _delete_personal_supabase_objects(_user_id: str) -> int:
    # Supabase solo guarda figuras públicas de FELGTBI+: no hay objetos propiedad
    # del usuario que borrar y deben conservarse los datos públicos de investigación.
    return 0


def _delete_security_state(user_id: str) -> dict[str, int]:
    account = get_mongo_collection(ACCOUNT_COLLECTION).delete_many({"user_id": user_id})
    return {
        "account_security": int(account.deleted_count),
    }


def _anonymize_audits(user_id: str, subject_ref: str) -> dict[str, int]:
    expires_at = datetime.now(UTC) + timedelta(
        days=get_privacy_policy_config().audit_retention_days
    )
    security = get_mongo_collection(SECURITY_AUDIT_COLLECTION).update_many(
        {"user_id": user_id},
        {
            "$set": {"subject_ref": subject_ref, "expires_at": expires_at},
            "$unset": {"user_id": ""},
        },
    )
    collection = get_mongo_collection(ADMIN_AUDIT_COLLECTION)
    target = collection.update_many(
        {"target_user_id": user_id},
        {
            "$set": {"target_subject_ref": subject_ref, "expires_at": expires_at},
            "$unset": {"target_user_id": "", "before": "", "after": ""},
        },
    )
    actor = collection.update_many(
        {"actor_user_id": user_id},
        {
            "$set": {"actor_subject_ref": subject_ref, "expires_at": expires_at},
            "$unset": {"actor_user_id": ""},
        },
    )
    return {
        "security_audit_events": int(security.modified_count),
        "admin_audit_target_events": int(target.modified_count),
        "admin_audit_actor_events": int(actor.modified_count),
    }


def _delete_postgres_account(user_id: str) -> dict[str, int]:
    with postgres_connection(row_factory=cast(Any, dict_row)) as conn:
        conn.execute("select pg_advisory_xact_lock(%s)", (912_447_031,))
        current = conn.execute(
            "select user_type from public.users where id = %s::uuid for update",
            (user_id,),
        ).fetchone()
        if current is None:
            conn.rollback()
            return {"import_logs": 0, "user_profile": 0}
        if str(cast(dict[str, Any], current).get("user_type") or "").casefold() == "admin":
            count = conn.execute(
                "select count(*) as total from public.users where lower(user_type) = %s",
                (UserType.ADMIN.value,),
            ).fetchone()
            if int(cast(dict[str, Any], count or {}).get("total") or 0) <= 1:
                raise AccountDeletionError("last_admin")
        import_result = conn.execute(
            "delete from public.import_logs where user_id = %s::uuid", (user_id,)
        )
        user_result = conn.execute("delete from public.users where id = %s::uuid", (user_id,))
        conn.commit()
    return {
        "import_logs": int(import_result.rowcount),
        "user_profile": int(user_result.rowcount),
    }


def _invalidate_user_cache() -> None:
    if not cache.clear():
        logger.warning("privacy_cache_invalidation_degraded")


def _record_admin_deletion(actor_user_id: str, target_subject_ref: str) -> None:
    expires_at = datetime.now(UTC) + timedelta(
        days=get_privacy_policy_config().audit_retention_days
    )
    get_mongo_collection(ADMIN_AUDIT_COLLECTION).insert_one(
        {
            "actor_user_id": actor_user_id,
            "target_subject_ref": target_subject_ref,
            "action": "user_deleted_by_admin",
            "created_at": datetime.now(UTC),
            "expires_at": expires_at,
        }
    )


def _subject_reference(user_id: str) -> str:
    secret = get_app_config().secret_key.encode("utf-8")
    digest = hmac.new(secret, user_id.encode("utf-8"), sha256).hexdigest()[:32]
    return f"deleted:{digest}"


def _json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value
