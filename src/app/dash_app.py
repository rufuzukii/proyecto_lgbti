from __future__ import annotations

from dataclasses import dataclass
import logging
import os
from pathlib import Path
from urllib.parse import parse_qs, urlencode

from app.dash.compat import Dash, Input, Output, dcc, html
from flask import redirect, request
from flask_login import LoginManager, UserMixin, current_user, login_user, logout_user
from pydantic import ValidationError

from app.analytics import invalidate_analytics_cache
from app.analytics.repository import assert_analytics_databases_available
from app.auth.csrf import validate_csrf_token
from app.auth.rate_limit import create_rate_limiter
from app.cache import init_cache
from app.config import get_app_config
from app.dash.layouts.about import build_about_layout, register_about_callbacks
from app.dash.layouts.error_page import (
    build_database_unavailable_layout,
    render_database_unavailable_response,
)
from app.dash.layouts.home import build_home_layout, register_home_callbacks
from app.dash.layouts.user_page import build_user_page_layout
from app.dash.pages.admin.imports import build_admin_imports_layout
from app.dash.pages.admin.users import build_access_denied_layout, build_admin_users_layout
from app.dash.pages.session.login import build_login_layout
from app.dash.pages.session.register import build_register_layout
from app.dash.pages.statistics import (
    build_statistics_layout,
    register_statistics_callbacks,
)
from app.dash.pages.spain import build_spain_layout, register_spain_callbacks
from app.dash.pages.upload import build_upload_layout, register_upload_callbacks
from app.errors import DatabaseUnavailableError
from app.import_to_db.import_log import (
    delete_import_log,
    get_pending_import_log,
    list_pending_import_logs,
)
from app.users.schemas import UserRegister, UserRole
from app.users.service import (
    UserRecord,
    UserStorageError,
    authenticate_user,
    create_user,
    delete_user_as_admin,
    get_user_record,
    list_users,
    update_user_as_admin,
    update_user_profile,
)

logger = logging.getLogger(__name__)


@dataclass
class SessionUser(UserMixin):
    id: str
    username: str | None
    email: str
    role: UserRole
    organization: str | None


def create_dash_app() -> Dash:
    config = get_app_config()
    assets_path = Path(__file__).resolve().parent / "dash" / "assets"
    app = Dash(
        __name__,
        assets_folder=str(assets_path),
        suppress_callback_exceptions=True,
        title="RainbowLens",
    )
    app.index_string = """
    <!DOCTYPE html>
    <html>
        <head>
            {%metas%}
            <title>{%title%}</title>
            <link rel="icon" href="/assets/img/rainbow_lens_icono.ico">
            {%css%}
            <link rel="stylesheet" href="/assets/responsive/responsive.css">
        </head>
        <body>
            {%app_entry%}
            <footer>
                {%config%}
                {%scripts%}
                {%renderer%}
            </footer>
        </body>
    </html>
    """
    app.server.config.update(
        SECRET_KEY=config.secret_key,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=not config.local_mode,
    )
    init_cache(app.server)
    _register_error_routes(app)

    login_manager = LoginManager()
    login_manager.session_protection = "basic"
    login_manager.init_app(app.server)
    _register_user_loader(login_manager)
    _register_auth_routes(app)

    app.layout = html.Div(
        [
            dcc.Location(id="url"),
            html.Div(id="page-content"),
            html.Footer(
                [
                    html.Strong("RainbowLens"),
                    html.Span("Version 1.0.0"),
                ],
                className="site-footer",
            ),
        ]
    )

    @app.callback(
        Output("page-content", "children"),
        Input("url", "pathname"),
        Input("url", "search"),
    )
    def display_page(pathname: str | None, search: str | None):
        params = _query_params(search)
        try:
            if pathname == "/statistics":
                return build_statistics_layout()
            if pathname == "/stadistics":
                return dcc.Location(href="/statistics", id="legacy-statistics-redirect")
            if pathname == "/spain":
                return build_spain_layout()
            if pathname == "/upload":
                return build_upload_layout()
            if pathname == "/about":
                return build_about_layout()
            if pathname == "/login":
                if current_user.is_authenticated:
                    return build_user_page_layout(
                        status_code=_first_param(params, "status"),
                        error_code=_first_param(params, "error"),
                        mode=_first_param(params, "mode"),
                    )
                return build_login_layout(
                    next_path=_safe_next(_first_param(params, "next"), "/user"),
                    error_code=_first_param(params, "error"),
                )
            if pathname == "/register":
                if current_user.is_authenticated:
                    return build_user_page_layout()
                return build_register_layout(
                    next_path=_safe_next(_first_param(params, "next"), "/user"),
                    error_code=_first_param(params, "error"),
                )
            if pathname == "/admin":
                if not current_user.is_authenticated:
                    return build_login_layout(next_path="/admin")
                if not _is_admin():
                    return build_access_denied_layout()
                try:
                    users = list_users()
                except Exception:
                    logger.exception("admin_users_list_failed")
                    users = []
                    params["error"] = ["storage"]
                return build_admin_users_layout(
                    users,
                    status_code=_first_param(params, "status"),
                    error_code=_first_param(params, "error"),
                )
            if pathname == "/admin/imports":
                if not current_user.is_authenticated:
                    return build_login_layout(next_path="/admin/imports")
                if not _is_admin():
                    return build_access_denied_layout()
                try:
                    logs = list_pending_import_logs()
                except Exception:
                    logger.exception("admin_imports_list_failed")
                    logs = []
                    params["error"] = ["storage"]
                return build_admin_imports_layout(
                    logs,
                    status_code=_first_param(params, "status"),
                    error_code=_first_param(params, "error"),
                )
            if pathname == "/user":
                if not current_user.is_authenticated:
                    return build_login_layout(next_path="/user")
                return build_user_page_layout(
                    status_code=_first_param(params, "status"),
                    error_code=_first_param(params, "error"),
                    mode=_first_param(params, "mode"),
                )
            return build_home_layout()
        except DatabaseUnavailableError as exc:
            logger.warning(
                "database_unavailable_layout",
                extra={"path": pathname, "service": exc.service},
            )
            return build_database_unavailable_layout(exc)

    register_upload_callbacks(app)
    register_statistics_callbacks(app)
    register_spain_callbacks(app)
    register_home_callbacks(app)
    register_about_callbacks(app)
    return app


def _register_error_routes(app: Dash) -> None:
    @app.server.before_request
    def database_dependent_page_guard():
        if request.method != "GET":
            return None
        if request.path.rstrip("/") not in {"/statistics", "/stadistics"}:
            return None
        try:
            assert_analytics_databases_available()
        except DatabaseUnavailableError as exc:
            logger.warning(
                "database_unavailable_response",
                extra={"path": request.path, "service": exc.service},
            )
            return render_database_unavailable_response(exc)
        return None

    @app.server.errorhandler(DatabaseUnavailableError)
    def database_unavailable_error(error: DatabaseUnavailableError):
        logger.warning(
            "database_unavailable_error",
            extra={"path": request.path, "service": error.service},
        )
        return render_database_unavailable_response(error)


def _register_user_loader(login_manager: LoginManager) -> None:
    @login_manager.user_loader
    def load_user(user_id: str) -> SessionUser | None:
        try:
            record = get_user_record(user_id)
        except UserStorageError:
            logger.exception("user_loader_storage_error")
            return None
        if record is None:
            return None
        return _session_user_from_record(record)


def _register_auth_routes(app: Dash) -> None:
    rate_limiter = create_rate_limiter(
        max_attempts=int(os.getenv("AUTH_MAX_ATTEMPTS", "6")),
        window_seconds=int(os.getenv("AUTH_WINDOW_SECONDS", "300")),
        namespace="dash-auth",
    )

    @app.server.post("/auth/login")
    def login():
        next_path = _safe_next(request.form.get("next"), "/user")
        if not validate_csrf_token(request.form.get("csrf_token")):
            return _redirect("/login", error="csrf", next_path=next_path)

        email = request.form.get("email", "")
        password = request.form.get("password", "")
        rate_key = _rate_key(email)
        if rate_limiter.is_blocked(rate_key):
            return _redirect("/login", error="rate_limited", next_path=next_path)

        try:
            record = authenticate_user(email, password)
        except UserStorageError:
            logger.exception("login_storage_error")
            return _redirect("/login", error="storage", next_path=next_path)
        except Exception:
            logger.exception("login_failed")
            return _redirect("/login", error="storage", next_path=next_path)

        if record is None:
            rate_limiter.record_failure(rate_key)
            return _redirect("/login", error="invalid_credentials", next_path=next_path)

        login_user(_session_user_from_record(record), remember=False, fresh=True)
        rate_limiter.reset(rate_key)
        return redirect(next_path)

    @app.server.post("/auth/register")
    def register():
        next_path = _safe_next(request.form.get("next"), "/user")
        if not validate_csrf_token(request.form.get("csrf_token")):
            return _redirect("/register", error="csrf", next_path=next_path)

        rate_key = _rate_key(request.form.get("email"))
        if rate_limiter.is_blocked(rate_key):
            return _redirect("/register", error="rate_limited", next_path=next_path)

        try:
            payload = UserRegister.model_validate(
                {
                    "name": request.form.get("name", ""),
                    "email": request.form.get("email", ""),
                    "password": request.form.get("password", ""),
                    "organization": request.form.get("organization", ""),
                }
            )
        except ValidationError:
            rate_limiter.record_failure(rate_key)
            return _redirect("/register", error="invalid_payload", next_path=next_path)

        try:
            created_user = create_user(payload, role=UserRole.COMMON)
            record = get_user_record(created_user.id)
        except ValueError as exc:
            rate_limiter.record_failure(rate_key)
            return _redirect("/register", error=str(exc), next_path=next_path)
        except UserStorageError:
            logger.exception("register_storage_error")
            return _redirect("/register", error="storage", next_path=next_path)
        except Exception:
            logger.exception("register_failed")
            return _redirect("/register", error="storage", next_path=next_path)

        if record is None:
            return _redirect("/register", error="storage", next_path=next_path)

        login_user(_session_user_from_record(record), remember=False, fresh=True)
        rate_limiter.reset(rate_key)
        return redirect(next_path)

    @app.server.post("/auth/logout")
    def logout():
        if not validate_csrf_token(request.form.get("csrf_token")):
            return _redirect("/user", error="csrf")
        logout_user()
        return redirect("/")

    @app.server.post("/auth/profile")
    def profile():
        if not current_user.is_authenticated:
            return _redirect("/login", next_path="/user")
        if not validate_csrf_token(request.form.get("csrf_token")):
            return _redirect("/user", mode="edit", error="csrf")

        try:
            updated = update_user_profile(
                user_id=current_user.get_id(),
                username=request.form.get("username", ""),
                email=request.form.get("email", ""),
                current_password=request.form.get("current_password", ""),
                new_password=request.form.get("new_password", ""),
            )
        except ValueError as exc:
            return _redirect("/user", mode="edit", error=str(exc))
        except UserStorageError:
            logger.exception("profile_storage_error")
            return _redirect("/user", mode="edit", error="storage")
        except Exception:
            logger.exception("profile_update_failed")
            return _redirect("/user", mode="edit", error="storage")

        login_user(_session_user_from_record(updated), remember=False, fresh=True)
        return _redirect("/user", status="profile_updated")

    @app.server.post("/admin/users")
    def admin_users():
        if not current_user.is_authenticated:
            return _redirect("/login", next_path="/admin")
        if not _is_admin():
            return _redirect("/admin", error="access_denied")
        if not validate_csrf_token(request.form.get("csrf_token")):
            return _redirect("/admin", error="csrf")

        action = request.form.get("action")
        user_id = request.form.get("user_id", "")
        if action == "delete":
            if user_id == current_user.get_id():
                return _redirect("/admin", error="self_delete")
            try:
                delete_user_as_admin(user_id=user_id)
            except ValueError as exc:
                return _redirect("/admin", error=str(exc))
            except Exception:
                logger.exception("admin_user_delete_failed")
                return _redirect("/admin", error="storage")
            return _redirect("/admin", status="user_deleted")

        if action == "update":
            try:
                updated = update_user_as_admin(
                    user_id=user_id,
                    username=request.form.get("username", ""),
                    email=request.form.get("email", ""),
                    role=request.form.get("role", ""),
                    organization=request.form.get("organization", ""),
                )
            except ValueError as exc:
                return _redirect("/admin", error=str(exc))
            except Exception:
                logger.exception("admin_user_update_failed")
                return _redirect("/admin", error="storage")

            if updated.id == current_user.get_id():
                login_user(_session_user_from_record(updated), remember=False, fresh=True)
            return _redirect("/admin", status="user_updated")

        return _redirect("/admin", error="storage")

    @app.server.post("/admin/imports")
    def admin_imports():
        if not current_user.is_authenticated:
            return _redirect("/login", next_path="/admin/imports")
        if not _is_admin():
            return _redirect("/admin/imports", error="access_denied")
        if not validate_csrf_token(request.form.get("csrf_token")):
            return _redirect("/admin/imports", error="csrf")

        action = request.form.get("action")
        import_id = request.form.get("import_id", "")
        if action == "reject":
            try:
                delete_import_log(import_id)
            except ValueError as exc:
                return _redirect("/admin/imports", error=str(exc))
            except Exception:
                logger.exception("admin_import_reject_failed")
                return _redirect("/admin/imports", error="storage")
            return _redirect("/admin/imports", status="import_rejected")

        if action == "insert":
            try:
                pending_import = get_pending_import_log(import_id)
                if pending_import is None:
                    return _redirect("/admin/imports", error="import_not_found")
                _insert_approved_import(pending_import.file_json)
                invalidate_analytics_cache()
                delete_import_log(import_id)
            except ValueError as exc:
                return _redirect("/admin/imports", error=str(exc))
            except Exception:
                logger.exception("admin_import_insert_failed")
                return _redirect("/admin/imports", error="mongo")
            return _redirect("/admin/imports", status="import_inserted")

        return _redirect("/admin/imports", error="storage")


def _session_user_from_record(record: UserRecord) -> SessionUser:
    return SessionUser(
        id=record.id,
        username=record.username,
        email=record.email,
        role=record.role,
        organization=record.organization,
    )


def _insert_approved_import(file_json: dict | list) -> None:
    documents = file_json if isinstance(file_json, list) else [file_json]
    if not documents or not all(isinstance(document, dict) for document in documents):
        raise ValueError("invalid_json_payload")

    datasets = {document.get("dataset") for document in documents}
    sources = {document.get("source") for document in documents}
    if datasets == {"eu_lgbtiq_survey_iii"}:
        from app.import_to_db.fra import (
            insert_indicator_fra_json,
            upsert_indicators_from_json,
        )

        upsert_indicators_from_json(file_json)
        insert_indicator_fra_json(file_json)
        return
    if datasets == {"ilga_rainbow_map"}:
        from app.import_to_db.ilga import insert_indicator_ilga_json

        insert_indicator_ilga_json(file_json)
        return
    if sources == {"felgtbi_estado_lgtbi"}:
        from app.import_to_db.felgtbi import insert_indicator_felgtbi_json
        from app.import_to_db.fra import upsert_indicators_from_json

        upsert_indicators_from_json(file_json)
        insert_indicator_felgtbi_json(file_json)
        return
    raise ValueError("unsupported_import_dataset")


def _query_params(search: str | None) -> dict[str, list[str]]:
    if not search:
        return {}
    return parse_qs(search.lstrip("?"), keep_blank_values=False)


def _first_param(params: dict[str, list[str]], name: str) -> str | None:
    values = params.get(name)
    return values[0] if values else None


def _safe_next(value: str | None, default: str = "/user") -> str:
    if not value or not value.startswith("/") or value.startswith("//"):
        return default
    return value


def _is_admin() -> bool:
    role = getattr(current_user, "role", None)
    role_value = role.value if isinstance(role, UserRole) else str(role)
    return role_value == UserRole.ADMIN.value


def _redirect(path: str, **params: str | None):
    clean_params = {key: value for key, value in params.items() if value}
    query = f"?{urlencode(clean_params)}" if clean_params else ""
    return redirect(f"{path}{query}")


def _rate_key(email: str | None) -> str:
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "unknown")
    ip = ip.split(",")[0].strip()
    email_part = email.strip().lower() if isinstance(email, str) else ""
    return f"{ip}:{email_part}"
