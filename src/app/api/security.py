from __future__ import annotations

import hmac
import os

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


def _load_api_keys() -> set[str]:
    raw = os.getenv("API_KEYS") or os.getenv("API_KEY") or ""
    return {entry.strip() for entry in raw.split(",") if entry.strip()}


def require_api_key(api_key: str | None = Security(API_KEY_HEADER)) -> None:
    allowed = _load_api_keys()
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

