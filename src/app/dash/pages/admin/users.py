from __future__ import annotations

from urllib.parse import urlencode

from dash import Dash, Input, Output, State, dcc, html
from dash.development.base_component import Component
from flask_login import current_user

from app.auth.csrf import get_csrf_token
from app.auth.permissions import is_admin_user
from app.dash.components.page_structure import build_page_header
from app.dash.i18n import dash_attrs, text, text_attrs
from app.dash.layouts.navigation import build_navbar
from app.dash.routes import route_path
from app.taxonomy import taxonomy_pair
from app.users.schemas import UserRead, UserRole, UserType
from app.users.service import UserStorageError, list_users_page

STATUS_MESSAGES = {
    "user_updated": (
        "Los cambios se han guardado correctamente.",
        "Changes were saved successfully.",
    ),
    "user_deleted": (
        "La cuenta se ha eliminado correctamente.",
        "The account was deleted successfully.",
    ),
    "user_validated": (
        "La cuenta se ha marcado como validada.",
        "The account was marked as validated.",
    ),
}

ERROR_MESSAGES = {
    "access_denied": (
        "No tienes permisos para acceder a esta página.",
        "You do not have permission to access this page.",
    ),
    "csrf": (
        "La sesión ha caducado. Actualiza la página e inténtalo de nuevo.",
        "The session expired. Refresh the page and try again.",
    ),
    "email_exists": (
        "Ese correo electrónico ya está en uso por otra cuenta.",
        "That email address is already used by another account.",
    ),
    "invalid_email": ("Introduce un correo electrónico válido.", "Enter a valid email address."),
    "invalid_organization": (
        "La organización puede tener hasta 120 caracteres.",
        "Organization can be up to 120 characters.",
    ),
    "invalid_role": ("Selecciona un tipo de acceso válido.", "Select a valid access type."),
    "invalid_username": (
        "El nombre visible debe tener entre 2 y 80 caracteres.",
        "Display name must be between 2 and 80 characters.",
    ),
    "self_delete": (
        "No puedes eliminar tu propia cuenta desde esta página.",
        "You cannot delete your own account from this page.",
    ),
    "last_admin": (
        "Debe conservarse al menos una cuenta administradora.",
        "At least one administrator account must be retained.",
    ),
    "self_manage": (
        "No puedes modificar tu propia cuenta desde Gestión de usuarios.",
        "You cannot modify your own account from User management.",
    ),
    "concurrent_update": (
        "La cuenta cambi\u00f3 mientras la editabas. Revisa los datos actuales y vuelve a intentarlo.",
        "The account changed while you were editing it. Review the current data and try again.",
    ),
    "storage": (
        "La gestión de usuarios no está disponible en este momento.",
        "User management is not available right now.",
    ),
    "user_not_found": (
        "La cuenta seleccionada ya no existe.",
        "The selected account no longer exists.",
    ),
}


def build_admin_users_layout(
    users: list[UserRead],
    *,
    status_code: str | None = None,
    error_code: str | None = None,
    search: str = "",
    page: int = 1,
    page_count: int = 1,
    total: int | None = None,
    current_user_id: str | None = None,
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
                                    build_page_header(
                                        eyebrow=text("Administración", "Administration"),
                                        title=text("Gestión de usuarios", "User management"),
                                        description=text(
                                            "Revisa, valida, edita y elimina cuentas de usuario.",
                                            "Review, validate, edit, and delete user accounts.",
                                        ),
                                        class_name="admin-page-header",
                                    ),
                                    html.Div(
                                        [
                                            html.Div(
                                                [
                                                    html.H2(
                                                        text(
                                                            "Revisión de archivos pendientes",
                                                            "Pending file review",
                                                        )
                                                    ),
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
                                                text(
                                                    "Revisar archivos pendientes",
                                                    "Review pending files",
                                                ),
                                                href=route_path("admin_imports"),
                                                className="auth-button profile-edit-link",
                                            ),
                                        ],
                                        className="admin-review-panel",
                                    ),
                                    _message(status, is_error=False),
                                    _message(error, is_error=True),
                                    _search_users_control(search),
                                    dcc.Loading(
                                        html.Div(
                                            _users_results(
                                                users,
                                                current_user_id=current_user_id,
                                                search=search,
                                                page=page,
                                                page_count=page_count,
                                                total=total,
                                            ),
                                            id="admin-users-results",
                                            **dash_attrs({"aria-live": "polite"}),
                                        ),
                                        className="admin-users-local-loading",
                                        type="circle",
                                    ),
                                    _delete_confirmation_dialog(),
                                ],
                                className="admin-card app-surface",
                            )
                        ],
                        className="admin-shell app-page",
                    )
                ],
                className="page-shell app-page-container",
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
                                    html.P(
                                        "Administración",
                                        className="auth-eyebrow",
                                        **text_attrs("Administración", "Administration"),
                                    ),
                                    html.H1(text("Acceso denegado", "Access denied")),
                                    html.P(
                                        ERROR_MESSAGES["access_denied"][0],
                                        className="auth-copy",
                                        **text_attrs(*ERROR_MESSAGES["access_denied"]),
                                    ),
                                    html.A(
                                        text("Volver al inicio", "Back to home"),
                                        href=route_path("home"),
                                        className="auth-button profile-edit-link",
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


def _search_users_control(search: str) -> Component:
    return html.Div(
        [
            html.Label(
                text("Buscar usuarios", "Search users"),
                htmlFor="admin-user-search",
                className="admin-user-search-label",
            ),
            html.Div(
                [
                    dcc.Input(
                        id="admin-user-search",
                        name="q",
                        type="search",
                        value=search,
                        debounce=True,
                        maxLength=120,
                        placeholder="Nombre, correo u organizaci\u00f3n / Name, email or organization",
                        className="admin-user-search-input",
                    ),
                    html.Button(
                        text("Buscar", "Search"),
                        id="admin-user-search-button",
                        type="button",
                        className="admin-user-search-button",
                    ),
                ],
                className="admin-user-search-controls",
            ),
        ],
        className="admin-user-search-form",
        role="search",
    )


def _users_results(
    users: list[UserRead],
    *,
    current_user_id: str | None,
    search: str,
    page: int,
    page_count: int,
    total: int | None,
) -> list[Component | str]:
    result_total = len(users) if total is None else total
    return [
        html.P(
            f"{result_total} usuarios",
            className="admin-users-result-count",
            **text_attrs(f"{result_total} usuarios", f"{result_total} users"),
        ),
        _build_users_table(
            users,
            current_user_id=current_user_id,
            search=search,
            page=page,
        ),
        _pagination(search, page, page_count),
    ]


def register_admin_users_callbacks(app: Dash) -> None:
    @app.callback(
        Output("admin-users-results", "children"),
        Input("admin-user-search", "n_submit"),
        Input("admin-user-search-button", "n_clicks"),
        State("admin-user-search", "value"),
        prevent_initial_call=True,
    )
    def refresh_user_results(
        _submitted: int | None,
        _clicked: int | None,
        search: str | None,
    ) -> list[Component | str]:
        if not current_user.is_authenticated or not is_admin_user(current_user):
            return [_message(ERROR_MESSAGES["access_denied"], is_error=True)]
        clean_search = str(search or "").strip()[:120]
        try:
            user_page = list_users_page(search=clean_search, page=1)
        except UserStorageError:
            return [_message(ERROR_MESSAGES["storage"], is_error=True)]
        return _users_results(
            user_page.users,
            current_user_id=current_user.get_id(),
            search=clean_search,
            page=user_page.page,
            page_count=user_page.page_count,
            total=user_page.total,
        )


def _build_users_table(
    users: list[UserRead],
    *,
    current_user_id: str | None = None,
    search: str = "",
    page: int = 1,
) -> Component:
    return html.Div(
        [
            html.Div(
                [
                    html.Div(
                        "Acción", className="admin-table-heading", **text_attrs("Acción", "Action")
                    ),
                    html.Div(
                        "Nombre visible",
                        className="admin-table-heading",
                        **text_attrs("Nombre visible", "Display name"),
                    ),
                    html.Div(
                        "Correo electrónico",
                        className="admin-table-heading",
                        **text_attrs("Correo electrónico", "Email address"),
                    ),
                    html.Div(
                        "Organización",
                        className="admin-table-heading",
                        **text_attrs("Organización", "Organization"),
                    ),
                    html.Div(
                        "Acceso", className="admin-table-heading", **text_attrs("Acceso", "Access")
                    ),
                    html.Div(
                        "Validación",
                        className="admin-table-heading",
                        **text_attrs("Validación", "Validation"),
                    ),
                    html.Div(
                        "Eliminar",
                        className="admin-table-heading",
                        **text_attrs("Eliminar", "Delete"),
                    ),
                ],
                className="admin-table-row admin-table-header",
            ),
            *[
                _build_user_row(
                    user,
                    current_user_id=current_user_id,
                    search=search,
                    page=page,
                )
                for user in users
            ],
            (
                ""
                if users
                else html.Div(
                    text(
                        "No hay usuarios que coincidan con la b\u00fasqueda.",
                        "No users match the search.",
                    ),
                    className="admin-users-empty",
                    role="row",
                )
            ),
        ],
        className="admin-table",
        role="table",
    )


def _build_user_row(
    user: UserRead,
    *,
    current_user_id: str | None = None,
    search: str = "",
    page: int = 1,
) -> Component:
    form_id = f"admin-user-{user.id}"
    is_current = bool(current_user_id and user.id == current_user_id)
    return html.Form(
        [
            dcc.Input(type="hidden", name="csrf_token", value=get_csrf_token()),
            dcc.Input(type="hidden", name="user_id", value=user.id),
            dcc.Input(type="hidden", name="version", value=user.version),
            dcc.Input(type="hidden", name="q", value=search),
            dcc.Input(type="hidden", name="page", value=str(page)),
            html.Div(
                [
                    html.Button(
                        "Editar",
                        type="button",
                        disabled=is_current,
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
                        disabled=is_current,
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
                [
                    dcc.Input(
                        id=f"{form_id}-username",
                        name="username",
                        type="text",
                        value=user.username or "",
                        required=True,
                        disabled=is_current,
                        className="admin-input admin-editable-input",
                    ),
                    (
                        html.Span(
                            text("Tu cuenta", "Your account"),
                            className="admin-current-user-badge",
                        )
                        if is_current
                        else ""
                    ),
                ],
                className="admin-table-cell",
            ),
            html.Div(
                dcc.Input(
                    id=f"{form_id}-email",
                    name="email",
                    type="email",
                    value=user.email or "",
                    required=True,
                    disabled=is_current,
                    className="admin-input admin-editable-input",
                ),
                className="admin-table-cell",
            ),
            html.Div(
                dcc.Input(
                    id=f"{form_id}-organization",
                    name="organization",
                    type="text",
                    value=""
                    if user.organization in {"No organization", "Sin organización"}
                    else (user.organization or ""),
                    className="admin-input admin-editable-input",
                    disabled=is_current,
                ),
                className="admin-table-cell",
            ),
            html.Div(
                html.Select(
                    id=f"{form_id}-role",
                    children=_admin_role_options(user.user_type or user.role),
                    name="role",
                    className="admin-input admin-role-select",
                    disabled=is_current,
                ),
                className="admin-table-cell",
            ),
            html.Div(
                (
                    html.Span(
                        "Validada",
                        className="admin-validation-badge is-validated",
                        **text_attrs("Validada", "Validated"),
                    )
                    if user.admin_validated
                    else html.Button(
                        "Validar cuenta",
                        type="submit",
                        name="action",
                        value="validate",
                        disabled=is_current,
                        className="admin-action-button admin-validate-button",
                        **text_attrs("Validar cuenta", "Validate account"),
                    )
                ),
                className="admin-table-cell admin-validation-cell",
            ),
            html.Div(
                html.Button(
                    "Eliminar",
                    type="submit",
                    name="action",
                    value="delete",
                    disabled=is_current,
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
        className="admin-table-row" + (" is-current-user" if is_current else ""),
        **dash_attrs(
            {
                "data-admin-user-row": "true",
                "data-current-user-row": str(is_current).lower(),
                "aria-disabled": str(is_current).lower(),
            }
        ),
    )


def _pagination(search: str, page: int, page_count: int) -> Component | str:
    if page_count <= 1:
        return ""

    def page_href(target: int) -> str:
        query = {"page": str(target)}
        if search:
            query["q"] = search
        return f"{route_path('admin')}?{urlencode(query)}"

    return html.Nav(
        [
            html.A(
                text("Anterior", "Previous"),
                href=page_href(page - 1) if page > 1 else None,
                className="admin-pagination-link" + (" is-disabled" if page <= 1 else ""),
                **dash_attrs(
                    {
                        "aria-disabled": str(page <= 1).lower(),
                    }
                ),
            ),
            html.Span(
                f"P\u00e1gina {page} de {page_count}",
                className="admin-pagination-status",
                **text_attrs(
                    f"P\u00e1gina {page} de {page_count}",
                    f"Page {page} of {page_count}",
                ),
            ),
            html.A(
                text("Siguiente", "Next"),
                href=page_href(page + 1) if page < page_count else None,
                className="admin-pagination-link"
                + (" is-disabled" if page >= page_count else ""),
                **dash_attrs(
                    {
                        "aria-disabled": str(page >= page_count).lower(),
                    }
                ),
            ),
        ],
        className="admin-pagination",
        **dash_attrs({"aria-label": "Paginaci\u00f3n de usuarios / User pagination"}),
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


def _role_value(role: UserRole | UserType | str) -> str:
    value = role.value if isinstance(role, (UserRole, UserType)) else str(role)
    if value in {"comun", "user"}:
        return UserType.COMUN.value
    if value == UserRole.ADMIN.value:
        return UserRole.ADMIN.value
    try:
        return UserType(value).value
    except ValueError:
        return UserType.COMUN.value


def _admin_role_options(role: UserRole | UserType | str) -> list[Component]:
    current = _role_value(role)
    definitions = [
        (value, *taxonomy_pair("role", value))
        for value in (
            UserType.COMUN.value,
            UserType.DOCENTE.value,
            UserType.RRHH.value,
            UserType.POLITICO.value,
            UserType.ONG.value,
            UserType.SOCIOLOGO.value,
            UserRole.ADMIN.value,
        )
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
    class_name = (
        "auth-message auth-message-error" if is_error else "auth-message auth-message-success"
    )
    attrs = text_attrs(es, en)
    if not is_error:
        attrs["data-auto-dismiss-ms"] = "5000"
    return html.Div(
        es,
        className=class_name,
        role="alert" if is_error else "status",
        **dash_attrs(attrs),
    )
