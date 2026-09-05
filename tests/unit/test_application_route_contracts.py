from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest
from dash import dcc

from app.modules.didactics.custom_game_service import CustomGameAuthorizationError
from app.web import application


def _user(*, authenticated: bool, user_id: str = "user-1") -> SimpleNamespace:
    return SimpleNamespace(is_authenticated=authenticated, get_id=lambda: user_id)


@pytest.mark.parametrize(
    ("route_id", "builder_name", "params", "expected_args"),
    [
        ("home", "build_home_layout", {}, ()),
        ("privacy", "build_privacy_layout", {}, ()),
        ("privacy_deleted", "build_account_deleted_layout", {}, ()),
        ("statistics", "build_statistics_layout", {}, ()),
        ("trends", "build_trends_layout", {}, ()),
        ("spain", "build_spain_layout", {}, ()),
        ("about", "build_about_layout", {}, ()),
        ("didactica", "build_didactica_layout", {"notice": ["saved"]}, ("saved",)),
        ("dictionary", "build_dictionary_layout", {}, ()),
        ("presentations", "build_presentations_layout", {}, ()),
        ("word_search", "build_word_search_layout", {}, ()),
    ],
)
def test_public_route_dispatch_calls_its_owned_builder(
    monkeypatch,
    route_id: str,
    builder_name: str,
    params: dict[str, list[str]],
    expected_args: tuple,
) -> None:
    calls: list[tuple] = []
    monkeypatch.setattr(
        application,
        builder_name,
        lambda *args: calls.append(args) or f"layout:{route_id}",
    )

    result = application._build_page_for_route(route_id, "es", params, None)

    assert result == f"layout:{route_id}"
    assert calls == [expected_args]


@pytest.mark.parametrize("allowed", [False, True])
def test_games_route_enforces_permission(monkeypatch, allowed: bool) -> None:
    monkeypatch.setattr(application, "current_user", _user(authenticated=True))
    monkeypatch.setattr(application, "user_has_permission", lambda *_args: allowed)
    monkeypatch.setattr(application, "build_games_layout", lambda game: ("games", game))
    monkeypatch.setattr(application, "build_didactica_access_denied_layout", lambda: "denied")

    result = application._build_page_for_route("games", "es", {"game": ["quiz"]}, None)

    assert result == (("games", "quiz") if allowed else "denied")


@pytest.mark.parametrize(
    ("authenticated", "authorized", "expected"),
    [(False, False, "login"), (True, False, "redirect"), (True, True, "educators")],
)
def test_educators_route_has_login_role_and_success_branches(
    monkeypatch, authenticated: bool, authorized: bool, expected: str
) -> None:
    monkeypatch.setattr(application, "current_user", _user(authenticated=authenticated))
    monkeypatch.setattr(application, "can_access_docente_material", lambda _user: authorized)
    monkeypatch.setattr(application, "build_login_layout", lambda **_kwargs: "login")
    monkeypatch.setattr(application, "build_docente_layout", lambda: "educators")

    result = application._build_page_for_route("educators", "es", {}, None)

    assert ("redirect" if isinstance(result, dcc.Location) else result) == expected


@pytest.mark.parametrize("route_id", ["educator_create", "educator_activity"])
def test_owned_activity_routes_cover_login_role_owner_and_success(
    monkeypatch, route_id: str
) -> None:
    monkeypatch.setattr(application, "build_login_layout", lambda **_kwargs: "login")
    monkeypatch.setattr(application, "current_user", _user(authenticated=False))
    assert application._build_page_for_route(route_id, "en", {}, "?id=one") == "login"

    monkeypatch.setattr(application, "current_user", _user(authenticated=True))
    monkeypatch.setattr(application, "can_access_docente_material", lambda _user: False)
    denied = application._build_page_for_route(route_id, "en", {}, None)
    assert isinstance(denied, dcc.Location)

    monkeypatch.setattr(application, "can_access_docente_material", lambda _user: True)
    builder_name = (
        "build_activity_editor_layout"
        if route_id == "educator_create"
        else "build_custom_activity_layout"
    )
    monkeypatch.setattr(application, builder_name, lambda *_args: "activity")
    assert (
        application._build_page_for_route(route_id, "en", {"id": ["one"], "type": ["quiz"]}, None)
        == "activity"
    )

    def deny(*_args):
        raise CustomGameAuthorizationError("owner_required")

    monkeypatch.setattr(application, builder_name, deny)
    owner_denied = application._build_page_for_route(route_id, "en", {"id": ["one"]}, None)
    assert isinstance(owner_denied, dcc.Location)
    assert "docente_required" in cast(Any, owner_denied).href


def test_public_activity_and_reports_dispatch(monkeypatch) -> None:
    monkeypatch.setattr(application, "build_public_activity_layout", lambda public_id: public_id)
    assert (
        application._build_page_for_route(
            "educator_public_activity", "es", {"public_id": ["public-1"]}, None
        )
        == "public-1"
    )

    monkeypatch.setattr(application, "current_user", _user(authenticated=True))
    monkeypatch.setattr(application, "build_reports_access_denied_layout", lambda: "denied")
    monkeypatch.setattr(application, "user_has_permission", lambda *_args: False)
    assert application._build_page_for_route("reports", "es", {}, None) == "denied"
    monkeypatch.setattr(application, "user_has_permission", lambda *_args: True)
    monkeypatch.setattr(
        application,
        "build_reports_layout",
        lambda params, *, default_language: (params, default_language),
    )
    result = application._build_page_for_route(
        "reports", "en", {"countries": ["ES, FR"], "year": ["2026"]}, None
    )
    assert result == ({"countries": ["ES", "FR"], "year": "2026"}, "en")


@pytest.mark.parametrize(
    ("authenticated", "allowed", "expected"),
    [(False, False, "login"), (True, False, "denied"), (True, True, "upload")],
)
def test_upload_route_enforces_authentication_and_permission(
    monkeypatch, authenticated: bool, allowed: bool, expected: str
) -> None:
    monkeypatch.setattr(application, "current_user", _user(authenticated=authenticated))
    monkeypatch.setattr(application, "user_has_permission", lambda *_args: allowed)
    monkeypatch.setattr(application, "build_login_layout", lambda **_kwargs: "login")
    monkeypatch.setattr(application, "build_access_denied_layout", lambda: "denied")
    monkeypatch.setattr(application, "build_upload_layout", lambda: "upload")
    assert application._build_page_for_route("upload", "es", {}, None) == expected


@pytest.mark.parametrize("route_id", ["login", "register"])
def test_account_entry_routes_switch_between_forms_and_authenticated_page(
    monkeypatch, route_id: str
) -> None:
    monkeypatch.setattr(application, "build_user_page_layout", lambda **_kwargs: "user")
    monkeypatch.setattr(application, "current_user", _user(authenticated=True))
    assert application._build_page_for_route(route_id, "es", {}, None) == "user"

    monkeypatch.setattr(application, "current_user", _user(authenticated=False))
    builder = "build_login_layout" if route_id == "login" else "build_register_layout"
    monkeypatch.setattr(application, builder, lambda **kwargs: kwargs)
    result = application._build_page_for_route(
        route_id,
        "es",
        {"next": ["https://attacker.test"], "error": ["invalid"], "notice": ["saved"]},
        None,
    )
    assert result["next_path"] == "/es/perfil"
    assert result["error_code"] == "invalid"


def test_admin_users_route_covers_auth_role_success_and_storage_failure(monkeypatch) -> None:
    monkeypatch.setattr(application, "build_login_layout", lambda **_kwargs: "login")
    monkeypatch.setattr(application, "build_access_denied_layout", lambda: "denied")
    monkeypatch.setattr(application, "current_user", _user(authenticated=False))
    assert application._build_page_for_route("admin", "es", {}, None) == "login"

    monkeypatch.setattr(application, "current_user", _user(authenticated=True))
    monkeypatch.setattr(application, "_is_admin", lambda: False)
    assert application._build_page_for_route("admin", "es", {}, None) == "denied"

    monkeypatch.setattr(application, "_is_admin", lambda: True)
    page = SimpleNamespace(users=["one"], page=2, page_count=3, total=5)
    monkeypatch.setattr(application, "list_users_page", lambda **_kwargs: page)
    monkeypatch.setattr(
        application, "build_admin_users_layout", lambda *args, **kwargs: (args, kwargs)
    )
    _args, kwargs = application._build_page_for_route(
        "admin", "es", {"q": [" alex "], "page": ["2"]}, None
    )
    assert kwargs["search"] == "alex"
    assert kwargs["page"] == 2
    assert kwargs["total"] == 5

    monkeypatch.setattr(
        application,
        "list_users_page",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("offline")),
    )
    _args, kwargs = application._build_page_for_route("admin", "es", {}, None)
    assert kwargs["error_code"] == "storage"
    assert kwargs["total"] == 0


def test_admin_imports_and_profile_routes_cover_access_and_storage(monkeypatch) -> None:
    monkeypatch.setattr(application, "build_login_layout", lambda **_kwargs: "login")
    monkeypatch.setattr(application, "build_access_denied_layout", lambda: "denied")
    monkeypatch.setattr(application, "current_user", _user(authenticated=False))
    assert application._build_page_for_route("admin_imports", "es", {}, None) == "login"
    assert application._build_page_for_route("profile", "es", {}, None) == "login"

    monkeypatch.setattr(application, "current_user", _user(authenticated=True))
    monkeypatch.setattr(application, "_is_admin", lambda: False)
    assert application._build_page_for_route("admin_imports", "es", {}, None) == "denied"

    monkeypatch.setattr(application, "_is_admin", lambda: True)
    monkeypatch.setattr(application, "list_pending_import_logs", lambda: ["log"])
    monkeypatch.setattr(
        application, "build_admin_imports_layout", lambda logs, **kwargs: (logs, kwargs)
    )
    logs, kwargs = application._build_page_for_route("admin_imports", "es", {}, None)
    assert logs == ["log"] and kwargs["error_code"] is None

    monkeypatch.setattr(
        application,
        "list_pending_import_logs",
        lambda: (_ for _ in ()).throw(RuntimeError("offline")),
    )
    logs, kwargs = application._build_page_for_route("admin_imports", "es", {}, None)
    assert logs == [] and kwargs["error_code"] == "storage"

    monkeypatch.setattr(application, "build_user_page_layout", lambda **kwargs: kwargs)
    profile = application._build_page_for_route(
        "profile", "es", {"status": ["saved"], "mode": ["privacy"]}, None
    )
    assert profile["status_code"] == "saved"
    assert profile["mode"] == "privacy"


def test_unknown_route_returns_localized_404(monkeypatch) -> None:
    monkeypatch.setattr(application, "build_error_layout", lambda code, **kwargs: (code, kwargs))
    assert application._build_page_for_route("missing", "en", {}, None) == (
        "404",
        {"language": "en"},
    )
