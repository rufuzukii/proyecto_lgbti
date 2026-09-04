from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from app.modules.account import login_page, profile_page, register_page
from app.modules.account.users.schemas import MAX_PASSWORD_LENGTH, MIN_PASSWORD_LENGTH, UserRole


def test_password_fields_use_the_central_12_to_32_character_policy(monkeypatch) -> None:
    monkeypatch.setattr(login_page, "build_navbar", lambda **_kwargs: "")
    monkeypatch.setattr(login_page, "get_csrf_token", lambda: "csrf")
    monkeypatch.setattr(register_page, "build_navbar", lambda **_kwargs: "")
    monkeypatch.setattr(register_page, "get_csrf_token", lambda: "csrf")
    monkeypatch.setattr(profile_page, "build_navbar", lambda **_kwargs: "")
    monkeypatch.setattr(profile_page, "get_csrf_token", lambda: "csrf")
    monkeypatch.setattr(profile_page, "get_personal_data_inventory", lambda _user_id: None)
    monkeypatch.setattr(
        profile_page,
        "current_user",
        SimpleNamespace(
            username="Alex",
            email="alex@example.test",
            organization="RainbowLens",
            role=UserRole.COMMON,
            user_type=None,
            get_id=lambda: "user-1",
        ),
    )

    layouts = [
        login_page.build_login_layout(),
        register_page.build_register_layout(),
        profile_page.build_user_page_layout(),
        profile_page.build_user_page_layout(mode="edit"),
    ]
    fields = {
        getattr(component, "id", None): component.to_plotly_json()["props"]
        for layout in layouts
        for component in _walk(layout)
        if getattr(component, "type", None) == "password"
    }

    assert fields["register-password"]["minLength"] == MIN_PASSWORD_LENGTH
    assert fields["register-password"]["maxLength"] == MAX_PASSWORD_LENGTH
    assert fields["profile-new-password"]["minLength"] == MIN_PASSWORD_LENGTH
    assert fields["profile-new-password"]["maxLength"] == MAX_PASSWORD_LENGTH
    assert fields["login-password"]["maxLength"] == MAX_PASSWORD_LENGTH
    assert fields["profile-current-password"]["maxLength"] == MAX_PASSWORD_LENGTH
    assert fields["privacy-delete-password"]["maxLength"] == MAX_PASSWORD_LENGTH
    rendered = " ".join(str(layout) for layout in layouts)
    assert "12 y 32 caracteres" in rendered
    assert "12 and 32 characters" in rendered
    assert "128 caracteres" not in rendered
    assert "128 characters" not in rendered


def _walk(component: Any):
    yield component
    children = getattr(component, "children", None)
    values = children if isinstance(children, (list, tuple)) else [children]
    for child in values:
        if hasattr(child, "to_plotly_json"):
            yield from _walk(child)
