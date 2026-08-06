from __future__ import annotations

import os

from dash import Dash, Input, Output, State, dcc, html, no_update
from dash.development.base_component import Component
from flask_login import current_user

from app.auth.csrf import get_csrf_token
from app.auth.permissions import Permission, user_has_permission
from app.auth.rate_limit import create_rate_limiter
from app.dash.i18n import dash_attrs, text, text_attrs, ui_text
from app.dash.layouts.navigation import build_navbar
from app.http_security import rate_limit_key
from app.taxonomy import taxonomy_label, taxonomy_pair
from app.users.contact_service import (
    ContactDeliveryError,
    ContactValidationError,
    decode_contact_attachments,
    send_role_contact_email,
)
from app.users.schemas import UserRole, UserType

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
        "La nueva contraseña debe tener entre 12 y 128 caracteres.",
        "The new password must be between 12 and 128 characters.",
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
    user_type = getattr(current_user, "user_type", UserType.COMUN) or UserType.COMUN
    display_name = username or email or "Usuario"

    return html.Div(
        [
            build_navbar(active="user"),
            html.Main(
                [
                    html.Section(
                        [
                            _dashboard_header(display_name, role, user_type),
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
                                )
                            ),
                        ],
                        className="user-dashboard-shell",
                    )
                ],
                className="user-page-grid",
            ),
        ]
    )


def _dashboard_header(
    display_name: str,
    role: UserRole | str,
    user_type: UserType | str | None,
) -> Component:
    role_value = _role_label(role, user_type)
    role_value_en = _role_label(role, user_type, language="en")
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
                        "Gestiona tu perfil, utiliza tus herramientas y vuelve rápido a las áreas principales.",
                        className="user-lead",
                        **text_attrs(
                            "Gestiona tu perfil, utiliza tus herramientas y vuelve rápido a las áreas principales.",
                            "Manage your profile, use your tools, and jump back into the main work areas.",
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
        className="user-dashboard-header",
    )


def _build_dashboard(
    username: str,
    email: str,
    organization: str,
    role: UserRole | str,
    user_type: UserType | str | None,
) -> Component:
    return html.Div(
        [
            html.Section(
                [
                    _profile_card(username, email, organization, role, user_type),
                    _quick_actions(role, user_type),
                ],
                className="user-dashboard-main",
            ),
            html.Section(
                [
                    _contact_panel(username, email, role, user_type),
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
    user_type: UserType | str | None,
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
                        href="/user?mode=edit",
                        className="user-link-button",
                        **text_attrs("Editar", "Edit"),
                    ),
                ],
                className="user-card-header",
            ),
            html.Div(
                [
                    _detail_row(
                        "Nombre visible", "Display name", username or "No definido", "Not set"
                    ),
                    _detail_row("Email", "Email", email or "No definido", "Not set"),
                    _detail_row(
                        "Correo verificado",
                        "Verified email",
                        (
                            "S\u00ed"
                            if bool(getattr(current_user, "email_verified", True))
                            else "Pendiente"
                        ),
                        (
                            "Yes"
                            if bool(getattr(current_user, "email_verified", True))
                            else "Pending"
                        ),
                    ),
                    _detail_row("Organización", "Organization", organization_es, organization_en),
                    _detail_row(
                        "Perfil",
                        "Profile",
                        _role_label(role, user_type),
                        _role_label(role, user_type, language="en"),
                    ),
                ],
                className="profile-details user-detail-grid",
            ),
            _build_logout_form(),
        ],
        className="user-card user-profile-card",
    )


def _quick_actions(
    role: UserRole | str,
    user_type: UserType | str | None,
) -> Component:
    actions = [
        (
            "Ver estadísticas",
            "View statistics",
            "/statistics",
            "Comparar indicadores FRA e ILGA.",
            "Compare FRA and ILGA indicators.",
        ),
    ]
    profile = _user_type_value(user_type)
    if profile in {
        UserType.RRHH.value,
        UserType.POLITICO.value,
        UserType.ONG.value,
    } or _is_admin_role(role):
        actions.append(
            (
                ui_text("report_module_name", "es"),
                ui_text("report_module_name", "en"),
                "/informes",
                "Crear informes con opciones adaptadas a tu perfil.",
                "Create reports with options adapted to your profile.",
            )
        )
    if profile == UserType.DOCENTE.value or _is_admin_role(role):
        actions.append(
            (
                "Espacio Docente",
                "Educator space",
                "/didactica/docentes",
                "Crear juegos y utilizar recursos para el aula.",
                "Create games and use classroom resources.",
            )
        )
    if _is_admin_role(role):
        actions.append(
            (
                "Importar datos",
                "Import data",
                "/upload",
                "Validar e importar nuevas fuentes.",
                "Validate and import new sources.",
            )
        )
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


def _contact_panel(
    username: str,
    email: str,
    role: UserRole | str,
    user_type: UserType | str | None,
) -> Component:
    requested_role_options = [
        {"label": text(*taxonomy_pair("role", value)), "value": value}
        for value in (
            UserType.DOCENTE.value,
            UserType.RRHH.value,
            UserType.POLITICO.value,
            UserType.ONG.value,
            UserType.SOCIOLOGO.value,
            UserType.COMUN.value,
        )
    ]
    return html.Section(
        [
            html.H2("¡Contáctanos!", **text_attrs("¡Contáctanos!", "Contact us!")),
            html.P(
                "Solicita un nuevo perfil o envíanos cualquier sugerencia sobre RainbowLens Datahub.",
                **text_attrs(
                    "Solicita un nuevo perfil o envíanos cualquier sugerencia sobre RainbowLens Datahub.",
                    "Request a new profile or send us any suggestion about RainbowLens Datahub.",
                ),
            ),
            html.Div(
                [
                    _contact_field(
                        "Nombre",
                        "Name",
                        dcc.Input(
                            id="user-contact-name",
                            type="text",
                            value=username,
                            maxLength=80,
                            autoComplete="name",
                            readOnly=True,
                            className="auth-input user-contact-readonly",
                        ),
                    ),
                    _contact_field(
                        "Correo electrónico",
                        "Email address",
                        dcc.Input(
                            id="user-contact-email",
                            type="email",
                            value=email,
                            maxLength=254,
                            autoComplete="email",
                            readOnly=True,
                            className="auth-input user-contact-readonly",
                        ),
                    ),
                    _contact_field(
                        "Perfil solicitado (opcional)",
                        "Requested profile (optional)",
                        dcc.Dropdown(
                            id="user-contact-role",
                            options=requested_role_options,
                            value=None,
                            clearable=True,
                            className="user-contact-dropdown",
                        ),
                    ),
                    _contact_field(
                        "Asunto",
                        "Subject",
                        dcc.Input(
                            id="user-contact-subject",
                            type="text",
                            maxLength=160,
                            className="auth-input",
                        ),
                    ),
                    _contact_field(
                        "Mensaje",
                        "Message",
                        dcc.Textarea(
                            id="user-contact-message",
                            maxLength=4000,
                            className="user-contact-textarea",
                        ),
                    ),
                    html.Div(
                        [
                            html.Label(
                                "Documentación acreditativa",
                                htmlFor="user-contact-files",
                                **text_attrs(
                                    "Documentación acreditativa",
                                    "Supporting documentation",
                                ),
                            ),
                            dcc.Upload(
                                id="user-contact-files",
                                children=html.Div(
                                    text(
                                        "Adjunta hasta 3 archivos PDF, PNG, JPG, DOC o DOCX (5 MB por archivo).",
                                        "Attach up to 3 PDF, PNG, JPG, DOC or DOCX files (5 MB each).",
                                    )
                                ),
                                multiple=True,
                                className="user-contact-upload",
                            ),
                            html.P(
                                id="user-contact-file-summary",
                                className="auth-help",
                                **dash_attrs({"aria-live": "polite"}),
                            ),
                        ],
                        className="user-contact-field",
                    ),
                    html.Button(
                        "Enviar",
                        id="user-contact-submit",
                        type="button",
                        className="auth-button",
                        **text_attrs("Enviar", "Send"),
                    ),
                    html.P(
                        id="user-contact-status",
                        className="auth-message is-hidden",
                        role="status",
                        **dash_attrs({"aria-live": "polite"}),
                    ),
                    html.Span(
                        _role_label(role, user_type),
                        id="user-contact-current-role",
                        hidden=True,
                    ),
                ],
                className="user-contact-form",
            ),
        ],
        className="user-card user-contact-card",
    )


def _contact_field(label_es: str, label_en: str, control: Component) -> Component:
    control_id = getattr(control, "id", None)
    return html.Div(
        [html.Label(label_es, htmlFor=control_id, **text_attrs(label_es, label_en)), control],
        className="user-contact-field",
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
                maxLength=128,
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
                minLength=12,
                maxLength=128,
                autoComplete="new-password",
                className="auth-input",
            ),
            html.P(
                "Entre 12 y 128 caracteres. Déjala vacía si solo quieres actualizar nombre o email.",
                className="auth-help",
                **text_attrs(
                    "Entre 12 y 128 caracteres. Déjala vacía si solo quieres actualizar nombre o email.",
                    "Between 12 and 128 characters. Leave it empty to update only name or email.",
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


def register_user_page_callbacks(app: Dash) -> None:
    limiter = create_rate_limiter(
        max_attempts=max(1, int(os.getenv("CONTACT_MAX_ATTEMPTS", "5"))),
        window_seconds=max(60, int(os.getenv("CONTACT_WINDOW_SECONDS", "3600"))),
        namespace="user-contact",
    )

    @app.callback(
        Output("user-contact-file-summary", "children"),
        Input("user-contact-files", "filename"),
    )
    def summarize_contact_files(filenames: list[str] | str | None):
        if not filenames:
            return ""
        names = filenames if isinstance(filenames, list) else [filenames]
        return ", ".join(str(name) for name in names[:3])

    @app.callback(
        Output("user-contact-status", "children"),
        Output("user-contact-status", "className"),
        Output("user-contact-role", "value"),
        Output("user-contact-subject", "value"),
        Output("user-contact-message", "value"),
        Output("user-contact-files", "contents"),
        Output("user-contact-files", "filename"),
        Input("user-contact-submit", "n_clicks"),
        State("user-contact-name", "value"),
        State("user-contact-email", "value"),
        State("user-contact-role", "value"),
        State("user-contact-subject", "value"),
        State("user-contact-message", "value"),
        State("user-contact-files", "contents"),
        State("user-contact-files", "filename"),
        State("app-language-store", "data"),
        prevent_initial_call=True,
        running=[(Output("user-contact-submit", "disabled"), True, False)],
    )
    def submit_contact_request(
        clicks: int | None,
        name: str | None,
        email: str | None,
        requested_role: str | None,
        subject: str | None,
        message: str | None,
        contents: list[str] | str | None,
        filenames: list[str] | str | None,
        language: str | None,
    ):
        if not clicks or not user_has_permission(current_user, Permission.VIEW_DASHBOARD):
            return (no_update,) * 7
        clean_language = "en" if language == "en" else "es"
        if not bool(getattr(current_user, "email_verified", True)):
            return (
                (
                    "Verify your email before sending requests or attachments."
                    if clean_language == "en"
                    else "Verifica tu correo antes de enviar solicitudes o adjuntos."
                ),
                "auth-message auth-message-error",
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
            )
        limiter_key = rate_limit_key(subject=current_user.get_id() or "", scope="contact")
        if limiter.is_blocked(limiter_key):
            return (
                ui_text("contact_rate_limited", clean_language),
                "auth-message auth-message-error",
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
            )
        try:
            attachments = decode_contact_attachments(contents, filenames)
            send_role_contact_email(
                user_id=current_user.get_id() or "",
                name=getattr(current_user, "username", None) or name or "",
                email=getattr(current_user, "email", None) or email or "",
                current_role=_role_label(
                    getattr(current_user, "role", UserRole.COMMON),
                    getattr(current_user, "user_type", None),
                ),
                requested_role=requested_role or "",
                subject=subject or "",
                message=message or "",
                attachments=attachments,
            )
        except ContactValidationError:
            limiter.record_failure(limiter_key)
            return (
                ui_text("contact_validation_error", clean_language),
                "auth-message auth-message-error",
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
            )
        except ContactDeliveryError:
            limiter.record_failure(limiter_key)
            return (
                ui_text("contact_delivery_error", clean_language),
                "auth-message auth-message-error",
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
            )
        limiter.reset(limiter_key)
        return (
            ui_text("contact_success", clean_language),
            "auth-message auth-message-success",
            None,
            "",
            "",
            None,
            None,
        )


def _role_label(
    role: UserRole | str,
    user_type: UserType | str | None = None,
    *,
    language: str = "es",
) -> str:
    value = role.value if isinstance(role, UserRole) else str(role)
    if value == UserRole.ADMIN.value:
        return taxonomy_label("role", UserType.ADMIN.value, language)
    profile = _user_type_value(user_type) or UserType.COMUN.value
    return taxonomy_label("role", profile, language)


def _user_type_value(user_type: UserType | str | None) -> str:
    value = user_type.value if isinstance(user_type, UserType) else str(user_type or "")
    return UserType.DOCENTE.value if value == "profesor" else value


def _is_admin_role(role: UserRole | str) -> bool:
    value = role.value if isinstance(role, UserRole) else str(role)
    return value == UserRole.ADMIN.value


def _message(message: tuple[str, str] | None, *, is_error: bool) -> Component | str:
    if not message:
        return ""
    es, en = message
    class_name = (
        "auth-message auth-message-error" if is_error else "auth-message auth-message-success"
    )
    return html.Div(es, className=class_name, role="alert", **text_attrs(es, en))
