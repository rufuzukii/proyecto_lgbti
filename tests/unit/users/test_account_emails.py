from __future__ import annotations

import json
import logging
import smtplib
from email.message import EmailMessage, Message
from typing import ClassVar, Self
from urllib.error import HTTPError

import pytest

from app.mail import service as mail_service
from app.users import account_emails


class _SmtpClient:
    sent: ClassVar[list[EmailMessage]] = []
    logins: ClassVar[list[tuple[str, str]]] = []

    def __init__(self, *_args, **_kwargs) -> None:
        pass

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def login(self, username: str, password: str) -> None:
        self.logins.append((username, password))

    def ehlo(self) -> None:
        return None

    def send_message(self, message: EmailMessage) -> dict[str, tuple[int, bytes]]:
        self.sent.append(message)
        return {}


class _HttpResponse:
    def __init__(self, status: int, payload: dict[str, str]) -> None:
        self.status = status
        self._payload = payload

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")


def _configure_smtp(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EMAIL_TRANSPORT", "smtp")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.test")
    monkeypatch.setenv("SMTP_PORT", "465")
    monkeypatch.setenv("SMTP_USE_SSL", "true")
    monkeypatch.setenv("SMTP_STARTTLS", "false")
    monkeypatch.setenv("SMTP_USERNAME", "sender@example.test")
    monkeypatch.setenv("SMTP_PASSWORD", "mail-secret")
    monkeypatch.setenv("SMTP_FROM_EMAIL", "sender@example.test")


def test_verification_email_is_bilingual_and_uses_configured_public_url(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Arrange
    _SmtpClient.sent.clear()
    _SmtpClient.logins.clear()
    _configure_smtp(monkeypatch)
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://rainbowlens.example")
    monkeypatch.setattr(mail_service.smtplib, "SMTP_SSL", _SmtpClient)
    caplog.set_level(logging.INFO)

    # Act
    result = account_emails.send_verification_email("person@example.test", "safe-token")

    # Assert
    assert len(_SmtpClient.sent) == 1
    message = _SmtpClient.sent[0]
    body = message.get_body()
    assert body is not None
    content = body.get_content()
    assert "Confirma tu correo" in content
    assert "Confirm your email" in content
    assert "https://rainbowlens.example/account/verify-email/safe-token" in content
    html_body = message.get_body(preferencelist=("html",))
    assert html_body is not None
    assert "Verificar correo / Verify email" in html_body.get_content()
    assert message["From"] == "sender@example.test"
    assert _SmtpClient.logins == [("sender@example.test", "mail-secret")]
    assert result.accepted is True
    assert result.provider == "smtp"
    assert "verification_email_send_started" in caplog.text
    assert "verification_email_provider_connected provider=smtp" in caplog.text
    assert "verification_email_sent category=EMAIL_SENT provider=smtp" in caplog.text


def test_password_reset_email_never_contains_a_password(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    sent: list[EmailMessage] = []
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://rainbowlens.example")
    monkeypatch.setattr(
        account_emails,
        "send_email",
        lambda message, **_kwargs: sent.append(message),
    )

    # Act
    account_emails.send_password_reset_email("person@example.test", "reset-token")

    # Assert
    body = sent[0].get_body()
    assert body is not None
    content = body.get_content()
    assert "/es/restablecer-contrasena?token=reset-token" in content
    assert "new_password=" not in content
    assert "a-secure-password" not in content


def test_mail_service_rejects_missing_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange
    monkeypatch.delenv("SMTP_HOST", raising=False)
    monkeypatch.delenv("SMTP_USERNAME", raising=False)
    monkeypatch.delenv("SMTP_PASSWORD", raising=False)
    monkeypatch.delenv("SMTP_FROM_EMAIL", raising=False)
    monkeypatch.setenv("EMAIL_TRANSPORT", "smtp")

    # Act / Assert
    message = EmailMessage()
    message["To"] = "person@example.test"
    with pytest.raises(mail_service.MailDeliveryError, match="email_not_configured") as error:
        mail_service.send_email(message)
    assert error.value.category == mail_service.MailErrorCategory.CONFIG
    assert set(error.value.fields) == {
        "SMTP_HOST",
        "SMTP_USERNAME",
        "SMTP_PASSWORD",
        "SMTP_FROM_EMAIL",
    }


def test_smtp_timeout_is_classified_as_network_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_smtp(monkeypatch)
    monkeypatch.setattr(
        mail_service.smtplib,
        "SMTP_SSL",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(TimeoutError("timed out")),
    )
    message = EmailMessage()
    message["To"] = "person@example.test"

    with pytest.raises(mail_service.MailDeliveryError) as error:
        mail_service.send_email(message, event_name="verification_email")

    assert error.value.category == mail_service.MailErrorCategory.NETWORK
    assert error.value.code == "email_network_failed"


def test_smtp_authentication_failure_is_classified_without_false_success(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    class AuthFailureClient(_SmtpClient):
        def login(self, _username: str, _password: str) -> None:
            raise smtplib.SMTPAuthenticationError(535, b"authentication failed")

    _configure_smtp(monkeypatch)
    monkeypatch.setattr(mail_service.smtplib, "SMTP_SSL", AuthFailureClient)
    message = EmailMessage()
    message["To"] = "person@example.test"
    caplog.set_level(logging.INFO)

    with pytest.raises(mail_service.MailDeliveryError) as error:
        mail_service.send_email(message, event_name="verification_email")

    assert error.value.category == mail_service.MailErrorCategory.AUTH
    assert "verification_email_sent" not in caplog.text
    assert "category=EMAIL_AUTH_ERROR" in caplog.text


def test_smtp_recipient_rejection_is_not_treated_as_provider_acceptance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class RefusalClient(_SmtpClient):
        def send_message(self, message: EmailMessage) -> dict[str, tuple[int, bytes]]:
            self.sent.append(message)
            return {"person@example.test": (550, b"rejected")}

    _configure_smtp(monkeypatch)
    monkeypatch.setattr(mail_service.smtplib, "SMTP_SSL", RefusalClient)
    message = EmailMessage()
    message["To"] = "person@example.test"

    with pytest.raises(mail_service.MailDeliveryError) as error:
        mail_service.send_email(message)

    assert error.value.category == mail_service.MailErrorCategory.PROVIDER_REJECTED
    assert error.value.code == "smtp_recipients_refused"


def test_incompatible_ssl_and_starttls_configuration_fails_before_connecting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_smtp(monkeypatch)
    monkeypatch.setenv("SMTP_STARTTLS", "true")
    message = EmailMessage()
    message["To"] = "person@example.test"

    with pytest.raises(mail_service.MailDeliveryError) as error:
        mail_service.send_email(message)

    assert error.value.category == mail_service.MailErrorCategory.CONFIG


def test_gmail_api_acceptance_uses_https_and_returns_provider_confirmation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EMAIL_TRANSPORT", "gmail_api")
    monkeypatch.setenv("GMAIL_API_CLIENT_ID", "client-id")
    monkeypatch.setenv("GMAIL_API_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("GMAIL_API_REFRESH_TOKEN", "refresh-token")
    monkeypatch.setenv("SMTP_FROM_EMAIL", "sender@example.test")
    requests: list[str] = []

    def fake_urlopen(request, *, timeout):
        assert timeout == 10.0
        requests.append(request.full_url)
        if request.full_url == mail_service.GMAIL_TOKEN_URL:
            return _HttpResponse(200, {"access_token": "short-lived-token"})
        return _HttpResponse(200, {"id": "provider-message-id"})

    monkeypatch.setattr(mail_service, "urlopen", fake_urlopen)
    message = EmailMessage()
    message["To"] = "person@example.test"
    message.set_content("Verification")

    result = mail_service.send_email(message, event_name="verification_email")

    assert result.accepted is True
    assert result.provider == "gmail_api"
    assert requests == [mail_service.GMAIL_TOKEN_URL, mail_service.GMAIL_SEND_URL]


def test_gmail_api_rejects_invalid_oauth_credentials_without_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EMAIL_TRANSPORT", "gmail_api")
    monkeypatch.setenv("GMAIL_API_CLIENT_ID", "client-id")
    monkeypatch.setenv("GMAIL_API_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("GMAIL_API_REFRESH_TOKEN", "refresh-token")
    monkeypatch.setenv("SMTP_FROM_EMAIL", "sender@example.test")
    attempts = 0

    def fail_auth(request, *, timeout):
        nonlocal attempts
        attempts += 1
        raise HTTPError(request.full_url, 401, "Unauthorized", Message(), None)

    monkeypatch.setattr(mail_service, "urlopen", fail_auth)
    message = EmailMessage()
    message["To"] = "person@example.test"

    with pytest.raises(mail_service.MailDeliveryError) as error:
        mail_service.send_email(message)

    assert error.value.category == mail_service.MailErrorCategory.AUTH
    assert attempts == 1


def test_public_email_links_require_an_explicit_deployment_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PUBLIC_BASE_URL", raising=False)
    monkeypatch.delenv("RENDER_EXTERNAL_URL", raising=False)
    monkeypatch.delenv("RENDER_EXTERNAL_HOSTNAME", raising=False)

    with pytest.raises(mail_service.MailDeliveryError, match="public_base_url_not_configured"):
        mail_service.public_base_url()


def test_public_email_links_use_the_render_hostname(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PUBLIC_BASE_URL", raising=False)
    monkeypatch.delenv("RENDER_EXTERNAL_URL", raising=False)
    monkeypatch.setenv("RENDER_EXTERNAL_HOSTNAME", "rainbowlens.onrender.com")

    assert mail_service.public_base_url() == "https://rainbowlens.onrender.com"
