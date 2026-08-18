from __future__ import annotations

import os

from dash import Dash, Input, Output, State, dcc, html, no_update
from dash.development.base_component import Component
from flask_login import current_user

from app.auth.rate_limit import create_rate_limiter
from app.dash.components.user_profile import role_label
from app.dash.i18n import dash_attrs, text, text_attrs, ui_text
from app.http_security import rate_limit_key
from app.taxonomy import taxonomy_pair
from app.users.contact_service import (
    ContactDeliveryError,
    ContactValidationError,
    decode_contact_attachments,
    send_role_contact_email,
)
from app.users.schemas import UserRole, UserType


def build_contact_panel() -> Component:
    authenticated = _is_authenticated()
    username = str(getattr(current_user, "username", "") or "") if authenticated else ""
    email = str(getattr(current_user, "email", "") or "") if authenticated else ""
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
            html.H2(
                "\u00a1Cont\u00e1ctanos!", **text_attrs("\u00a1Cont\u00e1ctanos!", "Contact us!")
            ),
            html.P(
                "Solicita un nuevo perfil o env\u00edanos cualquier sugerencia sobre RainbowLens Datahub.",
                **text_attrs(
                    "Solicita un nuevo perfil o env\u00edanos cualquier sugerencia sobre RainbowLens Datahub.",
                    "Request a new profile or send us any suggestion about RainbowLens Datahub.",
                ),
            ),
            html.Div(
                [
                    _contact_field(
                        "Nombre",
                        "Name",
                        dcc.Input(
                            id="about-contact-name",
                            type="text",
                            value=username,
                            required=True,
                            maxLength=80,
                            autoComplete="name",
                            readOnly=authenticated,
                            className=(
                                "auth-input about-contact-readonly"
                                if authenticated
                                else "auth-input"
                            ),
                        ),
                    ),
                    _contact_field(
                        "Correo electr\u00f3nico",
                        "Email address",
                        dcc.Input(
                            id="about-contact-email",
                            type="email",
                            value=email,
                            required=True,
                            maxLength=254,
                            autoComplete="email",
                            readOnly=authenticated,
                            className=(
                                "auth-input about-contact-readonly"
                                if authenticated
                                else "auth-input"
                            ),
                        ),
                    ),
                    _contact_field(
                        "Perfil solicitado (opcional)",
                        "Requested profile (optional)",
                        dcc.Dropdown(
                            id="about-contact-role",
                            options=requested_role_options,
                            value=None,
                            clearable=True,
                            className="about-contact-dropdown",
                        ),
                    ),
                    _contact_field(
                        "Asunto",
                        "Subject",
                        dcc.Input(
                            id="about-contact-subject",
                            type="text",
                            maxLength=160,
                            className="auth-input",
                        ),
                    ),
                    _contact_field(
                        "Mensaje",
                        "Message",
                        dcc.Textarea(
                            id="about-contact-message",
                            maxLength=4000,
                            className="about-contact-textarea",
                        ),
                    ),
                    html.Div(
                        [
                            html.Label(
                                "Documentaci\u00f3n acreditativa",
                                htmlFor="about-contact-files",
                                **text_attrs(
                                    "Documentaci\u00f3n acreditativa",
                                    "Supporting documentation",
                                ),
                            ),
                            dcc.Upload(
                                id="about-contact-files",
                                children=html.Div(
                                    text(
                                        "Adjunta hasta 3 archivos PDF, PNG, JPG, DOC o DOCX (5 MB por archivo).",
                                        "Attach up to 3 PDF, PNG, JPG, DOC or DOCX files (5 MB each).",
                                    )
                                ),
                                multiple=True,
                                className="about-contact-upload",
                            ),
                            html.P(
                                id="about-contact-file-summary",
                                className="auth-help",
                                **dash_attrs({"aria-live": "polite"}),
                            ),
                        ],
                        className="about-contact-field",
                    ),
                    html.Button(
                        "Enviar",
                        id="about-contact-submit",
                        type="button",
                        className="auth-button",
                        **text_attrs("Enviar", "Send"),
                    ),
                    html.P(
                        id="about-contact-status",
                        className="auth-message is-hidden",
                        role="status",
                        **dash_attrs({"aria-live": "polite"}),
                    ),
                ],
                className="about-contact-form",
            ),
        ],
        id="about-contact",
        className="about-contact-card user-card",
    )


def register_contact_form_callbacks(app: Dash) -> None:
    limiter = create_rate_limiter(
        max_attempts=max(1, int(os.getenv("CONTACT_MAX_ATTEMPTS", "5"))),
        window_seconds=max(60, int(os.getenv("CONTACT_WINDOW_SECONDS", "3600"))),
        namespace="about-contact",
    )

    @app.callback(
        Output("about-contact-file-summary", "children"),
        Input("about-contact-files", "filename"),
    )
    def summarize_contact_files(filenames: list[str] | str | None):
        if not filenames:
            return ""
        names = filenames if isinstance(filenames, list) else [filenames]
        return ", ".join(str(name) for name in names[:3])

    @app.callback(
        Output("about-contact-status", "children"),
        Output("about-contact-status", "className"),
        Output("about-contact-role", "value"),
        Output("about-contact-subject", "value"),
        Output("about-contact-message", "value"),
        Output("about-contact-files", "contents"),
        Output("about-contact-files", "filename"),
        Input("about-contact-submit", "n_clicks"),
        State("about-contact-name", "value"),
        State("about-contact-email", "value"),
        State("about-contact-role", "value"),
        State("about-contact-subject", "value"),
        State("about-contact-message", "value"),
        State("about-contact-files", "contents"),
        State("about-contact-files", "filename"),
        State("app-language-store", "data"),
        prevent_initial_call=True,
        running=[(Output("about-contact-submit", "disabled"), True, False)],
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
        if not clicks:
            return (no_update,) * 7
        clean_language = "en" if language == "en" else "es"
        authenticated = _is_authenticated()
        if authenticated and not bool(getattr(current_user, "email_verified", True)):
            return _error_result(
                "Verify your email before sending requests or attachments."
                if clean_language == "en"
                else "Verifica tu correo antes de enviar solicitudes o adjuntos."
            )

        user_id = str(current_user.get_id() or "") if authenticated else "anonymous"
        limiter_key = rate_limit_key(subject=user_id, scope="contact")
        if limiter.is_blocked(limiter_key):
            return _error_result(ui_text("contact_rate_limited", clean_language))

        resolved_name = (
            str(getattr(current_user, "username", "") or "") if authenticated else name or ""
        )
        resolved_email = (
            str(getattr(current_user, "email", "") or "") if authenticated else email or ""
        )
        resolved_role = (
            role_label(
                getattr(current_user, "role", UserRole.COMMON),
                getattr(current_user, "user_type", None),
            )
            if authenticated
            else role_label(UserRole.ANONYMOUS, UserType.COMUN)
        )
        try:
            attachments = decode_contact_attachments(contents, filenames)
            send_role_contact_email(
                user_id=user_id,
                name=resolved_name,
                email=resolved_email,
                current_role=resolved_role,
                requested_role=requested_role or "",
                subject=subject or "",
                message=message or "",
                attachments=attachments,
            )
        except ContactValidationError:
            limiter.record_failure(limiter_key)
            return _error_result(ui_text("contact_validation_error", clean_language))
        except ContactDeliveryError:
            limiter.record_failure(limiter_key)
            return _error_result(ui_text("contact_delivery_error", clean_language))
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


def _contact_field(label_es: str, label_en: str, control: Component) -> Component:
    control_id = getattr(control, "id", None)
    return html.Div(
        [html.Label(label_es, htmlFor=control_id, **text_attrs(label_es, label_en)), control],
        className="about-contact-field",
    )


def _is_authenticated() -> bool:
    try:
        return bool(current_user.is_authenticated)
    except AttributeError, RuntimeError:
        return False


def _error_result(message: str) -> tuple[object, ...]:
    return (
        message,
        "auth-message auth-message-error",
        no_update,
        no_update,
        no_update,
        no_update,
        no_update,
    )
