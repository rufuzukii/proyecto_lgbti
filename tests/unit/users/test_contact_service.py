import base64
from email.message import EmailMessage

import pytest

from app.users import contact_service


def _data_uri(content: bytes, mime_type: str = "application/pdf") -> str:
    return f"data:{mime_type};base64,{base64.b64encode(content).decode()}"


def test_contact_attachments_are_in_memory_safe_named_and_signature_checked() -> None:
    attachments = contact_service.decode_contact_attachments(
        _data_uri(b"%PDF-1.7\nproof"),
        "../../certificate.pdf",
    )

    assert len(attachments) == 1
    assert attachments[0].filename == "certificate.pdf"
    assert attachments[0].mime_type == "application/pdf"
    assert attachments[0].content.startswith(b"%PDF-")

    with pytest.raises(contact_service.ContactValidationError):
        contact_service.decode_contact_attachments(_data_uri(b"not-pdf"), "proof.pdf")
    with pytest.raises(contact_service.ContactValidationError):
        contact_service.decode_contact_attachments(_data_uri(b"payload"), "payload.exe")


def test_contact_email_uses_authenticated_metadata_and_in_memory_attachments(monkeypatch) -> None:
    sent: list[EmailMessage] = []

    class SMTP:
        def __init__(self, *_args, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def login(self, *_args):
            pass

        def send_message(self, message):
            sent.append(message)

    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_USERNAME", "sender@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "secret")
    monkeypatch.setattr(contact_service.smtplib, "SMTP_SSL", SMTP)
    attachment = contact_service.decode_contact_attachments(
        _data_uri(b"%PDF-1.7\nproof"), "certificate.pdf"
    )

    contact_service.send_role_contact_email(
        user_id="user-1",
        name="Ana <b>Example</b>",
        email="ana@example.com",
        current_role="Usuario",
        requested_role="",
        subject="Solicitud docente",
        message="Adjunto mi certificado.",
        attachments=attachment,
    )

    assert len(sent) == 1
    assert sent[0]["To"] == contact_service.CONTACT_RECIPIENT
    assert sent[0]["Reply-To"] == "ana@example.com"
    assert "user-1" in sent[0].get_body().get_content()
    assert "Perfil solicitado: No indicado" in sent[0].get_body().get_content()
    assert len(list(sent[0].iter_attachments())) == 1
