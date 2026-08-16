from __future__ import annotations

import os
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from urllib.parse import urlsplit


class MailDeliveryError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class SmtpConfig:
    host: str
    port: int
    username: str
    password: str
    sender: str
    use_ssl: bool
    starttls: bool
    timeout_seconds: float


def send_email(message: EmailMessage) -> None:
    config = _smtp_config()
    if "From" not in message:
        message["From"] = config.sender
    context = ssl.create_default_context()
    try:
        if config.use_ssl:
            with smtplib.SMTP_SSL(
                config.host,
                config.port,
                timeout=config.timeout_seconds,
                context=context,
            ) as client:
                _authenticate_and_send(client, config, message)
        else:
            with smtplib.SMTP(
                config.host,
                config.port,
                timeout=config.timeout_seconds,
            ) as client:
                client.ehlo()
                if config.starttls:
                    client.starttls(context=context)
                    client.ehlo()
                _authenticate_and_send(client, config, message)
    except (OSError, smtplib.SMTPException) as exc:
        raise MailDeliveryError("mail_delivery_failed") from exc


def public_base_url() -> str:
    configured = (os.getenv("PUBLIC_BASE_URL") or os.getenv("RENDER_EXTERNAL_URL") or "").strip()
    if not configured:
        render_hostname = (os.getenv("RENDER_EXTERNAL_HOSTNAME") or "").strip()
        configured = f"https://{render_hostname}" if render_hostname else ""
    if not configured:
        raise MailDeliveryError("public_base_url_not_configured")
    parsed = urlsplit(configured)
    production = os.getenv("APP_ENV", "local").strip().casefold() == "production" and os.getenv(
        "LOCAL_MODE", ""
    ).strip().casefold() not in {"1", "true", "yes", "on"}
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or (production and parsed.scheme != "https")
    ):
        raise MailDeliveryError("invalid_public_base_url")
    return configured.rstrip("/")


def _smtp_config() -> SmtpConfig:
    host = (os.getenv("SMTP_HOST") or "").strip()
    username = (os.getenv("SMTP_USERNAME") or "").strip()
    password = os.getenv("SMTP_PASSWORD") or ""
    sender = (os.getenv("SMTP_FROM_EMAIL") or username).strip()
    use_ssl = _env_bool("SMTP_USE_SSL", True)
    if not host or not sender:
        raise MailDeliveryError("smtp_not_configured")
    try:
        port = int(os.getenv("SMTP_PORT", "465" if use_ssl else "587"))
        timeout = float(os.getenv("SMTP_TIMEOUT_SECONDS", "15"))
    except ValueError as exc:
        raise MailDeliveryError("invalid_smtp_configuration") from exc
    if port <= 0 or timeout <= 0:
        raise MailDeliveryError("invalid_smtp_configuration")
    return SmtpConfig(
        host=host,
        port=port,
        username=username,
        password=password,
        sender=sender,
        use_ssl=use_ssl,
        starttls=_env_bool("SMTP_STARTTLS", True),
        timeout_seconds=min(timeout, 30.0),
    )


def _authenticate_and_send(client: smtplib.SMTP, config: SmtpConfig, message: EmailMessage) -> None:
    if config.username:
        client.login(config.username, config.password)
    client.send_message(message)


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    return default if value is None else value.strip().casefold() in {"1", "true", "yes", "on"}
