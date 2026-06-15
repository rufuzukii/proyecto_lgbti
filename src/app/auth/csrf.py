from __future__ import annotations

import hmac
from secrets import token_urlsafe

from flask import session

SESSION_KEY = "_csrf_token"


def get_csrf_token() -> str:
    token = session.get(SESSION_KEY)
    if not isinstance(token, str) or not token:
        token = token_urlsafe(32)
        session[SESSION_KEY] = token
    return token


def validate_csrf_token(token: str | None) -> bool:
    expected = session.get(SESSION_KEY)
    if not isinstance(expected, str) or not isinstance(token, str):
        return False
    return hmac.compare_digest(expected, token)
