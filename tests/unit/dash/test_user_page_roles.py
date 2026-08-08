from types import SimpleNamespace
from typing import Any

from dash import Dash, no_update

from app.dash.layouts import user_page
from app.users.contact_service import ContactDeliveryError
from app.users.schemas import UserRole, UserType


def _layout(monkeypatch, user_type: UserType, role: UserRole = UserRole.COMMON):
    monkeypatch.setattr(user_page, "get_csrf_token", lambda: "csrf")
    monkeypatch.setattr(user_page, "build_navbar", lambda **_kwargs: "")
    monkeypatch.setattr(
        user_page,
        "current_user",
        SimpleNamespace(
            is_authenticated=True,
            username="Alex",
            email="alex@example.test",
            organization="Rainbow Org",
            role=role,
            user_type=user_type,
        ),
    )
    return user_page.build_user_page_layout()


def test_panel_replaces_permissions_with_prefilled_contact_form(monkeypatch) -> None:
    layout = _layout(monkeypatch, UserType.COMUN)

    assert "Permisos" not in _text(layout)
    assert "Permissions" not in _text(layout)
    account_detail_labels = [
        component.to_plotly_json()["props"]
        for component in _walk(layout)
        if getattr(component, "className", "") == "profile-detail-label"
    ]
    assert all(props.get("data-i18n-es") != "Perfil" for props in account_detail_labels)
    assert all(props.get("data-i18n-en") != "Profile" for props in account_detail_labels)
    assert _by_id(layout, "user-contact-name").value == "Alex"
    assert _by_id(layout, "user-contact-email").value == "alex@example.test"
    assert _by_id(layout, "user-contact-name").readOnly is True
    assert _by_id(layout, "user-contact-email").readOnly is True
    assert "opcional" in _text(layout)
    assert _by_id(layout, "user-contact-files").multiple is True


def test_personal_panel_does_not_render_quick_actions(monkeypatch) -> None:
    layout = _layout(monkeypatch, UserType.COMUN, UserRole.ADMIN)

    assert "Accesos rápidos" not in _text(layout)
    assert "Quick actions" not in _text(layout)
    assert all(
        getattr(component, "className", "") != "user-action-tile"
        for component in _walk(layout)
    )


def test_contact_callback_clears_form_only_after_success_and_returns_safe_errors(monkeypatch) -> None:
    app = Dash("user-contact-callback", suppress_callback_exceptions=True)
    user_page.register_user_page_callbacks(app)
    callback = next(
        metadata["callback"].__wrapped__
        for metadata in app.callback_map.values()
        if metadata["callback"].__wrapped__.__name__ == "submit_contact_request"
    )
    monkeypatch.setattr(
        user_page,
        "current_user",
        SimpleNamespace(
            is_authenticated=True,
            role=UserRole.COMMON,
            user_type=UserType.COMUN,
            username="Alex",
            email="alex@example.com",
            get_id=lambda: "user-1",
        ),
    )
    monkeypatch.setattr(user_page, "decode_contact_attachments", lambda *_args: [])
    monkeypatch.setattr(user_page, "send_role_contact_email", lambda **_kwargs: None)
    monkeypatch.setattr(user_page, "rate_limit_key", lambda **_kwargs: "contact-user-1")

    success = callback(
        1,
        "Alex",
        "alex@example.com",
        None,
        "Solicitud",
        "Mensaje suficientemente claro",
        None,
        None,
        "es",
    )
    assert len(success) == 7
    assert success[2:] == (None, "", "", None, None)

    def fail(**_kwargs):
        raise ContactDeliveryError("failed")

    monkeypatch.setattr(user_page, "send_role_contact_email", fail)
    error = callback(2, "Alex", "alex@example.com", "docente", "Solicitud", "Mensaje", None, None, "en")
    assert len(error) == 7
    assert all(value is no_update for value in error[2:])


def _walk(component: Any):
    yield component
    children = getattr(component, "children", None)
    values = children if isinstance(children, (list, tuple)) else [children]
    for child in values:
        if hasattr(child, "to_plotly_json"):
            yield from _walk(child)


def _by_id(component: Any, identifier: str):
    return next(item for item in _walk(component) if getattr(item, "id", None) == identifier)


def _text(component: Any) -> str:
    return " ".join(
        str(item.children)
        for item in _walk(component)
        if isinstance(getattr(item, "children", None), str)
    )
