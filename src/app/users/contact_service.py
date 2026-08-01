from __future__ import annotations

import base64
import binascii
import os
import smtplib
import ssl
import unicodedata
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path
from typing import Any

import bleach
from email_validator import EmailNotValidError, validate_email

CONTACT_RECIPIENT = "rainbowlensdatahub@gmail.com"
MAX_CONTACT_ATTACHMENTS = 3
MAX_CONTACT_ATTACHMENT_BYTES = 5 * 1024 * 1024
MAX_CONTACT_TOTAL_BYTES = 10 * 1024 * 1024
ALLOWED_CONTACT_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".doc", ".docx"}
CONTACT_MIME_TYPES = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


class ContactValidationError(ValueError):
    pass


class ContactDeliveryError(RuntimeError):
    pass


@dataclass(frozen=True)
class ContactAttachment:
    filename: str
    content: bytes
    mime_type: str


def decode_contact_attachments(
    contents: list[str] | str | None,
    filenames: list[str] | str | None,
) -> list[ContactAttachment]:
    encoded_items = _as_list(contents)
    name_items = _as_list(filenames)
    if len(encoded_items) != len(name_items) or len(encoded_items) > MAX_CONTACT_ATTACHMENTS:
        raise ContactValidationError("invalid_attachment_count")
    attachments: list[ContactAttachment] = []
    total = 0
    for encoded, raw_name in zip(encoded_items, name_items, strict=True):
        safe_name = _safe_filename(raw_name)
        extension = Path(safe_name).suffix.casefold()
        if extension not in ALLOWED_CONTACT_EXTENSIONS:
            raise ContactValidationError("invalid_attachment_extension")
        header, separator, payload = encoded.partition(",")
        if not separator or not header.startswith("data:") or ";base64" not in header.casefold():
            raise ContactValidationError("invalid_attachment")
        estimated = max(0, (len(payload) * 3) // 4 - len(payload) + len(payload.rstrip("=")))
        if estimated > MAX_CONTACT_ATTACHMENT_BYTES:
            raise ContactValidationError("attachment_too_large")
        try:
            decoded = base64.b64decode(payload, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ContactValidationError("invalid_attachment") from exc
        total += len(decoded)
        if len(decoded) > MAX_CONTACT_ATTACHMENT_BYTES or total > MAX_CONTACT_TOTAL_BYTES:
            raise ContactValidationError("attachment_too_large")
        _validate_signature(extension, decoded)
        attachments.append(ContactAttachment(safe_name, decoded, CONTACT_MIME_TYPES[extension]))
    return attachments


def send_role_contact_email(
    *,
    user_id: str,
    name: str,
    email: str,
    current_role: str,
    requested_role: str,
    subject: str,
    message: str,
    attachments: list[ContactAttachment],
) -> None:
    clean_name = _single_line(name, 80)
    clean_email = _single_line(email, 254)
    clean_subject = _single_line(subject, 160)
    clean_message = _text(message, 4000)
    clean_requested = _single_line(requested_role, 40)
    if not all((user_id, clean_name, clean_email, clean_subject, clean_message)):
        raise ContactValidationError("missing_contact_fields")
    try:
        clean_email = validate_email(clean_email, check_deliverability=False).normalized
    except EmailNotValidError as exc:
        raise ContactValidationError("invalid_contact_email") from exc

    smtp_host = str(os.getenv("SMTP_HOST") or "").strip()
    smtp_username = str(os.getenv("SMTP_USERNAME") or "").strip()
    smtp_password = str(os.getenv("SMTP_PASSWORD") or "")
    sender = str(os.getenv("SMTP_FROM_EMAIL") or smtp_username or "").strip()
    if not smtp_host or not sender:
        raise ContactDeliveryError("smtp_not_configured")

    email_message = EmailMessage()
    email_message["Subject"] = f"RainbowLens · Contacto · {clean_subject}"
    email_message["From"] = sender
    email_message["To"] = CONTACT_RECIPIENT
    email_message["Reply-To"] = clean_email
    email_message.set_content(
        "\n".join(
            (
                f"Usuario: {clean_name}",
                f"Correo: {clean_email}",
                f"ID de usuario: {user_id}",
                f"Perfil actual: {_single_line(current_role, 40)}",
                f"Perfil solicitado: {clean_requested or 'No indicado'}",
                f"Asunto: {clean_subject}",
                "",
                clean_message,
            )
        )
    )
    for attachment in attachments:
        maintype, _, subtype = attachment.mime_type.partition("/")
        if not subtype:
            maintype, subtype = "application", "octet-stream"
        email_message.add_attachment(
            attachment.content,
            maintype=maintype,
            subtype=subtype,
            filename=attachment.filename,
        )

    try:
        port = int(os.getenv("SMTP_PORT", "465" if _env_bool("SMTP_USE_SSL", True) else "587"))
    except ValueError as exc:
        raise ContactDeliveryError("invalid_smtp_configuration") from exc
    context = ssl.create_default_context()
    try:
        if _env_bool("SMTP_USE_SSL", True):
            with smtplib.SMTP_SSL(smtp_host, port, timeout=20, context=context) as client:
                if smtp_username:
                    client.login(smtp_username, smtp_password)
                client.send_message(email_message)
        else:
            with smtplib.SMTP(smtp_host, port, timeout=20) as client:
                client.ehlo()
                if _env_bool("SMTP_STARTTLS", True):
                    client.starttls(context=context)
                    client.ehlo()
                if smtp_username:
                    client.login(smtp_username, smtp_password)
                client.send_message(email_message)
    except (OSError, smtplib.SMTPException) as exc:
        raise ContactDeliveryError("contact_delivery_failed") from exc


def _text(value: Any, maximum: int) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or "")).strip()
    return bleach.clean(normalized, tags=[], attributes={}, strip=True)[:maximum].strip()


def _single_line(value: Any, maximum: int) -> str:
    return " ".join(_text(value, maximum).split())[:maximum].strip()


def _safe_filename(value: str) -> str:
    clean = Path(str(value or "").replace("\\", "/")).name
    clean = "".join(character for character in clean if character.isalnum() or character in "._-")
    if not clean or len(clean) > 120:
        raise ContactValidationError("invalid_attachment_name")
    return clean


def _validate_signature(extension: str, content: bytes) -> None:
    signatures = {
        ".pdf": (b"%PDF-",),
        ".png": (b"\x89PNG\r\n\x1a\n",),
        ".jpg": (b"\xff\xd8\xff",),
        ".jpeg": (b"\xff\xd8\xff",),
        ".doc": (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",),
        ".docx": (b"PK\x03\x04",),
    }
    if not any(content.startswith(signature) for signature in signatures[extension]):
        raise ContactValidationError("invalid_attachment_signature")


def _as_list(value: list[str] | str | None) -> list[str]:
    if value is None:
        return []
    return [str(item) for item in value] if isinstance(value, list) else [str(value)]


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    return default if value is None else value.strip().casefold() in {"1", "true", "yes", "on"}
