from __future__ import annotations

from app.auth.csrf import get_csrf_token
from app.dash.compat import dcc, html
from app.dash.layouts.navigation import build_navbar
from app.users.schemas import UserRead, UserRole


STATUS_MESSAGES = {
    "user_updated": "User updated.",
    "user_deleted": "User deleted.",
}

ERROR_MESSAGES = {
    "access_denied": "You do not have permission to access this page.",
    "csrf": "The session expired. Refresh the page and try again.",
    "email_exists": "That email is already used by another account.",
    "invalid_email": "Enter a valid email address.",
    "invalid_organization": "Organization must be up to 120 characters.",
    "invalid_role": "Select a valid role.",
    "invalid_username": "Display name must be between 2 and 80 characters.",
    "self_delete": "You cannot delete your own account from this page.",
    "storage": "User management is not available right now.",
    "user_not_found": "The selected user no longer exists.",
}


def build_admin_users_layout(
    users: list[UserRead],
    *,
    status_code: str | None = None,
    error_code: str | None = None,
) -> html.Div:
    status = STATUS_MESSAGES.get(status_code)
    error = ERROR_MESSAGES.get(error_code)

    return html.Div(
        [
            build_navbar(active="admin"),
            html.Main(
                [
                    html.Section(
                        [
                            html.Div(
                                [
                                    html.P("Administration", className="auth-eyebrow"),
                                    html.H1("User management"),
                                    html.P(
                                        "Review, edit, and delete application users.",
                                        className="auth-copy",
                                    ),
                                    html.Div(
                                        [
                                            html.Div(
                                                [
                                                    html.H2("JSON import review"),
                                                    html.P(
                                                        "Inspect pending JSON files before inserting them into MongoDB."
                                                    ),
                                                ],
                                                className="admin-review-copy",
                                            ),
                                            html.A(
                                                "Inspect JSON imports",
                                                href="/admin/imports",
                                                className="auth-button profile-edit-link",
                                            ),
                                        ],
                                        className="admin-review-panel",
                                    ),
                                    _message(status, is_error=False),
                                    _message(error, is_error=True),
                                    _build_users_table(users),
                                ],
                                className="admin-card",
                            )
                        ],
                        className="admin-shell",
                    )
                ],
                className="page-shell",
            ),
        ]
    )


def build_access_denied_layout() -> html.Div:
    return html.Div(
        [
            build_navbar(active="admin"),
            html.Main(
                [
                    html.Section(
                        [
                            html.Div(
                                [
                                    html.P("Administration", className="auth-eyebrow"),
                                    html.H1("Access denied"),
                                    html.P(ERROR_MESSAGES["access_denied"], className="auth-copy"),
                                    html.A(
                                        "Back to main page",
                                        href="/",
                                        className="auth-button profile-edit-link",
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


def _build_users_table(users: list[UserRead]) -> html.Div:
    return html.Div(
        [
            html.Div(
                [
                    html.Div("Edit", className="admin-table-heading"),
                    html.Div("Display name", className="admin-table-heading"),
                    html.Div("Email", className="admin-table-heading"),
                    html.Div("Organization", className="admin-table-heading"),
                    html.Div("Role", className="admin-table-heading"),
                    html.Div("Delete", className="admin-table-heading"),
                ],
                className="admin-table-row admin-table-header",
            ),
            *[_build_user_row(user) for user in users],
        ],
        className="admin-table",
        role="table",
    )


def _build_user_row(user: UserRead) -> html.Form:
    form_id = f"admin-user-{user.id}"
    return html.Form(
        [
            dcc.Input(type="hidden", name="csrf_token", value=get_csrf_token()),
            dcc.Input(type="hidden", name="user_id", value=user.id),
            html.Div(
                html.Button(
                    "Save",
                    type="submit",
                    name="action",
                    value="update",
                    className="admin-action-button admin-save-button",
                ),
                className="admin-table-cell",
            ),
            html.Div(
                dcc.Input(
                    id=f"{form_id}-username",
                    name="username",
                    type="text",
                    value=user.username or "",
                    required=True,
                    className="admin-input",
                ),
                className="admin-table-cell",
            ),
            html.Div(
                dcc.Input(
                    id=f"{form_id}-email",
                    name="email",
                    type="email",
                    value=user.email or "",
                    required=True,
                    className="admin-input",
                ),
                className="admin-table-cell",
            ),
            html.Div(
                dcc.Input(
                    id=f"{form_id}-organization",
                    name="organization",
                    type="text",
                    value="" if user.organization == "No organization" else (user.organization or ""),
                    className="admin-input",
                ),
                className="admin-table-cell",
            ),
            html.Div(
                html.Select(
                    id=f"{form_id}-role",
                    children=[
                        html.Option(
                            "common",
                            value=UserRole.COMMON.value,
                            selected=_role_value(user.role) == UserRole.COMMON.value,
                        ),
                        html.Option(
                            "admin",
                            value=UserRole.ADMIN.value,
                            selected=_role_value(user.role) == UserRole.ADMIN.value,
                        ),
                    ],
                    name="role",
                    className="admin-input admin-role-select",
                ),
                className="admin-table-cell",
            ),
            html.Div(
                html.Button(
                    "Delete",
                    type="submit",
                    name="action",
                    value="delete",
                    className="admin-action-button admin-delete-button",
                ),
                className="admin-table-cell",
            ),
        ],
        action="/admin/users",
        method="post",
        className="admin-table-row",
    )


def _role_value(role: UserRole | str) -> str:
    value = role.value if isinstance(role, UserRole) else str(role)
    if value in {"comun", "user"}:
        return UserRole.COMMON.value
    if value == UserRole.ADMIN.value:
        return UserRole.ADMIN.value
    return UserRole.COMMON.value


def _message(message: str | None, *, is_error: bool) -> html.Div | str:
    if not message:
        return ""
    class_name = "auth-message auth-message-error" if is_error else "auth-message auth-message-success"
    return html.Div(message, className=class_name, role="alert")
