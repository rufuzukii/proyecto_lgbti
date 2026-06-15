from __future__ import annotations

from flask_login import current_user

from app.auth.csrf import get_csrf_token
from app.dash.compat import dcc, html
from app.dash.layouts.navigation import build_navbar
from app.users.schemas import UserRole


STATUS_MESSAGES = {
    "profile_updated": "Your profile was updated.",
    "signed_in": "You are signed in.",
}

ERROR_MESSAGES = {
    "invalid_current_password": "The current password is not correct.",
    "invalid_username": "The display name must be between 2 and 80 characters.",
    "invalid_email": "Enter a valid email address.",
    "weak_password": "The new password must be between 8 and 32 characters.",
    "email_exists": "That email is already used by another account.",
    "csrf": "The session expired. Refresh the page and try again.",
    "storage": "Profile changes are not configured yet. Contact the administrator.",
    "user_not_found": "The account no longer exists.",
}


def build_user_page_layout(
    status_code: str | None = None,
    error_code: str | None = None,
    mode: str | None = None,
) -> html.Div:
    status = STATUS_MESSAGES.get(status_code)
    error = ERROR_MESSAGES.get(error_code)
    is_editing = mode == "edit"
    username = getattr(current_user, "username", None) or ""
    email = getattr(current_user, "email", None) or ""
    organization = getattr(current_user, "organization", None) or "No organization"
    role = getattr(current_user, "role", UserRole.COMMON)

    return html.Div(
        [
            build_navbar(active="user"),
            html.Main(
                [
                    html.Section(
                        [
                            html.Div(
                                [
                                    html.Div(
                                        [
                                            html.A(
                                                "Back to main page",
                                                href="/",
                                                className="profile-back-link",
                                            ),
                                        ],
                                        className="profile-top-actions",
                                    ),
                                    html.Div(
                                        [
                                            html.P("Account settings", className="auth-eyebrow"),
                                            html.H1("Your profile"),
                                            html.P(
                                                "Review your account information."
                                                if not is_editing
                                                else "Edit your personal data securely.",
                                                className="auth-copy",
                                            ),
                                        ],
                                        className="profile-heading",
                                    ),
                                    _message(status, is_error=False),
                                    _message(error, is_error=True),
                                    _build_edit_form(username, email, organization)
                                    if is_editing
                                    else _build_profile_summary(username, email, organization, role),
                                    _build_logout_form(),
                                ],
                                className="auth-card profile-card",
                            )
                        ],
                        className="auth-shell",
                    )
                ],
                className="page-shell",
            ),
        ]
    )


def _build_profile_summary(
    username: str,
    email: str,
    organization: str,
    role: UserRole | str,
) -> html.Div:
    return html.Div(
        [
            html.Div(
                [
                    _detail_row("Display name", username or "Not set"),
                    _detail_row("Email", email or "Not set"),
                    _detail_row("Organization", organization or "No organization"),
                    _detail_row("Role", _role_label(role)),
                ],
                className="profile-details",
            ),
            html.Div(
                [
                    html.A(
                        "Edit personal data",
                        href="/user?mode=edit",
                        className="auth-button profile-edit-link",
                    ),
                ],
                className="profile-actions",
            ),
        ]
    )


def _build_edit_form(username: str, email: str, organization: str) -> html.Form:
    return html.Form(
        [
            dcc.Input(
                type="hidden",
                name="csrf_token",
                value=get_csrf_token(),
            ),
            html.Label("Display name", htmlFor="profile-username"),
            dcc.Input(
                id="profile-username",
                name="username",
                type="text",
                required=True,
                value=username,
                className="auth-input",
            ),
            html.P(
                "Display name between 2 - 80 characters.",
                className="auth-help",
            ),
            html.Label("Email", htmlFor="profile-email"),
            dcc.Input(
                id="profile-email",
                name="email",
                type="email",
                required=True,
                value=email,
                className="auth-input",
            ),
            html.Label("Organization", htmlFor="profile-organization"),
            dcc.Input(
                id="profile-organization",
                type="text",
                value=organization,
                disabled=True,
                className="auth-input auth-input-disabled",
            ),
            html.Label("Current password", htmlFor="profile-current-password"),
            dcc.Input(
                id="profile-current-password",
                name="current_password",
                type="password",
                required=True,
                className="auth-input",
            ),
            html.Label("New password", htmlFor="profile-new-password"),
            dcc.Input(
                id="profile-new-password",
                name="new_password",
                type="password",
                className="auth-input",
            ),
            html.P(
                "Password between 8 - 32 characters. Leave it empty if you only want to update your name or email.",
                className="auth-help",
            ),
            html.Div(
                [
                    html.Button("Save changes", type="submit", className="auth-button"),
                    html.A("Cancel editing", href="/user", className="auth-button auth-button-secondary"),
                ],
                className="profile-actions",
            ),
        ],
        action="/auth/profile",
        method="post",
        className="auth-form profile-form",
    )


def _build_logout_form() -> html.Form:
    return html.Form(
        [
            dcc.Input(
                type="hidden",
                name="csrf_token",
                value=get_csrf_token(),
            ),
            html.Button("Sign out", type="submit", className="auth-button auth-button-secondary"),
        ],
        action="/auth/logout",
        method="post",
        className="logout-form",
    )


def _detail_row(label: str, value: str) -> html.Div:
    return html.Div(
        [
            html.Span(label, className="profile-detail-label"),
            html.Strong(value, className="profile-detail-value"),
        ],
        className="profile-detail",
    )


def _role_label(role: UserRole | str) -> str:
    value = role.value if isinstance(role, UserRole) else str(role)
    if value == "comun":
        return "common"
    return value


def _message(message: str | None, *, is_error: bool) -> html.Div | str:
    if not message:
        return ""
    class_name = "auth-message auth-message-error" if is_error else "auth-message auth-message-success"
    return html.Div(message, className=class_name, role="alert")
