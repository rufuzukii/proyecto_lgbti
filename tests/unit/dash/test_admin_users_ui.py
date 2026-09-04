from pathlib import Path
from types import SimpleNamespace
from typing import Any

import app.modules.administration.users_page as admin_users
from app.modules.account.users.schemas import UserRead, UserRole, UserType


def test_admin_layout_builds_accessible_search_form_with_supported_dash_props(monkeypatch) -> None:
    monkeypatch.setattr(admin_users, "get_csrf_token", lambda: "csrf-token")
    monkeypatch.setattr(admin_users, "build_navbar", lambda **_kwargs: "")
    user = UserRead(
        id="user-1",
        username="Admin",
        email="admin@example.com",
        role=UserRole.ADMIN,
        user_type=UserType.ADMIN,
    )

    layout = admin_users.build_admin_users_layout([user], current_user_id=user.id)

    search = next(
        component
        for component in _walk(layout)
        if _props(component).get("id") == "admin-user-search"
    )
    label = next(
        component
        for component in _walk(layout)
        if _props(component).get("htmlFor") == "admin-user-search"
    )
    assert search.__class__.__name__ == "Input"
    assert _props(search)["type"] == "search"
    assert _props(search)["debounce"] is True
    assert "data-i18n-aria-label-es" not in _props(search)
    assert _props(label)["htmlFor"] == _props(search)["id"]


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
    cancel = next(
        component
        for component in components
        if _props(component).get("data-admin-user-cancel") == "true"
    )
    delete = _component_with_class(components, "admin-delete-button")
    editable_fields = [
        component for component in components if "admin-editable-input" in _classes(component)
    ]
    role = _component_with_class(components, "admin-role-select")

    assert _props(row)["data-admin-user-row"] == "true"
    assert _props(row)["id"] == "admin-user-user-1"
    assert _props(edit)["type"] == "button"
    assert _props(edit)["data-admin-user-edit"] == "true"
    assert _props(edit)["aria-expanded"] == "false"
    assert _props(save)["hidden"] is True
    assert _props(save)["value"] == "update"
    assert _props(cancel)["hidden"] is True
    assert _props(cancel)["type"] == "button"
    assert _props(delete)["value"] == "delete"
    assert _props(delete)["data-admin-user-delete"] == "true"
    assert len(editable_fields) == 3
    assert all("readOnly" not in _props(field) for field in editable_fields)
    assert all(_props(field)["disabled"] is True for field in editable_fields)
    assert all(
        not any(prop.startswith("data-i18n-aria-label-") for prop in _props(field))
        for field in editable_fields
    )
    assert _props(role)["disabled"] is True
    username, email, organization = editable_fields
    assert (_props(username)["minLength"], _props(username)["maxLength"]) == (2, 80)
    assert _props(email)["maxLength"] == 254
    assert _props(organization)["maxLength"] == 120
    labelled_controls = {
        _props(component)["htmlFor"]
        for component in components
        if _props(component).get("className") == "sr-only"
    }
    assert labelled_controls == {
        "admin-user-user-1-username",
        "admin-user-user-1-email",
        "admin-user-user-1-organization",
        "admin-user-user-1-role",
    }
    role_options = _props(role)["children"]
    assert [_props(option)["value"] for option in role_options] == [
        "comun",
        "docente",
        "rrhh",
        "politico",
        "ong",
        "sociologo",
        "admin",
    ]
    assert all("selected" not in _props(option) for option in role_options)


def test_admin_role_is_selected_natively_without_react_selected_prop() -> None:
    options = admin_users._admin_role_options(UserRole.ADMIN)

    assert [_props(option)["value"] for option in options] == [
        "admin",
        UserType.COMUN.value,
        UserType.DOCENTE.value,
        UserType.RRHH.value,
        UserType.POLITICO.value,
        UserType.ONG.value,
        UserType.SOCIOLOGO.value,
    ]
    assert all("selected" not in _props(option) for option in options)


def test_non_admin_canonical_role_is_preserved_in_options() -> None:
    options = admin_users._admin_role_options(UserType.DOCENTE)

    assert _props(options[0])["value"] == UserType.DOCENTE.value


def test_current_user_row_is_fully_disabled_in_admin_table(monkeypatch) -> None:
    monkeypatch.setattr(admin_users, "get_csrf_token", lambda: "csrf-token")
    user = UserRead(
        id="user-1",
        username="Admin",
        email="admin@example.com",
        role=UserRole.ADMIN,
        user_type=UserType.ADMIN,
        version="version-1",
    )

    row = admin_users._build_user_row(user, current_user_id="user-1", search="adm", page=2)

    components = list(_walk(row))
    edit = _component_with_class(components, "admin-edit-button")
    save = _component_with_class(components, "admin-save-button")
    delete = _component_with_class(components, "admin-delete-button")
    editable_fields = [
        component for component in components if "admin-editable-input" in _classes(component)
    ]
    role = _component_with_class(components, "admin-role-select")
    hidden_values = {
        _props(component).get("name"): _props(component).get("value")
        for component in components
        if _props(component).get("type") == "hidden"
    }
    assert "is-current-user" in _classes(row)
    assert _props(row)["aria-disabled"] == "true"
    assert _props(edit)["disabled"] is True
    assert _props(save)["disabled"] is True
    assert _props(delete)["disabled"] is True
    assert all(_props(field)["disabled"] is True for field in editable_fields)
    assert _props(role)["disabled"] is True
    assert hidden_values["version"] == "version-1"
    assert hidden_values["q"] == "adm"
    assert hidden_values["page"] == "2"


def test_admin_user_table_has_only_profile_role_and_required_actions(monkeypatch) -> None:
    monkeypatch.setattr(admin_users, "get_csrf_token", lambda: "csrf-token")
    user = UserRead(
        id="user-2",
        username="María",
        email="maria@example.com",
        role=UserRole.COMMON,
    )

    table = admin_users._build_users_table([user])
    rendered = _text_content(table)
    props = [_props(component) for component in _walk(table)]

    assert "Estado" not in rendered
    assert "Activar" not in rendered
    assert "Desactivar" not in rendered
    assert "Validación" not in rendered
    assert "Validada" not in rendered
    assert "Validar cuenta" not in rendered
    assert "Validation" not in str(table)
    assert "Validated" not in str(table)
    assert "Validate account" not in str(table)
    assert not any(item.get("value") == "toggle_active" for item in props)
    assert not any(item.get("value") == "validate" for item in props)


def test_admin_validation_styles_were_removed() -> None:
    stylesheet = Path("src/app/web/assets/admin.css").read_text(encoding="utf-8")

    assert "admin-validation" not in stylesheet
    assert "admin-validate-button" not in stylesheet


def test_admin_search_callback_updates_only_results_component(monkeypatch) -> None:
    monkeypatch.setattr(admin_users, "get_csrf_token", lambda: "csrf-token")
    monkeypatch.setattr(admin_users, "build_navbar", lambda **_kwargs: "")
    admin = SimpleNamespace(
        is_authenticated=True,
        role=UserRole.ADMIN,
        user_type=UserType.ADMIN,
        get_id=lambda: "admin-1",
    )
    result_user = UserRead(
        id="user-2",
        username="María",
        email="maria@example.com",
        role=UserRole.COMMON,
    )
    monkeypatch.setattr(admin_users, "current_user", admin)
    monkeypatch.setattr(
        admin_users,
        "list_users_page",
        lambda **kwargs: SimpleNamespace(
            users=[result_user], page=1, page_count=1, total=1, query=kwargs
        ),
    )
    from dash import Dash

    app = Dash(__name__, suppress_callback_exceptions=True)
    app.layout = admin_users.build_admin_users_layout([], current_user_id="admin-1")
    admin_users.register_admin_users_callbacks(app)
    callback = app.callback_map["admin-users-results.children"]["callback"].__wrapped__

    result = callback(1, None, "maria")

    result_components = list(_walk(SimpleNamespace(children=result)))
    assert any(
        _props(component).get("value") == "María"
        for component in result_components
        if hasattr(component, "to_plotly_json")
    )
    assert set(app.callback_map) == {"admin-users-results.children"}


def test_admin_pagination_preserves_search() -> None:
    pagination = admin_users._pagination("rainbow", 2, 4)

    assert not isinstance(pagination, str)
    links = [item for item in _walk(pagination) if getattr(item, "href", None)]
    assert [item.href for item in links] == [
        "/es/administracion?page=1&q=rainbow",
        "/es/administracion?page=3&q=rainbow",
    ]


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
    dash_root = Path(admin_users.__file__).parents[2] / "web"
    bootstrap = dash_root / "assets" / "js" / "40_bootstrap.js"
    admin_css = dash_root / "assets" / "admin.css"
    auth_css = dash_root / "assets" / "auth.css"

    javascript = bootstrap.read_text(encoding="utf-8")
    css = admin_css.read_text(encoding="utf-8")
    auth_styles = auth_css.read_text(encoding="utf-8")

    assert 'closest("[data-admin-user-edit]")' in javascript
    assert 'closest("[data-admin-user-cancel]")' in javascript
    assert 'row.classList.add("is-editing")' in javascript
    assert "initializeAdminUserRows(document)" in javascript
    assert 'row.querySelectorAll(".admin-input")' in javascript
    assert "control.disabled = true" in javascript
    assert "control.disabled = false" in javascript
    assert "saveButton.hidden = false" in javascript
    assert "cancelButton.hidden = false" in javascript
    assert "rememberAdminUserValues(row)" in javascript
    assert "restoreAdminUserValues(row)" in javascript
    assert "activeAdminUserRow !== row" in javascript
    assert "cancelAdminUserEdit(activeAdminUserRow, false)" in javascript
    assert 'activeAdminUserRow.classList.contains("is-saving")' in javascript
    assert 'row.classList.add("is-saving")' in javascript
    assert 'submitter.setAttribute("aria-disabled", "true")' in javascript
    assert "submitter.disabled = true" in javascript
    assert 'formData.set("action", "update")' in javascript
    assert '"X-Requested-With": "XMLHttpRequest"' in javascript
    assert "applySavedAdminUser(row, payload.user)" in javascript
    assert "finishAdminUserEdit(row, false)" in javascript
    assert 'row.classList.remove("is-saving")' in javascript
    assert "submitter.disabled = false" in javascript
    assert "deleteButton.disabled = isCurrentUser" in javascript
    assert "feedback.dataset.errorEs" in javascript
    assert "feedback.dataset.errorEn" in javascript
    assert "scheduleAutoDismissMessages(document)" in javascript
    assert 'message.classList.add("is-dismissing")' in javascript
    assert "message.hidden = true" in javascript
    assert 'closest("[data-admin-user-delete]")' in javascript
    assert "openAdminUserDeleteDialog(adminUserDelete)" in javascript
    assert "dialog.showModal()" in javascript
    assert "submitAdminUserDelete(deleteButton)" in javascript
    assert "row.requestSubmit(deleteButton)" in javascript
    assert "data-admin-user-deactivate" not in javascript
    assert "deactivateConfirmed" not in javascript
    assert ".admin-table-row.is-editing" in css
    assert ".admin-edit-actions" in css
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
