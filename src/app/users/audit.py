from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from app.mongo import get_mongo_collection
from app.privacy.policy import get_privacy_policy_config

COLLECTION_NAME = "user_admin_audit"


def record_user_admin_event(
    *,
    actor_user_id: str,
    target_user_id: str,
    action: str,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> None:
    """Persist a security audit event without passwords, hashes or tokens."""

    now = datetime.now(UTC)
    get_mongo_collection(COLLECTION_NAME).insert_one(
        {
            "actor_user_id": actor_user_id,
            "target_user_id": target_user_id,
            "action": action,
            "before": _safe_snapshot(before),
            "after": _safe_snapshot(after),
            "created_at": now,
            "expires_at": now
            + timedelta(days=get_privacy_policy_config().audit_retention_days),
        }
    )


def _safe_snapshot(value: dict[str, Any] | None) -> dict[str, Any] | None:
    if value is None:
        return None
    allowed = {"username", "email", "organization", "user_type", "active"}
    return {key: value.get(key) for key in allowed if key in value}
