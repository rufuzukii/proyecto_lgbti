from __future__ import annotations

import os
from dataclasses import dataclass

from app.users.contact_service import CONTACT_RECIPIENT

PRIVACY_NOTICE_VERSION = "2026-08-06-v1"
AEPD_RIGHTS_URL = "https://www.aepd.es/derechos-y-deberes/conoce-tus-derechos"
AEPD_COMPLAINT_URL = "https://www.aepd.es/la-agencia/en-que-podemos-ayudarte"


@dataclass(frozen=True, slots=True)
class PrivacyPolicyConfig:
    controller_name: str
    contact_email: str
    controller_address: str | None
    policy_effective_date: str
    audit_retention_days: int
    deletion_job_retention_days: int
    backup_retention: str | None
    email_retention: str | None
    access_log_retention: str | None
    hosting_location: str | None
    postgres_provider: str | None
    mongo_provider: str | None
    email_provider: str | None
    transfer_safeguards: str | None
    controller_identity_configured: bool


def get_privacy_policy_config() -> PrivacyPolicyConfig:
    configured_name = _clean_env("PRIVACY_CONTROLLER_NAME")
    contact = (
        _clean_env("PRIVACY_CONTACT_EMAIL")
        or _clean_env("SMTP_FROM_EMAIL")
        or CONTACT_RECIPIENT
    )
    return PrivacyPolicyConfig(
        controller_name=configured_name or "RainbowLens DataHub",
        contact_email=contact,
        controller_address=_clean_env("PRIVACY_CONTROLLER_ADDRESS"),
        policy_effective_date=_clean_env("PRIVACY_POLICY_EFFECTIVE_DATE") or "6 de agosto de 2026",
        audit_retention_days=_bounded_int("PRIVACY_AUDIT_RETENTION_DAYS", 90, 30, 730),
        deletion_job_retention_days=_bounded_int(
            "PRIVACY_DELETION_JOB_RETENTION_DAYS", 30, 7, 365
        ),
        backup_retention=_clean_env("PRIVACY_BACKUP_RETENTION"),
        email_retention=_clean_env("PRIVACY_EMAIL_RETENTION"),
        access_log_retention=_clean_env("PRIVACY_ACCESS_LOG_RETENTION"),
        hosting_location=_clean_env("PRIVACY_HOSTING_LOCATION"),
        postgres_provider=_clean_env("PRIVACY_POSTGRES_PROVIDER"),
        mongo_provider=_clean_env("PRIVACY_MONGO_PROVIDER"),
        email_provider=_clean_env("PRIVACY_EMAIL_PROVIDER"),
        transfer_safeguards=_clean_env("PRIVACY_TRANSFER_SAFEGUARDS"),
        controller_identity_configured=configured_name is not None,
    )


def _clean_env(name: str) -> str | None:
    value = os.getenv(name)
    return value.strip() if value and value.strip() else None


def _bounded_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        value = default
    return min(maximum, max(minimum, value))
