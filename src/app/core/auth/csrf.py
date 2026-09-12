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
    # compare_digest solo admite texto ASCII o bytes. Una entrada Unicode debe rechazarse
    # mediante la comparación, sin convertir una petición inválida en un error interno.
    return hmac.compare_digest(expected.encode("utf-8"), token.encode("utf-8"))


def rotate_csrf_token() -> str:
    """Renueva el token cuando cambia el estado de autenticación."""
    token = token_urlsafe(32)
    session[SESSION_KEY] = token
    return token
