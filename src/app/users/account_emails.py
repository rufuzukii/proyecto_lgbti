from __future__ import annotations

from email.message import EmailMessage
from html import escape
from urllib.parse import quote

from app.dash.routes import normalize_language, route_path
from app.mail.service import MailDeliveryResult, public_base_url, send_email


def send_verification_email(
    email: str,
    token: str,
    language: str = "es",
) -> MailDeliveryResult:
    selected = normalize_language(language)
    link = (
        f"{public_base_url()}/account/verify-email/{quote(token, safe='')}"
        f"?lang={selected}"
    )
    message = EmailMessage()
    message["To"] = email
    message["Subject"] = "RainbowLens DataHub \u00b7 Verifica tu correo / Verify your email"
    message.set_content(
        f"""RainbowLens DataHub

Confirma tu correo para activar las funciones protegidas:
{link}
Este enlace caduca y solo puede utilizarse una vez.

Confirm your email to activate protected features using the same link above.
This link expires and can only be used once."""
    )
    safe_link = escape(link, quote=True)
    message.add_alternative(
        f"""<!doctype html>
<html lang="{selected}">
  <body style="font-family:Arial,sans-serif;color:#202124;line-height:1.5">
    <h1 style="font-size:22px">RainbowLens DataHub</h1>
    <p>Confirma tu correo para activar las funciones protegidas.</p>
    <p>Confirm your email to activate protected features.</p>
    <p><a href="{safe_link}" style="display:inline-block;padding:12px 18px;
      border-radius:6px;background:#6f2dbd;color:#fff;text-decoration:none">
      Verificar correo / Verify email</a></p>
    <p>Este enlace caduca y solo puede utilizarse una vez.<br>
      This link expires and can only be used once.</p>
  </body>
</html>""",
        subtype="html",
    )
    return send_email(message, event_name="verification_email")


def send_password_reset_email(
    email: str,
    token: str,
    language: str = "es",
) -> MailDeliveryResult:
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
    return send_email(message, event_name="password_reset_email")
