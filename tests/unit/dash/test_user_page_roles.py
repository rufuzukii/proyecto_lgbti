from types import SimpleNamespace
from typing import Any

from app.dash.layouts import user_page
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


def test_panel_does_not_render_contact_form(monkeypatch) -> None:
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
    assert "¡Contáctanos!" not in _text(layout)
    assert "Contact us!" not in _text(layout)
    assert all(
        not str(getattr(component, "id", "") or "").startswith("about-contact")
        for component in _walk(layout)
    )


def test_personal_panel_does_not_render_quick_actions(monkeypatch) -> None:
    layout = _layout(monkeypatch, UserType.COMUN, UserRole.ADMIN)

    assert "Accesos rápidos" not in _text(layout)
    assert "Quick actions" not in _text(layout)
    assert all(
        getattr(component, "className", "") != "user-action-tile" for component in _walk(layout)
    )


def test_dashboard_blocks_are_single_column_with_privacy_last(monkeypatch) -> None:
    layout = _layout(monkeypatch, UserType.COMUN)
    dashboard = next(
        component
        for component in _walk(layout)
        if getattr(component, "className", "") == "user-dashboard-grid"
    )

    assert [getattr(component, "className", "") for component in dashboard.children] == [
        "user-card user-profile-card",
        "user-card privacy-zone-card",
    ]


def test_account_details_keep_real_values_in_english(monkeypatch) -> None:
    layout = _layout(monkeypatch, UserType.COMUN)
    values = [
        component.to_plotly_json()["props"]
        for component in _walk(layout)
        if getattr(component, "className", "") == "profile-detail-value"
    ]

    assert values[0]["data-i18n-en"] == "Alex"
    assert values[1]["data-i18n-en"] == "alex@example.test"
    assert values[0]["data-i18n-en"] != "Not set"
    assert values[1]["data-i18n-en"] != "Not set"


def _walk(component: Any):
    yield component
    children = getattr(component, "children", None)
    values = children if isinstance(children, (list, tuple)) else [children]
    for child in values:
        if hasattr(child, "to_plotly_json"):
            yield from _walk(child)


def _text(component: Any) -> str:
    return " ".join(
        str(item.children)
        for item in _walk(component)
        if isinstance(getattr(item, "children", None), str)
    )
