from __future__ import annotations

import base64
import json
import logging
import os
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import getaddresses, parseaddr
from enum import StrEnum
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

GMAIL_TOKEN_URL = "https://oauth2.googleapis.com/token"  # nosec B105
GMAIL_SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
MAX_MAIL_TIMEOUT_SECONDS = 15.0


class MailErrorCategory(StrEnum):
    CONFIG = "EMAIL_CONFIG_ERROR"
    AUTH = "EMAIL_AUTH_ERROR"
    NETWORK = "EMAIL_NETWORK_ERROR"
    PROVIDER_REJECTED = "EMAIL_PROVIDER_REJECTED"


class MailDeliveryError(RuntimeError):
    def __init__(
        self,
        code: str,
        category: MailErrorCategory = MailErrorCategory.PROVIDER_REJECTED,
        *,
        fields: tuple[str, ...] = (),
    ) -> None:
        super().__init__(code)
        self.code = code
        self.category = category
        self.fields = fields


@dataclass(frozen=True, slots=True)
class MailDeliveryResult:
    provider: str
    accepted: bool


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


@dataclass(frozen=True, slots=True)
class GmailApiConfig:
    client_id: str
    client_secret: str
    refresh_token: str
    sender: str
    timeout_seconds: float


def send_email(
    message: EmailMessage,
    *,
    event_name: str = "email",
) -> MailDeliveryResult:
    """Send one message and return only after the provider accepts it."""
    logger.info("%s_send_started", event_name)
    try:
        transport = _email_transport()
        if transport == "smtp":
            result = _send_with_smtp(message, _smtp_config(), event_name=event_name)
        else:
            result = _send_with_gmail_api(
                message,
                _gmail_api_config(),
                event_name=event_name,
            )
    except MailDeliveryError as exc:
        field_names = ",".join(exc.fields) if exc.fields else "none"
        logger.exception(
            "%s_send_failed category=%s code=%s fields=%s",
            event_name,
            exc.category.value,
            exc.code,
            field_names,
        )
        raise
    except (TimeoutError, OSError, URLError, smtplib.SMTPException) as exc:
        failure = _classified_delivery_error(exc)
        logger.exception(
            "%s_send_failed category=%s code=%s fields=none",
            event_name,
            failure.category.value,
            failure.code,
        )
        raise failure from None

    logger.info(
        "%s_sent category=EMAIL_SENT provider=%s",
        event_name,
        result.provider,
    )
    return result


def public_base_url() -> str:
    configured = (os.getenv("PUBLIC_BASE_URL") or os.getenv("RENDER_EXTERNAL_URL") or "").strip()
    if not configured:
        render_hostname = (os.getenv("RENDER_EXTERNAL_HOSTNAME") or "").strip()
        configured = f"https://{render_hostname}" if render_hostname else ""
    if not configured:
        raise MailDeliveryError(
            "public_base_url_not_configured",
            MailErrorCategory.CONFIG,
            fields=("PUBLIC_BASE_URL",),
        )
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
        raise MailDeliveryError("invalid_public_base_url", MailErrorCategory.CONFIG)
    return configured.rstrip("/")


def _email_transport() -> str:
    transport = (os.getenv("EMAIL_TRANSPORT") or "smtp").strip().casefold()
    if transport not in {"smtp", "gmail_api"}:
        raise MailDeliveryError(
            "unsupported_email_transport",
            MailErrorCategory.CONFIG,
            fields=("EMAIL_TRANSPORT",),
        )
    return transport


def _smtp_config() -> SmtpConfig:
    required = ("SMTP_HOST", "SMTP_USERNAME", "SMTP_PASSWORD", "SMTP_FROM_EMAIL")
    values = _required_environment(required)
    use_ssl = _env_bool("SMTP_USE_SSL", True)
    starttls = _env_bool("SMTP_STARTTLS", not use_ssl)
    try:
        port = int(_clean_optional_env("SMTP_PORT") or ("465" if use_ssl else "587"))
        timeout = float(_clean_optional_env("SMTP_TIMEOUT_SECONDS") or "15")
    except ValueError as exc:
        raise MailDeliveryError(
            "invalid_smtp_configuration",
            MailErrorCategory.CONFIG,
        ) from exc
    if (
        port <= 0
        or timeout <= 0
        or timeout > MAX_MAIL_TIMEOUT_SECONDS
        or (use_ssl and starttls)
        or (port == 465 and not use_ssl)
        or (port == 587 and use_ssl)
    ):
        raise MailDeliveryError("invalid_smtp_configuration", MailErrorCategory.CONFIG)
    _validate_sender(values["SMTP_FROM_EMAIL"])
    return SmtpConfig(
        host=values["SMTP_HOST"],
        port=port,
        username=values["SMTP_USERNAME"],
        password=values["SMTP_PASSWORD"],
        sender=values["SMTP_FROM_EMAIL"],
        use_ssl=use_ssl,
        starttls=starttls,
        timeout_seconds=timeout,
    )


def _gmail_api_config() -> GmailApiConfig:
    required = (
        "GMAIL_API_CLIENT_ID",
        "GMAIL_API_CLIENT_SECRET",
        "GMAIL_API_REFRESH_TOKEN",
        "SMTP_FROM_EMAIL",
    )
    values = _required_environment(required)
    try:
        timeout = float(_clean_optional_env("GMAIL_API_TIMEOUT_SECONDS") or "10")
    except ValueError as exc:
        raise MailDeliveryError(
            "invalid_gmail_api_configuration",
            MailErrorCategory.CONFIG,
        ) from exc
    if timeout <= 0 or timeout > MAX_MAIL_TIMEOUT_SECONDS:
        raise MailDeliveryError("invalid_gmail_api_configuration", MailErrorCategory.CONFIG)
    _validate_sender(values["SMTP_FROM_EMAIL"])
    return GmailApiConfig(
        client_id=values["GMAIL_API_CLIENT_ID"],
        client_secret=values["GMAIL_API_CLIENT_SECRET"],
        refresh_token=values["GMAIL_API_REFRESH_TOKEN"],
        sender=values["SMTP_FROM_EMAIL"],
        timeout_seconds=timeout,
    )


def _send_with_smtp(
    message: EmailMessage,
    config: SmtpConfig,
    *,
    event_name: str,
) -> MailDeliveryResult:
    _prepare_message(message, config.sender)
    context = ssl.create_default_context()
    if config.use_ssl:
        with smtplib.SMTP_SSL(
            config.host,
            config.port,
            timeout=config.timeout_seconds,
            context=context,
        ) as client:
            client.ehlo()
            return _authenticate_and_send(client, config, message, event_name=event_name)

    with smtplib.SMTP(
        config.host,
        config.port,
        timeout=config.timeout_seconds,
    ) as client:
        client.ehlo()
        if config.starttls:
            client.starttls(context=context)
            client.ehlo()
        return _authenticate_and_send(client, config, message, event_name=event_name)


def _authenticate_and_send(
    client: smtplib.SMTP,
    config: SmtpConfig,
    message: EmailMessage,
    *,
    event_name: str,
) -> MailDeliveryResult:
    client.login(config.username, config.password)
    logger.info("%s_provider_connected provider=smtp", event_name)
    refused = client.send_message(message)
    if refused:
        raise MailDeliveryError(
            "smtp_recipients_refused",
            MailErrorCategory.PROVIDER_REJECTED,
        )
    return MailDeliveryResult(provider="smtp", accepted=True)


def _send_with_gmail_api(
    message: EmailMessage,
    config: GmailApiConfig,
    *,
    event_name: str,
) -> MailDeliveryResult:
    _prepare_message(message, config.sender)
    access_token = _gmail_access_token(config)
    logger.info("%s_provider_connected provider=gmail_api", event_name)
    encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
    request = Request(
        GMAIL_SEND_URL,
        data=json.dumps({"raw": encoded_message}).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=utf-8",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=config.timeout_seconds) as response:  # nosec B310
            status = response.status
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise _gmail_http_error(exc, token_request=False) from None
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MailDeliveryError(
            "gmail_api_invalid_response",
            MailErrorCategory.PROVIDER_REJECTED,
        ) from exc
    if status != 200 or not isinstance(payload, dict) or not payload.get("id"):
        raise MailDeliveryError(
            "gmail_api_message_rejected",
            MailErrorCategory.PROVIDER_REJECTED,
        )
    return MailDeliveryResult(provider="gmail_api", accepted=True)


def _gmail_access_token(config: GmailApiConfig) -> str:
    request = Request(
        GMAIL_TOKEN_URL,
        data=urlencode(
            {
                "client_id": config.client_id,
                "client_secret": config.client_secret,
                "refresh_token": config.refresh_token,
                "grant_type": "refresh_token",
            }
        ).encode("ascii"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=config.timeout_seconds) as response:  # nosec B310
            status = response.status
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise _gmail_http_error(exc, token_request=True) from None
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MailDeliveryError("gmail_api_auth_failed", MailErrorCategory.AUTH) from exc
    access_token = payload.get("access_token") if isinstance(payload, dict) else None
    if status != 200 or not isinstance(access_token, str) or not access_token:
        raise MailDeliveryError("gmail_api_auth_failed", MailErrorCategory.AUTH)
    return access_token


def _gmail_http_error(exc: HTTPError, *, token_request: bool) -> MailDeliveryError:
    if token_request or exc.code in {401, 403}:
        return MailDeliveryError("gmail_api_auth_failed", MailErrorCategory.AUTH)
    if exc.code == 429 or 400 <= exc.code < 500:
        return MailDeliveryError(
            "gmail_api_message_rejected",
            MailErrorCategory.PROVIDER_REJECTED,
        )
    return MailDeliveryError("gmail_api_network_failed", MailErrorCategory.NETWORK)


def _prepare_message(message: EmailMessage, sender: str) -> None:
    configured_from = message.get("From")
    if configured_from is None:
        message["From"] = sender
    elif parseaddr(configured_from)[1].casefold() != sender.casefold():
        raise MailDeliveryError("sender_mismatch", MailErrorCategory.CONFIG)
    recipients = [address for _, address in getaddresses(message.get_all("To", [])) if address]
    if not recipients:
        raise MailDeliveryError("recipient_not_configured", MailErrorCategory.CONFIG)


def _validate_sender(sender: str) -> None:
    parsed = parseaddr(sender)[1]
    if not parsed or parsed.casefold() != sender.casefold() or "@" not in parsed:
        raise MailDeliveryError(
            "invalid_sender_configuration",
            MailErrorCategory.CONFIG,
            fields=("SMTP_FROM_EMAIL",),
        )


def _required_environment(names: tuple[str, ...]) -> dict[str, str]:
    values: dict[str, str] = {}
    missing: list[str] = []
    invalid: list[str] = []
    for name in names:
        raw = os.getenv(name)
        if raw is None or not raw.strip():
            missing.append(name)
            continue
        if raw != raw.strip() or _has_outer_quotes(raw):
            invalid.append(name)
            continue
        values[name] = raw
    if missing:
        raise MailDeliveryError(
            "email_not_configured",
            MailErrorCategory.CONFIG,
            fields=tuple(missing),
        )
    if invalid:
        raise MailDeliveryError(
            "invalid_email_configuration",
            MailErrorCategory.CONFIG,
            fields=tuple(invalid),
        )
    return values


def _clean_optional_env(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    clean = value.strip()
    if value != clean or _has_outer_quotes(value):
        raise MailDeliveryError(
            "invalid_email_configuration",
            MailErrorCategory.CONFIG,
            fields=(name,),
        )
    return clean or None


def _has_outer_quotes(value: str) -> bool:
    return len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}


def _env_bool(name: str, default: bool) -> bool:
    value = _clean_optional_env(name)
    if value is None:
        return default
    normalized = value.casefold()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise MailDeliveryError(
        "invalid_email_configuration",
        MailErrorCategory.CONFIG,
        fields=(name,),
    )


def _classified_delivery_error(exc: BaseException) -> MailDeliveryError:
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        return MailDeliveryError("smtp_authentication_failed", MailErrorCategory.AUTH)
    if isinstance(
        exc,
        (
            TimeoutError,
            OSError,
            URLError,
            ssl.SSLError,
            smtplib.SMTPConnectError,
            smtplib.SMTPServerDisconnected,
        ),
    ):
        return MailDeliveryError("email_network_failed", MailErrorCategory.NETWORK)
    return MailDeliveryError(
        "email_provider_rejected",
        MailErrorCategory.PROVIDER_REJECTED,
    )
