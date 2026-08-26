from __future__ import annotations

from dash import dcc, html
from dash.development.base_component import Component

from app.auth.csrf import get_csrf_token
from app.dash.i18n import dash_attrs, text, text_attrs, ui_text_component
from app.dash.layouts.navigation import build_navbar
from app.dash.routes import route_path

ERROR_MESSAGES = {
    "invalid_credentials": (
        "El correo electrónico o la contraseña no son correctos.",
        "The email address or password is incorrect.",
    ),
    "invalid_payload": (
        "Introduce un correo electrónico y una contraseña válidos.",
        "Enter a valid email address and password.",
    ),
    "rate_limited": (
        "Se han realizado demasiados intentos. Inténtalo de nuevo en unos minutos.",
        "Too many attempts. Try again in a few minutes.",
    ),
    "csrf": (
        "La sesión ha caducado. Actualiza la página e inténtalo de nuevo.",
        "The session expired. Refresh the page and try again.",
    ),
    "storage": (
        "No ha sido posible iniciar sesión en este momento. Inténtalo de nuevo más tarde.",
        "Sign-in is not available right now. Please try again later.",
    ),
}


def build_login_layout(
    next_path: str | None = None,
    error_code: str | None = None,
    notice_code: str | None = None,
) -> Component:
    message = ERROR_MESSAGES.get(error_code) if error_code is not None else None
    notice = _notice(notice_code)

    return html.Div(
        [
            build_navbar(active="login"),
            html.Main(
                [
                    html.Section(
                        [
                            html.Div(
                                [
                                    html.P(
                                        "Acceso seguro",
                                        className="auth-eyebrow",
                                        **text_attrs("Acceso seguro", "Secure access"),
                                    ),
                                    html.H1(text("Iniciar sesión", "Sign in")),
                                    html.P(
                                        text(
                                            "Usa tu correo electrónico y contraseña para acceder a tu perfil.",
                                            "Use your email address and password to access your profile.",
                                        ),
                                        className="auth-copy",
                                    ),
                                    notice,
                                    _message(message, is_error=True),
                                    html.Form(
                                        [
                                            dcc.Input(
                                                type="hidden",
                                                name="csrf_token",
                                                value=get_csrf_token(),
                                            ),
                                            dcc.Input(
                                                type="hidden",
                                                name="next",
                                                value=next_path or route_path("profile"),
                                            ),
                                            dcc.Input(
                                                type="hidden",
                                                name="language",
                                                value="es",
                                                className="current-language-input",
                                            ),
                                            html.Label(
                                                "Correo electrónico",
                                                htmlFor="login-email",
                                                **text_attrs("Correo electrónico", "Email address"),
                                            ),
                                            dcc.Input(
                                                id="login-email",
                                                name="email",
                                                type="email",
                                                required=True,
                                                maxLength=254,
                                                autoComplete="email",
                                                className="auth-input",
                                            ),
                                            html.Label(
                                                "Contraseña",
                                                htmlFor="login-password",
                                                **text_attrs("Contraseña", "Password"),
                                            ),
                                            dcc.Input(
                                                id="login-password",
                                                name="password",
                                                type="password",
                                                required=True,
                                                maxLength=128,
                                                autoComplete="current-password",
                                                className="auth-input",
                                            ),
                                            html.Button(
                                                "Iniciar sesión",
                                                type="submit",
                                                className="auth-button",
                                                **text_attrs("Iniciar sesión", "Sign in"),
                                            ),
                                        ],
                                        action="/auth/login",
                                        method="post",
                                        className="auth-form",
                                    ),
                                    html.P(
                                        [
                                            html.Span(
                                                "¿No tienes cuenta? ",
                                                **text_attrs(
                                                    "¿No tienes cuenta? ", "Don't have an account? "
                                                ),
                                            ),
                                            html.A(
                                                "Crear cuenta",
                                                href=route_path("register"),
                                                **text_attrs("Crear cuenta", "Register"),
                                            ),
                                        ],
                                        className="auth-switch",
                                    ),
                                ],
                                className="auth-card app-surface",
                            )
                        ],
                        className="auth-shell app-page",
                    )
                ],
                className="page-shell",
            ),
        ]
    )


def _message(message: tuple[str, str] | None, *, is_error: bool) -> Component | str:
    if not message:
        return ""
    es, en = message
    class_name = (
        "auth-message auth-message-error" if is_error else "auth-message auth-message-success"
    )
    return html.Div(es, className=class_name, role="alert", **text_attrs(es, en))


def _notice(notice_code: str | None) -> Component | str:
    if notice_code == "account_created":
        message = (
            "Cuenta creada correctamente. Ya puedes iniciar sesión en RainbowLens DataHub.",
            "Account created successfully. You can now sign in to RainbowLens DataHub.",
        )
        content: Component | str = message[0]
        translated = text_attrs(*message)
    elif notice_code == "report_login_required":
        content = ui_text_component("report_login_required")
        translated = {}
    else:
        return ""
    return html.Div(
        content,
        className="auth-message auth-message-info auth-toast",
        role="status",
        **dash_attrs(
            {
                "aria-live": "polite",
                "data-auto-dismiss-ms": "5000",
                **translated,
            }
        ),
    )
