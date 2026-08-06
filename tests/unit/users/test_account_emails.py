from __future__ import annotations

from email.message import EmailMessage
from typing import ClassVar, Self

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

    def send_message(self, message: EmailMessage) -> None:
        self.sent.append(message)


def test_verification_email_is_bilingual_and_uses_configured_public_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    _SmtpClient.sent.clear()
    _SmtpClient.logins.clear()
    monkeypatch.setenv("SMTP_HOST", "smtp.example.test")
    monkeypatch.setenv("SMTP_USERNAME", "sender@example.test")
    monkeypatch.setenv("SMTP_PASSWORD", "mail-secret")
    monkeypatch.setenv("SMTP_FROM_EMAIL", "sender@example.test")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://rainbowlens.example")
    monkeypatch.setattr(mail_service.smtplib, "SMTP_SSL", _SmtpClient)

    # Act
    account_emails.send_verification_email("person@example.test", "safe-token")

    # Assert
    assert len(_SmtpClient.sent) == 1
    message = _SmtpClient.sent[0]
    body = message.get_body()
    assert body is not None
    content = body.get_content()
    assert "Confirma tu correo" in content
    assert "Confirm your email" in content
    assert "https://rainbowlens.example/account/verify-email/safe-token" in content
    assert message["From"] == "sender@example.test"
    assert _SmtpClient.logins == [("sender@example.test", "mail-secret")]


def test_password_reset_email_never_contains_a_password(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    sent: list[EmailMessage] = []
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://rainbowlens.example")
    monkeypatch.setattr(account_emails, "send_email", sent.append)

    # Act
    account_emails.send_password_reset_email("person@example.test", "reset-token")

    # Assert
    body = sent[0].get_body()
    assert body is not None
    content = body.get_content()
    assert "reset-password?token=reset-token" in content
    assert "new_password=" not in content
    assert "a-secure-password" not in content


def test_mail_service_rejects_missing_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange
    monkeypatch.delenv("SMTP_HOST", raising=False)
    monkeypatch.delenv("SMTP_USERNAME", raising=False)
    monkeypatch.delenv("SMTP_FROM_EMAIL", raising=False)

    # Act / Assert
    with pytest.raises(mail_service.MailDeliveryError, match="smtp_not_configured"):
        mail_service.send_email(EmailMessage())
