from __future__ import annotations

import hashlib
import os
from datetime import timedelta
from typing import Any, cast
from urllib.parse import urlsplit

from flask import Flask, Response, abort, request, session
from werkzeug.middleware.proxy_fix import ProxyFix

AUTH_REQUEST_MAX_BYTES = 64 * 1024
SENSITIVE_PATH_PREFIXES = ("/auth/", "/admin", "/privacy/", "/user")


def configure_flask_security(
    app: Flask,
    *,
    production: bool,
    cookie_name: str,
    max_auth_request_bytes: int = AUTH_REQUEST_MAX_BYTES,
) -> None:
    """Apply shared production-safe HTTP, proxy and session settings."""
    app.config.update(
        SESSION_COOKIE_NAME=f"__Host-{cookie_name}" if production else cookie_name,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=production,
        SESSION_REFRESH_EACH_REQUEST=True,
        PERMANENT_SESSION_LIFETIME=timedelta(
            hours=_bounded_int_env("SESSION_LIFETIME_HOURS", 12, minimum=1, maximum=168)
        ),
        PREFERRED_URL_SCHEME="https" if production else "http",
    )

    trusted_hosts = _trusted_hosts()
    if trusted_hosts:
        app.config["TRUSTED_HOSTS"] = trusted_hosts

    if production:
        app.wsgi_app = cast(Any, ProxyFix(app.wsgi_app, x_for=1, x_proto=1))

    @app.before_request
    def keep_authenticated_session_active() -> None:
        # Flask-Login's strong protection removes a non-permanent session when
        # the proxy-visible client identifier changes. Promote both new and
        # pre-existing authenticated sessions before current_user is loaded so
        # ordinary navigation cannot silently log the user out.
        if session.get("_user_id") is not None and not session.permanent:
            session.permanent = True

    @app.before_request
    def reject_oversized_auth_request() -> None:
        content_length = request.content_length
        if (
            request.path.startswith(("/auth/", "/privacy/"))
            and content_length is not None
            and content_length > max_auth_request_bytes
        ):
            abort(413)
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            fetch_site = request.headers.get("Sec-Fetch-Site", "").casefold()
            if fetch_site == "cross-site":
                abort(403)
            origin = request.headers.get("Origin", "")
            parsed_origin = urlsplit(origin) if origin else None
            if parsed_origin is not None and (
                parsed_origin.netloc.casefold() != request.host.casefold()
                or parsed_origin.scheme.casefold() != request.scheme.casefold()
            ):
                abort(403)

    @app.after_request
    def apply_security_headers(response: Response) -> Response:
        for name, value in security_headers(production=production).items():
            response.headers.setdefault(name, value)
        if request.path.startswith(SENSITIVE_PATH_PREFIXES):
            response.headers["Cache-Control"] = "no-store, max-age=0"
            response.headers["Pragma"] = "no-cache"
        return response


def security_headers(*, production: bool) -> dict[str, str]:
    headers = {
        "Content-Security-Policy": (
            "base-uri 'self'; object-src 'none'; frame-ancestors 'none'; form-action 'self'"
        ),
        "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "X-Permitted-Cross-Domain-Policies": "none",
    }
    if production:
        headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return headers


def client_ip() -> str:
    """Return the proxy-normalized client address without trusting raw headers."""
    return (request.remote_addr or "unknown").strip()[:64]


def rate_limit_key(*, subject: str = "", scope: str = "") -> str:
    """Build a non-identifying key suitable for the local rate limiter."""
    identity = f"{scope}|{client_ip()}|{subject[:254]}"
    return hashlib.sha256(
        identity.encode("utf-8"),
        usedforsecurity=False,
    ).hexdigest()


def _trusted_hosts() -> list[str]:
    configured = os.getenv("TRUSTED_HOSTS", "")
    hosts = [item.strip() for item in configured.split(",") if item.strip()]
    render_hostname = os.getenv("RENDER_EXTERNAL_HOSTNAME", "").strip()
    if render_hostname and render_hostname not in hosts:
        hosts.append(render_hostname)
    return hosts


def _bounded_int_env(name: str, default: int, *, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        value = default
    return min(maximum, max(minimum, value))
