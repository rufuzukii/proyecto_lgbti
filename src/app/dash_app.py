from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlencode, urlsplit

from dash import Dash, Input, Output, dcc, html
from flask import abort, redirect, request, send_file, session
from flask_login import LoginManager, UserMixin, current_user, login_user, logout_user
from pydantic import ValidationError

from app.analytics import invalidate_analytics_cache
from app.analytics.repository import assert_analytics_databases_available
from app.auth.csrf import rotate_csrf_token, validate_csrf_token
from app.auth.permissions import (
    Permission,
    can_access_docente_material,
    is_admin_user,
    user_has_permission,
)
from app.auth.rate_limit import create_rate_limiter
from app.cache import init_cache
from app.config import get_app_config
from app.dash.i18n import dash_attrs
from app.dash.layouts.about import build_about_layout, register_about_callbacks
from app.dash.layouts.error_page import (
    build_database_unavailable_layout,
    build_error_layout,
    render_database_unavailable_response,
    render_error_response,
)
from app.dash.layouts.home import build_home_layout, register_home_callbacks
from app.dash.layouts.user_page import build_user_page_layout, register_user_page_callbacks
from app.dash.pages.admin.imports import build_admin_imports_layout
from app.dash.pages.admin.users import (
    build_access_denied_layout,
    build_admin_users_layout,
)
from app.dash.pages.didactica import (
    build_access_denied_layout as build_didactica_access_denied_layout,
)
from app.dash.pages.didactica import (
    build_dictionary_layout,
    build_didactica_layout,
    build_docente_layout,
    build_games_layout,
    build_presentations_layout,
    build_progress_layout,
    register_didactica_callbacks,
)
from app.dash.pages.reports import (
    build_reports_access_denied_layout,
    build_reports_layout,
    register_reports_callbacks,
)
from app.dash.pages.session.account import (
    build_forgot_password_layout,
    build_reset_password_layout,
    build_verification_required_layout,
    build_verify_email_layout,
)
from app.dash.pages.session.login import build_login_layout
from app.dash.pages.session.register import build_register_layout
from app.dash.pages.spain import build_spain_layout, register_spain_callbacks
from app.dash.pages.statistics import (
    build_statistics_layout,
    register_statistics_callbacks,
)
from app.dash.pages.upload import (
    MAX_UPLOAD_REQUEST_BYTES,
    build_upload_layout,
    register_upload_callbacks,
)
from app.edu.teacher_service import generate_teacher_resource_pdf
from app.errors import DatabaseUnavailableError
from app.health import register_health_endpoint
from app.http_security import configure_flask_security, rate_limit_key
from app.import_to_db.import_log import (
    delete_import_log,
    get_pending_import_log,
    list_pending_import_logs,
)
from app.logging_config import configure_secure_logging
from app.mail.service import MailDeliveryError
from app.mongo_indexes import initialize_mongo_indexes
from app.trends import build_trends_layout, register_trend_callbacks
from app.users.account_emails import send_password_reset_email, send_verification_email
from app.users.account_security import (
    AccountSecurityStorageError,
    consume_security_token,
    issue_security_token,
    mark_email_verified,
    record_security_event,
)
from app.users.schemas import UserRegister, UserRole, UserType
from app.users.service import (
    UserRecord,
    UserStorageError,
    authenticate_user,
    create_user,
    delete_user_as_admin,
    get_user_record,
    get_user_record_by_email,
    list_users_page,
    set_user_active_as_admin,
    set_user_password,
    update_user_as_admin,
    update_user_profile,
)

logger = logging.getLogger(__name__)
SAFE_NEXT_PATHS = {
    "/",
    "/about",
    "/admin",
    "/admin/imports",
    "/informes",
    "/reports",
    "/spain",
    "/statistics",
    "/tendencias",
    "/upload",
    "/user",
    "/didactica",
    "/didactica/diccionario",
    "/didactica/presentaciones",
    "/didactica/juegos",
    "/didactica/docentes",
    "/didactica/progreso",
}

PUBLIC_PAGE_PATHS = {
    *SAFE_NEXT_PATHS,
    "/didactics",
    "/didactica/profesores",
    "/informes",
    "/login",
    "/register",
    "/forgot-password",
    "/reset-password",
    "/verify-email",
    "/report",
    "/stadistics",
}

DASH_INDEX_STRING = """
<!DOCTYPE html>
<html>
    <head>
        {%metas%}
        <title>{%title%}</title>
        <script>
            (function () {
                var theme = "light";
                try {
                    var savedTheme = window.localStorage.getItem("rainbowlens-theme");
                    if (savedTheme === "dark" || savedTheme === "light") {
                        theme = savedTheme;
                    }
                } catch (_error) {
                    /* Local storage may be unavailable in privacy-restricted contexts. */
                }
                document.documentElement.dataset.theme = theme;
                document.documentElement.style.colorScheme = theme;
            })();
        </script>
        <link rel="icon" href="/assets/img/rainbow_lens_icono.ico">
        {%css%}
    </head>
    <body>
        <script>
            document.body.dataset.theme = document.documentElement.dataset.theme || "light";
        </script>
        {%app_entry%}
        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
        </footer>
    </body>
</html>
"""


@dataclass
class SessionUser(UserMixin):
    id: str
    username: str | None
    email: str
    role: UserRole
    organization: str | None
    user_type: UserType | None = None
    active: bool = True
    email_verified: bool = True
    session_version: int = 0


def create_dash_app() -> Dash:
    _configure_application_logging()
    config = get_app_config()
    assets_path = Path(__file__).resolve().parent / "dash" / "assets"
    app = Dash(
        __name__,
        assets_folder=str(assets_path),
        suppress_callback_exceptions=True,
        serve_locally=True,
        title="RainbowLens Datahub",
    )
    app.index_string = DASH_INDEX_STRING
    app.server.config.update(
        SECRET_KEY=config.secret_key,
        MAX_CONTENT_LENGTH=MAX_UPLOAD_REQUEST_BYTES,
    )
    configure_flask_security(
        app.server,
        production=not config.local_mode,
        cookie_name="rainbowlens_session",
    )
    init_cache(app.server)
    register_health_endpoint(app.server)
    try:
        initialize_mongo_indexes()
    except Exception:
        logger.warning("mongo_index_initialization_failed", exc_info=True)
    _register_error_routes(app)

    login_manager = LoginManager()
    login_manager.session_protection = "strong"
    login_manager.init_app(app.server)
    _register_user_loader(login_manager)
    _register_auth_routes(app)
    _register_docente_routes(app)

    app.layout = html.Div(
        [
            dcc.Location(id="url"),
            dcc.Store(id="app-language-store", storage_type="local"),
            dcc.Interval(id="app-language-init", interval=150, max_intervals=1),
            html.Button(
                "",
                id="app-language-toggle",
                type="button",
                style={"display": "none"},
                **dash_attrs({"aria-hidden": "true"}),
            ),
            html.Div(id="page-content"),
            html.Footer(
                [
                    html.Strong("RainbowLens Datahub"),
                    html.Span(
                        "Versión 1.0.0",
                        **dash_attrs(
                            {
                                "data-i18n-es": "Versión 1.0.0",
                                "data-i18n-en": "Version 1.0.0",
                            }
                        ),
                    ),
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
            if pathname == "/tendencias":
                return build_trends_layout()
            if pathname == "/didactics":
                return dcc.Location(href="/didactica", id="legacy-didactica-redirect")
            if pathname == "/didactica":
                return build_didactica_layout()
            if pathname == "/didactica/diccionario":
                return build_dictionary_layout()
            if pathname == "/didactica/presentaciones":
                return build_presentations_layout(_first_param(params, "lesson"))
            if pathname == "/didactica/juegos":
                if not current_user.is_authenticated:
                    return build_login_layout(next_path="/didactica/juegos")
                if not user_has_permission(current_user, Permission.PLAY_EDU_GAMES):
                    return build_didactica_access_denied_layout()
                return build_games_layout(_first_param(params, "game"))
            if pathname == "/didactica/profesores":
                return dcc.Location(href="/didactica/docentes", id="legacy-docente-redirect")
            if pathname == "/didactica/docentes":
                if not current_user.is_authenticated:
                    return build_login_layout(next_path="/didactica/docentes")
                if not can_access_docente_material(current_user):
                    return build_didactica_access_denied_layout()
                if not _is_email_verified(current_user):
                    return build_verification_required_layout()
                return build_docente_layout()
            if pathname == "/didactica/progreso":
                if not current_user.is_authenticated:
                    return build_login_layout(next_path="/didactica/progreso")
                return build_progress_layout()
            if pathname in {"/informes", "/reports"}:
                if not current_user.is_authenticated:
                    requested_report = _safe_next(f"{pathname}{search or ''}", pathname)
                    return dcc.Location(
                        href=f"/login?{urlencode({'next': requested_report, 'notice': 'report_login_required'})}",
                        id="reports-login-redirect",
                    )
                if not _is_email_verified(current_user):
                    return build_verification_required_layout()
                if not user_has_permission(current_user, Permission.GENERATE_REPORTS):
                    return build_reports_access_denied_layout()
                return build_reports_layout(
                    _report_params(params),
                    default_language="en" if pathname == "/reports" else "es",
                )
            if pathname == "/report":
                return dcc.Location(href="/informes", id="legacy-reports-redirect")
            if pathname == "/stadistics":
                return dcc.Location(href="/statistics", id="legacy-statistics-redirect")
            if pathname == "/spain":
                return build_spain_layout()
            if pathname == "/upload":
                if not current_user.is_authenticated:
                    return build_login_layout(next_path="/upload")
                if not user_has_permission(current_user, Permission.UPLOAD_DATA):
                    return build_access_denied_layout()
                if not _is_email_verified(current_user):
                    return build_verification_required_layout()
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
                    notice_code=_first_param(params, "notice"),
                )
            if pathname == "/register":
                if current_user.is_authenticated:
                    return build_user_page_layout()
                return build_register_layout(
                    next_path=_safe_next(_first_param(params, "next"), "/user"),
                    error_code=_first_param(params, "error"),
                )
            if pathname == "/verify-email":
                return build_verify_email_layout(_first_param(params, "status"))
            if pathname == "/forgot-password":
                return build_forgot_password_layout(_first_param(params, "status"))
            if pathname == "/reset-password":
                return build_reset_password_layout(
                    _first_param(params, "token"),
                    status=_first_param(params, "status"),
                    error=_first_param(params, "error"),
                )
            if pathname == "/admin":
                if not current_user.is_authenticated:
                    return build_login_layout(next_path="/admin")
                if not _is_admin():
                    return build_access_denied_layout()
                try:
                    search = (_first_param(params, "q") or "").strip()[:120]
                    requested_page = _positive_int(_first_param(params, "page"), default=1)
                    user_page = list_users_page(search=search, page=requested_page)
                except Exception:
                    logger.exception("admin_users_list_failed")
                    search = ""
                    user_page = None
                    params["error"] = ["storage"]
                return build_admin_users_layout(
                    user_page.users if user_page is not None else [],
                    status_code=_first_param(params, "status"),
                    error_code=_first_param(params, "error"),
                    search=search,
                    page=user_page.page if user_page is not None else 1,
                    page_count=user_page.page_count if user_page is not None else 1,
                    total=user_page.total if user_page is not None else 0,
                    current_user_id=current_user.get_id(),
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
            if pathname in {None, "", "/"}:
                return build_home_layout()
            return build_error_layout("404")
        except DatabaseUnavailableError as exc:
            logger.warning(
                "database_unavailable_layout",
                extra={"path": pathname, "service": exc.service},
            )
            return build_database_unavailable_layout(exc)

    _register_client_preferences_callbacks(app)
    register_upload_callbacks(app)
    register_statistics_callbacks(app)
    register_trend_callbacks(app)
    register_reports_callbacks(app)
    register_spain_callbacks(app)
    register_home_callbacks(app)
    register_about_callbacks(app)
    register_didactica_callbacks(app)
    register_user_page_callbacks(app)
    return app


def _configure_application_logging() -> None:
    configure_secure_logging()


def _register_client_preferences_callbacks(app: Dash) -> None:
    app.clientside_callback(
        """
        function(initTick, nClicks) {
            const appState = window.RainbowLens || {};
            const state = appState.state || {};
            const i18n = appState.i18n || {};
            const theme = appState.theme || {};
            const config = appState.config || {};
            const ctx = window.dash_clientside.callback_context;
            const triggered = ctx.triggered && ctx.triggered.length ? ctx.triggered[0].prop_id : "";
            const isToggle =
                triggered.indexOf("app-language-toggle") === 0 &&
                Number.isFinite(nClicks) &&
                nClicks > 0;
            const persisted =
                typeof state.currentLanguage === "function"
                    ? state.currentLanguage()
                    : "es";
            const selected =
                isToggle && typeof state.nextLanguage === "function"
                    ? state.nextLanguage(persisted)
                    : persisted;
            if (config.LANGUAGE_KEY) {
                window.localStorage.setItem(config.LANGUAGE_KEY, selected);
            }
            if (typeof i18n.applyLanguage === "function") {
                i18n.applyLanguage(selected);
            }
            if (typeof theme.applyToggleLabels === "function" && typeof state.currentTheme === "function") {
                theme.applyToggleLabels(state.currentTheme(), selected);
            }
            return selected;
        }
        """,
        Output("app-language-store", "data"),
        Input("app-language-init", "n_intervals"),
        Input("app-language-toggle", "n_clicks"),
    )


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

    @app.server.before_request
    def unknown_page_guard():
        if request.method not in {"GET", "HEAD"}:
            return None
        path = request.path.rstrip("/") or "/"
        if request.url_rule is not None and request.url_rule.rule != "/<path:path>":
            return None
        if (
            path in PUBLIC_PAGE_PATHS
            or path == "/health"
            or path == "/_favicon.ico"
            or path == "/_reload-hash"
            or path.startswith(
                (
                    "/_dash",
                    "/assets/",
                    "/static/",
                    "/didactica/docentes/descargar/",
                    "/account/verify-email/",
                )
            )
        ):
            return None
        logger.info("unknown_page_requested", extra={"path": path})
        return render_error_response("404", language=_request_language())

    @app.server.errorhandler(DatabaseUnavailableError)
    def database_unavailable_error(error: DatabaseUnavailableError):
        logger.warning(
            "database_unavailable_error",
            extra={"path": request.path, "service": error.service},
        )
        return render_database_unavailable_response(error)

    @app.server.errorhandler(401)
    def authentication_required_error(_error: Exception):
        return render_error_response("401", language=_request_language())

    @app.server.errorhandler(403)
    def access_denied_error(_error: Exception):
        return render_error_response("403", language=_request_language())

    @app.server.errorhandler(404)
    def page_not_found_error(_error: Exception):
        return render_error_response("404", language=_request_language())

    @app.server.errorhandler(500)
    def internal_error(_error: Exception):
        logger.exception("unhandled_http_error", extra={"path": request.path})
        return render_error_response("500", language=_request_language())


def _register_user_loader(login_manager: LoginManager) -> None:
    @login_manager.user_loader
    def load_user(user_id: str) -> SessionUser | None:
        try:
            record = get_user_record(user_id)
        except UserStorageError:
            logger.exception("user_loader_storage_error")
            return None
        if record is None or not record.active:
            return None
        stored_version = session.get("_security_version")
        if stored_version is not None and stored_version != record.session_version:
            session.clear()
            return None
        session["_security_version"] = record.session_version
        return _session_user_from_record(record)


def _register_auth_routes(app: Dash) -> None:
    rate_limiter = create_rate_limiter(
        max_attempts=int(os.getenv("AUTH_MAX_ATTEMPTS", "6")),
        window_seconds=int(os.getenv("AUTH_WINDOW_SECONDS", "300")),
        namespace="dash-auth",
    )
    verification_limiter = create_rate_limiter(
        max_attempts=int(os.getenv("EMAIL_TOKEN_MAX_ATTEMPTS", "4")),
        window_seconds=int(os.getenv("EMAIL_TOKEN_WINDOW_SECONDS", "900")),
        namespace="email-verification",
    )
    recovery_limiter = create_rate_limiter(
        max_attempts=int(os.getenv("PASSWORD_RESET_MAX_ATTEMPTS", "4")),
        window_seconds=int(os.getenv("PASSWORD_RESET_WINDOW_SECONDS", "900")),
        namespace="password-reset",
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

        session.clear()
        session.permanent = True
        login_user(_session_user_from_record(record), remember=False, fresh=True)
        session["_security_version"] = record.session_version
        rotate_csrf_token()
        rate_limiter.reset(rate_key)
        return redirect(next_path)

    @app.server.post("/auth/register")
    def register():
        next_path = _safe_next(request.form.get("next"), "/user")
        if not validate_csrf_token(request.form.get("csrf_token")):
            return _redirect("/register", error="csrf", next_path=next_path)

        rate_key = _rate_key(request.form.get("email"), include_email=False)
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
        except ValueError:
            rate_limiter.record_failure(rate_key)
            return _redirect("/register", error="registration_failed", next_path=next_path)
        except UserStorageError:
            logger.exception("register_storage_error")
            return _redirect("/register", error="storage", next_path=next_path)
        except Exception:
            logger.exception("register_failed")
            return _redirect("/register", error="storage", next_path=next_path)

        delivery_status = "sent"
        try:
            verification_token = issue_security_token(
                created_user.id,
                "email_verification",
                ttl_seconds=int(os.getenv("EMAIL_VERIFICATION_TTL_SECONDS", "86400")),
            )
            send_verification_email(str(created_user.email or payload.email), verification_token)
        except (AccountSecurityStorageError, MailDeliveryError):
            logger.exception("verification_email_delivery_failed")
            delivery_status = "delivery_failed"
        rate_limiter.reset(rate_key)
        return _redirect("/verify-email", status=delivery_status)

    @app.server.get("/account/verify-email/<token>")
    def verify_email(token: str):
        try:
            user_id = consume_security_token(token, "email_verification")
            record = get_user_record(user_id or "") if user_id else None
            if record is None:
                return _redirect("/verify-email", status="invalid")
            mark_email_verified(record.id)
            try:
                record_security_event(record.id, "email_verified")
            except AccountSecurityStorageError:
                logger.exception("email_verification_audit_failed")
        except (AccountSecurityStorageError, UserStorageError):
            logger.exception("email_verification_failed")
            return _redirect("/verify-email", status="invalid")
        return _redirect("/verify-email", status="verified")

    @app.server.post("/auth/resend-verification")
    def resend_verification():
        if not validate_csrf_token(request.form.get("csrf_token")):
            return _redirect("/verify-email", status="sent")
        email = request.form.get("email", "")
        rate_key = rate_limit_key(subject=email.casefold()[:254], scope="email-verification")
        if not verification_limiter.is_blocked(rate_key):
            try:
                record = get_user_record_by_email(email)
                if record is not None and record.active and not record.email_verified:
                    token = issue_security_token(
                        record.id,
                        "email_verification",
                        ttl_seconds=int(os.getenv("EMAIL_VERIFICATION_TTL_SECONDS", "86400")),
                    )
                    send_verification_email(record.email, token)
                verification_limiter.record_failure(rate_key)
            except (AccountSecurityStorageError, MailDeliveryError, UserStorageError):
                logger.exception("verification_resend_failed")
        return _redirect("/verify-email", status="sent")

    @app.server.post("/auth/forgot-password")
    def forgot_password():
        if not validate_csrf_token(request.form.get("csrf_token")):
            return _redirect("/forgot-password", status="sent")
        email = request.form.get("email", "")
        rate_key = rate_limit_key(subject=email.casefold()[:254], scope="password-reset-request")
        if not recovery_limiter.is_blocked(rate_key):
            try:
                record = get_user_record_by_email(email)
                if record is not None and record.active:
                    token = issue_security_token(
                        record.id,
                        "password_reset",
                        ttl_seconds=int(os.getenv("PASSWORD_RESET_TTL_SECONDS", "3600")),
                    )
                    send_password_reset_email(record.email, token)
                recovery_limiter.record_failure(rate_key)
            except (AccountSecurityStorageError, MailDeliveryError, UserStorageError):
                logger.exception("password_reset_request_failed")
        return _redirect("/forgot-password", status="sent")

    @app.server.post("/auth/reset-password")
    def reset_password():
        token = request.form.get("token", "")
        if not validate_csrf_token(request.form.get("csrf_token")):
            return _redirect("/reset-password", token=token, error="invalid_token")
        password = request.form.get("password", "")
        confirmation = request.form.get("password_confirmation", "")
        if password != confirmation:
            return _redirect("/reset-password", token=token, error="password_mismatch")
        if not (12 <= len(password) <= 128):
            return _redirect("/reset-password", token=token, error="weak_password")
        rate_key = rate_limit_key(subject=token[:128], scope="password-reset-consume")
        if recovery_limiter.is_blocked(rate_key):
            return _redirect("/reset-password", error="invalid_token")
        try:
            user_id = consume_security_token(token, "password_reset")
            if not user_id:
                recovery_limiter.record_failure(rate_key)
                return _redirect("/reset-password", error="invalid_token")
            set_user_password(user_id=user_id, new_password=password)
        except (AccountSecurityStorageError, UserStorageError):
            logger.exception("password_reset_failed")
            return _redirect("/reset-password", error="storage")
        recovery_limiter.reset(rate_key)
        return _redirect("/reset-password", status="completed")

    @app.server.post("/auth/logout")
    def logout():
        if not validate_csrf_token(request.form.get("csrf_token")):
            return _redirect("/user", error="csrf")
        logout_user()
        session.clear()
        return redirect("/")

    @app.server.post("/auth/profile")
    def profile():
        if not current_user.is_authenticated:
            return _redirect("/login", next_path="/user")
        if not validate_csrf_token(request.form.get("csrf_token")):
            return _redirect("/user", mode="edit", error="csrf")

        previous_email = str(getattr(current_user, "email", "") or "").casefold()
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
        session["_security_version"] = updated.session_version
        rotate_csrf_token()
        if updated.email.casefold() != previous_email:
            delivery_status = "sent"
            try:
                token = issue_security_token(
                    updated.id,
                    "email_verification",
                    ttl_seconds=int(os.getenv("EMAIL_VERIFICATION_TTL_SECONDS", "86400")),
                )
                send_verification_email(updated.email, token)
            except (AccountSecurityStorageError, MailDeliveryError):
                logger.exception("profile_verification_email_failed")
                delivery_status = "delivery_failed"
            return _redirect("/verify-email", status=delivery_status)
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
        return_params = {
            "q": (request.form.get("q") or "")[:120] or None,
            "page": str(_positive_int(request.form.get("page"), default=1)),
        }
        if action == "delete":
            if user_id == current_user.get_id():
                return _redirect("/admin", error="self_delete", **return_params)
            try:
                delete_user_as_admin(
                    user_id=user_id,
                    actor_user_id=current_user.get_id(),
                )
            except ValueError as exc:
                return _redirect("/admin", error=str(exc), **return_params)
            except Exception:
                logger.exception("admin_user_delete_failed")
                return _redirect("/admin", error="storage", **return_params)
            return _redirect("/admin", status="user_deleted", **return_params)

        if action == "toggle_active":
            active = request.form.get("active") == "true"
            try:
                set_user_active_as_admin(
                    user_id=user_id,
                    active=active,
                    actor_user_id=current_user.get_id(),
                )
            except ValueError as exc:
                return _redirect("/admin", error=str(exc), **return_params)
            except UserStorageError:
                logger.exception("admin_user_activation_failed")
                return _redirect("/admin", error="storage", **return_params)
            return _redirect(
                "/admin",
                status="user_activated" if active else "user_deactivated",
                **return_params,
            )

        if action == "update":
            try:
                updated = update_user_as_admin(
                    user_id=user_id,
                    username=request.form.get("username", ""),
                    email=request.form.get("email", ""),
                    role=request.form.get("role", ""),
                    organization=request.form.get("organization", ""),
                    actor_user_id=current_user.get_id(),
                    expected_version=request.form.get("version"),
                )
            except ValueError as exc:
                return _redirect("/admin", error=str(exc), **return_params)
            except Exception:
                logger.exception("admin_user_update_failed")
                return _redirect("/admin", error="storage", **return_params)

            if updated.id == current_user.get_id():
                login_user(_session_user_from_record(updated), remember=False, fresh=True)
            return _redirect("/admin", status="user_updated", **return_params)

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
                if pending_import.file_json is None:
                    return _redirect("/admin/imports", error="invalid_json_payload")
                _insert_approved_import(
                    pending_import.file_json,
                    original_filename=pending_import.file_name,
                )
                invalidate_analytics_cache()
                delete_import_log(import_id)
            except ValueError as exc:
                return _redirect("/admin/imports", error=str(exc))
            except Exception:
                logger.exception("admin_import_insert_failed")
                return _redirect("/admin/imports", error="mongo")
            return _redirect("/admin/imports", status="import_inserted")

        return _redirect("/admin/imports", error="storage")


def _register_docente_routes(app: Dash) -> None:
    @app.server.get("/didactica/docentes/descargar/<resource_id>")
    def download_docente_resource_direct(resource_id: str):
        if not current_user.is_authenticated:
            return redirect(f"/login?{urlencode({'next': '/didactica/docentes'})}")
        if not can_access_docente_material(current_user):
            abort(403)
        if not _is_email_verified(current_user):
            abort(403)
        language = "en" if request.args.get("lang") == "en" else "es"
        try:
            payload, filename = generate_teacher_resource_pdf(resource_id, language)
        except ValueError:
            abort(404)
        return send_file(
            BytesIO(payload),
            mimetype="application/pdf",
            as_attachment=True,
            download_name=filename,
            max_age=0,
        )


def _session_user_from_record(record: UserRecord) -> SessionUser:
    return SessionUser(
        id=record.id,
        username=record.username,
        email=record.email,
        role=record.role,
        organization=record.organization,
        user_type=record.user_type,
        active=record.active,
        email_verified=record.email_verified,
        session_version=record.session_version,
    )


def _insert_approved_import(
    file_json: dict | list,
    *,
    original_filename: str | None = None,
) -> None:
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
        insert_indicator_felgtbi_json(file_json, original_filename=original_filename)
        return
    raise ValueError("unsupported_import_dataset")


def _query_params(search: str | None) -> dict[str, list[str]]:
    if not search:
        return {}
    return parse_qs(search.lstrip("?"), keep_blank_values=False)


def _request_language() -> str:
    explicit = (request.args.get("lang") or "").casefold()
    if explicit in {"es", "en"}:
        return explicit
    best = request.accept_languages.best_match(["es", "en"])
    return "en" if best == "en" else "es"


def _first_param(params: dict[str, list[str]], name: str) -> str | None:
    values = params.get(name)
    return values[0] if values else None


def _positive_int(value: str | None, *, default: int) -> int:
    try:
        return max(1, int(value or default))
    except (TypeError, ValueError):
        return default


def _report_params(params: dict[str, list[str]]) -> dict[str, object]:
    allowed = {
        "source",
        "category",
        "indicator_id",
        "indicator_label",
        "answer",
        "criterion",
        "year",
        "primary_country",
        "filter_a_name",
        "filter_a_value",
        "filter_b_name",
        "filter_b_value",
        "title",
        "organization",
        "author",
        "language",
        "mode",
        "detail_level",
        "generated_on",
    }
    values: dict[str, object] = {
        key: first for key in allowed if (first := _first_param(params, key)) is not None
    }
    for list_key in ("countries", "sections", "charts"):
        raw = _first_param(params, list_key)
        if raw:
            values[list_key] = [item.strip() for item in raw.split(",") if item.strip()]
    return values


def _safe_next(value: str | None, default: str = "/user") -> str:
    if not value or "\\" in value:
        return default
    parsed = urlsplit(value)
    decoded_path = unquote(parsed.path)
    if (
        parsed.scheme
        or parsed.netloc
        or parsed.fragment
        or decoded_path.startswith("//")
        or decoded_path not in SAFE_NEXT_PATHS
    ):
        return default
    return value


def _is_admin() -> bool:
    return is_admin_user(current_user)


def _is_email_verified(user: object) -> bool:
    return bool(getattr(user, "email_verified", True))


def _redirect(path: str, **params: str | None):
    clean_params = {key: value for key, value in params.items() if value}
    query = f"?{urlencode(clean_params)}" if clean_params else ""
    return redirect(f"{path}{query}")


def _rate_key(email: str | None, *, include_email: bool = True) -> str:
    email_part = email.strip().lower()[:254] if isinstance(email, str) else ""
    return rate_limit_key(
        subject=email_part if include_email else "",
        scope="login" if include_email else "registration",
    )
