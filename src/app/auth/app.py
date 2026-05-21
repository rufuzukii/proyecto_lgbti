from dataclasses import dataclass
from typing import Optional

from flask import Flask, jsonify, request
from flask_login import LoginManager, UserMixin, current_user, login_required, login_user, logout_user
from werkzeug.security import check_password_hash

from app.config import get_app_config
from app.users.schemas import UserRegister, UserRole
from app.users.service import authenticate_user, create_user, get_user


@dataclass
class AuthUser(UserMixin):
    id: int
    email: Optional[str]
    role: UserRole


def create_auth_app() -> Flask:
    config = get_app_config()
    app = Flask(__name__)
    app.config["SECRET_KEY"] = config.secret_key

    login_manager = LoginManager()
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id: str) -> Optional[AuthUser]:
        user = get_user(int(user_id))
        if user is None:
            return None
        return AuthUser(id=user.id, email=user.email, role=user.role)

    @app.post("/auth/register")
    def register_user():
        payload = request.get_json(silent=True) or {}
        data = UserRegister.model_validate(payload)
        user = create_user(data)
        return jsonify(user.model_dump())

    @app.post("/auth/login")
    def login():
        payload = request.get_json(silent=True) or {}
        email = payload.get("email")
        password = payload.get("password")
        record = authenticate_user(email, password)
        if record is None:
            return jsonify({"status": "error", "message": "invalid_credentials"}), 401
        login_user(AuthUser(id=record.id, email=record.email, role=record.role))
        return jsonify({"status": "ok"})

    @app.post("/auth/logout")
    @login_required
    def logout():
        logout_user()
        return jsonify({"status": "ok"})

    @app.get("/auth/me")
    def me():
        if not current_user.is_authenticated:
            return jsonify({"role": UserRole.ANONYMOUS, "user": None})
        return jsonify({"role": current_user.role, "user_id": current_user.id})

    return app

