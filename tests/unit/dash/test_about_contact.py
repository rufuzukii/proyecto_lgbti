from types import SimpleNamespace
from typing import Any

from dash import Dash, no_update

from app.dash.components import contact_form
from app.dash.layouts import about, user_page
from app.users.contact_service import ContactDeliveryError
from app.users.schemas import UserRole, UserType


def test_contact_is_last_about_section_and_editable_for_anonymous(monkeypatch) -> None:
    monkeypatch.setattr(about, "build_navbar", lambda **_kwargs: "")
    monkeypatch.setattr(
        contact_form,
        "current_user",
        SimpleNamespace(is_authenticated=False),
    )

    layout = about.build_about_layout()
    shell = next(
        item
        for item in _walk(layout)
        if "about-shell" in str(getattr(item, "className", "")).split()
    )

    assert shell.children[-1].id == "about-contact"
    assert _by_id(layout, "about-contact-name").value == ""
    assert _by_id(layout, "about-contact-email").value == ""
    assert _by_id(layout, "about-contact-name").readOnly is False
    assert _by_id(layout, "about-contact-email").readOnly is False


def test_contact_uses_fresh_readonly_account_data_after_session_change(monkeypatch) -> None:
    monkeypatch.setattr(about, "build_navbar", lambda **_kwargs: "")
    first_user = SimpleNamespace(
        is_authenticated=True,
        username="Alex",
        email="alex@example.test",
    )
    monkeypatch.setattr(contact_form, "current_user", first_user)
    first_layout = about.build_about_layout()

    assert _by_id(first_layout, "about-contact-name").value == "Alex"
    assert _by_id(first_layout, "about-contact-email").value == "alex@example.test"
    assert _by_id(first_layout, "about-contact-name").readOnly is True
    assert _by_id(first_layout, "about-contact-email").readOnly is True

    monkeypatch.setattr(
        contact_form,
        "current_user",
        SimpleNamespace(
            is_authenticated=True,
            username="Sam",
            email="sam@example.test",
        ),
    )
    second_layout = about.build_about_layout()

    assert _by_id(second_layout, "about-contact-name").value == "Sam"
    assert _by_id(second_layout, "about-contact-email").value == "sam@example.test"


def test_contact_labels_target_only_native_form_controls(monkeypatch) -> None:
    # Arrange
    monkeypatch.setattr(
        contact_form,
        "current_user",
        SimpleNamespace(is_authenticated=False),
    )

    # Act
    layout = contact_form.build_contact_panel()
    labels = [item for item in _walk(layout) if item.__class__.__name__ == "Label"]
    labelled_targets = {
        target
        for item in labels
        if isinstance((target := getattr(item, "htmlFor", None)), str)
    }

    # Assert
    assert labelled_targets == {
        "about-contact-name",
        "about-contact-email",
        "about-contact-subject",
        "about-contact-message",
    }
    assert all(
        _by_id(layout, target).__class__.__name__ in {"Input", "Textarea"}
        for target in labelled_targets
    )


def test_contact_composite_controls_use_accessible_group_labels(monkeypatch) -> None:
    # Arrange
    monkeypatch.setattr(
        contact_form,
        "current_user",
        SimpleNamespace(is_authenticated=False),
    )

    # Act
    layout = contact_form.build_contact_panel()
    role_group = _parent_of(layout, "about-contact-role")
    upload_group = _parent_of(layout, "about-contact-files")

    # Assert
    assert role_group.role == "group"
    assert role_group.to_plotly_json()["props"]["aria-labelledby"] == (
        "about-contact-role-label"
    )
    assert _by_id(layout, "about-contact-role-label").children == (
        "Perfil solicitado (opcional)"
    )
    assert upload_group.role == "group"
    assert upload_group.to_plotly_json()["props"]["aria-labelledby"] == (
        "about-contact-files-label"
    )
    assert _by_id(layout, "about-contact-files-label").children == (
        "Documentaci\u00f3n acreditativa"
    )


def test_contact_component_ids_are_unique_for_anonymous_and_authenticated_users(
    monkeypatch,
) -> None:
    for user in (
        SimpleNamespace(is_authenticated=False),
        SimpleNamespace(
            is_authenticated=True,
            username="Alex",
            email="alex@example.test",
        ),
    ):
        # Arrange
        monkeypatch.setattr(contact_form, "current_user", user)

        # Act
        layout = contact_form.build_contact_panel()
        identifiers = [item.id for item in _walk(layout) if getattr(item, "id", None)]

        # Assert
        assert len(identifiers) == len(set(identifiers))


def test_authenticated_submit_uses_account_data_as_source_of_truth(monkeypatch) -> None:
    callback = _submit_callback()
    sent: dict[str, Any] = {}
    monkeypatch.setattr(
        contact_form,
        "current_user",
        SimpleNamespace(
            is_authenticated=True,
            email_verified=True,
            role=UserRole.COMMON,
            user_type=UserType.COMUN,
            username="Alex Account",
            email="account@example.test",
            get_id=lambda: "user-1",
        ),
    )
    monkeypatch.setattr(contact_form, "decode_contact_attachments", lambda *_args: [])
    monkeypatch.setattr(contact_form, "rate_limit_key", lambda **_kwargs: "contact-user-1")
    monkeypatch.setattr(
        contact_form,
        "send_role_contact_email",
        lambda **kwargs: sent.update(kwargs),
    )

    result = callback(
        1,
        "Browser override",
        "attacker@example.test",
        None,
        "Solicitud",
        "Mensaje suficientemente claro",
        None,
        None,
        "es",
    )

    assert sent["user_id"] == "user-1"
    assert sent["name"] == "Alex Account"
    assert sent["email"] == "account@example.test"
    assert result[2:] == (None, "", "", None, None)


def test_anonymous_submit_uses_editable_form_values(monkeypatch) -> None:
    callback = _submit_callback()
    sent: dict[str, Any] = {}
    monkeypatch.setattr(
        contact_form,
        "current_user",
        SimpleNamespace(is_authenticated=False),
    )
    monkeypatch.setattr(contact_form, "decode_contact_attachments", lambda *_args: [])
    monkeypatch.setattr(contact_form, "rate_limit_key", lambda **_kwargs: "contact-anonymous")
    monkeypatch.setattr(
        contact_form,
        "send_role_contact_email",
        lambda **kwargs: sent.update(kwargs),
    )

    callback(
        1,
        "Visitante",
        "visitor@example.test",
        None,
        "Sugerencia",
        "Mensaje suficientemente claro",
        None,
        None,
        "es",
    )

    assert sent["user_id"] == "anonymous"
    assert sent["name"] == "Visitante"
    assert sent["email"] == "visitor@example.test"


def test_contact_error_preserves_form_values(monkeypatch) -> None:
    callback = _submit_callback()
    monkeypatch.setattr(
        contact_form,
        "current_user",
        SimpleNamespace(is_authenticated=False),
    )
    monkeypatch.setattr(contact_form, "decode_contact_attachments", lambda *_args: [])
    monkeypatch.setattr(contact_form, "rate_limit_key", lambda **_kwargs: "contact-error")

    def fail(**_kwargs):
        raise ContactDeliveryError("failed")

    monkeypatch.setattr(contact_form, "send_role_contact_email", fail)
    result = callback(
        1,
        "Visitante",
        "visitor@example.test",
        None,
        "Sugerencia",
        "Mensaje suficientemente claro",
        None,
        None,
        "en",
    )

    assert all(value is no_update for value in result[2:])


def test_user_panel_contains_no_contact_component(monkeypatch) -> None:
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
            role=UserRole.COMMON,
            user_type=UserType.COMUN,
        ),
    )

    layout = user_page.build_user_page_layout()

    assert _find_by_id(layout, "about-contact") is None
    assert "¡Contáctanos!" not in _text(layout)


def _submit_callback():
    app = Dash("about-contact-callback", suppress_callback_exceptions=True)
    contact_form.register_contact_form_callbacks(app)
    return next(
        metadata["callback"].__wrapped__
        for metadata in app.callback_map.values()
        if metadata["callback"].__wrapped__.__name__ == "submit_contact_request"
    )


def _walk(component: Any):
    yield component
    children = getattr(component, "children", None)
    values = children if isinstance(children, (list, tuple)) else [children]
    for child in values:
        if hasattr(child, "to_plotly_json"):
            yield from _walk(child)


def _by_id(component: Any, identifier: str):
    return next(item for item in _walk(component) if getattr(item, "id", None) == identifier)


def _find_by_id(component: Any, identifier: str):
    return next(
        (item for item in _walk(component) if getattr(item, "id", None) == identifier),
        None,
    )


def _parent_of(component: Any, identifier: str):
    return next(
        item
        for item in _walk(component)
        if any(
            getattr(child, "id", None) == identifier
            for child in (
                item.children
                if isinstance(getattr(item, "children", None), (list, tuple))
                else [getattr(item, "children", None)]
            )
        )
    )


def _text(component: Any) -> str:
    return " ".join(
        str(item.children)
        for item in _walk(component)
        if isinstance(getattr(item, "children", None), str)
    )
