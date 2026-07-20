from __future__ import annotations

from dash import dcc, html
from dash.development.base_component import Component
from flask_login import current_user

from app.auth.csrf import get_csrf_token
from app.dash.i18n import text_attrs
from app.dash.layouts.navigation import build_navbar
from app.users.schemas import UserRole


STATUS_MESSAGES = {
    "profile_updated": ("Tu perfil se ha actualizado.", "Your profile was updated."),
    "signed_in": ("Sesión iniciada.", "You are signed in."),
}

ERROR_MESSAGES = {
    "invalid_current_password": (
        "La contraseña actual no es correcta.",
        "The current password is not correct.",
    ),
    "invalid_username": (
        "El nombre visible debe tener entre 2 y 80 caracteres.",
        "The display name must be between 2 and 80 characters.",
    ),
    "invalid_email": (
        "Introduce un email válido.",
        "Enter a valid email address.",
    ),
    "weak_password": (
        "La nueva contraseña debe tener entre 8 y 32 caracteres.",
        "The new password must be between 8 and 32 characters.",
    ),
    "email_exists": (
        "Ese email ya está en uso por otra cuenta.",
        "That email is already used by another account.",
    ),
    "csrf": (
        "La sesión ha caducado. Actualiza la página e inténtalo de nuevo.",
        "The session expired. Refresh the page and try again.",
    ),
    "storage": (
        "Los cambios de perfil no están configurados. Contacta con administración.",
        "Profile changes are not configured yet. Contact the administrator.",
    ),
    "user_not_found": (
        "La cuenta ya no existe.",
        "The account no longer exists.",
    ),
}


def build_user_page_layout(
    status_code: str | None = None,
    error_code: str | None = None,
    mode: str | None = None,
) -> Component:
    status = STATUS_MESSAGES.get(status_code) if status_code is not None else None
    error = ERROR_MESSAGES.get(error_code) if error_code is not None else None
    is_editing = mode == "edit"
    username = getattr(current_user, "username", None) or ""
    email = getattr(current_user, "email", None) or ""
    organization = getattr(current_user, "organization", None) or "Sin organización"
    role = getattr(current_user, "role", UserRole.COMMON)
    display_name = username or email or "Usuario"

    return html.Div(
        [
            build_navbar(active="user"),
            html.Main(
                [
                    html.Section(
                        [
                            _dashboard_header(display_name, role),
                            _message(status, is_error=False),
                            _message(error, is_error=True),
                            (
                                _build_edit_panel(username, email, organization)
                                if is_editing
                                else _build_dashboard(username, email, organization, role)
                            ),
                        ],
                        className="user-dashboard-shell",
                    )
                ],
                className="user-page-grid",
            ),
        ]
    )


def _dashboard_header(display_name: str, role: UserRole | str) -> Component:
    role_value = _role_label(role)
    return html.Header(
        [
            html.Div(
                [
                    html.P(
                        "Panel personal",
                        className="user-eyebrow",
                        **text_attrs("Panel personal", "Personal dashboard"),
                    ),
                    html.H1(
                        f"Hola, {display_name}",
                        **text_attrs(f"Hola, {display_name}", f"Hi, {display_name}"),
                    ),
                    html.P(
                        "Gestiona tu perfil, revisa tus permisos y vuelve rápido a las áreas principales.",
                        className="user-lead",
                        **text_attrs(
                            "Gestiona tu perfil, revisa tus permisos y vuelve rápido a las áreas principales.",
                            "Manage your profile, review your permissions, and jump back into the main work areas.",
                        ),
                    ),
                ],
                className="user-title-block",
            ),
            html.Div(
                [
                    html.Span(
                        "Rol",
                        className="user-role-label",
                        **text_attrs("Rol", "Role"),
                    ),
                    html.Strong(role_value, className="user-role-value"),
                ],
                className="user-role-badge",
            ),
        ],
        className="user-dashboard-header",
    )


def _build_dashboard(
    username: str,
    email: str,
    organization: str,
    role: UserRole | str,
) -> Component:
    return html.Div(
        [
            html.Section(
                [
                    _profile_card(username, email, organization, role),
                    _quick_actions(role),
                ],
                className="user-dashboard-main",
            ),
            html.Section(
                [
                    _permission_panel(role),
                ],
                className="user-dashboard-side",
            ),
        ],
        className="user-dashboard-grid",
    )


def _profile_card(
    username: str,
    email: str,
    organization: str,
    role: UserRole | str,
) -> Component:
    organization_es = organization if organization else "Sin organización"
    organization_en = organization if organization else "No organization"
    return html.Section(
        [
            html.Div(
                [
                    html.H2(
                        "Datos de la cuenta",
                        **text_attrs("Datos de la cuenta", "Account details"),
                    ),
                    html.A(
                        "Editar",
                        href="/user?mode=edit",
                        className="user-link-button",
                        **text_attrs("Editar", "Edit"),
                    ),
                ],
                className="user-card-header",
            ),
            html.Div(
                [
                    _detail_row("Nombre visible", "Display name", username or "No definido", "Not set"),
                    _detail_row("Email", "Email", email or "No definido", "Not set"),
                    _detail_row("Organización", "Organization", organization_es, organization_en),
                    _detail_row("Rol", "Role", _role_label(role), _role_label(role)),
                ],
                className="profile-details user-detail-grid",
            ),
            _build_logout_form(),
        ],
        className="user-card user-profile-card",
    )


def _quick_actions(role: UserRole | str) -> Component:
    actions = [
        (
            "Ver estadísticas",
            "View statistics",
            "/statistics",
            "Comparar indicadores FRA e ILGA.",
            "Compare FRA and ILGA indicators.",
        ),
        (
            "Importar CSV",
            "Import CSV",
            "/upload",
            "Enviar datos para revisión.",
            "Submit data for review.",
        ),
    ]
    if _is_admin_role(role):
        actions.append(
            (
                "Administración",
                "Administration",
                "/admin",
                "Gestionar usuarios y revisiones.",
                "Manage users and reviews.",
            )
        )

    return html.Section(
        [
            html.H2("Accesos rápidos", **text_attrs("Accesos rápidos", "Quick actions")),
            html.Div(
                [
                    html.A(
                        [
                            html.Strong(title_es, **text_attrs(title_es, title_en)),
                            html.Span(copy_es, **text_attrs(copy_es, copy_en)),
                        ],
                        href=href,
                        className="user-action-tile",
                    )
                    for title_es, title_en, href, copy_es, copy_en in actions
                ],
                className="user-action-grid",
            ),
        ],
        className="user-card",
    )


def _permission_panel(role: UserRole | str) -> Component:
    can_admin = _is_admin_role(role)
    permissions = [
        (
            "Analítica",
            "Analytics",
            "Disponible",
            "Available",
            True,
        ),
        (
            "Importación",
            "Import",
            "Disponible",
            "Available",
            True,
        ),
        (
            "Gestión de usuarios",
            "User management",
            "Disponible",
            "Available",
            can_admin,
        ),
    ]
    return html.Section(
        [
            html.H2("Permisos", **text_attrs("Permisos", "Permissions")),
            html.Div(
                [
                    _permission_item(title_es, title_en, value_es, value_en)
                    for title_es, title_en, value_es, value_en, enabled in permissions
                    if enabled
                ],
                className="user-permission-list",
            ),
        ],
        className="user-card",
    )


def _build_edit_panel(username: str, email: str, organization: str) -> Component:
    return html.Div(
        [
            html.Section(
                [
                    html.Div(
                        [
                            html.H2(
                                "Editar perfil",
                                **text_attrs("Editar perfil", "Edit profile"),
                            ),
                        ],
                        className="user-card-header",
                    ),
                    _build_edit_form(username, email, organization),
                ],
                className="user-card user-edit-card",
            ),
        ],
        className="user-dashboard-grid user-dashboard-grid-single",
    )


def _build_edit_form(username: str, email: str, organization: str) -> Component:
    return html.Form(
        [
            dcc.Input(
                type="hidden",
                name="csrf_token",
                value=get_csrf_token(),
            ),
            html.Label(
                "Nombre visible",
                htmlFor="profile-username",
                **text_attrs("Nombre visible", "Display name"),
            ),
            dcc.Input(
                id="profile-username",
                name="username",
                type="text",
                required=True,
                value=username,
                className="auth-input",
            ),
            html.P(
                "Debe tener entre 2 y 80 caracteres.",
                className="auth-help",
                **text_attrs(
                    "Debe tener entre 2 y 80 caracteres.",
                    "Must be between 2 and 80 characters.",
                ),
            ),
            html.Label("Email", htmlFor="profile-email", **text_attrs("Email", "Email")),
            dcc.Input(
                id="profile-email",
                name="email",
                type="email",
                required=True,
                value=email,
                className="auth-input",
            ),
            html.Label(
                "Organización",
                htmlFor="profile-organization",
                **text_attrs("Organización", "Organization"),
            ),
            dcc.Input(
                id="profile-organization",
                type="text",
                value=organization,
                disabled=True,
                className="auth-input auth-input-disabled",
            ),
            html.Label(
                "Contraseña actual",
                htmlFor="profile-current-password",
                **text_attrs("Contraseña actual", "Current password"),
            ),
            dcc.Input(
                id="profile-current-password",
                name="current_password",
                type="password",
                required=True,
                className="auth-input",
            ),
            html.Label(
                "Nueva contraseña",
                htmlFor="profile-new-password",
                **text_attrs("Nueva contraseña", "New password"),
            ),
            dcc.Input(
                id="profile-new-password",
                name="new_password",
                type="password",
                className="auth-input",
            ),
            html.P(
                "Entre 8 y 32 caracteres. Déjala vacía si solo quieres actualizar nombre o email.",
                className="auth-help",
                **text_attrs(
                    "Entre 8 y 32 caracteres. Déjala vacía si solo quieres actualizar nombre o email.",
                    "Between 8 and 32 characters. Leave it empty to update only name or email.",
                ),
            ),
            html.Div(
                [
                    html.Button(
                        "Guardar cambios",
                        type="submit",
                        className="auth-button",
                        **text_attrs("Guardar cambios", "Save changes"),
                    ),
                    html.A(
                        "Cancelar",
                        href="/user",
                        className="auth-button auth-button-secondary profile-cancel-link",
                        **text_attrs("Cancelar", "Cancel"),
                    ),
                ],
                className="profile-actions",
            ),
        ],
        action="/auth/profile",
        method="post",
        className="auth-form profile-form",
    )


def _build_logout_form() -> Component:
    return html.Form(
        [
            dcc.Input(
                type="hidden",
                name="csrf_token",
                value=get_csrf_token(),
            ),
            html.Button(
                "Cerrar sesión",
                type="submit",
                className="auth-button auth-button-secondary user-logout-button",
                **text_attrs("Cerrar sesión", "Sign out"),
            ),
        ],
        action="/auth/logout",
        method="post",
        className="logout-form",
    )


def _detail_row(label_es: str, label_en: str, value_es: str, value_en: str) -> Component:
    return html.Div(
        [
            html.Span(
                label_es,
                className="profile-detail-label",
                **text_attrs(label_es, label_en),
            ),
            html.Strong(
                value_es,
                className="profile-detail-value",
                **text_attrs(value_es, value_en),
            ),
        ],
        className="profile-detail",
    )


def _permission_item(
    title_es: str,
    title_en: str,
    value_es: str,
    value_en: str,
) -> Component:
    return html.Div(
        [
            html.Span(
                title_es,
                className="user-permission-title",
                **text_attrs(title_es, title_en),
            ),
            html.Strong(
                value_es,
                className="user-permission-state",
                **text_attrs(value_es, value_en),
            ),
        ],
        className="user-permission-item",
    )


def _role_label(role: UserRole | str) -> str:
    value = role.value if isinstance(role, UserRole) else str(role)
    if value in {"comun", "common"}:
        return "common"
    if value == "admin":
        return "admin"
    return value


def _is_admin_role(role: UserRole | str) -> bool:
    value = role.value if isinstance(role, UserRole) else str(role)
    return value == UserRole.ADMIN.value


def _message(message: tuple[str, str] | None, *, is_error: bool) -> Component | str:
    if not message:
        return ""
    es, en = message
    class_name = "auth-message auth-message-error" if is_error else "auth-message auth-message-success"
    return html.Div(es, className=class_name, role="alert", **text_attrs(es, en))
