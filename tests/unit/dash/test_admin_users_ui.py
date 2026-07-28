from pathlib import Path
from typing import Any

import app.dash.pages.admin.users as admin_users
from app.users.schemas import UserRead, UserRole


def test_user_row_starts_locked_with_edit_action(monkeypatch) -> None:
    monkeypatch.setattr(admin_users, "get_csrf_token", lambda: "csrf-token")
    row = admin_users._build_user_row(
        UserRead(
            id="user-1",
            username="Usuario",
            email="user@example.com",
            organization="Entidad",
            role=UserRole.COMMON,
        )
    )

    components = list(_walk(row))
    edit = _component_with_class(components, "admin-edit-button")
    save = _component_with_class(components, "admin-save-button")
    delete = _component_with_class(components, "admin-delete-button")
    editable_fields = [component for component in components if "admin-editable-input" in _classes(component)]
    role = _component_with_class(components, "admin-role-select")

    assert _props(row)["data-admin-user-row"] == "true"
    assert _props(row)["id"] == "admin-user-user-1"
    assert _props(edit)["type"] == "button"
    assert _props(edit)["data-admin-user-edit"] == "true"
    assert _props(edit)["aria-expanded"] == "false"
    assert _props(save)["hidden"] is True
    assert _props(save)["value"] == "update"
    assert _props(delete)["value"] == "delete"
    assert _props(delete)["data-admin-user-delete"] == "true"
    assert len(editable_fields) == 3
    assert all("readOnly" not in _props(field) for field in editable_fields)
    assert all("disabled" not in _props(field) for field in editable_fields)
    assert "disabled" not in _props(role)
    role_options = _props(role)["children"]
    assert [_props(option)["value"] for option in role_options] == ["common", "admin"]
    assert all("selected" not in _props(option) for option in role_options)


def test_admin_role_is_selected_natively_without_react_selected_prop() -> None:
    options = admin_users._admin_role_options(UserRole.ADMIN)

    assert [_props(option)["value"] for option in options] == ["admin", "common"]
    assert all("selected" not in _props(option) for option in options)


def test_success_message_auto_dismisses_but_error_remains_visible() -> None:
    success = admin_users._message(("Guardado", "Saved"), is_error=False)
    error = admin_users._message(("Error", "Error"), is_error=True)

    assert not isinstance(success, str)
    assert not isinstance(error, str)
    assert _props(success)["data-auto-dismiss-ms"] == "5000"
    assert _props(success)["role"] == "status"
    assert "data-auto-dismiss-ms" not in _props(error)
    assert _props(error)["role"] == "alert"


def test_delete_confirmation_dialog_has_cancel_and_confirm_actions() -> None:
    dialog = admin_users._delete_confirmation_dialog()
    components = list(_walk(dialog))
    cancel = _component_with_class(components, "admin-cancel-button")
    confirm = next(
        component
        for component in components
        if _props(component).get("data-admin-user-delete-confirm") == "true"
    )

    assert _props(dialog)["id"] == "admin-user-delete-dialog"
    assert _props(dialog)["aria-modal"] == "true"
    assert _props(dialog)["aria-labelledby"] == "admin-user-delete-title"
    assert "¿Quieres eliminar a este usuario?" in _text_content(dialog)
    assert _props(cancel)["type"] == "button"
    assert _props(cancel)["data-admin-user-delete-cancel"] == "true"
    assert _props(confirm)["type"] == "button"


def test_admin_assets_define_editing_and_saving_states() -> None:
    dash_root = Path(admin_users.__file__).parents[2]
    bootstrap = dash_root / "assets" / "js" / "40_bootstrap.js"
    admin_css = dash_root / "assets" / "admin.css"
    auth_css = dash_root / "assets" / "auth.css"

    javascript = bootstrap.read_text(encoding="utf-8")
    css = admin_css.read_text(encoding="utf-8")
    auth_styles = auth_css.read_text(encoding="utf-8")

    assert 'closest("[data-admin-user-edit]")' in javascript
    assert 'row.classList.add("is-editing")' in javascript
    assert "initializeAdminUserRows(document)" in javascript
    assert 'row.querySelectorAll(".admin-input")' in javascript
    assert "control.disabled = true" in javascript
    assert "control.disabled = false" in javascript
    assert "saveButton.hidden = false" in javascript
    assert 'adminUserRow.classList.add("is-saving")' in javascript
    assert 'adminUserSubmitter.setAttribute("aria-disabled", "true")' in javascript
    assert "adminUserSubmitter.disabled = true" not in javascript
    assert "scheduleAutoDismissMessages(document)" in javascript
    assert 'message.classList.add("is-dismissing")' in javascript
    assert "message.hidden = true" in javascript
    assert 'closest("[data-admin-user-delete]")' in javascript
    assert "openAdminUserDeleteDialog(adminUserDelete)" in javascript
    assert "dialog.showModal()" in javascript
    assert "submitAdminUserDelete(deleteButton)" in javascript
    assert "row.requestSubmit(deleteButton)" in javascript
    assert ".admin-table-row.is-editing" in css
    assert ".admin-input:disabled" in css
    assert "background: #ffffff" in css
    assert "border-radius: 999px" in css
    assert ".admin-delete-dialog::backdrop" in css
    assert ".admin-delete-dialog-actions" in css
    assert ".auth-message.is-dismissing" in auth_styles


def _walk(component: Any):
    yield component
    children = getattr(component, "children", None)
    if not isinstance(children, (list, tuple)):
        children = [children]
    for child in children:
        if hasattr(child, "to_plotly_json"):
            yield from _walk(child)


def _classes(component: Any) -> set[str]:
    return set(str(getattr(component, "className", "") or "").split())


def _component_with_class(components: list[Any], class_name: str) -> Any:
    return next(component for component in components if class_name in _classes(component))


def _props(component: Any) -> dict[str, Any]:
    return component.to_plotly_json()["props"]


def _text_content(component: Any) -> str:
    parts: list[str] = []
    for item in _walk(component):
        children = getattr(item, "children", None)
        values = children if isinstance(children, (list, tuple)) else [children]
        parts.extend(value for value in values if isinstance(value, str))
    return " ".join(parts)
