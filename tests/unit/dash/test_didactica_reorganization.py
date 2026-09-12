from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from dash import Dash

from app.modules.account.users.schemas import UserRole
from app.modules.didactics import page as didactica
from app.modules.didactics.ranking_component import ranking_game_rows
from app.modules.didactics.ranking_game_service import check_ranking_game
from app.web.routes import localized_route_context


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


def test_educator_term_catalog_uses_route_language_and_preserves_identifiers(monkeypatch) -> None:
    monkeypatch.setattr(didactica, "build_navbar", lambda **_kwargs: "")
    monkeypatch.setattr(didactica, "current_user", _anonymous())
    monkeypatch.setattr(didactica, "can_manage_own_edu_games", lambda _user: True)
    monkeypatch.setattr(didactica, "get_ilga_years", lambda: [2026])
    monkeypatch.setattr(didactica, "_legal_country_options", lambda _year: [])
    catalogs = {}
    for language in ("es", "en"):
        with localized_route_context(language):
            layout = didactica.build_activity_editor_layout(initial_game_type="word_search")
        dropdown = next(
            node for node in _walk(layout)
            if getattr(node, "id", None) == "teacher-editor-term-ids"
        )
        catalogs[language] = {option["value"]: option["label"] for option in dropdown.options}
    assert catalogs["es"].keys() == catalogs["en"].keys()
    assert "Lesbiana" in catalogs["es"].values()
    assert "Lesbian" in catalogs["en"].values()
    assert "Lesbiana" not in catalogs["en"].values()


def test_educator_callback_links_keep_the_selected_language(monkeypatch) -> None:
    app = Dash("educator-localized-links", suppress_callback_exceptions=True)
    didactica.register_didactica_callbacks(app)
    callbacks = {
        entry["callback"].__wrapped__.__name__: entry["callback"].__wrapped__
        for entry in app.callback_map.values()
        if getattr(entry.get("callback"), "__wrapped__", None)
    }
    activity = {"id": "test-activity", "public_id": "public-test", "game_type": "word_search"}
    monkeypatch.setattr(didactica, "current_user", _anonymous())
    monkeypatch.setattr(didactica, "can_manage_own_edu_games", lambda _user: True)
    monkeypatch.setattr(didactica, "save_owned_game", lambda *_args: activity)
    monkeypatch.setattr(didactica, "_teacher_activity_payload", lambda _values: {})
    monkeypatch.setattr(didactica, "list_owned_games", lambda _user: [activity])
    monkeypatch.setattr(didactica, "duplicate_owned_game", lambda *_args, **_kwargs: activity)
    monkeypatch.setattr(
        didactica, "ctx",
        SimpleNamespace(triggered_id={"type": "teacher-activity-duplicate", "index": "test-activity"}),
    )
    for language, base in (("es", "/es/didactica/juegos/actividad"), ("en", "/en/learning/games/activity")):
        saved = callbacks["save_teacher_activity"](1, None, language)
        assert f"{base}/public-test" in _text(saved[2])
        cards = callbacks["manage_teacher_activities"]([1], [], language)[0]
        links = [getattr(node, "href", "") for node in _walk(cards)]
        assert f"{base}/public-test" in links


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
    monkeypatch.setattr(didactica, "build_navbar", lambda **_kwargs: "")
    monkeypatch.setattr(didactica, "current_user", _anonymous())

    layout = didactica.build_didactica_layout()
    components = list(_walk(layout))
    hrefs = {getattr(item, "href", None) for item in components}

    assert (
        len(
            [
                item
                for item in components
                if str(getattr(item, "className", "")).startswith("didactica-mode-row")
            ]
        )
        == 3
    )
    assert "/es/didactica/diccionario" in hrefs
    assert "/es/didactica/presentaciones" in hrefs
    assert "/es/didactica/juegos?game=guess_term" in hrefs
    assert "/es/didactica/juegos/sopa-de-letras" in hrefs
    assert "/es/didactica/juegos?game=rank_countries" in hrefs
    assert "/es/didactica/juegos" not in hrefs


def test_direct_cards_use_localized_english_routes(monkeypatch) -> None:
    monkeypatch.setattr(didactica, "build_navbar", lambda **_kwargs: "")
    monkeypatch.setattr(didactica, "current_user", _anonymous())

    with localized_route_context("en"):
        layout = didactica.build_didactica_layout()
    hrefs = {getattr(item, "href", None) for item in _walk(layout)}

    assert "/en/learning/dictionary" in hrefs
    assert "/en/learning/presentations" in hrefs
    assert "/en/learning/games?game=rank_countries" in hrefs
    assert "/en/learning/games/word-search" in hrefs


def test_dictionary_header_is_rendered_in_the_active_route_language(monkeypatch) -> None:
    monkeypatch.setattr(didactica, "build_navbar", lambda **_kwargs: "")

    with localized_route_context("es"):
        spanish = didactica.build_dictionary_layout()
    with localized_route_context("en"):
        english = didactica.build_dictionary_layout()

    spanish_titles = [
        getattr(item, "children", None)
        for item in _walk(spanish)
        if item.__class__.__name__ == "H1"
    ]
    english_titles = [
        getattr(item, "children", None)
        for item in _walk(english)
        if item.__class__.__name__ == "H1"
    ]
    assert "Diccionario LGBTIQ+" in spanish_titles
    assert "LGBTIQ+ Dictionary" in english_titles
    assert "Diccionario LGBTIQ+" not in english_titles


def test_games_catalog_redirects_to_didactica_and_unknown_games_are_not_routable(
    monkeypatch,
) -> None:
    monkeypatch.setattr(didactica, "build_navbar", lambda **_kwargs: "")

    catalog = didactica.build_games_layout()
    unknown = didactica.build_games_layout("removed_game")

    assert any(getattr(item, "href", None) == "/es/didactica" for item in _walk(catalog))
    assert any(getattr(item, "href", None) == "/es/didactica" for item in _walk(unknown))
    assert not any(getattr(item, "id", None) == "didactica-game-state" for item in _walk(unknown))


def test_ranking_game_hides_scores_until_check_and_localizes_country_names(monkeypatch) -> None:
    monkeypatch.setattr(didactica, "build_navbar", lambda **_kwargs: "")
    monkeypatch.setattr(didactica, "new_ranking_game", lambda: _state())

    layout = didactica.build_games_layout("rank_countries")
    initial_list = next(
        item for item in _walk(layout) if getattr(item, "id", None) == "didactica-ranking-list"
    )
    revealed = ranking_game_rows(_state(checked=True), "en")

    assert "%" not in _text(initial_list)
    assert "España" in _text(initial_list)
    assert "Spain" in _text(revealed)
    assert "Germany" in _text(revealed)
    assert "78%" in _text(revealed)
    assert "0%" in _text(revealed)


def test_didactica_rows_and_ranking_game_have_responsive_dark_theme_styles() -> None:
    stylesheet = Path("src/app/web/assets/didactica.css").read_text(encoding="utf-8")

    assert ".didactica-mode-row" in stylesheet
    assert "grid-template-columns: repeat(3" in stylesheet
    assert "@media (max-width: 900px)" in stylesheet
    assert ".didactica-game-access-grid" in stylesheet
    assert ".ranking-game-row" in stylesheet
    assert "var(--panel-bg)" in stylesheet
    assert "var(--color-text)" in stylesheet
