from __future__ import annotations

from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import app.dash.pages.statistics as statistics_page
import app.dash_app as dash_app_module
from app.dash.layouts import navigation
from app.users.schemas import UserRole, UserType


def _user(*, authenticated: bool):
    return SimpleNamespace(
        is_authenticated=authenticated,
        role=UserRole.COMMON if authenticated else UserRole.ANONYMOUS,
        user_type=UserType.COMUN if authenticated else None,
        username="Report user",
        organization="Example Org",
        get_id=lambda: "report-user-1" if authenticated else None,
    )


def _walk(component):
    if component is None:
        return
    if isinstance(component, (list, tuple)):
        for item in component:
            yield from _walk(item)
        return
    yield component
    children = getattr(component, "children", None)
    if children is not None:
        yield from _walk(children)


def _ids(component) -> set[str]:
    return {
        item_id
        for item in _walk(component)
        if isinstance((item_id := getattr(item, "id", None)), str)
    }


def _callback(app, name: str):
    return next(
        value["callback"].__wrapped__
        for value in app.callback_map.values()
        if getattr(value.get("callback"), "__wrapped__", None)
        and value["callback"].__wrapped__.__name__ == name
    )


def test_navbar_uses_short_report_name(monkeypatch) -> None:
    monkeypatch.setattr(navigation, "current_user", _user(authenticated=True))
    monkeypatch.setattr(navigation, "user_has_permission", lambda *_args: True)

    navbar = navigation.build_navbar()

    report_link = next(
        component
        for component in _walk(navbar)
        if getattr(component, "href", None) == "/es/informe"
    )
    label = report_link.children
    props = label.to_plotly_json()["props"]
    assert props["children"] == "Informe"
    assert props["data-i18n-en"] == "Report"


def test_statistics_report_link_preserves_selection_for_authenticated_user(monkeypatch) -> None:
    monkeypatch.setattr(dash_app_module, "initialize_mongo_indexes", lambda: None)
    app = dash_app_module.create_dash_app()
    monkeypatch.setattr(statistics_page, "current_user", _user(authenticated=True))

    href = _callback(app, "update_create_report_link")(
        "fra",
        2024,
        "Discrimination",
        "D1_1",
        "Yes",
        "Age",
        "25-39",
        "All",
        "All",
        None,
        ["ES", "PT"],
        "es",
    )

    parsed = urlsplit(href)
    params = parse_qs(parsed.query)
    assert parsed.path == "/es/informe"
    assert params["indicator_id"] == ["D1_1"]
    assert params["filter_a_value"] == ["25-39"]
    assert params["countries"] == ["ES,PT"]
    assert params["primary_country"] == ["ES"]


def test_anonymous_report_flow_redirects_to_login_with_notice_and_safe_next(monkeypatch) -> None:
    monkeypatch.setattr(dash_app_module, "initialize_mongo_indexes", lambda: None)
    app = dash_app_module.create_dash_app()
    anonymous = _user(authenticated=False)
    monkeypatch.setattr(statistics_page, "current_user", anonymous)
    monkeypatch.setattr(dash_app_module, "current_user", anonymous)

    destination = statistics_page._report_destination(
        "/es/informe?source=fra&countries=ES%2CPT",
        authenticated=False,
    )
    login_params = parse_qs(urlsplit(destination).query)
    assert urlsplit(destination).path == "/es/iniciar-sesion"
    assert login_params["notice"] == ["report_login_required"]
    assert login_params["next"] == ["/es/informe?source=fra&countries=ES%2CPT"]

    display_page = app.callback_map["page-content.children"]["callback"].__wrapped__
    redirect_component = display_page(
        "/es/informe",
        "?source=fra&countries=ES%2CPT&indicator_id=D1_1",
    )
    redirect_params = parse_qs(urlsplit(redirect_component.href).query)
    assert redirect_component.id == "reports-login-redirect"
    assert redirect_params["notice"] == ["report_login_required"]
    assert redirect_params["next"] == [
        "/es/informe?source=fra&countries=ES%2CPT&indicator_id=D1_1"
    ]

    monkeypatch.setattr("app.dash.pages.session.login.build_navbar", lambda **_kwargs: "")
    monkeypatch.setattr("app.dash.pages.session.login.get_csrf_token", lambda: "csrf")
    login_layout = display_page(
        "/es/iniciar-sesion",
        redirect_component.href.partition("?")[2],
    )
    assert "login-email" in _ids(login_layout)
    next_input = next(
        component for component in _walk(login_layout) if getattr(component, "name", None) == "next"
    )
    assert next_input.value == "/es/informe?source=fra&countries=ES%2CPT&indicator_id=D1_1"
    assert any(
        "auth-toast" in str(getattr(component, "className", ""))
        and component.to_plotly_json()["props"].get("data-auto-dismiss-ms") == "5000"
        for component in _walk(login_layout)
        if hasattr(component, "to_plotly_json")
    )
