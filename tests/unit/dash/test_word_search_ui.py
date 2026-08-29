from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import app.modules.didactics.page as didactica_page
import app.web.application as dash_app_module
from app.modules.account.users.schemas import UserRole, UserType
from app.web.routes import route_path


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


def _user(
    *, authenticated: bool, role=UserRole.COMMON, user_type: UserType | None = UserType.COMUN
):
    return SimpleNamespace(
        is_authenticated=authenticated,
        role=role,
        user_type=user_type,
        get_id=lambda: "user-1",
    )


def test_word_search_layout_contains_an_interactive_board_and_memory_only_state(
    monkeypatch,
) -> None:
    # Arrange
    monkeypatch.setattr(didactica_page, "build_navbar", lambda **_kwargs: "")

    # Act
    layout = didactica_page.build_word_search_layout(seed=1234)
    components = list(_walk(layout))
    store = next(
        item for item in components if getattr(item, "id", None) == "didactica-word-search-state"
    )
    cells = [
        item
        for item in components
        if isinstance(getattr(item, "id", None), dict)
        and item.id.get("type") == "didactica-word-search-cell"
    ]

    # Assert
    assert store.storage_type == "memory"
    assert len(store.data["words"]) == 8
    assert 10 <= store.data["rows"] <= 15
    assert len(cells) == store.data["rows"] * store.data["columns"]
    assert all(cell.type == "button" and cell.role == "gridcell" for cell in cells)
    assert any(getattr(item, "id", None) == "didactica-word-search-new" for item in components)


@pytest.mark.parametrize(
    ("authenticated", "role", "user_type"),
    [
        (False, UserRole.ANONYMOUS, None),
        (True, UserRole.COMMON, UserType.COMUN),
        (True, UserRole.COMMON, UserType.DOCENTE),
        (True, UserRole.COMMON, UserType.RRHH),
        (True, UserRole.COMMON, UserType.POLITICO),
        (True, UserRole.COMMON, UserType.ONG),
        (True, UserRole.COMMON, UserType.SOCIOLOGO),
        (True, UserRole.ADMIN, UserType.ADMIN),
    ],
)
def test_word_search_route_is_public_for_every_role(
    monkeypatch, authenticated, role, user_type
) -> None:
    # Arrange
    monkeypatch.setattr(dash_app_module, "initialize_mongo_indexes", lambda: None)
    monkeypatch.setattr(didactica_page, "build_navbar", lambda **_kwargs: "")
    user = _user(authenticated=authenticated, role=role, user_type=user_type)
    monkeypatch.setattr(dash_app_module, "current_user", user)
    app = dash_app_module.create_dash_app()
    display_page = app.callback_map["page-content.children"]["callback"].__wrapped__

    # Act
    page = display_page(route_path("word_search", "es"), "")

    # Assert
    assert any(getattr(item, "id", None) == "didactica-word-search-state" for item in _walk(page))


def test_didactica_index_exposes_the_public_word_search_to_anonymous_users(monkeypatch) -> None:
    # Arrange
    monkeypatch.setattr(didactica_page, "build_navbar", lambda **_kwargs: "")
    monkeypatch.setattr(
        didactica_page,
        "current_user",
        _user(authenticated=False, role=UserRole.ANONYMOUS, user_type=None),
    )

    # Act
    layout = didactica_page.build_didactica_layout()
    hrefs = {getattr(item, "href", None) for item in _walk(layout)}

    # Assert
    assert route_path("word_search", "es") in hrefs
    assert f"{route_path('games', 'es')}?game=guess_term" in hrefs
    assert f"{route_path('games', 'es')}?game=rank_countries" in hrefs


def test_word_search_styles_cover_touch_mobile_and_dark_mode() -> None:
    # Arrange / Act
    stylesheet = Path("src/app/web/assets/didactica.css").read_text(encoding="utf-8")

    # Assert
    assert ".word-search-grid" in stylesheet
    assert "touch-action: manipulation" in stylesheet
    assert "aspect-ratio: 1" in stylesheet
    assert "@media (max-width: 760px)" in stylesheet
    assert ':root[data-theme="dark"] .word-search-cell.is-found' in stylesheet
    assert ".word-search-word.is-found" in stylesheet
