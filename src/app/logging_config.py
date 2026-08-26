from __future__ import annotations

import logging
import os
import re
from typing import Any

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"
SENSITIVE_ENVIRONMENT_NAMES = (
    "SECRET_KEY",
    "DATABASE_URL",
    "POSTGRES_PASSWORD",
    "MONGO_URI",
    "MONGO_PASSWORD",
    "SMTP_PASSWORD",
    "GMAIL_API_CLIENT_SECRET",
    "GMAIL_API_REFRESH_TOKEN",
    "SUPABASE_S3_ACCESS_KEY",
    "SUPABASE_S3_SECRET_KEY",
    "API_KEY",
    "API_KEYS",
    "ADMIN_API_KEYS",
)
URL_CREDENTIAL_PATTERN = re.compile(
    r"(?P<prefix>[a-z][a-z0-9+.-]*://[^:/@\s]+:)(?P<secret>[^@\s]+)(?P<suffix>@)",
    re.IGNORECASE,
)
NAMED_SECRET_PATTERN = re.compile(
    r"(?P<name>password|secret|token|api[_-]?key|access[_-]?key|authorization)"
    r"(?P<separator>\s*[:=]\s*)"
    r"(?P<value>[^\s,;]+)",
    re.IGNORECASE,
)
PRIVATE_KEY_PATTERN = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
    re.DOTALL,
)


class RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return redact_sensitive_text(super().format(record))


def configure_secure_logging() -> None:
    level_name = os.getenv("LOG_LEVEL", "INFO").strip().upper()
    level = getattr(logging, level_name, logging.INFO)
    root_logger = logging.getLogger()
    if not root_logger.handlers:
        root_logger.addHandler(logging.StreamHandler())
    formatter = RedactingFormatter(LOG_FORMAT)
    for handler in root_logger.handlers:
        handler.setFormatter(formatter)
    root_logger.setLevel(level)
    logging.getLogger("app").setLevel(level)


def redact_sensitive_text(value: Any) -> str:
    text = str(value)
    text = PRIVATE_KEY_PATTERN.sub("[REDACTED PRIVATE KEY]", text)
    text = URL_CREDENTIAL_PATTERN.sub(r"\g<prefix>***\g<suffix>", text)
    text = NAMED_SECRET_PATTERN.sub(
        lambda match: f"{match.group('name')}{match.group('separator')}***",
        text,
    )
    for environment_name in SENSITIVE_ENVIRONMENT_NAMES:
        secret = os.getenv(environment_name, "")
        if len(secret) >= 8:
            text = text.replace(secret, "***")
    return text
