from __future__ import annotations

from dash import dcc, html
from dash.development.base_component import Component

from app.auth.csrf import get_csrf_token
from app.dash.i18n import dash_attrs, text, text_attrs
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
) -> Component:
    status = STATUS_MESSAGES.get(status_code) if status_code is not None else None
    error = ERROR_MESSAGES.get(error_code) if error_code is not None else None

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
                                    _delete_confirmation_dialog(),
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


def build_access_denied_layout() -> Component:
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


def _build_users_table(users: list[UserRead]) -> Component:
    return html.Div(
        [
            html.Div(
                [
                    html.Div("Acción", className="admin-table-heading", **text_attrs("Acción", "Action")),
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


def _build_user_row(user: UserRead) -> Component:
    form_id = f"admin-user-{user.id}"
    return html.Form(
        [
            dcc.Input(type="hidden", name="csrf_token", value=get_csrf_token()),
            dcc.Input(type="hidden", name="user_id", value=user.id),
            html.Div(
                [
                    html.Button(
                        "Editar",
                        type="button",
                        className="admin-action-button admin-edit-button",
                        **dash_attrs(
                            {
                                "data-admin-user-edit": "true",
                                "aria-controls": form_id,
                                "aria-expanded": "false",
                                **text_attrs("Editar", "Edit"),
                            }
                        ),
                    ),
                    html.Button(
                        "Guardar",
                        type="submit",
                        name="action",
                        value="update",
                        hidden=True,
                        className="admin-action-button admin-save-button",
                        **dash_attrs(
                            {
                                "data-admin-user-save": "true",
                                **text_attrs("Guardar", "Save"),
                            }
                        ),
                    ),
                ],
                className="admin-table-cell",
            ),
            html.Div(
                dcc.Input(
                    id=f"{form_id}-username",
                    name="username",
                    type="text",
                    value=user.username or "",
                    required=True,
                    className="admin-input admin-editable-input",
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
                    className="admin-input admin-editable-input",
                ),
                className="admin-table-cell",
            ),
            html.Div(
                dcc.Input(
                    id=f"{form_id}-organization",
                    name="organization",
                    type="text",
                    value="" if user.organization in {"No organization", "Sin organización"} else (user.organization or ""),
                    className="admin-input admin-editable-input",
                ),
                className="admin-table-cell",
            ),
            html.Div(
                html.Select(
                    id=f"{form_id}-role",
                    children=_admin_role_options(user.role),
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
                    **dash_attrs(
                        {
                            "data-admin-user-delete": "true",
                            **text_attrs("Eliminar", "Delete"),
                        }
                    ),
                ),
                className="admin-table-cell",
            ),
        ],
        id=form_id,
        action="/admin/users",
        method="post",
        className="admin-table-row",
        **dash_attrs({"data-admin-user-row": "true"}),
    )


def _delete_confirmation_dialog() -> Component:
    return html.Dialog(
        html.Div(
            [
                html.H2(
                    "Confirmar eliminación",
                    id="admin-user-delete-title",
                    **text_attrs("Confirmar eliminación", "Confirm deletion"),
                ),
                html.P(
                    "¿Quieres eliminar a este usuario?",
                    **text_attrs(
                        "¿Quieres eliminar a este usuario?",
                        "Do you want to delete this user?",
                    ),
                ),
                html.Div(
                    [
                        html.Button(
                            "Cancelar",
                            type="button",
                            className="admin-action-button admin-cancel-button",
                            **dash_attrs(
                                {
                                    "data-admin-user-delete-cancel": "true",
                                    **text_attrs("Cancelar", "Cancel"),
                                }
                            ),
                        ),
                        html.Button(
                            "Eliminar",
                            type="button",
                            className="admin-action-button admin-delete-button",
                            **dash_attrs(
                                {
                                    "data-admin-user-delete-confirm": "true",
                                    **text_attrs("Eliminar", "Delete"),
                                }
                            ),
                        ),
                    ],
                    className="admin-delete-dialog-actions",
                ),
            ],
            className="admin-delete-dialog-panel",
        ),
        id="admin-user-delete-dialog",
        className="admin-delete-dialog",
        **dash_attrs(
            {
                "aria-labelledby": "admin-user-delete-title",
                "aria-modal": "true",
            }
        ),
    )


def _role_value(role: UserRole | str) -> str:
    value = role.value if isinstance(role, UserRole) else str(role)
    if value in {"comun", "user"}:
        return UserRole.COMMON.value
    if value == UserRole.ADMIN.value:
        return UserRole.ADMIN.value
    return UserRole.COMMON.value


def _admin_role_options(role: UserRole | str) -> list[Component]:
    current = _role_value(role)
    definitions = [
        (UserRole.COMMON.value, "Estándar", "Standard"),
        (UserRole.ADMIN.value, "Administración", "Administration"),
    ]
    ordered = sorted(definitions, key=lambda item: item[0] != current)
    return [
        html.Option(label_es, value=value, **text_attrs(label_es, label_en))
        for value, label_es, label_en in ordered
    ]


def _message(message: tuple[str, str] | None, *, is_error: bool) -> Component | str:
    if not message:
        return ""
    es, en = message
    class_name = "auth-message auth-message-error" if is_error else "auth-message auth-message-success"
    attrs = text_attrs(es, en)
    if not is_error:
        attrs["data-auto-dismiss-ms"] = "5000"
    return html.Div(
        es,
        className=class_name,
        role="alert" if is_error else "status",
        **dash_attrs(attrs),
    )
