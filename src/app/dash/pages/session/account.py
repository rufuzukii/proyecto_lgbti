from __future__ import annotations

from dash import dcc, html
from dash.development.base_component import Component

from app.auth.csrf import get_csrf_token
from app.dash.i18n import dash_attrs, text, text_attrs
from app.dash.layouts.navigation import build_navbar
from app.dash.routes import route_path


def build_verify_email_layout(status: str | None = None) -> Component:
    notice: Component | None = None
    if status == "verified":
        title = ("Correo verificado", "Email verified")
        message = (
            "Tu direcci\u00f3n se ha verificado correctamente. Ya puedes iniciar sesi\u00f3n.",
            "Your address has been verified. You can now sign in.",
        )
        content: Component = html.A(
            text("Iniciar sesi\u00f3n", "Sign in"),
            href=route_path("login"),
            className="auth-button auth-inline-action",
        )
    else:
        title = ("Revisa tu correo", "Check your email")
        messages = {
            "invalid": (
                "El enlace no es v\u00e1lido o ha caducado. Solicita uno nuevo.",
                "The link is invalid or has expired. Request a new one.",
            ),
            "delivery_failed": (
                "La cuenta se ha creado, pero el correo no pudo enviarse. Puedes solicitar otro enlace.",
                "The account was created, but the email could not be sent. You can request another link.",
            ),
            "sent": (
                "Si la direcci\u00f3n es v\u00e1lida, recibir\u00e1s un enlace de verificaci\u00f3n.",
                "If the address is valid, you will receive a verification link.",
            ),
            "registration_sent": (
                "Te hemos enviado un enlace de verificaci\u00f3n.",
                "We sent you a verification link.",
            ),
        }
        message = messages.get(
            status or "sent",
            (
                "Te hemos enviado un enlace de verificaci\u00f3n.",
                "We sent you a verification link.",
            ),
        )
        content = _email_request_form(
            action="/auth/resend-verification",
            button_es="Reenviar enlace",
            button_en="Resend link",
        )
        if status == "registration_sent":
            notice = _registration_spam_notice()
    return _account_shell(title, message, content, notice=notice)


def build_forgot_password_layout(status: str | None = None) -> Component:
    if status == "sent":
        message = (
            "Si existe una cuenta con esa direcci\u00f3n, recibir\u00e1s un enlace temporal.",
            "If an account exists for that address, you will receive a temporary link.",
        )
    else:
        message = (
            "Introduce tu correo y te enviaremos un enlace para crear una nueva contrase\u00f1a.",
            "Enter your email and we will send a link to create a new password.",
        )
    return _account_shell(
        ("Recuperar contrase\u00f1a", "Reset password"),
        message,
        _email_request_form(
            action="/auth/forgot-password",
            button_es="Enviar enlace",
            button_en="Send link",
        ),
    )


def build_reset_password_layout(
    token: str | None,
    *,
    status: str | None = None,
    error: str | None = None,
) -> Component:
    if status == "completed":
        return _account_shell(
            ("Contrase\u00f1a actualizada", "Password updated"),
            (
                "La contrase\u00f1a se ha cambiado y las sesiones anteriores se han invalidado.",
                "The password was changed and previous sessions were invalidated.",
            ),
            html.A(
                text("Iniciar sesi\u00f3n", "Sign in"),
                href=route_path("login"),
                className="auth-button auth-inline-action",
            ),
        )
    if not token:
        return _account_shell(
            ("Enlace no v\u00e1lido", "Invalid link"),
            (
                "Solicita un nuevo enlace de recuperaci\u00f3n.",
                "Request a new password recovery link.",
            ),
            html.A(
                text("Solicitar enlace", "Request link"),
                href=route_path("forgot_password"),
                className="auth-button auth-inline-action",
            ),
        )
    error_copy = {
        "weak_password": (
            "La contrase\u00f1a debe tener entre 12 y 128 caracteres.",
            "The password must be between 12 and 128 characters.",
        ),
        "password_mismatch": (
            "Las contrase\u00f1as no coinciden.",
            "The passwords do not match.",
        ),
        "invalid_token": (
            "El enlace no es v\u00e1lido o ha caducado.",
            "The link is invalid or has expired.",
        ),
        "storage": (
            "No ha sido posible cambiar la contrase\u00f1a en este momento.",
            "The password could not be changed right now.",
        ),
    }.get(error or "")
    form = html.Form(
        [
            dcc.Input(type="hidden", name="csrf_token", value=get_csrf_token()),
            dcc.Input(type="hidden", name="token", value=token),
            dcc.Input(
                type="hidden",
                name="language",
                value="es",
                className="current-language-input",
            ),
            (
                html.Div(
                    error_copy[0],
                    className="auth-message auth-message-error",
                    role="alert",
                    **text_attrs(*error_copy),
                )
                if error_copy
                else ""
            ),
            html.Label(
                text("Nueva contrase\u00f1a", "New password"),
                htmlFor="reset-password",
            ),
            dcc.Input(
                id="reset-password",
                name="password",
                type="password",
                minLength=12,
                maxLength=128,
                required=True,
                autoComplete="new-password",
                className="auth-input",
            ),
            html.Label(
                text("Repite la contrase\u00f1a", "Repeat password"),
                htmlFor="reset-password-confirmation",
            ),
            dcc.Input(
                id="reset-password-confirmation",
                name="password_confirmation",
                type="password",
                minLength=12,
                maxLength=128,
                required=True,
                autoComplete="new-password",
                className="auth-input",
            ),
            html.Button(
                text("Guardar contrase\u00f1a", "Save password"),
                type="submit",
                className="auth-button",
            ),
        ],
        action="/auth/reset-password",
        method="post",
        className="auth-form",
    )
    return _account_shell(
        ("Crear nueva contrase\u00f1a", "Create a new password"),
        (
            "Elige una contrase\u00f1a segura que no utilices en otros servicios.",
            "Choose a secure password that you do not use for other services.",
        ),
        form,
    )


def build_verification_required_layout() -> Component:
    return _account_shell(
        ("Verifica tu correo para continuar", "Verify your email to continue"),
        (
            "Esta funci\u00f3n requiere una direcci\u00f3n de correo verificada.",
            "This feature requires a verified email address.",
        ),
        html.A(
            text("Solicitar otro enlace", "Request another link"),
            href=route_path("verify_email"),
            className="auth-button auth-inline-action",
        ),
    )


def _email_request_form(*, action: str, button_es: str, button_en: str) -> Component:
    control_id = f"email-{action}".replace("/", "-")
    return html.Form(
        [
            dcc.Input(type="hidden", name="csrf_token", value=get_csrf_token()),
            dcc.Input(
                type="hidden",
                name="language",
                value="es",
                className="current-language-input",
            ),
            html.Label(text("Correo electr\u00f3nico", "Email address"), htmlFor=control_id),
            dcc.Input(
                id=control_id,
                name="email",
                type="email",
                required=True,
                maxLength=254,
                autoComplete="email",
                className="auth-input",
            ),
            html.Button(
                text(button_es, button_en),
                type="submit",
                className="auth-button",
            ),
        ],
        action=action,
        method="post",
        className="auth-form",
    )


def _registration_spam_notice() -> Component:
    message_es = (
        "Revisa tambi\u00e9n tu carpeta de Spam o correo no deseado por si el mensaje "
        "de verificaci\u00f3n hubiera llegado all\u00ed."
    )
    message_en = (
        "Also check your Spam or junk mail folder in case the verification message "
        "was delivered there."
    )
    return html.Div(
        [
            html.Span(
                "i",
                className="auth-secondary-notice-icon",
                **dash_attrs({"aria-hidden": "true"}),
            ),
            html.P(message_es, **text_attrs(message_es, message_en)),
        ],
        id="registration-spam-notice",
        className="auth-secondary-notice",
        role="note",
    )


def _account_shell(
    title: tuple[str, str],
    message: tuple[str, str],
    content: Component,
    *,
    notice: Component | None = None,
) -> Component:
    return html.Div(
        [
            build_navbar(active="login"),
            html.Main(
                html.Section(
                    html.Div(
                        [
                            html.P(
                                text("Seguridad de la cuenta", "Account security"),
                                className="auth-eyebrow",
                            ),
                            html.H1(text(*title)),
                            html.P(text(*message), className="auth-copy"),
                            notice or "",
                            content,
                            html.A(
                                text("Volver al inicio", "Back to home"),
                                href=route_path("home"),
                                className="auth-switch auth-security-home-link",
                            ),
                        ],
                        className="auth-card",
                    ),
                    className="auth-shell",
                ),
                className="page-shell",
            ),
        ]
    )
