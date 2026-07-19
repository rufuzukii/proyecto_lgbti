from __future__ import annotations

from app.auth.csrf import get_csrf_token
from app.dash.compat import dcc, html
from app.dash.i18n import text, text_attrs
from app.dash.layouts.navigation import build_navbar
from app.users.schemas import UserRead, UserRole


STATUS_MESSAGES = {
    "user_updated": ("Los cambios se han guardado correctamente.", "Changes were saved successfully."),
    "user_deleted": ("La cuenta se ha eliminado correctamente.", "The account was deleted successfully."),
}

ERROR_MESSAGES = {
    "access_denied": ("No tienes permisos para acceder a esta página.", "You do not have permission to access this page."),
    "csrf": ("La sesión ha caducado. Actualiza la página e inténtalo de nuevo.", "The session expired. Refresh the page and try again."),
    "email_exists": ("Ese correo electrónico ya está en uso por otra cuenta.", "That email address is already used by another account."),
    "invalid_email": ("Introduce un correo electrónico válido.", "Enter a valid email address."),
    "invalid_organization": ("La organización puede tener hasta 120 caracteres.", "Organization can be up to 120 characters."),
    "invalid_role": ("Selecciona un tipo de acceso válido.", "Select a valid access type."),
    "invalid_username": ("El nombre visible debe tener entre 2 y 80 caracteres.", "Display name must be between 2 and 80 characters."),
    "self_delete": ("No puedes eliminar tu propia cuenta desde esta página.", "You cannot delete your own account from this page."),
    "storage": ("La gestión de usuarios no está disponible en este momento.", "User management is not available right now."),
    "user_not_found": ("La cuenta seleccionada ya no existe.", "The selected account no longer exists."),
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
                                    html.P("Administración", className="auth-eyebrow", **text_attrs("Administración", "Administration")),
                                    html.H1(text("Gestión de usuarios", "User management")),
                                    html.P(
                                        text("Revisa, edita y elimina cuentas de usuario.", "Review, edit, and delete user accounts."),
                                        className="auth-copy",
                                    ),
                                    html.Div(
                                        [
                                            html.Div(
                                                [
                                                    html.H2(text("Revisión de archivos pendientes", "Pending file review")),
                                                    html.P(
                                                        text(
                                                            "Revisa los archivos pendientes antes de incorporarlos a la aplicación.",
                                                            "Review pending files before adding them to the application.",
                                                        )
                                                    ),
                                                ],
                                                className="admin-review-copy",
                                            ),
                                            html.A(
                                                text("Revisar archivos pendientes", "Review pending files"),
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
                                    html.P("Administración", className="auth-eyebrow", **text_attrs("Administración", "Administration")),
                                    html.H1(text("Acceso denegado", "Access denied")),
                                    html.P(ERROR_MESSAGES["access_denied"][0], className="auth-copy", **text_attrs(*ERROR_MESSAGES["access_denied"])),
                                    html.A(
                                        text("Volver al inicio", "Back to home"),
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
                    html.Div("Editar", className="admin-table-heading", **text_attrs("Editar", "Edit")),
                    html.Div("Nombre visible", className="admin-table-heading", **text_attrs("Nombre visible", "Display name")),
                    html.Div("Correo electrónico", className="admin-table-heading", **text_attrs("Correo electrónico", "Email address")),
                    html.Div("Organización", className="admin-table-heading", **text_attrs("Organización", "Organization")),
                    html.Div("Acceso", className="admin-table-heading", **text_attrs("Acceso", "Access")),
                    html.Div("Eliminar", className="admin-table-heading", **text_attrs("Eliminar", "Delete")),
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
                    "Guardar",
                    type="submit",
                    name="action",
                    value="update",
                    className="admin-action-button admin-save-button",
                    **text_attrs("Guardar", "Save"),
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
                    value="" if user.organization in {"No organization", "Sin organización"} else (user.organization or ""),
                    className="admin-input",
                ),
                className="admin-table-cell",
            ),
            html.Div(
                html.Select(
                    id=f"{form_id}-role",
                    children=[
                        html.Option(
                            "Estándar",
                            value=UserRole.COMMON.value,
                            selected=_role_value(user.role) == UserRole.COMMON.value,
                            **text_attrs("Estándar", "Standard"),
                        ),
                        html.Option(
                            "Administración",
                            value=UserRole.ADMIN.value,
                            selected=_role_value(user.role) == UserRole.ADMIN.value,
                            **text_attrs("Administración", "Administration"),
                        ),
                    ],
                    name="role",
                    className="admin-input admin-role-select",
                ),
                className="admin-table-cell",
            ),
            html.Div(
                html.Button(
                    "Eliminar",
                    type="submit",
                    name="action",
                    value="delete",
                    className="admin-action-button admin-delete-button",
                    **text_attrs("Eliminar", "Delete"),
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


def _message(message: tuple[str, str] | None, *, is_error: bool) -> html.Div | str:
    if not message:
        return ""
    es, en = message
    class_name = "auth-message auth-message-error" if is_error else "auth-message auth-message-success"
    return html.Div(es, className=class_name, role="alert", **text_attrs(es, en))
