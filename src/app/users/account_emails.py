from __future__ import annotations

from email.message import EmailMessage
from urllib.parse import quote

from app.dash.routes import normalize_language, route_path
from app.mail.service import public_base_url, send_email


def send_verification_email(email: str, token: str, language: str = "es") -> None:
    selected = normalize_language(language)
    link = (
        f"{public_base_url()}/account/verify-email/{quote(token, safe='')}"
        f"?lang={selected}"
    )
    message = EmailMessage()
    message["To"] = email
    message["Subject"] = "RainbowLens DataHub \u00b7 Verifica tu correo / Verify your email"
    message.set_content(
        f"""Confirma tu correo para activar las funciones protegidas de RainbowLens DataHub:
{link}
Este enlace caduca y solo puede utilizarse una vez.

Confirm your email to activate protected RainbowLens DataHub features:
{link}
This link expires and can only be used once."""
    )
    send_email(message)


def send_password_reset_email(email: str, token: str, language: str = "es") -> None:
    selected = normalize_language(language)
    link = (
        f"{public_base_url()}{route_path('reset_password', selected)}"
        f"?token={quote(token, safe='')}"
    )
    message = EmailMessage()
    message["To"] = email
    message["Subject"] = "RainbowLens DataHub \u00b7 Recupera tu contrase\u00f1a / Reset your password"
    message.set_content(
        f"""Utiliza este enlace para establecer una nueva contrase\u00f1a:
{link}
Si no lo solicitaste, ignora este mensaje. El enlace caduca y es de un solo uso.

Use this link to set a new password:
{link}
If you did not request this, ignore this message. The link expires and is single-use."""
    )
    send_email(message)
