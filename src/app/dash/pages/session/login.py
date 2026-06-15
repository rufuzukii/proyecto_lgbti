from __future__ import annotations

from app.auth.csrf import get_csrf_token
from app.dash.compat import dcc, html
from app.dash.layouts.navigation import build_navbar


ERROR_MESSAGES = {
    "invalid_credentials": "Invalid email or password.",
    "invalid_payload": "Enter a valid email and password.",
    "rate_limited": "Too many attempts. Try again in a few minutes.",
    "csrf": "The session expired. Refresh the page and try again.",
    "storage": "Login is not configured yet. Contact the administrator.",
}


def build_login_layout(next_path: str = "/user", error_code: str | None = None) -> html.Div:
    message = ERROR_MESSAGES.get(error_code)

    return html.Div(
        [
            build_navbar(active="login"),
            html.Main(
                [
                    html.Section(
                        [
                            html.Div(
                                [
                                    html.P("Secure access", className="auth-eyebrow"),
                                    html.H1("Sign in"),
                                    html.P(
                                        "Use your account email and password to access your profile.",
                                        className="auth-copy",
                                    ),
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
                                                value=next_path,
                                            ),
                                            html.Label("Email", htmlFor="login-email"),
                                            dcc.Input(
                                                id="login-email",
                                                name="email",
                                                type="email",
                                                required=True,
                                                className="auth-input",
                                            ),
                                            html.Label("Password", htmlFor="login-password"),
                                            dcc.Input(
                                                id="login-password",
                                                name="password",
                                                type="password",
                                                required=True,
                                                className="auth-input",
                                            ),
                                            html.Button("Sign in", type="submit", className="auth-button"),
                                        ],
                                        action="/auth/login",
                                        method="post",
                                        className="auth-form",
                                    ),
                                    html.P(
                                        [
                                            "Don't have an account? ",
                                            html.A("Register", href="/register"),
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


def _message(message: str | None, *, is_error: bool) -> html.Div | str:
    if not message:
        return ""
    class_name = "auth-message auth-message-error" if is_error else "auth-message auth-message-success"
    return html.Div(message, className=class_name, role="alert")
