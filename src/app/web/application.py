from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

from dash import Dash, Input, Output, State, dcc, html
from dash.development.base_component import Component
from flask import abort, jsonify, redirect, request, send_file, session
from flask_login import LoginManager, UserMixin, current_user, login_user, logout_user
from pydantic import ValidationError

from app.core.auth.csrf import rotate_csrf_token, validate_csrf_token
from app.core.auth.permissions import (
    Permission,
    can_access_docente_material,
    is_admin_user,
    user_has_permission,
)
from app.core.auth.rate_limit import create_rate_limiter
from app.core.config import get_app_config
from app.core.dates import utc_today
from app.core.errors import DatabaseUnavailableError
from app.core.health import register_health_endpoint
from app.core.http_security import configure_flask_security, rate_limit_key
from app.core.logging import configure_secure_logging
from app.infrastructure.cache import init_cache
from app.infrastructure.mongo_indexes import initialize_mongo_indexes
from app.modules.account.login_page import build_login_layout
from app.modules.account.privacy.policy import get_privacy_policy_config
from app.modules.account.privacy.service import (
    AccountDeletionError,
    delete_user_account,
    delete_user_account_as_admin,
    personal_data_export_bytes,
)
from app.modules.account.privacy_page import build_account_deleted_layout, build_privacy_layout
from app.modules.account.profile_page import build_user_page_layout
from app.modules.account.register_page import build_register_layout
from app.modules.account.users.account_security import migrate_account_security_schema
from app.modules.account.users.schemas import UserRead, UserRegister, UserRole, UserType
from app.modules.account.users.service import (
    UserRecord,
    UserStorageError,
    authenticate_user,
    create_user,
    get_user_record,
    list_users_page,
    update_user_as_admin,
    update_user_profile,
)
from app.modules.administration.imports_page import build_admin_imports_layout
from app.modules.administration.upload_page import (
    MAX_UPLOAD_REQUEST_BYTES,
    build_upload_layout,
    register_upload_callbacks,
)
from app.modules.administration.users_page import (
    build_access_denied_layout,
    build_admin_users_layout,
    register_admin_users_callbacks,
)
from app.modules.didactics.custom_game_service import CustomGameAuthorizationError
from app.modules.didactics.page import (
    build_access_denied_layout as build_didactica_access_denied_layout,
)
from app.modules.didactics.page import (
    build_activity_editor_layout,
    build_custom_activity_layout,
    build_dictionary_layout,
    build_didactica_layout,
    build_docente_layout,
    build_games_layout,
    build_presentations_layout,
    build_public_activity_layout,
    build_word_search_layout,
    register_didactica_callbacks,
)
from app.modules.didactics.teacher_service import generate_teacher_resource_pdf
from app.modules.home.page import build_home_layout, register_home_callbacks
from app.modules.imports.import_log import (
    delete_import_log,
    get_pending_import_log,
    list_pending_import_logs,
)
from app.modules.reports.page import (
    build_reports_access_denied_layout,
    build_reports_layout,
    register_reports_callbacks,
)
from app.modules.spain.page import build_spain_layout, register_spain_callbacks
from app.modules.statistics.chart_export_runtime import log_chart_export_runtime
from app.modules.statistics.page import (
    build_statistics_layout,
    register_statistics_callbacks,
)
from app.modules.trends import build_trends_layout, register_trend_callbacks
from app.shared.components.source_attribution import build_footer_attributions
from app.shared.data import invalidate_analytics_cache
from app.shared.data.repository import assert_analytics_databases_available
from app.web.about import build_about_layout
from app.web.error_page import (
    build_database_unavailable_layout,
    build_error_layout,
    render_database_unavailable_response,
    render_error_response,
)
from app.web.i18n import dash_attrs, text_attrs, ui_text, ui_text_component
from app.web.routes import (
    PUBLIC_PAGE_PATHS,
    canonical_safe_next,
    client_route_config,
    language_from_path,
    legacy_redirect_target,
    localized_route_context,
    match_route,
    route_path,
)

logger = logging.getLogger(__name__)

DASH_INDEX_STRING = """
<!DOCTYPE html>
<html lang="es">
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
        <link rel="icon" type="image/png" href="/assets/img/rainbow_lens_icono.png?v=20260821">
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
    session_version: int = 0


def create_dash_app() -> Dash:
    _configure_application_logging()
    log_chart_export_runtime()
    config = get_app_config()
    assets_path = Path(__file__).resolve().parent / "assets"
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
    if _mongo_indexes_on_startup(config.local_mode):
        try:
            initialize_mongo_indexes()
        except Exception:
            logger.warning("mongo_index_initialization_failed", exc_info=True)
    else:
        try:
            migrate_account_security_schema()
        except Exception:
            logger.warning("account_security_migration_failed", exc_info=True)
        logger.info(
            "mongo_index_initialization_skipped run_with=python_-m_app.infrastructure.mongo_indexes"
        )
    _register_error_routes(app)

    login_manager = LoginManager()
    login_manager.session_protection = "strong"
    login_manager.init_app(app.server)
    _register_user_loader(login_manager)
    _register_auth_routes(app)
    _register_privacy_routes(app)
    _register_docente_routes(app)

    app.layout = _build_application_shell

    @app.callback(
        Output("page-content", "children"),
        Input("url", "pathname"),
        Input("url", "search"),
        State("statistics-selection", "data"),
    )
    def display_page(pathname: str | None, search: str | None, statistics_selection=None):
        params = _query_params(search)
        legacy_target = legacy_redirect_target(pathname)
        if legacy_target:
            return dcc.Location(
                href=f"{legacy_target}{search or ''}",
                id="localized-route-redirect",
                refresh=True,
            )
        route = match_route(pathname)
        if route is None:
            language = language_from_path(pathname)
            with localized_route_context(language):
                return build_error_layout("404", language=language)
        try:
            if route.public_id:
                params = {**params, "public_id": [route.public_id]}
            with localized_route_context(route.language):
                if route.route_id == "statistics" and statistics_selection:
                    return build_statistics_layout(statistics_selection)
                return _build_page_for_route(route.route_id, route.language, params, search)
        except DatabaseUnavailableError as exc:
            logger.warning(
                "database_unavailable_layout",
                extra={"path": pathname, "service": exc.service},
            )
            with localized_route_context(route.language):
                return build_database_unavailable_layout(exc)

    _register_client_preferences_callbacks(app)
    register_upload_callbacks(app)
    register_statistics_callbacks(app)
    register_trend_callbacks(app)
    register_reports_callbacks(app)
    register_spain_callbacks(app)
    register_home_callbacks(app)
    register_didactica_callbacks(app)
    register_admin_users_callbacks(app)
    return app


def _build_page_for_route(
    route_id: str,
    language: str,
    params: dict[str, list[str]],
    search: str | None,
) -> Component:
    if route_id == "home":
        return build_home_layout()
    if route_id == "privacy":
        return build_privacy_layout()
    if route_id == "privacy_deleted":
        return build_account_deleted_layout()
    if route_id == "statistics":
        return build_statistics_layout()
    if route_id == "trends":
        return build_trends_layout()
    if route_id == "spain":
        return build_spain_layout()
    if route_id == "about":
        return build_about_layout()
    if route_id == "didactica":
        return build_didactica_layout(_first_param(params, "notice"))
    if route_id == "dictionary":
        return build_dictionary_layout()
    if route_id == "presentations":
        return build_presentations_layout()
    if route_id == "word_search":
        return build_word_search_layout()
    if route_id == "games":
        if not user_has_permission(current_user, Permission.PLAY_EDU_GAMES):
            return build_didactica_access_denied_layout()
        return build_games_layout(_first_param(params, "game"))
    if route_id == "educators":
        if not current_user.is_authenticated:
            return build_login_layout(next_path=route_path("educators", language))
        if not can_access_docente_material(current_user):
            return dcc.Location(
                href=f"{route_path('didactica', language)}?notice=docente_required",
                id="educator-access-denied-redirect",
                refresh=True,
            )
        return build_docente_layout()
    if route_id == "educator_create":
        if not current_user.is_authenticated:
            return build_login_layout(
                next_path=f"{route_path('educator_create', language)}{search or ''}"
            )
        if not can_access_docente_material(current_user):
            return dcc.Location(
                href=f"{route_path('didactica', language)}?notice=docente_required",
                id="educator-create-access-denied-redirect",
                refresh=True,
            )
        try:
            return build_activity_editor_layout(
                _first_param(params, "id"), _first_param(params, "type")
            )
        except CustomGameAuthorizationError:
            return dcc.Location(
                href=f"{route_path('didactica', language)}?notice=docente_required",
                id="educator-editor-owner-denied-redirect",
                refresh=True,
            )
    if route_id == "educator_activity":
        activity_path = route_path("educator_activity", language)
        if not current_user.is_authenticated:
            return build_login_layout(next_path=f"{activity_path}{search or ''}")
        if not can_access_docente_material(current_user):
            return dcc.Location(
                href=f"{route_path('didactica', language)}?notice=docente_required",
                id="educator-activity-access-denied-redirect",
                refresh=True,
            )
        try:
            return build_custom_activity_layout(_first_param(params, "id"))
        except CustomGameAuthorizationError:
            return dcc.Location(
                href=f"{route_path('didactica', language)}?notice=docente_required",
                id="educator-activity-owner-denied-redirect",
                refresh=True,
            )
    if route_id == "educator_public_activity":
        return build_public_activity_layout(_first_param(params, "public_id"))
    if route_id == "reports":
        if not user_has_permission(current_user, Permission.GENERATE_REPORTS):
            return build_reports_access_denied_layout()
        return build_reports_layout(_report_params(params), default_language=language)
    if route_id == "upload":
        if not current_user.is_authenticated:
            return build_login_layout(next_path=route_path("upload", language))
        if not user_has_permission(current_user, Permission.UPLOAD_DATA):
            return build_access_denied_layout()
        return build_upload_layout()
    if route_id == "login":
        if current_user.is_authenticated:
            return build_user_page_layout(
                status_code=_first_param(params, "status"),
                error_code=_first_param(params, "error"),
                mode=_first_param(params, "mode"),
                privacy_error=_first_param(params, "privacy_error"),
            )
        return build_login_layout(
            next_path=_safe_next(_first_param(params, "next"), route_path("profile", language)),
            error_code=_first_param(params, "error"),
            notice_code=_first_param(params, "notice"),
        )
    if route_id == "register":
        if current_user.is_authenticated:
            return build_user_page_layout()
        return build_register_layout(
            next_path=_safe_next(_first_param(params, "next"), route_path("profile", language)),
            error_code=_first_param(params, "error"),
        )
    if route_id == "admin":
        if not current_user.is_authenticated:
            return build_login_layout(next_path=route_path("admin", language))
        if not _is_admin():
            return build_access_denied_layout()
        try:
            query = (_first_param(params, "q") or "").strip()[:120]
            requested_page = _positive_int(_first_param(params, "page"), default=1)
            user_page = list_users_page(search=query, page=requested_page)
        except Exception:
            logger.exception("admin_users_list_failed")
            query = ""
            user_page = None
            params["error"] = ["storage"]
        return build_admin_users_layout(
            user_page.users if user_page is not None else [],
            status_code=_first_param(params, "status"),
            error_code=_first_param(params, "error"),
            search=query,
            page=user_page.page if user_page is not None else 1,
            page_count=user_page.page_count if user_page is not None else 1,
            total=user_page.total if user_page is not None else 0,
            current_user_id=current_user.get_id(),
        )
    if route_id == "admin_imports":
        if not current_user.is_authenticated:
            return build_login_layout(next_path=route_path("admin_imports", language))
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
    if route_id == "profile":
        if not current_user.is_authenticated:
            return build_login_layout(next_path=route_path("profile", language))
        return build_user_page_layout(
            status_code=_first_param(params, "status"),
            error_code=_first_param(params, "error"),
            mode=_first_param(params, "mode"),
            privacy_error=_first_param(params, "privacy_error"),
        )
    return build_error_layout("404", language=language)


def _build_application_shell() -> Component:
    config = get_privacy_policy_config()
    footer_links: list[Component] = [
        dcc.Link(
            ui_text_component("privacy_title"),
            href=route_path("privacy"),
            refresh=False,
            className="site-footer-link site-footer-link--privacy",
        )
    ]
    footer_links.append(
        html.A(
            config.contact_email,
            href=f"mailto:{config.contact_email}",
            className="site-footer-link",
        )
    )
    return html.Div(
        [
            dcc.Location(id="url", refresh="callback-nav"),
            dcc.Store(id="app-language-store", storage_type="local"),
            dcc.Store(id="statistics-selection", storage_type="session"),
            dcc.Store(id="app-route-config", data=client_route_config()),
            dcc.Interval(id="app-language-init", interval=150, max_intervals=1),
            html.Button(
                "",
                id="app-language-toggle",
                type="button",
                style={"display": "none"},
                **dash_attrs({"aria-hidden": "true"}),
            ),
            html.A(
                "Saltar al contenido",
                href="#page-content",
                className="skip-link",
                **text_attrs("Saltar al contenido", "Skip to content"),
            ),
            html.Div(id="page-content"),
            html.Footer(
                [
                    build_footer_attributions(),
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.Strong("RainbowLens DataHub"),
                                    html.Span(
                                        "Versión 1.0.0",
                                        **text_attrs("Versión 1.0.0", "Version 1.0.0"),
                                    ),
                                ],
                                className="site-footer-brand",
                            ),
                            html.Nav(
                                footer_links,
                                className="site-footer-links",
                                **dash_attrs(
                                    {
                                        "aria-label": "Enlaces de privacidad y contacto",
                                        "data-i18n-aria-label-es": (
                                            "Enlaces de privacidad y contacto"
                                        ),
                                        "data-i18n-aria-label-en": ("Privacy and contact links"),
                                    }
                                ),
                            ),
                            html.Span(
                                ui_text("footer_copyright", "es").format(year=utc_today().year),
                                className="site-footer-copyright",
                                **text_attrs(
                                    ui_text("footer_copyright", "es").format(year=utc_today().year),
                                    ui_text("footer_copyright", "en").format(year=utc_today().year),
                                ),
                            ),
                        ],
                        className="site-footer-bottom",
                    ),
                ],
                className="site-footer",
            ),
        ],
        className="app-shell",
    )


def _configure_application_logging() -> None:
    configure_secure_logging()


def _register_client_preferences_callbacks(app: Dash) -> None:
    app.clientside_callback(
        """
        function(initTick, nClicks, pathname, search, hash, routeConfig) {
            // Match the central route helper's trailing-slash normalization before lookup.
            pathname = (pathname || "/").replace(/[/]+$/, "") || "/";
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
            const inferred =
                pathname === "/en" || (typeof pathname === "string" && pathname.indexOf("/en/") === 0)
                    ? "en"
                    : pathname === "/es" || (typeof pathname === "string" && pathname.indexOf("/es/") === 0)
                        ? "es"
                        : persisted;
            const selected = isToggle && typeof state.nextLanguage === "function"
                ? state.nextLanguage(inferred)
                : inferred;
            appState.routes = routeConfig || {routes: {}, pathIndex: {}};
            if (config.LANGUAGE_KEY) {
                window.localStorage.setItem(config.LANGUAGE_KEY, selected);
            }
            if (typeof i18n.applyLanguage === "function") {
                i18n.applyLanguage(selected);
            }
            if (typeof theme.applyToggleLabels === "function" && typeof state.currentTheme === "function") {
                theme.applyToggleLabels(state.currentTheme(), selected);
            }
            let nextHref = window.dash_clientside.no_update;
            if (isToggle && routeConfig && routeConfig.pathIndex && routeConfig.routes) {
                let routeId = routeConfig.pathIndex[pathname];
                let dynamicSuffix = "";
                if (!routeId && Array.isArray(routeConfig.dynamicRouteIds)) {
                    routeId = routeConfig.dynamicRouteIds.find(function(candidate) {
                        const candidateRoute = routeConfig.routes[candidate];
                        const base = candidateRoute && candidateRoute[inferred];
                        if (base && typeof pathname === "string" && pathname.indexOf(base + "/") === 0) {
                            dynamicSuffix = pathname.slice(base.length);
                            return true;
                        }
                        return false;
                    });
                }
                const route = routeConfig.routes[routeId];
                if (route && route[selected]) {
                    nextHref = route[selected] + dynamicSuffix + (search || "") + (hash || "");
                }
            }
            return [selected, nextHref];
        }
        """,
        Output("app-language-store", "data"),
        Output("url", "href"),
        Input("app-language-init", "n_intervals"),
        Input("app-language-toggle", "n_clicks"),
        Input("url", "pathname"),
        Input("url", "search"),
        Input("url", "hash"),
        State("app-route-config", "data"),
    )


def _register_error_routes(app: Dash) -> None:
    @app.server.before_request
    def legacy_page_redirect():
        if request.method not in {"GET", "HEAD"}:
            return None
        target = legacy_redirect_target(request.path)
        if target is None:
            return None
        query = f"?{request.query_string.decode('utf-8')}" if request.query_string else ""
        return redirect(f"{target}{query}", code=302)

    @app.server.before_request
    def database_dependent_page_guard():
        if request.method != "GET":
            return None
        route = match_route(request.path)
        target = legacy_redirect_target(request.path)
        if route is None and target:
            route = match_route(target)
        if route is None or route.route_id != "statistics":
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
            or match_route(path) is not None
            or path == "/health"
            or path == "/_favicon.ico"
            or path == "/_reload-hash"
            or path.startswith(
                (
                    "/_dash",
                    "/assets/",
                    "/static/",
                    "/didactica/docentes/descargar/",
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
            created = create_user(payload, role=UserRole.COMMON)
        except ValueError as exc:
            rate_limiter.record_failure(rate_key)
            if str(exc) == "email_exists":
                return _redirect("/register", error="email_exists", next_path=next_path)
            return _redirect("/register", error="registration_failed", next_path=next_path)
        except UserStorageError:
            logger.exception("register_storage_error")
            return _redirect("/register", error="storage", next_path=next_path)
        except Exception:
            logger.exception("register_failed")
            return _redirect("/register", error="storage", next_path=next_path)

        session.clear()
        session.permanent = True
        login_user(_session_user_from_record(created), remember=False, fresh=True)
        session["_security_version"] = created.session_version
        rotate_csrf_token()
        rate_limiter.reset(rate_key)
        return redirect(next_path)

    @app.server.post("/auth/logout")
    def logout():
        if not validate_csrf_token(request.form.get("csrf_token")):
            return _redirect("/user", error="csrf")
        logout_user()
        session.clear()
        return _redirect("/")

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
        session["_security_version"] = updated.session_version
        rotate_csrf_token()
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
                delete_user_account_as_admin(
                    user_id=user_id,
                    actor_user_id=current_user.get_id(),
                )
            except (ValueError, AccountDeletionError) as exc:
                error_code = exc.code if isinstance(exc, AccountDeletionError) else str(exc)
                return _redirect("/admin", error=error_code, **return_params)
            except Exception:
                logger.exception("admin_user_delete_failed")
                return _redirect("/admin", error="storage", **return_params)
            return _redirect("/admin", status="user_deleted", **return_params)

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
                if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                    return jsonify({"ok": False, "error": str(exc)}), 400
                return _redirect("/admin", error=str(exc), **return_params)
            except Exception:
                logger.exception("admin_user_update_failed")
                if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                    return jsonify({"ok": False, "error": "storage"}), 503
                return _redirect("/admin", error="storage", **return_params)

            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                role = updated.user_type or updated.role
                return jsonify(
                    {
                        "ok": True,
                        "user": {
                            "id": updated.id,
                            "username": updated.username or "",
                            "email": updated.email or "",
                            "organization": (
                                ""
                                if updated.organization in {"No organization", "Sin organización"}
                                else (updated.organization or "")
                            ),
                            "role": role.value,
                            "version": updated.version,
                        },
                    }
                )
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
                imported_source = _insert_approved_import(
                    pending_import.file_json,
                    original_filename=pending_import.file_name,
                )
                invalidate_analytics_cache(imported_source)
                delete_import_log(import_id)
            except ValueError as exc:
                return _redirect("/admin/imports", error=str(exc))
            except Exception:
                logger.exception("admin_import_insert_failed")
                return _redirect("/admin/imports", error="mongo")
            return _redirect("/admin/imports", status="import_inserted")

        return _redirect("/admin/imports", error="storage")


def _register_privacy_routes(app: Dash) -> None:
    deletion_limiter = create_rate_limiter(
        max_attempts=max(1, int(os.getenv("PRIVACY_DELETE_MAX_ATTEMPTS", "5"))),
        window_seconds=max(300, int(os.getenv("PRIVACY_DELETE_WINDOW_SECONDS", "3600"))),
        namespace="privacy-delete",
    )
    export_limiter = create_rate_limiter(
        max_attempts=max(1, int(os.getenv("PRIVACY_EXPORT_MAX_ATTEMPTS", "10"))),
        window_seconds=max(300, int(os.getenv("PRIVACY_EXPORT_WINDOW_SECONDS", "3600"))),
        namespace="privacy-export",
    )

    @app.server.post("/privacy/delete-account")
    def privacy_delete_account():
        if not current_user.is_authenticated:
            return _redirect("/login", next_path="/user")
        if not validate_csrf_token(request.form.get("csrf_token")):
            return _redirect("/user", mode="privacy", privacy_error="csrf")

        user_id = current_user.get_id() or ""
        limiter_key = rate_limit_key(subject=user_id, scope="privacy-delete")
        if deletion_limiter.is_blocked(limiter_key):
            return _redirect("/user", mode="privacy", privacy_error="rate_limited")
        language = "en" if request.form.get("language") == "en" else "es"
        try:
            outcome = delete_user_account(
                user_id=user_id,
                email=request.form.get("email", ""),
                password=request.form.get("password", ""),
                confirmation_checked=(request.form.get("confirmation_checked") or "").casefold()
                in {"1", "on", "true", "yes"},
                confirmation_text=request.form.get("confirmation_text", ""),
                language=language,
            )
        except AccountDeletionError as exc:
            deletion_limiter.record_failure(limiter_key)
            return _redirect("/user", mode="privacy", privacy_error=exc.code)
        except Exception:
            logger.exception("privacy_account_deletion_route_failed")
            deletion_limiter.record_failure(limiter_key)
            return _redirect("/user", mode="privacy", privacy_error="deletion_incomplete")

        deletion_limiter.reset(limiter_key)
        if outcome.status not in {"completed", "already_deleted"}:
            return _redirect("/user", mode="privacy", privacy_error="deletion_incomplete")
        logout_user()
        session.clear()
        response = _redirect("/privacidad/cuenta-eliminada")
        response.delete_cookie(app.server.config["SESSION_COOKIE_NAME"], path="/")
        return response

    @app.server.post("/privacy/export")
    def privacy_export():
        if not current_user.is_authenticated:
            return _redirect("/login", next_path="/user")
        if not validate_csrf_token(request.form.get("csrf_token")):
            return _redirect("/user", error="csrf")

        user_id = current_user.get_id() or ""
        limiter_key = rate_limit_key(subject=user_id, scope="privacy-export")
        if export_limiter.is_blocked(limiter_key):
            return _redirect("/user", mode="privacy", privacy_error="rate_limited")
        try:
            payload = personal_data_export_bytes(user_id)
        except Exception:
            logger.exception("privacy_data_export_failed")
            export_limiter.record_failure(limiter_key)
            return _redirect("/user", mode="privacy", privacy_error="export_failed")
        export_limiter.reset(limiter_key)
        response = send_file(
            BytesIO(payload),
            mimetype="application/json",
            as_attachment=True,
            download_name="rainbowlens-mis-datos.json",
            max_age=0,
        )
        response.headers["Cache-Control"] = "no-store, max-age=0"
        return response


def _register_docente_routes(app: Dash) -> None:
    @app.server.get("/didactica/docentes/descargar/<resource_id>")
    def download_docente_resource_direct(resource_id: str):
        if not can_access_docente_material(current_user):
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


def _session_user_from_record(record: UserRecord | UserRead) -> SessionUser:
    return SessionUser(
        id=record.id,
        username=record.username,
        email=record.email or "",
        role=record.role,
        organization=record.organization,
        user_type=record.user_type,
        active=record.active,
        session_version=record.session_version,
    )


def _insert_approved_import(
    file_json: dict | list,
    *,
    original_filename: str | None = None,
) -> str:
    documents = file_json if isinstance(file_json, list) else [file_json]
    if not documents or not all(isinstance(document, dict) for document in documents):
        raise ValueError("invalid_json_payload")

    datasets = {document.get("dataset") for document in documents}
    sources = {document.get("source") for document in documents}
    from app.shared.data.fra_surveys import FRA_SURVEYS

    fra_dataset_codes = {survey.dataset_code for survey in FRA_SURVEYS if survey.enabled}
    if len(datasets) == 1 and datasets.issubset(fra_dataset_codes):
        from app.modules.imports.fra import (
            insert_indicator_fra_json,
            resolve_and_upsert_indicators_from_json,
        )

        resolved, _resolutions = resolve_and_upsert_indicators_from_json(file_json)
        insert_indicator_fra_json(resolved)
        return "fra"
    if datasets == {"ilga_rainbow_map"}:
        from app.modules.imports.ilga import insert_indicator_ilga_json

        insert_indicator_ilga_json(file_json)
        return "ilga"
    if sources == {"felgtbi_estado_lgtbi"}:
        from app.modules.imports.felgtbi import insert_indicator_felgtbi_json

        # Spain reads report sections from MongoDB; these are not FRA survey
        # indicators and must not enter its relational catalog or validation.
        insert_indicator_felgtbi_json(file_json, original_filename=original_filename)
        return "felgtbi"
    raise ValueError("unsupported_import_dataset")


def _query_params(search: str | None) -> dict[str, list[str]]:
    if not search:
        return {}
    return parse_qs(search.lstrip("?"), keep_blank_values=False)


def _request_language() -> str:
    explicit = (request.args.get("lang") or "").casefold()
    if explicit in {"es", "en"}:
        return explicit
    path_language = language_from_path(request.path, fallback="")
    if request.path == "/es" or request.path.startswith("/es/"):
        return path_language
    if request.path == "/en" or request.path.startswith("/en/"):
        return path_language
    best = request.accept_languages.best_match(["es", "en"])
    return "en" if best == "en" else "es"


def _first_param(params: dict[str, list[str]], name: str) -> str | None:
    values = params.get(name)
    return values[0] if values else None


def _positive_int(value: str | None, *, default: int) -> int:
    try:
        return max(1, int(value or default))
    except TypeError, ValueError:
        return default


def _mongo_indexes_on_startup(local_mode: bool) -> bool:
    configured = os.getenv("MONGO_ENSURE_INDEXES_ON_STARTUP")
    if configured is None:
        return local_mode
    return configured.strip().casefold() in {"1", "true", "yes", "on"}


def _report_params(params: dict[str, list[str]]) -> dict[str, object]:
    allowed = {
        "source",
        "category",
        "indicator_id",
        "indicator_label",
        "answer",
        "criterion",
        "objective",
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
    }
    values: dict[str, object] = {
        key: first for key in allowed if (first := _first_param(params, key)) is not None
    }
    for list_key in ("countries",):
        raw = _first_param(params, list_key)
        if raw:
            values[list_key] = [item.strip() for item in raw.split(",") if item.strip()]
    return values


def _safe_next(value: str | None, default: str = "/es/perfil") -> str:
    return canonical_safe_next(value) or default


def _is_admin() -> bool:
    return is_admin_user(current_user)


def _redirect(path: str, **params: str | None):
    clean_params = {key: value for key, value in params.items() if value}
    next_path = clean_params.pop("next_path", None)
    language = _navigation_language(next_path)
    if next_path:
        next_target = legacy_redirect_target(next_path) or next_path
        next_route = match_route(next_target)
        clean_params["next"] = (
            route_path(next_route.route_id, language) if next_route else next_path
        )
    target = legacy_redirect_target(path) or path
    route = match_route(target)
    if route is not None:
        target = route_path(route.route_id, language)
    query = f"?{urlencode(clean_params)}" if clean_params else ""
    return redirect(f"{target}{query}")


def _navigation_language(next_path: str | None = None) -> str:
    candidates = (
        next_path,
        request.form.get("next"),
        request.args.get("next"),
        request.referrer,
    )
    for candidate in candidates:
        if not candidate:
            continue
        path = urlsplit(candidate).path
        if path == "/en" or path.startswith("/en/"):
            return "en"
        if path == "/es" or path.startswith("/es/"):
            return "es"
    explicit = (request.form.get("language") or request.args.get("lang") or "").casefold()
    return "en" if explicit == "en" else "es"


def _rate_key(email: str | None, *, include_email: bool = True) -> str:
    email_part = email.strip().lower()[:254] if isinstance(email, str) else ""
    return rate_limit_key(
        subject=email_part if include_email else "",
        scope="login" if include_email else "registration",
    )
