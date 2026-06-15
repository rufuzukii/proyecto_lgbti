from __future__ import annotations

from app.auth.csrf import get_csrf_token
from app.dash.compat import dcc, html
from app.dash.layouts.navigation import build_navbar


ERROR_MESSAGES = {
    "invalid_payload": "Enter a valid name, email, password, and organization.",
    "email_exists": "That email is already registered.",
    "rate_limited": "Too many attempts. Try again in a few minutes.",
    "csrf": "The session expired. Refresh the page and try again.",
    "storage": "Registration is not configured yet. Contact the administrator.",
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
                                    html.P("Create access", className="auth-eyebrow"),
                                    html.H1("Register"),
                                    html.P(
                                        "Create your account with your display name, email, password, and organization.",
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
                                            html.Label("Display name", htmlFor="register-name"),
                                            dcc.Input(
                                                id="register-name",
                                                name="name",
                                                type="text",
                                                required=True,
                                                className="auth-input",
                                            ),
                                            html.P(
                                                "Display name between 2 - 80 characters.",
                                                className="auth-help",
                                            ),
                                            html.Label("Email", htmlFor="register-email"),
                                            dcc.Input(
                                                id="register-email",
                                                name="email",
                                                type="email",
                                                required=True,
                                                className="auth-input",
                                            ),
                                            html.Label("Organization", htmlFor="register-organization"),
                                            dcc.Input(
                                                id="register-organization",
                                                name="organization",
                                                type="text",
                                                placeholder="No organization",
                                                className="auth-input",
                                            ),
                                            html.P(
                                                "Organization up to 120 characters.",
                                                className="auth-help",
                                            ),
                                            html.Label("Password", htmlFor="register-password"),
                                            dcc.Input(
                                                id="register-password",
                                                name="password",
                                                type="password",
                                                required=True,
                                                className="auth-input",
                                            ),
                                            html.P(
                                                "Password between 8 - 32 characters.",
                                                className="auth-help",
                                            ),
                                            html.P(
                                                "The account role will be common. Only an administrator can change it.",
                                                className="auth-help",
                                            ),
                                            html.Button("Create account", type="submit", className="auth-button"),
                                        ],
                                        action="/auth/register",
                                        method="post",
                                        className="auth-form",
                                    ),
                                    html.P(
                                        [
                                            "Already have an account? ",
                                            html.A("Sign in", href="/login"),
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


def _message(message: str | None) -> html.Div | str:
    if not message:
        return ""
    return html.Div(message, className="auth-message auth-message-error", role="alert")
