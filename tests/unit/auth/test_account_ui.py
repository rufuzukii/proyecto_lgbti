from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from app.dash.pages.session import account


def test_registration_sent_renders_one_bilingual_spam_notice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(account, "get_csrf_token", lambda: "csrf")
    monkeypatch.setattr(account, "build_navbar", lambda **_kwargs: "navbar")
    layout = account.build_verify_email_layout("registration_sent")
    notices = [
        component
        for component in _walk(layout)
        if getattr(component, "id", None) == "registration-spam-notice"
    ]

    assert len(notices) == 1
    assert notices[0].className == "auth-secondary-notice"
    assert notices[0].role == "note"
    copy = next(
        component
        for component in _walk(notices[0])
        if component.to_plotly_json()["props"].get("data-i18n-es")
    )
    assert copy.children == (
        "Revisa también tu carpeta de Spam o correo no deseado por si el mensaje "
        "de verificación hubiera llegado allí."
    )
    assert copy.to_plotly_json()["props"]["data-i18n-en"] == (
        "Also check your Spam or junk mail folder in case the verification message "
        "was delivered there."
    )


def test_spam_notice_is_absent_from_every_other_verification_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(account, "get_csrf_token", lambda: "csrf")
    monkeypatch.setattr(account, "build_navbar", lambda **_kwargs: "navbar")
    for status in (None, "sent", "delivery_failed", "invalid", "verified"):
        layout = account.build_verify_email_layout(status)
        assert all(
            getattr(component, "id", None) != "registration-spam-notice"
            for component in _walk(layout)
        )


def test_successful_resend_includes_the_spam_notice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(account, "get_csrf_token", lambda: "csrf")
    monkeypatch.setattr(account, "build_navbar", lambda **_kwargs: "navbar")

    layout = account.build_verify_email_layout("resend_sent")

    assert any(
        getattr(component, "id", None) == "registration-spam-notice"
        for component in _walk(layout)
    )


def test_spam_notice_styles_cover_light_dark_and_responsive_layout() -> None:
    assets = Path(__file__).resolve().parents[3] / "src" / "app" / "dash" / "assets"
    styles = (assets / "auth.css").read_text(encoding="utf-8")

    assert ".auth-secondary-notice {" in styles
    assert ':root[data-theme="dark"] .auth-secondary-notice' in styles
    assert 'body[data-theme="dark"] .auth-secondary-notice' in styles
    assert "display: flex;" in styles


def _walk(component: Any):
    yield component
    children = getattr(component, "children", None)
    values = children if isinstance(children, (list, tuple)) else [children]
    for child in values:
        if hasattr(child, "to_plotly_json"):
            yield from _walk(child)
