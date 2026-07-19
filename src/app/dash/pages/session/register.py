from __future__ import annotations

from app.auth.csrf import get_csrf_token
from app.dash.compat import dcc, html
from app.dash.i18n import text, text_attrs
from app.dash.layouts.navigation import build_navbar


ERROR_MESSAGES = {
    "invalid_payload": ("Introduce un nombre, correo electrónico y contraseña válidos.", "Enter a valid name, email address, and password."),
    "email_exists": ("Ese correo electrónico ya está registrado.", "That email address is already registered."),
    "rate_limited": ("Se han realizado demasiados intentos. Inténtalo de nuevo en unos minutos.", "Too many attempts. Try again in a few minutes."),
    "csrf": ("La sesión ha caducado. Actualiza la página e inténtalo de nuevo.", "The session expired. Refresh the page and try again."),
    "storage": ("No ha sido posible crear la cuenta en este momento. Inténtalo de nuevo más tarde.", "Registration is not available right now. Please try again later."),
}


def build_register_layout(
    next_path: str = "/user",
    error_code: str | None = None,
) -> html.Div:
    message = ERROR_MESSAGES.get(error_code)

    return html.Div(
        [
            build_navbar(active="register"),
            html.Main(
                [
                    html.Section(
                        [
                            html.Div(
                                [
                                    html.P("Crear acceso", className="auth-eyebrow", **text_attrs("Crear acceso", "Create access")),
                                    html.H1(text("Crear cuenta", "Register")),
                                    html.P(
                                        text(
                                            "Crea tu cuenta con tu nombre, correo electrónico y contraseña.",
                                            "Create your account with your name, email address, and password.",
                                        ),
                                        className="auth-copy",
                                    ),
                                    _message(message),
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
                                                value=next_path,
                                            ),
                                            html.Label("Nombre visible", htmlFor="register-name", **text_attrs("Nombre visible", "Display name")),
                                            dcc.Input(
                                                id="register-name",
                                                name="name",
                                                type="text",
                                                required=True,
                                                className="auth-input",
                                            ),
                                            html.P(
                                                text(
                                                    "El nombre visible debe tener entre 2 y 80 caracteres.",
                                                    "Display name must be between 2 and 80 characters.",
                                                ),
                                                className="auth-help",
                                            ),
                                            html.Label("Correo electrónico", htmlFor="register-email", **text_attrs("Correo electrónico", "Email address")),
                                            dcc.Input(
                                                id="register-email",
                                                name="email",
                                                type="email",
                                                required=True,
                                                className="auth-input",
                                            ),
                                            html.Label("Organización", htmlFor="register-organization", **text_attrs("Organización", "Organization")),
                                            dcc.Input(
                                                id="register-organization",
                                                name="organization",
                                                type="text",
                                                placeholder="Sin organización",
                                                className="auth-input",
                                            ),
                                            html.P(
                                                text(
                                                    "La organización puede tener hasta 120 caracteres.",
                                                    "Organization can be up to 120 characters.",
                                                ),
                                                className="auth-help",
                                            ),
                                            html.Label("Contraseña", htmlFor="register-password", **text_attrs("Contraseña", "Password")),
                                            dcc.Input(
                                                id="register-password",
                                                name="password",
                                                type="password",
                                                required=True,
                                                className="auth-input",
                                            ),
                                            html.P(
                                                text(
                                                    "La contraseña debe tener entre 8 y 32 caracteres.",
                                                    "Password must be between 8 and 32 characters.",
                                                ),
                                                className="auth-help",
                                            ),
                                            html.P(
                                                text(
                                                    "La cuenta tendrá acceso estándar.",
                                                    "The account will have standard access.",
                                                ),
                                                className="auth-help",
                                            ),
                                            html.Button("Crear cuenta", type="submit", className="auth-button", **text_attrs("Crear cuenta", "Create account")),
                                        ],
                                        action="/auth/register",
                                        method="post",
                                        className="auth-form",
                                    ),
                                    html.P(
                                        [
                                            html.Span("¿Ya tienes cuenta? ", **text_attrs("¿Ya tienes cuenta? ", "Already have an account? ")),
                                            html.A("Iniciar sesión", href="/login", **text_attrs("Iniciar sesión", "Sign in")),
                                        ],
                                        className="auth-switch",
                                    ),
                                ],
                                className="auth-card",
                            )
                        ],
                        className="auth-shell",
                    )
                ],
                className="page-shell",
            ),
        ]
    )


def _message(message: tuple[str, str] | None) -> html.Div | str:
    if not message:
        return ""
    es, en = message
    return html.Div(es, className="auth-message auth-message-error", role="alert", **text_attrs(es, en))
