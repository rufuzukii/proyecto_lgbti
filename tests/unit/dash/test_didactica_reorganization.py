from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from app.dash.components.ranking_game import ranking_game_rows
from app.dash.pages import didactica
from app.dash.routes import localized_route_context
from app.edu.ranking_game_service import check_ranking_game
from app.users.schemas import UserRole


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


def _text(component) -> str:
    return " ".join(str(item) for item in _walk(component) if isinstance(item, str))


def _anonymous():
    return SimpleNamespace(
        is_authenticated=False,
        role=UserRole.ANONYMOUS,
        user_type=None,
        get_id=lambda: None,
    )


def _state(*, checked: bool = False) -> dict:
    state = {
        "game_id": "rank_countries",
        "year": 2026,
        "items": [
            {"country_code": "ES", "country_name": "Spain", "score": 78},
            {"country_code": "DE", "country_name": "Germany", "score": 69},
            {"country_code": "IT", "country_name": "Italy", "score": 24},
            {"country_code": "PL", "country_name": "Poland", "score": 0},
        ],
        "checked": False,
        "positions_correct": 0,
        "is_correct": False,
        "correct_order": [],
    }
    return check_ranking_game(state) if checked else state


def test_didactica_uses_one_row_per_section_and_exposes_games_directly(monkeypatch) -> None:
    # Arrange
    monkeypatch.setattr(didactica, "build_navbar", lambda **_kwargs: "")
    monkeypatch.setattr(didactica, "current_user", _anonymous())

    # Act
    layout = didactica.build_didactica_layout()
    components = list(_walk(layout))
    hrefs = {getattr(item, "href", None) for item in components}

    # Assert
    assert (
        len(
            [
                item
                for item in components
                if str(getattr(item, "className", "")).startswith("didactica-mode-row")
            ]
        )
        == 4
    )
    assert "/es/didactica/diccionario" in hrefs
    assert "/es/didactica/presentaciones" in hrefs
    assert "/es/didactica/juegos?game=guess_term" in hrefs
    assert "/es/didactica/juegos/sopa-de-letras" in hrefs
    assert "/es/didactica/juegos?game=rank_countries" in hrefs
    assert "/es/didactica/juegos" not in hrefs


def test_direct_cards_use_localized_english_routes(monkeypatch) -> None:
    # Arrange
    monkeypatch.setattr(didactica, "build_navbar", lambda **_kwargs: "")
    monkeypatch.setattr(didactica, "current_user", _anonymous())

    # Act
    with localized_route_context("en"):
        layout = didactica.build_didactica_layout()
    hrefs = {getattr(item, "href", None) for item in _walk(layout)}

    # Assert
    assert "/en/learning/dictionary" in hrefs
    assert "/en/learning/presentations" in hrefs
    assert "/en/learning/games?game=rank_countries" in hrefs
    assert "/en/learning/games/word-search" in hrefs


def test_games_catalog_redirects_to_didactica_and_unknown_games_are_not_routable(
    monkeypatch,
) -> None:
    # Arrange
    monkeypatch.setattr(didactica, "build_navbar", lambda **_kwargs: "")

    # Act
    catalog = didactica.build_games_layout()
    unknown = didactica.build_games_layout("removed_game")

    # Assert
    assert any(getattr(item, "href", None) == "/es/didactica" for item in _walk(catalog))
    assert any(getattr(item, "href", None) == "/es/didactica" for item in _walk(unknown))
    assert not any(getattr(item, "id", None) == "didactica-game-state" for item in _walk(unknown))


def test_ranking_game_hides_scores_until_check_and_localizes_country_names(monkeypatch) -> None:
    # Arrange
    monkeypatch.setattr(didactica, "build_navbar", lambda **_kwargs: "")
    monkeypatch.setattr(didactica, "new_ranking_game", lambda: _state())

    # Act
    layout = didactica.build_games_layout("rank_countries")
    initial_list = next(
        item for item in _walk(layout) if getattr(item, "id", None) == "didactica-ranking-list"
    )
    revealed = ranking_game_rows(_state(checked=True), "en")

    # Assert
    assert "%" not in _text(initial_list)
    assert "España" in _text(initial_list)
    assert "Spain" in _text(revealed)
    assert "Germany" in _text(revealed)
    assert "78%" in _text(revealed)
    assert "0%" in _text(revealed)


def test_didactica_rows_and_ranking_game_have_responsive_dark_theme_styles() -> None:
    # Arrange / Act
    stylesheet = Path("src/app/dash/assets/didactica.css").read_text(encoding="utf-8")

    # Assert
    assert ".didactica-mode-row" in stylesheet
    assert "grid-template-columns: repeat(3" in stylesheet
    assert "@media (max-width: 900px)" in stylesheet
    assert ".didactica-game-access-grid" in stylesheet
    assert ".ranking-game-row" in stylesheet
    assert "var(--panel-bg)" in stylesheet
    assert "var(--color-text)" in stylesheet
