from __future__ import annotations

from dash import dcc, html
from dash.development.base_component import Component
from flask_login import current_user

from app.core.auth.csrf import get_csrf_token
from app.modules.account.components import role_label
from app.modules.account.privacy.service import PrivacyStorageError, get_personal_data_inventory
from app.modules.account.users.schemas import (
    MAX_PASSWORD_LENGTH,
    MIN_PASSWORD_LENGTH,
    UserRole,
    UserType,
)
from app.web.i18n import dash_attrs, text, text_attrs
from app.web.navigation import build_navbar
from app.web.routes import route_path

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
        f"La nueva contraseña debe tener entre {MIN_PASSWORD_LENGTH} y {MAX_PASSWORD_LENGTH} caracteres.",
        f"The new password must be between {MIN_PASSWORD_LENGTH} and {MAX_PASSWORD_LENGTH} characters.",
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

PRIVACY_ERROR_MESSAGES = {
    "confirmation_required": (
        "Marca la casilla para confirmar que comprendes la eliminación.",
        "Tick the box to confirm that you understand the deletion.",
    ),
    "invalid_email": (
        "El correo introducido no coincide con el de tu cuenta.",
        "The email entered does not match your account.",
    ),
    "invalid_password": (
        "La contraseña no es correcta.",
        "The password is not correct.",
    ),
    "invalid_confirmation_text": (
        "Escribe exactamente ELIMINAR MI CUENTA.",
        "Type DELETE MY ACCOUNT exactly.",
    ),
    "last_admin": (
        "No puedes eliminar la última cuenta administradora activa.",
        "You cannot delete the last active administrator account.",
    ),
    "rate_limited": (
        "Se ha alcanzado el límite temporal de intentos. Inténtalo más tarde.",
        "The temporary attempt limit has been reached. Try again later.",
    ),
    "csrf": (
        "La sesión ha caducado. Actualiza la página antes de continuar.",
        "The session expired. Refresh the page before continuing.",
    ),
    "deletion_incomplete": (
        "No se ha podido completar la eliminación de tus datos. Inténtalo de nuevo o contacta con el equipo responsable.",
        "Your data could not be deleted. Try again or contact the responsible team.",
    ),
    "export_failed": (
        "No se ha podido preparar la copia de tus datos. Inténtalo de nuevo o contacta con el equipo responsable.",
        "Your data copy could not be prepared. Try again or contact the responsible team.",
    ),
}


def build_user_page_layout(
    status_code: str | None = None,
    error_code: str | None = None,
    mode: str | None = None,
    privacy_error: str | None = None,
) -> Component:
    status = STATUS_MESSAGES.get(status_code) if status_code is not None else None
    error = ERROR_MESSAGES.get(error_code) if error_code is not None else None
    is_editing = mode == "edit"
    username = getattr(current_user, "username", None) or ""
    email = getattr(current_user, "email", None) or ""
    organization = getattr(current_user, "organization", None) or ""
    role = getattr(current_user, "role", UserRole.COMMON)
    user_type = getattr(current_user, "user_type", UserType.COMUN) or UserType.COMUN
    return html.Div(
        [
            build_navbar(active="user"),
            html.Main(
                [
                    html.Section(
                        [
                            _dashboard_header(role, user_type),
                            _message(status, is_error=False),
                            _message(error, is_error=True),
                            (
                                _build_edit_panel(username, email, organization)
                                if is_editing
                                else _build_dashboard(
                                    username,
                                    email,
                                    organization,
                                    role,
                                    user_type,
                                    privacy_error=privacy_error,
                                    privacy_dialog_open=mode == "privacy",
                                )
                            ),
                        ],
                        className="user-dashboard-shell",
                    )
                ],
                className="user-page-grid app-page app-page-container",
            ),
        ]
    )


def _dashboard_header(
    role: UserRole | str,
    user_type: UserType | str | None,
) -> Component:
    role_value = role_label(role, user_type)
    role_value_en = role_label(role, user_type, language="en")
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
                        "Gestiona tu perfil",
                        **text_attrs("Gestiona tu perfil", "Manage your profile"),
                    ),
                    html.P(
                        "Consulta y actualiza los datos de tu cuenta, revisa tus permisos y accede a las opciones de privacidad desde este espacio.",
                        className="user-lead",
                        **text_attrs(
                            "Consulta y actualiza los datos de tu cuenta, revisa tus permisos y accede a las opciones de privacidad desde este espacio.",
                            "Review and update your account details, check your permissions, and access your privacy options from this page.",
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
                    html.Strong(
                        role_value,
                        className="user-role-value",
                        **text_attrs(role_value, role_value_en),
                    ),
                ],
                className="user-role-badge",
            ),
        ],
        className="user-dashboard-header app-page-header",
    )


def _build_dashboard(
    username: str,
    email: str,
    organization: str,
    role: UserRole | str,
    user_type: UserType | str | None,
    *,
    privacy_error: str | None = None,
    privacy_dialog_open: bool = False,
) -> Component:
    return html.Div(
        [
            _profile_card(username, email, organization),
            _privacy_zone(
                username,
                email,
                organization,
                role,
                user_type,
                error_code=privacy_error,
                dialog_open=privacy_dialog_open,
            ),
        ],
        className="user-dashboard-grid",
    )


def _profile_card(
    username: str,
    email: str,
    organization: str,
) -> Component:
    organization_es = organization or "Sin organización"
    organization_en = organization or "No organization"
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
                        href=f"{route_path('profile')}?mode=edit",
                        className="user-link-button",
                        **text_attrs("Editar", "Edit"),
                    ),
                ],
                className="user-card-header",
            ),
            html.Div(
                [
                    _detail_row(
                        "Nombre visible",
                        "Display name",
                        username or "No definido",
                        username or "Not set",
                    ),
                    _detail_row(
                        "Correo electrónico",
                        "Email",
                        email or "No definido",
                        email or "Not set",
                    ),
                    _detail_row("Organización", "Organization", organization_es, organization_en),
                ],
                className="profile-details user-detail-grid",
            ),
            _build_logout_form(),
        ],
        className="user-card user-profile-card",
    )


def _privacy_zone(
    username: str,
    email: str,
    organization: str,
    role: UserRole | str,
    user_type: UserType | str | None,
    *,
    error_code: str | None,
    dialog_open: bool,
) -> Component:
    inventory = None
    try:
        user_id = str(getattr(current_user, "get_id", lambda: "")() or "")
        inventory = get_personal_data_inventory(user_id) if user_id else None
    except PrivacyStorageError:
        # The deletion service performs the authoritative inventory again. A
        # preview outage must not turn the complete dashboard into a 500 page.
        inventory = None

    content_items: list[Component] = []
    if inventory is not None:
        if inventory.teacher_games:
            content_items.append(
                html.Li(
                    f"{inventory.teacher_games} juego(s) docente(s) privado(s).",
                    **text_attrs(
                        f"{inventory.teacher_games} juego(s) docente(s) privado(s).",
                        f"{inventory.teacher_games} private educator game(s).",
                    ),
                )
            )
        if inventory.import_logs:
            content_items.append(
                html.Li(
                    f"{inventory.import_logs} carga(s) o registro(s) de importación.",
                    **text_attrs(
                        f"{inventory.import_logs} carga(s) o registro(s) de importación.",
                        f"{inventory.import_logs} upload or import record(s).",
                    ),
                )
            )
    if not content_items:
        content_items.append(
            html.Li(
                "Los contenidos personales asociados que existan al confirmar.",
                **text_attrs(
                    "Los contenidos personales asociados que existan al confirmar.",
                    "Any associated personal content present at confirmation time.",
                ),
            )
        )

    error = PRIVACY_ERROR_MESSAGES.get(error_code or "")
    dialog = html.Dialog(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.H2(
                                "Confirmar eliminación",
                                id="privacy-delete-dialog-title",
                                **text_attrs("Confirmar eliminación", "Confirm deletion"),
                            ),
                            html.Button(
                                "X",
                                type="button",
                                className="privacy-dialog-close",
                                **dash_attrs(
                                    {
                                        "data-privacy-dialog-close": "true",
                                        "aria-label": "Cerrar confirmación",
                                        "data-i18n-aria-label-es": "Cerrar confirmación",
                                        "data-i18n-aria-label-en": "Close confirmation",
                                    }
                                ),
                            ),
                        ],
                        className="privacy-dialog-header",
                    ),
                    html.P(
                        "¿Quieres eliminar definitivamente tu cuenta y los datos personales asociados?",
                        className="privacy-dialog-question",
                        **text_attrs(
                            "¿Quieres eliminar definitivamente tu cuenta y los datos personales asociados?",
                            "Do you want to permanently delete your account and associated personal data?",
                        ),
                    ),
                    html.P(
                        "Esta acción no se puede deshacer.",
                        className="privacy-dialog-warning",
                        **text_attrs(
                            "Esta acción no se puede deshacer.",
                            "This action cannot be undone.",
                        ),
                    ),
                    html.Dl(
                        [
                            *_privacy_summary_row("Nombre", "Name", username or "No definido"),
                            *_privacy_summary_row("Correo", "Email", email),
                            *_privacy_summary_row(
                                "Organización",
                                "Organization",
                                organization or "Sin organización",
                                organization or "No organization",
                            ),
                            *_privacy_summary_row(
                                "Rol actual",
                                "Current role",
                                role_label(role, user_type),
                                role_label(role, user_type, language="en"),
                            ),
                        ],
                        className="privacy-account-summary",
                    ),
                    html.H3(
                        "Contenido que se eliminará",
                        **text_attrs("Contenido que se eliminará", "Content that will be deleted"),
                    ),
                    html.Ul(content_items, className="privacy-content-summary"),
                    _message(error, is_error=True),
                    html.Form(
                        [
                            dcc.Input(
                                type="hidden",
                                name="csrf_token",
                                value=get_csrf_token(),
                            ),
                            dcc.Input(
                                id="privacy-delete-language",
                                name="language",
                                type="hidden",
                                value="es",
                            ),
                            html.Label(
                                "Introduce tu correo",
                                htmlFor="privacy-delete-email",
                                **text_attrs("Introduce tu correo", "Enter your email"),
                            ),
                            dcc.Input(
                                id="privacy-delete-email",
                                name="email",
                                type="email",
                                required=True,
                                autoComplete="email",
                                maxLength=254,
                                className="auth-input",
                            ),
                            html.Label(
                                "Introduce tu contraseña",
                                htmlFor="privacy-delete-password",
                                **text_attrs("Introduce tu contraseña", "Enter your password"),
                            ),
                            dcc.Input(
                                id="privacy-delete-password",
                                name="password",
                                type="password",
                                required=True,
                                autoComplete="current-password",
                                maxLength=MAX_PASSWORD_LENGTH,
                                className="auth-input",
                            ),
                            html.Label(
                                [
                                    dcc.Checklist(
                                        id="privacy-confirm-checklist",
                                        options=[
                                            {
                                                "label": text(
                                                    "Comprendo que esta acción es permanente.",
                                                    "I understand that this action is permanent.",
                                                ),
                                                "value": "confirmed",
                                            }
                                        ],
                                        value=[],
                                        className="privacy-confirm-checklist",
                                    ),
                                    dcc.Input(
                                        id="privacy-confirm-value",
                                        name="confirmation_checked",
                                        type="hidden",
                                        value="",
                                    ),
                                ],
                                className="privacy-confirm-check",
                            ),
                            html.Label(
                                "Escribe ELIMINAR MI CUENTA",
                                htmlFor="privacy-delete-phrase",
                                **text_attrs(
                                    "Escribe ELIMINAR MI CUENTA",
                                    "Type DELETE MY ACCOUNT",
                                ),
                            ),
                            dcc.Input(
                                id="privacy-delete-phrase",
                                name="confirmation_text",
                                type="text",
                                required=True,
                                maxLength=40,
                                autoComplete="off",
                                className="auth-input",
                                placeholder="ELIMINAR MI CUENTA",
                            ),
                            html.Div(
                                [
                                    html.Button(
                                        "Cancelar",
                                        type="button",
                                        className="auth-button auth-button-secondary",
                                        **text_attrs("Cancelar", "Cancel"),
                                        **dash_attrs({"data-privacy-dialog-close": "true"}),
                                    ),
                                    html.Button(
                                        "Eliminar cuenta",
                                        type="submit",
                                        className="auth-button privacy-danger-button",
                                        **text_attrs("Eliminar cuenta", "Delete account"),
                                    ),
                                ],
                                className="privacy-dialog-actions",
                            ),
                        ],
                        action="/privacy/delete-account",
                        method="post",
                        className="privacy-delete-form",
                    ),
                ],
                className="privacy-dialog-content",
            )
        ],
        id="privacy-delete-dialog",
        className="privacy-dialog",
        **dash_attrs(
            {
                "aria-labelledby": "privacy-delete-dialog-title",
                "data-privacy-dialog": "true",
                "data-auto-open": "true" if dialog_open else "false",
            }
        ),
    )

    return html.Section(
        [
            html.H2("Zona de privacidad", **text_attrs("Zona de privacidad", "Privacy area")),
            html.P(
                "Gestiona tu privacidad y tus datos personales.",
                **text_attrs(
                    "Gestiona tu privacidad y tus datos personales.",
                    "Manage your privacy and personal data.",
                ),
            ),
            html.Div(
                [
                    html.Form(
                        [
                            dcc.Input(type="hidden", name="csrf_token", value=get_csrf_token()),
                            html.Button(
                                "Descargar mis datos",
                                type="submit",
                                className="auth-button auth-button-secondary",
                                **text_attrs("Descargar mis datos", "Download my data"),
                            ),
                        ],
                        action="/privacy/export",
                        method="post",
                    ),
                    html.Button(
                        "Eliminar mis datos",
                        type="button",
                        className="auth-button privacy-danger-button",
                        **text_attrs("Eliminar mis datos", "Delete my data"),
                        **dash_attrs(
                            {
                                "data-privacy-dialog-open": "privacy-delete-dialog",
                                "aria-haspopup": "dialog",
                            }
                        ),
                    ),
                ],
                className="privacy-zone-actions",
            ),
            dialog,
        ],
        className="user-card privacy-zone-card",
    )


def _privacy_summary_row(
    label_es: str,
    label_en: str,
    value_es: str,
    value_en: str | None = None,
) -> list[Component]:
    return [
        html.Dt(label_es, **text_attrs(label_es, label_en)),
        html.Dd(value_es, **text_attrs(value_es, value_en or value_es)),
    ]


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
            dcc.Input(
                type="hidden",
                name="language",
                value="es",
                className="current-language-input",
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
                minLength=2,
                maxLength=80,
                autoComplete="name",
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
                maxLength=254,
                autoComplete="email",
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
                maxLength=MAX_PASSWORD_LENGTH,
                autoComplete="current-password",
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
                minLength=MIN_PASSWORD_LENGTH,
                maxLength=MAX_PASSWORD_LENGTH,
                autoComplete="new-password",
                className="auth-input",
            ),
            html.P(
                f"Entre {MIN_PASSWORD_LENGTH} y {MAX_PASSWORD_LENGTH} caracteres. Déjala vacía si solo quieres actualizar nombre o email.",
                className="auth-help",
                **text_attrs(
                    f"Entre {MIN_PASSWORD_LENGTH} y {MAX_PASSWORD_LENGTH} caracteres. Déjala vacía si solo quieres actualizar nombre o email.",
                    f"Between {MIN_PASSWORD_LENGTH} and {MAX_PASSWORD_LENGTH} characters. Leave it empty to update only name or email.",
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
                        href=route_path("profile"),
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
            dcc.Input(
                type="hidden",
                name="language",
                value="es",
                className="current-language-input",
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


def _message(message: tuple[str, str] | None, *, is_error: bool) -> Component | str:
    if not message:
        return ""
    es, en = message
    class_name = (
        "auth-message auth-message-error" if is_error else "auth-message auth-message-success"
    )
    return html.Div(es, className=class_name, role="alert", **text_attrs(es, en))
