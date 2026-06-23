from dataclasses import dataclass
import logging
import os
from typing import Optional

from flask import Flask, jsonify, request
from flask_login import LoginManager, UserMixin, current_user, login_required, login_user, logout_user
from pydantic import ValidationError

from app.config import get_app_config
from app.auth.rate_limit import create_rate_limiter
from app.users.schemas import UserRegister, UserRole
from app.users.service import UserStorageError, authenticate_user, create_user, get_user


@dataclass
class AuthUser(UserMixin):
    id: str
    email: Optional[str]
    role: UserRole


def create_auth_app() -> Flask:
    config = get_app_config()
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=config.secret_key,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=not config.local_mode,
    )

    logger = logging.getLogger(__name__)
    rate_limiter = create_rate_limiter(
        max_attempts=int(os.getenv("AUTH_MAX_ATTEMPTS", "6")),
        window_seconds=int(os.getenv("AUTH_WINDOW_SECONDS", "300")),
        namespace="auth-service",
    )

    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.session_protection = "strong"

    @login_manager.user_loader
    def load_user(user_id: str) -> Optional[AuthUser]:
        try:
            user = get_user(user_id)
        except UserStorageError:
            logger.exception("user_loader_storage_error")
            return None
        if user is None:
            return None
        return AuthUser(id=user.id, email=user.email, role=user.role)

    @app.post("/auth/register")
    def register_user():
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify({"status": "error", "message": "invalid_payload"}), 400

        rate_key: str = _rate_key(payload.get("email"))
        if rate_limiter.is_blocked(rate_key):
            return jsonify({"status": "error", "message": "rate_limited"}), 429

        try:
            data = UserRegister.model_validate(payload)
        except ValidationError:
            rate_limiter.record_failure(rate_key)
            return jsonify({"status": "error", "message": "invalid_payload"}), 400

        try:
            user = create_user(data)
        except ValueError as exc:
            rate_limiter.record_failure(rate_key)
            if str(exc) == "email_exists":
                return jsonify({"status": "error", "message": "email_exists"}), 409
            logger.exception("register_failed")
            return jsonify({"status": "error", "message": "register_failed"}), 500
        except UserStorageError:
            logger.exception("register_storage_error")
            return jsonify({"status": "error", "message": "storage_not_configured"}), 503

        rate_limiter.reset(rate_key)
        return jsonify(user.model_dump())

    @app.post("/auth/login")
    def login():
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify({"status": "error", "message": "invalid_payload"}), 400

        email = payload.get("email")
        password = payload.get("password")
        rate_key: str = _rate_key(email)

        if rate_limiter.is_blocked(rate_key):
            return jsonify({"status": "error", "message": "rate_limited"}), 429

        if not isinstance(email, str) or not isinstance(password, str):
            rate_limiter.record_failure(_rate_key(email if isinstance(email, str) else None))
            return jsonify({"status": "error", "message": "invalid_payload"}), 400

        try:
            record = authenticate_user(email, password)
        except UserStorageError:
            logger.exception("login_storage_error")
            return jsonify({"status": "error", "message": "storage_not_configured"}), 503
        if record is None:
            rate_limiter.record_failure(rate_key)
            return jsonify({"status": "error", "message": "invalid_credentials"}), 401
        login_user(AuthUser(id=record.id, email=record.email, role=record.role))
        rate_limiter.reset(rate_key)
        return jsonify({"status": "ok"})

    @app.post("/auth/logout")
    @login_required
    def logout():
        logout_user()
        return jsonify({"status": "ok"})

    @app.get("/auth/me")
    def me():
        if not current_user.is_authenticated:
            return jsonify({"role": UserRole.ANONYMOUS.value, "user": None})
        return jsonify({"role": current_user.role.value, "user_id": current_user.id})

    return app


def _rate_key(email: str | None) -> str:
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "unknown")
    ip = ip.split(",")[0].strip()
    email_part = email.strip().lower() if isinstance(email, str) else ""
    return f"{ip}:{email_part}"


