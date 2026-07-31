from __future__ import annotations

import hmac
import os

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


def _load_api_keys(environment_name: str, fallback_name: str | None = None) -> set[str]:
    raw = os.getenv(environment_name) or (os.getenv(fallback_name) if fallback_name else "") or ""
    return {entry.strip() for entry in raw.split(",") if len(entry.strip()) >= 32}


def require_api_key(api_key: str | None = Security(API_KEY_HEADER)) -> None:
    _validate_api_key(api_key, _load_api_keys("API_KEYS", "API_KEY"))


def require_admin_api_key(api_key: str | None = Security(API_KEY_HEADER)) -> None:
    _validate_api_key(api_key, _load_api_keys("ADMIN_API_KEYS"))


def _validate_api_key(api_key: str | None, allowed: set[str]) -> None:
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="api_key_not_configured",
        )
    if not api_key or not any(hmac.compare_digest(api_key, key) for key in allowed):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid_api_key",
        )
